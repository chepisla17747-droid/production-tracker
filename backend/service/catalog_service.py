"""Authorized catalog actions for the Operations page's product and process editor.

Form drafts stay in the UI until Apply. Every action below owns one transaction;
no orders, execution records, email, or live connection configuration are used.
"""
from backend.annotations import UNSET, UnsetType, editable, PositiveInt, PositiveBigInt, NonBlankText
from datetime import datetime, timezone
from typing import Sequence

from backend.operations import catalog_operations as db
from backend.validation import validate_call, validate_fields, validate_operation_fields
from backend.service.permissions_service import actor_permissions, require_permission
from backend.service.product_image import compress_upload


# Product details a form may set. The picture is excluded: it goes only through
# set_product_image_service, which compresses and checks it first.
PRODUCT_DETAIL_FIELDS = ("name", "reference_code", "description", "is_orderable")


def _product_details(values):
    unsupported = set(values) - set(PRODUCT_DETAIL_FIELDS)
    if unsupported:
        raise ValueError(f"Unsupported product field: {', '.join(sorted(unsupported))}")
    return values


# Draft-only fields describe how to attach/edit a step; values stay dictionaries.
_STEP_INPUT_SCHEMA = {
    "association_id": PositiveInt | None,
    "source_step_id": PositiveInt | None,
    "make_independent_copy": bool,
    "name": NonBlankText | UnsetType,
    "unit_id": PositiveInt | UnsetType,
    "instructions": str | None | UnsetType,
    "standard_time_seconds": PositiveBigInt | None | UnsetType,
}
# Process details a form may set; a new version always needs its name.
_PROCESS_SCHEMA = {"name": NonBlankText, "reference_code": str | None, "is_active": bool}


# Check permission and update only the supplied product details.
@validate_call
def edit_product_type_service(actor, pool, product_id: PositiveInt, **changes) -> bool:
    _product_details(changes)
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "product.manage")
        validate_operation_fields(db.edit_product_type, changes, editable)
        return db.edit_product_type(conn, product_id, **changes)


# All catalog saves now build a new route; existing associations remain untouched.
@validate_call
def _save_ordered_process_steps(conn, process_id: PositiveInt, steps: Sequence[dict]):
    """Attach ordered draft steps, copying changed definitions to preserve history."""
    db.lock_process(conn, process_id)
    seen = set()
    for entry in steps:
        validate_fields(entry, _STEP_INPUT_SCHEMA)
        if entry.get("association_id") is not None:
            raise ValueError("An existing association cannot belong to a new process")
        source = None
        if entry.get("source_step_id") is not None:
            source = db.get_process_step(conn, entry['source_step_id'],
                ("id", "name", "unit_id", "instructions", "standard_time_seconds"))
            if source is None:
                raise ValueError("Source step does not exist")
        details = {
            field: entry[field] if entry.get(field, UNSET) is not UNSET
            else (source[field] if source is not None else None)
            for field in ("name", "unit_id", "instructions", "standard_time_seconds")
        }
        validate_operation_fields(db.add_process_step, details, editable)
        if db.get_production_unit(conn, details['unit_id'], ('id',)) is None:
            raise ValueError("Production unit does not exist")
        copy = (source is None or entry.get('make_independent_copy', True)
                or any(value != source[key] for key, value in details.items()))
        step_id = db.add_process_step(conn, **details) if copy else source['id']
        if step_id in seen:
            raise ValueError("The same shared step cannot appear twice in one process; make a copy")
        seen.add(step_id)
        db.add_step_to_process(conn, process_id, step_id)
    return db.get_steps_for_process(conn, process_id)


# Create a product, its first process, and its steps together.
def create_product_with_process_service(
    actor, pool, *, product: dict, process: dict,
    steps: Sequence[dict] = (),
) -> dict:
    """Create a product and version-1 process, returning IDs and saved step rows."""
    _product_details(product)
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "product.manage")
        validate_operation_fields(db.add_product_type, product, editable)
        validate_fields(process, _PROCESS_SCHEMA, required=("name",))
        db.lock_catalog(conn)
        product_id = db.add_product_type(conn, **product)
        process_id = db.add_process_definition(conn, product_id, **process)
        saved = _save_ordered_process_steps(conn, process_id, steps)
        return {"product_id": product_id, "process_id": process_id, "steps": saved}


# Create the next process version and its steps for an existing product.
@validate_call
def create_product_process_service(
    actor, pool, product_id: PositiveInt, *, process: dict,
    steps: Sequence[dict] = (),
) -> dict:
    """Create the next process version on an existing product."""
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "product.manage")
        validate_fields(process, _PROCESS_SCHEMA, required=("name",))
        process_id = db.add_process_definition(conn, product_id, **process)
        saved = _save_ordered_process_steps(conn, process_id, steps)
        return {"product_id": product_id, "process_id": process_id, "steps": saved}


