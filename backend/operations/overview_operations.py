"""Read-only work-order queries for the manager overview. Services authorize callers."""
from psycopg.rows import dict_row

from backend.operations.catalog_operations import IMAGE_VERSION
from backend.operations.dbops_core import like_pattern

from backend.operations.supervisor_operations import EXECUTION_COLUMNS


# Order lists that page through history, newest first: sort column per list.
ORDERINGS = {'created': 'orders.creation_time', 'completed': 'orders.completion_time'}


def get_orders(conn, *, order_id=None, active_since=None, supervisor_id=None, created_by=None,
               include_cancelled=False, open_only=False, completed_from=None, completed_to=None,
               search='', order_by=None, after=None, before=None, limit=None):
    """Orders with their product, contractor, piece and open-request counts.

    Filters: one ``order_id``; ``active_since`` keeps open orders and those completed from
    that moment; ``supervisor_id`` keeps orders with a route step in a unit that employee
    supervises now; ``created_by`` keeps one planner's orders; ``open_only`` keeps unfinished
    ones; ``completed_from``/``completed_to`` keep orders completed in that half-open range;
    ``search`` matches order number, product or contractor, ignoring case. Cancelled orders
    are left out unless ``include_cancelled``.

    Paging (keyset): with ``order_by`` ('created' or 'completed') rows come newest first,
    ``limit`` at a time, starting after the ``after`` cursor or just before ``before``.
    A cursor is the (timestamp, id) of a row already shown, so every page is an index range
    read rather than a scan of everything before it. Without ``order_by`` rows come by id.
    Orders without pieces or route steps are still returned, so none silently vanish.
    """
    clauses, params = [], []

    def where(clause, *values):
        clauses.append(clause)
        params.extend(values)

    if not include_cancelled:
        where('NOT orders.is_cancelled')
    if order_id is not None:
        where('orders.id = %s', order_id)
    if created_by is not None:
        where('orders.created_by = %s', created_by)
    if active_since is not None:
        where('(orders.completion_time IS NULL OR orders.completion_time >= %s)', active_since)
    if open_only:
        where('orders.completion_time IS NULL')
    if completed_from is not None:
        where('orders.completion_time >= %s', completed_from)
    if completed_to is not None:
        where('orders.completion_time < %s', completed_to)
    if order_by == 'completed':
        where('orders.completion_time IS NOT NULL')
    if supervisor_id is not None:
        where("""EXISTS (
            SELECT 1 FROM public.process_definition_process_step link
            JOIN public.process_step step ON step.id = link.process_step_id
            JOIN public.employee_unit_assignment assignment
              ON assignment.unit_id = step.unit_id AND assignment.is_supervisor
             AND assignment.valid_until IS NULL AND assignment.valid_from <= CURRENT_TIMESTAMP
            WHERE link.process_definition_id = items.process_def_id
              AND assignment.employee_id = %s)""", supervisor_id)
    if search.strip():
        pattern = like_pattern(search)
        where('(orders.order_number ILIKE %s OR product.name ILIKE %s OR contractor.name ILIKE %s)',
              pattern, pattern, pattern)
    order_sql, reverse = 'orders.id', False
    if order_by is not None:
        column = ORDERINGS[order_by]
        if after is not None:
            where(f'({column}, orders.id) < (%s, %s)', *after)
        elif before is not None:
            # The previous page is read upwards from the cursor, then turned back round.
            where(f'({column}, orders.id) > (%s, %s)', *before)
            reverse = True
        order_sql = f'{column} ASC, orders.id ASC' if reverse else f'{column} DESC, orders.id DESC'
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT orders.id AS work_order_id, orders.order_number, orders.creation_time,
                   orders.completion_time, orders.start_date, orders.due_date,
                   orders.is_cancelled, orders.notes, orders.created_by, orders.contractor_id,
                   contractor.name AS contractor_name,
                   items.product_type_id, {IMAGE_VERSION} AS product_image_version,
                   product.name AS product_name, product.reference_code,
                   route.name AS process_name, route.version,
                   coalesce(items.pieces, 0) AS pieces, coalesce(items.scrapped, 0) AS scrapped,
                   (SELECT count(*) FROM public.corrective_request request
                    WHERE request.work_order_id = orders.id AND request.resolved_at IS NULL)
                       AS open_requests
            FROM public.work_order orders
            JOIN public.contractor contractor ON contractor.id = orders.contractor_id
            -- One product and route per order: every piece is created from the same pair.
            LEFT JOIN LATERAL (
                SELECT min(item.product_type_id) AS product_type_id,
                       min(item.process_def_id) AS process_def_id, count(*) AS pieces,
                       count(*) FILTER (WHERE item.scrapped_at IS NOT NULL) AS scrapped
                FROM public.product_instance item WHERE item.work_order_id = orders.id) items ON TRUE
            LEFT JOIN public.product_type product ON product.id = items.product_type_id
            LEFT JOIN public.process_definition route ON route.id = items.process_def_id
            WHERE {' AND '.join(clauses) or 'TRUE'}
            ORDER BY {order_sql}
            {'LIMIT %s' if limit else ''}""", params + ([limit] if limit else []))
        rows = cur.fetchall()
    return rows[::-1] if reverse else rows


def get_order_steps(conn, order_ids):
    """One row per piece and route step, including steps with no execution row yet.

    A missing execution row appears with NULL timestamps, so it counts as unfinished
    rather than being dropped from the step's piece total.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT {EXECUTION_COLUMNS}
            FROM public.product_instance item
            JOIN public.work_order orders ON orders.id = item.work_order_id
            JOIN public.process_definition_process_step link
              ON link.process_definition_id = item.process_def_id
            LEFT JOIN public.process_step_execution execution
              ON execution.product_instance_id = item.id
             AND execution.process_step_id = link.process_step_id
            JOIN public.process_step step ON step.id = link.process_step_id
            JOIN public.production_unit unit ON unit.id = step.unit_id
            JOIN public.product_type product ON product.id = item.product_type_id
            JOIN public.process_definition route ON route.id = item.process_def_id
            WHERE NOT orders.is_cancelled AND orders.id = ANY(%s)
            ORDER BY orders.id, link.sequence_number, item.id""", (list(order_ids),))
        return cur.fetchall()


def get_long_pauses(conn, minutes):
    """Pauses still open after this many minutes."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT pause.work_order_id, orders.order_number, step.name AS step_name, pause.reason,
                   EXTRACT(EPOCH FROM clock_timestamp() - pause.paused_at) / 60 AS minutes
            FROM public.step_pause pause
            JOIN public.work_order orders ON orders.id = pause.work_order_id
            JOIN public.process_step step ON step.id = pause.process_step_id
            WHERE pause.resumed_at IS NULL AND NOT orders.is_cancelled
              AND pause.paused_at < clock_timestamp() - make_interval(mins => %s)
            ORDER BY pause.paused_at""", (minutes,))
        return cur.fetchall()


def get_open_requests(conn):
    """Unanswered scrap requests on orders that are not cancelled."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT request.work_order_id, orders.order_number, step.name AS step_name,
                   request.quantity, request.kind
            FROM public.corrective_request request
            JOIN public.work_order orders ON orders.id = request.work_order_id
            JOIN public.process_step step ON step.id = request.process_step_id
            WHERE request.resolved_at IS NULL AND NOT orders.is_cancelled
            ORDER BY request.requested_at""")
        return cur.fetchall()
