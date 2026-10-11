"""Product catalog database operations. Callers authorize and own transactions.

All mutations acquire the catalog advisory lock first. Use READ COMMITTED and
keep transactions short; direct SQL writers must follow this protocol too.
"""
from backend.annotations import PositiveInt, PositiveBigInt, NonBlankText, UNSET, UnsetType, editable
from backend.validation import validate_call

from datetime import datetime
from typing import Annotated

from psycopg import Connection
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row, tuple_row

from backend.operations.dbops_core import (
    add_query_compose, edit_query_compose, get_query_compose, list_query_compose,
)


# A picture's version: when it was stored, in milliseconds. Pages put it in the picture's URL
# so browsers can keep a picture until it changes. NULL without a picture.
IMAGE_VERSION = "(extract(epoch FROM product.image_updated_at) * 1000)::bigint"


def lock_catalog(conn: Connection) -> None:
    """Serialize catalog writes until commit/rollback, including shared-step edits."""
    if conn.autocommit and conn.info.transaction_status == TransactionStatus.IDLE:
        raise ValueError("Catalog writes require a transaction")
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SHOW transaction_isolation")
        if cur.fetchone()[0] != "read committed":
            raise ValueError("Catalog writes require READ COMMITTED isolation")
        cur.execute("SELECT pg_advisory_xact_lock(74129, 1)")


@validate_call
def get_production_unit(conn: Connection, key: PositiveInt, fields: tuple[str, ...]) -> dict | None:
    """Read backend-selected fields by ID."""
    return get_query_compose(conn, key, "production_unit", fields=fields)


@validate_call
def add_production_unit(conn: Connection, name: NonBlankText, location: str | None = None) -> int:
    """Insert an active production unit; its name is unique within its location."""
    lock_catalog(conn)
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("INSERT INTO public.production_unit (name, location) VALUES (%s, %s) RETURNING id",
                    (name, location))
        return cur.fetchone()[0]


@validate_call
def set_production_unit_active(conn: Connection, unit_id: PositiveInt, active: bool) -> bool:
    """Activate or deactivate a unit; False when it does not exist. Its steps are untouched."""
    lock_catalog(conn)
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("UPDATE public.production_unit SET active = %s WHERE id = %s RETURNING id",
                    (active, unit_id))
        return cur.fetchone() is not None


def get_production_units(conn: Connection) -> list[dict]:
    return list_query_compose(conn, "production_unit", ('id', 'name', 'location', 'active'),
                              order_by=('name', 'id'))


@validate_call
def add_product_type(
    conn: Connection,
    name: Annotated[NonBlankText, editable],
    *,
    reference_code: Annotated[str | None, editable] = None,
    description: Annotated[str | None, editable] = None,
    image: Annotated[bytes | None, editable] = None,
    image_media_type: Annotated[str | None, editable] = None,
    is_orderable: Annotated[bool, editable] = True,
) -> int:
    """Insert a product_type; return its ID."""
    lock_catalog(conn)
    return add_query_compose(conn, add_product_type, locals(), "product_type")

@validate_call
def get_product_type(conn: Connection, key: PositiveInt, fields: tuple[str, ...]) -> dict | None:
    """Read backend-selected fields by ID."""
    return get_query_compose(conn, key, "product_type", fields=fields)

def get_product_types(conn: Connection) -> list[dict]:
    """List products. The stored picture is excluded; fetch it with get_product_image."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, name, reference_code, description, is_orderable, "
                    f"{IMAGE_VERSION} AS image_version FROM product_type product ORDER BY name, id")
        return cur.fetchall()


@validate_call
def product_image_version(conn: Connection, key: PositiveInt) -> int | None:
    """The stored picture's version, or None without one; the bytes are not transferred."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(f'SELECT {IMAGE_VERSION} FROM product_type product WHERE id=%s', (key,))
        row = cur.fetchone()
    return row[0] if row else None


