"""Authorized reads and contractor edits for the Planner website."""
from backend.annotations import PositiveInt, Email, PhoneNumber, Name
from backend.validation import validate_call
from backend.operations import catalog_operations as catalog
from backend.operations import production_operations as production
from backend.service import paging
from backend.service.permissions_service import require_permission


def get_planner_catalog(actor, pool):
    with pool.connection() as conn:
        require_permission(conn, actor, 'work_order.create')
        return catalog.get_product_types(conn)


@validate_call
def get_planner_product(actor, pool, product_id: PositiveInt):
    with pool.connection() as conn:
        require_permission(conn, actor, 'work_order.create')
        product = catalog.get_product_type(conn, product_id,
            ('id', 'name', 'reference_code', 'description', 'is_orderable'))
        if product is None:
            raise ValueError('Product no longer exists. Refresh the product list.')
        # The picture itself is fetched by the browser from /products/<id>/image?v=<version>.
        product['image_version'] = catalog.product_image_version(conn, product_id)
        return product, catalog.get_product_processes(conn, product_id)


@validate_call
def get_planner_process(actor, pool, product_id: PositiveInt, process_id: PositiveInt):
    with pool.connection() as conn:
        require_permission(conn, actor, 'work_order.create')
        process = catalog.get_process_definition(conn, process_id,
            ('id', 'product_type_id', 'name', 'version', 'is_active'))
        if process is None or process['product_type_id'] != product_id:
            raise ValueError('Select a process belonging to this product.')
        return process, catalog.get_steps_for_process(conn, process_id)


def get_contractors_service(actor, pool):
    """Every contractor, for the new-order selector."""
    with pool.connection() as conn:
        require_permission(conn, actor, 'contractor.view')
        return production.get_contractors(conn)


CONTRACTOR_PAGE_SIZE = 50


def list_contractors_service(actor, pool, *, search='', after=None, before=None):
    """One page of the contractor directory by name, from a ``next``/``previous`` cursor."""
    kinds = (paging.TEXT, paging.KEY)
    with pool.connection() as conn:
        require_permission(conn, actor, 'contractor.view')
        rows = production.get_contractors(conn, search=search, after=paging.decode(after, *kinds),
                                          before=paging.decode(before, *kinds),
                                          limit=CONTRACTOR_PAGE_SIZE + 1)
    result = paging.page(rows, CONTRACTOR_PAGE_SIZE, lambda c: (c['name'], c['id']),
                         after=after, before=before)
    return {'contractors': result.pop('rows'), **result}


def _contractor_fields(name, email, phone_number):
    # Validation is annotation-driven; trimming a display name is explicit normalization.
    return dict(name=name.strip(), email=email, phone_number=phone_number)


@validate_call
def create_contractor_service(
    actor, pool, *, name: Name, email: Email | None = None,
    phone_number: PhoneNumber | None = None,
):
    fields = _contractor_fields(name, email, phone_number)
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, 'contractor.manage')
        return production.add_contractor(conn, **fields)


@validate_call
def edit_contractor_service(
    actor, pool, contractor_id: PositiveInt, *, name: Name,
    email: Email | None = None, phone_number: PhoneNumber | None = None,
):
    fields = _contractor_fields(name, email, phone_number)
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, 'contractor.manage')
        if not production.edit_contractor(conn, contractor_id, **fields):
            raise ValueError('Contractor no longer exists. Refresh the list.')
        return fields
