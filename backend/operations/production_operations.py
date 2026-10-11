"""Contractor, order and item queries. Callers authorize and own transactions.

These helpers do not start executions. Services must validate workflow transitions and
that a selected process belongs to the product type. Database constraints enforce
references and unique identifiers.
Read fields and expected values must be chosen by trusted backend code.
"""
from backend.annotations import Email, PhoneNumber, Name, PositiveInt, NonBlankText, UNSET, UnsetType, editable
from backend.validation import validate_call

from datetime import date
from typing import Annotated

from psycopg import Connection
from psycopg.rows import dict_row

from backend.operations.dbops_core import add_query_compose, edit_query_compose, get_query_compose, like_pattern

CONTRACTOR_FIELDS = ("id", "name", "email", "phone_number")
WORK_ORDER_FIELDS = (
    "id", "order_number", "contractor_id", "created_by", "creation_time",
    "completion_time", "is_cancelled", "notes", "start_date", "due_date",
)


@validate_call
def add_contractor(
    conn: Connection, name: Annotated[Name, editable], *,
    email: Annotated[Email | None, editable] = None,
    phone_number: Annotated[PhoneNumber | None, editable] = None,
) -> int:
    return add_query_compose(conn, add_contractor, locals(), "contractor")


@validate_call
def get_contractor(
    conn: Connection, contractor_id: PositiveInt,
    fields: tuple[str, ...] = CONTRACTOR_FIELDS,
) -> dict | None:
    return get_query_compose(conn, contractor_id, "contractor", fields)


def get_contractors(conn: Connection, *, search: str = "", after=None, before=None,
                    limit=None) -> list[dict]:
    """Contractors by name, all of them or one keyset page (see backend.service.paging)."""
    clauses, params = [], []
    if search.strip():
        clauses.append("(name ILIKE %s OR email ILIKE %s OR phone_number ILIKE %s)")
        params += [like_pattern(search)] * 3
    order = "name, id"
    if after is not None:
        clauses.append("(name, id) > (%s, %s)")
        params += list(after)
    elif before is not None:
        clauses.append("(name, id) < (%s, %s)")
        params += list(before)
        order = "name DESC, id DESC"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {', '.join(CONTRACTOR_FIELDS)} FROM public.contractor "
                    f"WHERE {' AND '.join(clauses) or 'TRUE'} ORDER BY {order} "
                    f"{'LIMIT %s' if limit else ''}", params + ([limit] if limit else []))
        rows = cur.fetchall()
    return rows[::-1] if before is not None else rows


@validate_call
def edit_contractor(
    conn: Connection, contractor_id: PositiveInt, *,
    name: Annotated[Name | UnsetType, editable] = UNSET,
    email: Annotated[Email | None | UnsetType, editable] = UNSET,
    phone_number: Annotated[PhoneNumber | None | UnsetType, editable] = UNSET,
) -> bool:
    return edit_query_compose(conn, contractor_id, edit_contractor, locals(), "contractor")


@validate_call
def add_work_order(
    conn: Connection,
    order_number: Annotated[NonBlankText, editable],
    contractor_id: Annotated[PositiveInt, editable],
    created_by: Annotated[PositiveInt, editable], *,
    notes: Annotated[str | None, editable] = None,
    start_date: Annotated[date | None, editable] = None,
    due_date: Annotated[date | None, editable] = None,
) -> int:
    """Create an unfinished, uncancelled order using database time/defaults."""
    return add_query_compose(conn, add_work_order, locals(), "work_order")


@validate_call
def get_work_order(conn: Connection, order_id: PositiveInt,
                   fields: tuple[str, ...] = WORK_ORDER_FIELDS) -> dict | None:
    return get_query_compose(conn, order_id, "work_order", fields)