@validate_call
def get_product_image(conn: Connection, key: PositiveInt) -> tuple[bytes, str, int] | None:
    """Return the stored picture, its media type and version, or None when absent."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(f'SELECT image, image_media_type, {IMAGE_VERSION} FROM product_type product '
                    'WHERE id=%s', (key,))
        row = cur.fetchone()
    return None if row is None or row[0] is None else (bytes(row[0]), row[1], row[2])

@validate_call
def edit_product_type(
    conn: Connection, key: PositiveInt, *,
    name: Annotated[NonBlankText | UnsetType, editable] = UNSET,
    reference_code: Annotated[str | None | UnsetType, editable] = UNSET,
    description: Annotated[str | None | UnsetType, editable] = UNSET,
    image: Annotated[bytes | None | UnsetType, editable] = UNSET,
    image_media_type: Annotated[str | None | UnsetType, editable] = UNSET,
    image_updated_at: Annotated[datetime | None | UnsetType, editable] = UNSET,
    is_orderable: Annotated[bool | UnsetType, editable] = UNSET,
) -> bool:
    """Update supplied fields only; no authorization is performed here."""
    lock_catalog(conn)
    return edit_query_compose(conn, key, edit_product_type, locals(), "product_type")


@validate_call
def add_process_step(
    conn: Connection,
    name: Annotated[NonBlankText, editable],
    unit_id: Annotated[PositiveInt, editable],
    *,
    instructions: Annotated[str | None, editable] = None,
    standard_time_seconds: Annotated[PositiveBigInt | None, editable] = None,
) -> int:
    """Insert a process_step; return its ID."""
    lock_catalog(conn)
    return add_query_compose(conn, add_process_step, locals(), "process_step")

@validate_call
def get_process_step(conn: Connection, key: PositiveInt, fields: tuple[str, ...]) -> dict | None:
    """Read backend-selected fields by ID."""
    return get_query_compose(conn, key, "process_step", fields=fields)

def get_process_steps(conn: Connection) -> list[dict]:
    return list_query_compose(conn, "process_step",
                              ('id', 'name', 'unit_id', 'instructions', 'standard_time_seconds'),
                              order_by=('name', 'id'))


@validate_call
def _insert_process_definition(
    conn: Connection,
    product_type_id: Annotated[PositiveInt, editable],
    name: Annotated[NonBlankText, editable],
    version: Annotated[PositiveInt, editable],
    reference_code: Annotated[str | None, editable],
    is_active: Annotated[bool, editable],
) -> int:
    return add_query_compose(conn, _insert_process_definition, locals(), "process_definition")


@validate_call
def add_process_definition(
    conn: Connection, product_type_id: PositiveInt, name: NonBlankText,
    *, reference_code: str | None = None, is_active: bool = True,
) -> int:
    """Allocate the next product version while locking the product row."""
    lock_catalog(conn)
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT id FROM public.product_type WHERE id = %s FOR UPDATE", (product_type_id,))
        if cur.fetchone() is None:
            raise ValueError("Product does not exist")
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM public.process_definition WHERE product_type_id = %s",
            (product_type_id,),
        )
        version = cur.fetchone()[0]
    return _insert_process_definition(conn, product_type_id, name, version, reference_code, is_active)


@validate_call
def get_process_definition(conn: Connection, key: PositiveInt, fields: tuple[str, ...]) -> dict | None:
    return get_query_compose(conn, key, "process_definition", fields=fields)


@validate_call
def get_product_processes(conn: Connection, product_type_id: PositiveInt) -> list[dict]:
    return list_query_compose(
        conn, "process_definition",
        ("id", "product_type_id", "name", "reference_code", "version", "is_active"),
        filters={"product_type_id": product_type_id}, order_by=("version", "id"),
    )


@validate_call
def lock_process(conn: Connection, process_id: PositiveInt) -> None:
    lock_catalog(conn)
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT id FROM public.process_definition WHERE id = %s FOR UPDATE", (process_id,))
        if cur.fetchone() is None:
            raise ValueError("Process does not exist")


@validate_call
def get_steps_for_process(conn: Connection, process_id: PositiveInt) -> list[dict]:
    """Ordered associations with current details and database-derived usage counts."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT link.id AS association_id, step.id AS step_id,
                   link.sequence_number, step.name, step.unit_id, step.instructions,
                   step.standard_time_seconds,
                   (SELECT count(*) FROM public.process_definition_process_step AS uses
                    WHERE uses.process_step_id = step.id) AS usage_count
            FROM public.process_definition_process_step AS link
            JOIN public.process_step AS step ON step.id = link.process_step_id
            WHERE link.process_definition_id = %s
            ORDER BY link.sequence_number, link.id
            """,
            (process_id,),
        )
        return cur.fetchall()


@validate_call
def add_step_to_process(conn: Connection, process_id: PositiveInt, step_id: PositiveInt) -> int:
    """Append an existing definition; copying is handled by the calling service."""
    lock_process(conn, process_id)
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO public.process_definition_process_step
                (process_definition_id, process_step_id, sequence_number)
            SELECT %s, %s, COALESCE(MAX(sequence_number), 0) + 1
            FROM public.process_definition_process_step WHERE process_definition_id = %s
            RETURNING id
            """,
            (process_id, step_id, process_id),
        )
        return cur.fetchone()[0]