# Save edits as a new version; existing orders retain their original route.
@validate_call
def save_process_service(
    actor, pool, process_id: PositiveInt, *, steps: Sequence[dict],
    name=UNSET, reference_code=UNSET, is_active=UNSET,
) -> dict:
    """Create the next version from a full ordered draft, leaving the source intact.

    Association IDs refer to the source version. New associations and independent
    step copies belong to the new version. An omitted reference_code becomes NULL
    because reference codes are globally unique; supply a new code if required.
    """
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "product.manage")
        db.lock_process(conn, process_id)
        original = db.get_process_definition(conn, process_id, (
            "id", "product_type_id", "name", "reference_code", "version", "is_active",
        ))
        current = {row['association_id']: row for row in db.get_steps_for_process(conn, process_id)}
        drafts, seen = [], set()
        for entry in steps:
            validate_fields(entry, _STEP_INPUT_SCHEMA)
            draft = dict(entry)
            association = draft.pop('association_id', None)
            if association is not None:
                if association not in current or association in seen or draft.get('source_step_id') is not None:
                    raise ValueError('Association is missing, duplicated, or belongs to another process')
                seen.add(association)
                draft['source_step_id'] = current[association]['step_id']
            # Every version owns its step details, including unchanged steps.
            draft['make_independent_copy'] = True
            drafts.append(draft)
        details = dict(name=original['name'] if name is UNSET else name,
                       reference_code=None if reference_code is UNSET else reference_code,
                       is_active=original['is_active'] if is_active is UNSET else is_active)
        validate_fields(details, _PROCESS_SCHEMA, required=('name',))
        new_id = db.add_process_definition(conn, original['product_type_id'], **details)
        saved = _save_ordered_process_steps(conn, new_id, drafts)
        process = db.get_process_definition(conn, new_id, (
            "id", "product_type_id", "name", "reference_code", "version", "is_active",
        ))
        return {"process": process, "steps": saved}


# Reads for the catalog editor; every write above already owns its transaction.
def get_catalog_service(actor, pool):
    """Products with a has_image flag, without their stored picture bytes."""
    with pool.connection() as conn:
        require_permission(conn, actor, "product.manage")
        return db.get_product_types(conn)


@validate_call
def get_product_processes_service(actor, pool, product_id: PositiveInt):
    """Every process version of one product, newest version first."""
    with pool.connection() as conn:
        require_permission(conn, actor, "product.manage")
        if db.get_product_type(conn, product_id, ('id',)) is None:
            raise ValueError('Product does not exist. Refresh the catalog.')
        return db.get_product_processes(conn, product_id)


@validate_call
def get_process_steps_service(actor, pool, process_id: PositiveInt):
    """The ordered steps of one process, for loading an editor draft."""
    with pool.connection() as conn:
        require_permission(conn, actor, "product.manage")
        if db.get_process_definition(conn, process_id, ('id',)) is None:
            raise ValueError('Process does not exist. Refresh the catalog.')
        return db.get_steps_for_process(conn, process_id)


def get_production_units_service(actor, pool):
    """Every unit with its active flag, for the step editor and the unit list.

    Either catalog permission may read them; the pages decide which units to offer.
    """
    with pool.connection() as conn:
        if actor_permissions(conn, actor).isdisjoint({"product.manage", "production_unit.manage"}):
            raise PermissionError("Catalog permission required")
        return db.get_production_units(conn)


@validate_call
def create_production_unit_service(actor, pool, *, name: NonBlankText, location: str | None = None) -> int:
    """Add an active unit. Only production_unit.manage may, never product management alone."""
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "production_unit.manage")
        return db.add_production_unit(conn, name.strip(), (location or "").strip() or None)


@validate_call
def set_production_unit_active_service(actor, pool, unit_id: PositiveInt, active: bool) -> None:
    """Activate or deactivate a unit. Inactive units are hidden, not deleted: existing steps,
    orders, assignments and history keep pointing at them."""
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "production_unit.manage")
        if not db.set_production_unit_active(conn, unit_id, active):
            raise ValueError("This production unit no longer exists. Refresh the list.")


@validate_call
def set_product_image_service(actor, pool, product_id: PositiveInt, upload: str | None) -> bool:
    """Compress and store an uploaded picture, or clear it with None."""
    image, media_type = (None, None) if upload is None else compress_upload(upload)
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "product.manage")
        if db.get_product_type(conn, product_id, ('id',)) is None:
            raise ValueError('Product does not exist. Refresh the catalog.')
        return db.edit_product_type(conn, product_id, image=image, image_media_type=media_type,
                                    image_updated_at=None if image is None else datetime.now(timezone.utc))


@validate_call
def get_product_image_service(pool, product_id: PositiveInt):
    """Serve a stored picture to any authenticated employee.

    The caller's session is checked by the HTTP route; product pictures carry no
    narrower action permission, so none is required here.
    """
    with pool.connection() as conn:
        return db.get_product_image(conn, product_id)


def get_step_library_service(actor, pool):
    """Every stored step definition, offered when reusing an existing step."""
    with pool.connection() as conn:
        require_permission(conn, actor, "product.manage")
        return db.get_process_steps(conn)