def lock_work_order(conn: Connection, order_id: int) -> dict | None:
    """Lock one order for a change and return it, or None when it does not exist."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {', '.join(WORK_ORDER_FIELDS)} FROM public.work_order "
                    "WHERE id = %s FOR UPDATE", (order_id,))
        return cur.fetchone()


@validate_call
def edit_work_order(
    conn: Connection, order_id: PositiveInt, *,
    order_number: Annotated[NonBlankText | UnsetType, editable] = UNSET,
    contractor_id: Annotated[PositiveInt | UnsetType, editable] = UNSET,
    notes: Annotated[str | None | UnsetType, editable] = UNSET,
    is_cancelled: Annotated[bool | UnsetType, editable] = UNSET,
    start_date: Annotated[date | None | UnsetType, editable] = UNSET,
    due_date: Annotated[date | None | UnsetType, editable] = UNSET,
) -> bool:
    """Edit metadata or cancel; the service must authorize cancellation.

    Does not update item executions. Creation time and creator remain unchanged, and
    completion is recorded only by `supervisor_operations.complete_order_if_finished`.
    """
    return edit_query_compose(conn, order_id, edit_work_order, locals(), "work_order")


@validate_call
def add_product_instances(conn: Connection, work_order_id: PositiveInt, product_type_id: PositiveInt,
                          process_def_id: PositiveInt, quantity: PositiveInt) -> None:
    """Create an order's pieces in one statement rather than one round trip per piece.

    The caller verifies process/product compatibility. The existing independent
    foreign keys alone cannot enforce that relationship.
    """
    conn.execute("""
        INSERT INTO public.product_instance (work_order_id, product_type_id, process_def_id)
        SELECT %s, %s, %s FROM generate_series(1, %s)
    """, (work_order_id, product_type_id, process_def_id, quantity))


def get_open_corrective_requests(conn: Connection, order_ids) -> list[dict]:
    """Unresolved scrap requests for these orders, oldest first."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT request.id, request.work_order_id, request.quantity, request.kind,
                   request.note, request.requested_at, step.name AS step_name,
                   who.name || ' ' || who.surname AS requested_by_name
            FROM public.corrective_request request
            JOIN public.process_step step ON step.id = request.process_step_id
            JOIN public.employee who ON who.id = request.requested_by
            WHERE request.resolved_at IS NULL AND request.work_order_id = ANY(%s)
            ORDER BY request.requested_at, request.id""", (list(order_ids),))
        return cur.fetchall()


def lock_corrective_request(conn: Connection, request_id: int) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM public.corrective_request WHERE id = %s FOR UPDATE',
                    (request_id,))
        return cur.fetchone()


def resolve_corrective_request(conn: Connection, request_id: int, resolved_by: int,
                               resolution: str, replaced_quantity: int | None, note: str | None):
    conn.execute("""UPDATE public.corrective_request SET resolved_at = clock_timestamp(),
        resolved_by = %s, resolution = %s, replaced_quantity = %s, resolution_note = %s
        WHERE id = %s""", (resolved_by, resolution, replaced_quantity, note, request_id))


def get_order_route(conn: Connection, order_id: int) -> tuple | None:
    """The product and process version an order's pieces follow."""
    return conn.execute('SELECT product_type_id, process_def_id FROM public.product_instance '
                        'WHERE work_order_id = %s ORDER BY id LIMIT 1', (order_id,)).fetchone()


def get_running_counts_by_unit(conn: Connection, unit_ids) -> dict:
    """How many pieces are running right now on each unit, across every order.

    Used for delay prediction: a unit running more pieces than the order being
    predicted has of its own is busy with someone else's queue too.
    """
    if not unit_ids:
        return {}
    rows = conn.execute("""
        SELECT step.unit_id, count(*) FROM public.process_step_execution execution
        JOIN public.process_step step ON step.id = execution.process_step_id
        WHERE step.unit_id = ANY(%s) AND execution.start_time IS NOT NULL
          AND execution.completion_time IS NULL AND execution.skipped_at IS NULL
        GROUP BY step.unit_id""", (list(unit_ids),)).fetchall()
    return dict(rows)
