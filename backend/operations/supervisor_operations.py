"""Execution queries. Services authorize, lock the order and own transactions."""
from psycopg.rows import dict_row

from backend.operations.catalog_operations import IMAGE_VERSION

from backend.annotations import PositiveInt
from backend.validation import validate_call

# The supervisor queue, its notifications and their counts leave out orders completed longer
# ago than this; the Order history page shows those. Open orders are always included.
RECENT = "(orders.completion_time IS NULL OR orders.completion_time >= CURRENT_TIMESTAMP - interval '1 month')"

# Missing upstream execution records are unfinished, never implicitly ready.
_READY = """NOT EXISTS (
    SELECT 1 FROM public.process_definition_process_step previous
    WHERE previous.process_definition_id = item.process_def_id
      AND previous.sequence_number < link.sequence_number
      AND NOT EXISTS (
          SELECT 1 FROM public.process_step_execution done
          WHERE done.product_instance_id = item.id
            AND done.process_step_id = previous.process_step_id
            AND COALESCE(done.completion_time,done.skipped_at) IS NOT NULL))"""


# Where a scrapped piece left its route: it counts at that step and not at any later one.
_SCRAPPED_SEQUENCE = """(
    SELECT scrap.sequence_number FROM public.process_definition_process_step scrap
    WHERE scrap.process_definition_id = item.process_def_id
      AND scrap.process_step_id = item.scrapped_step_id)"""


# Shared by the Supervisor queue and the manager overview, so both derive step status,
# readiness and elapsed time from the same columns. The step comes from the route link,
# which also works when a caller LEFT JOINs a missing execution row.
EXECUTION_COLUMNS = f"""
    execution.id, item.id AS item_id, item.work_order_id,
    item.process_def_id, link.process_step_id, link.sequence_number,
    execution.start_time, execution.completion_time, execution.skipped_at,
    (SELECT COALESCE(prev.completion_time,prev.skipped_at)
     FROM public.process_definition_process_step earlier
     LEFT JOIN public.process_step_execution prev ON prev.product_instance_id=item.id
       AND prev.process_step_id=earlier.process_step_id
     WHERE earlier.process_definition_id=item.process_def_id
       AND earlier.sequence_number<link.sequence_number
     ORDER BY earlier.sequence_number DESC LIMIT 1) AS predecessor_finished_at,
    step.name, step.instructions, step.standard_time_seconds,
    unit.id AS unit_id, unit.name AS unit_name,
    product.id AS product_type_id, {IMAGE_VERSION} AS product_image_version,
    product.name AS product_name, product.reference_code, product.description,
    route.name AS process_name, route.version,
    orders.order_number, orders.due_date, orders.creation_time,
    {_READY} AS upstream_complete,
    item.scrapped_at, {_SCRAPPED_SEQUENCE} AS scrapped_sequence"""


@validate_call
def get_assigned_executions(conn, supervisor_id: PositiveInt, order_id: PositiveInt | None = None):
    """Executions in the supervisor's current units: the queue (recent orders only), or
    every execution of one order, however old, for access checks and actions."""
    scope = 'orders.id = %s' if order_id is not None else RECENT
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT {EXECUTION_COLUMNS}
            FROM public.process_step_execution execution
            JOIN public.product_instance item ON item.id = execution.product_instance_id
            JOIN public.work_order orders ON orders.id = item.work_order_id
            JOIN public.process_definition_process_step link
              ON link.process_definition_id = item.process_def_id
             AND link.process_step_id = execution.process_step_id
            JOIN public.process_step step ON step.id = execution.process_step_id
            JOIN public.production_unit unit ON unit.id = step.unit_id
            JOIN public.employee_unit_assignment assignment ON assignment.unit_id=unit.id
              AND assignment.is_supervisor AND assignment.valid_until IS NULL
              AND assignment.valid_from<=CURRENT_TIMESTAMP
            JOIN public.product_type product ON product.id = item.product_type_id
            JOIN public.process_definition route ON route.id = item.process_def_id
            WHERE assignment.employee_id = %s AND NOT orders.is_cancelled AND {scope}
            ORDER BY item.id, link.sequence_number
        """, (supervisor_id,) + ((order_id,) if order_id is not None else ()))
        return cur.fetchall()


def lock_supervised_units(conn, unit_ids):
    """Serialize moves/actions without granting the app catalog UPDATE privileges."""
    rows = conn.execute('SELECT id FROM production_unit WHERE id=ANY(%s) ORDER BY id', (unit_ids,)).fetchall()
    for (unit_id,) in rows:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('supervisor-unit:' || %s::text,0))", (unit_id,))
    return rows


def create_order_executions(conn, order_id):
    """Materialize execution rows without starting any work."""
    conn.execute("""
        INSERT INTO public.process_step_execution (product_instance_id, process_step_id)
        SELECT item.id, link.process_step_id FROM public.product_instance item
        JOIN public.process_definition_process_step link ON link.process_definition_id = item.process_def_id
        WHERE item.work_order_id = %s
        ON CONFLICT (product_instance_id, process_step_id) DO NOTHING
    """, (order_id,))


def lock_order(conn, order_id):
    return conn.execute('SELECT id FROM public.work_order WHERE id=%s AND NOT is_cancelled FOR UPDATE',
                        (order_id,)).fetchone() is not None


def get_action(conn, request_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM public.supervisor_action WHERE request_id=%s', (request_id,))
        return cur.fetchone()


def record_action(conn, request_id, supervisor_id, order_id, process_id, step_id, action, quantity):
    conn.execute("""INSERT INTO public.supervisor_action
        (request_id,supervisor_id,work_order_id,process_def_id,process_step_id,action,quantity)
        VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (request_id,supervisor_id,order_id,process_id,step_id,action,quantity))


def update_executions(conn, rows, action, step_id):
    """Apply one action to these execution rows, and remember which rows it changed."""
    ids = [r['id'] for r in rows]
    if action == 'scrap':
        conn.execute("""UPDATE public.product_instance
            SET scrapped_at=clock_timestamp(), scrapped_step_id=%s WHERE id=ANY(%s)""",
            (step_id, [r['item_id'] for r in rows]))
        return ids
    # Only these backend-selected timestamp columns can be updated.
    column = {'start': 'start_time', 'complete': 'completion_time', 'skip':'skipped_at'}[action]
    conn.execute(f"""UPDATE public.process_step_execution
        SET {column}=clock_timestamp(), last_update_time=clock_timestamp() WHERE id=ANY(%s)""", (ids,))
    return ids


def record_action_items(conn, request_id, execution_ids):
    with conn.cursor() as cur:
        cur.executemany('INSERT INTO public.supervisor_action_item (request_id, execution_id) '
                        'VALUES (%s, %s)', [(request_id, e) for e in execution_ids])


def complete_order_if_finished(conn, order_id):
    conn.execute("""UPDATE public.work_order orders SET completion_time=clock_timestamp()
        WHERE orders.id=%s AND orders.completion_time IS NULL AND NOT orders.is_cancelled
          -- Scrapped pieces are out of the order; one good piece must remain and be finished.
          AND EXISTS (SELECT 1 FROM public.product_instance
                      WHERE work_order_id=orders.id AND scrapped_at IS NULL)
          AND NOT EXISTS (
            SELECT 1 FROM public.product_instance item
            JOIN public.process_definition_process_step link ON link.process_definition_id=item.process_def_id
            LEFT JOIN public.process_step_execution execution
              ON execution.product_instance_id=item.id AND execution.process_step_id=link.process_step_id
            WHERE item.work_order_id=orders.id AND item.scrapped_at IS NULL
              AND COALESCE(execution.completion_time,execution.skipped_at) IS NULL)
        """, (order_id,))


def sync_notifications(conn, supervisor_id, order_id=None):
    """Upsert monotonically increasing event counts, preserving read state on polls.

    Queue polling catches pre-existing/new assignments. Completion also calls this
    for the affected order's supervisors, so ready events persist while they are offline.
    A poll without an order recounts recent orders only; old counts no longer change.
    """
    filters, params = [], []
    if supervisor_id is not None:
        filters.append('assignment.employee_id=%s'); params.append(supervisor_id)
    if order_id is not None:
        filters.append('orders.id=%s'); params.append(order_id)
    else:
        filters.append(RECENT)
    conn.execute(f"""
        WITH counts AS (
            SELECT assignment.employee_id AS supervisor_id, item.work_order_id, item.process_def_id,
                   execution.process_step_id, count(*)::integer AS assigned,
                   count(*) FILTER (WHERE {_READY})::integer AS ready
            FROM public.process_step_execution execution
            JOIN public.product_instance item ON item.id=execution.product_instance_id
             AND item.scrapped_at IS NULL
            JOIN public.work_order orders ON orders.id=item.work_order_id AND NOT orders.is_cancelled
            JOIN public.process_definition_process_step link
              ON link.process_definition_id=item.process_def_id AND link.process_step_id=execution.process_step_id
            JOIN public.process_step step ON step.id=execution.process_step_id
            JOIN public.employee_unit_assignment assignment ON assignment.unit_id=step.unit_id
              AND assignment.is_supervisor AND assignment.valid_until IS NULL
              AND assignment.valid_from<=CURRENT_TIMESTAMP
            WHERE {' AND '.join(filters)}
            GROUP BY assignment.employee_id,item.work_order_id,item.process_def_id,execution.process_step_id
        )
        INSERT INTO public.supervisor_notification
            (supervisor_id,work_order_id,process_def_id,process_step_id,kind,event_count)
        SELECT supervisor_id,work_order_id,process_def_id,process_step_id,event.kind,event.quantity
        FROM counts CROSS JOIN LATERAL (VALUES ('assigned',assigned),('ready',ready)) event(kind,quantity)
        WHERE event.quantity > 0
        ORDER BY supervisor_id,work_order_id,process_def_id,process_step_id,event.kind
        ON CONFLICT (supervisor_id,work_order_id,process_def_id,process_step_id,kind)
        DO UPDATE SET event_count=EXCLUDED.event_count,updated_at=clock_timestamp(),read_at=NULL
        WHERE supervisor_notification.event_count < EXCLUDED.event_count
    """, params)


_VISIBLE_NOTIFICATION = """EXISTS (
    SELECT 1 FROM public.process_step_execution execution
    JOIN public.product_instance item ON item.id=execution.product_instance_id
    JOIN public.work_order orders ON orders.id=item.work_order_id AND NOT orders.is_cancelled
    JOIN public.process_definition_process_step link
      ON link.process_definition_id=item.process_def_id AND link.process_step_id=execution.process_step_id
    JOIN public.process_step step ON step.id=execution.process_step_id
    JOIN public.employee_unit_assignment assignment ON assignment.unit_id=step.unit_id
      AND assignment.is_supervisor AND assignment.valid_until IS NULL
      AND assignment.valid_from<=CURRENT_TIMESTAMP
    WHERE assignment.employee_id=notice.supervisor_id AND item.work_order_id=notice.work_order_id
      AND item.process_def_id=notice.process_def_id AND execution.process_step_id=notice.process_step_id)"""


NOTIFICATION_LIMIT = 50


def get_notifications(conn, supervisor_id):
    """The newest notifications (unread first) about recent orders in the supervisor's units."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT notice.*,orders.order_number,step.name
            FROM public.supervisor_notification notice
            JOIN public.work_order orders ON orders.id=notice.work_order_id
            JOIN public.process_step step ON step.id=notice.process_step_id
            WHERE notice.supervisor_id=%s AND {RECENT} AND {_VISIBLE_NOTIFICATION}
            ORDER BY (notice.read_at IS NULL) DESC,notice.updated_at DESC,notice.id DESC
            LIMIT {NOTIFICATION_LIMIT}""", (supervisor_id,))
        return cur.fetchall()


def mark_notification_read(conn, supervisor_id, notification_id):
    return conn.execute(f"""UPDATE public.supervisor_notification notice SET read_at=clock_timestamp()
        WHERE notice.id=%s AND notice.supervisor_id=%s AND {_VISIBLE_NOTIFICATION} RETURNING id""",
        (notification_id,supervisor_id)).fetchone() is not None


def add_corrective_request(conn, request_id, order_id, process_id, step_id, quantity, kind,
                           note, requested_by):
    conn.execute("""INSERT INTO public.corrective_request
        (request_id, work_order_id, process_def_id, process_step_id, quantity, kind, note, requested_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (request_id, order_id, process_id, step_id, quantity, kind, note, requested_by))


def get_action_rows(conn, request_id):
    """The executions one action changed, locked, with what happened to them since."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT execution.id, execution.start_time, execution.completion_time,
                   execution.skipped_at, item.id AS item_id, item.scrapped_at,
                   item.scrapped_step_id = execution.process_step_id AS scrapped_here,
                   EXISTS (
                       SELECT 1 FROM public.process_step_execution later
                       JOIN public.process_definition_process_step later_link
                         ON later_link.process_definition_id = item.process_def_id
                        AND later_link.process_step_id = later.process_step_id
                       WHERE later.product_instance_id = item.id
                         AND later_link.sequence_number > link.sequence_number
                         AND (later.start_time IS NOT NULL OR later.skipped_at IS NOT NULL)
                   ) AS later_activity
            FROM public.supervisor_action_item action_item
            JOIN public.process_step_execution execution ON execution.id = action_item.execution_id
            JOIN public.product_instance item ON item.id = execution.product_instance_id
            JOIN public.process_definition_process_step link
              ON link.process_definition_id = item.process_def_id
             AND link.process_step_id = execution.process_step_id
            WHERE action_item.request_id = %s
            ORDER BY execution.id
            FOR UPDATE OF execution""", (request_id,))
        return cur.fetchall()


def reverse_action(conn, action, rows, reversed_by, reason):
    """Undo one recorded action on exactly the rows it changed, and mark it reversed."""
    ids = [r['id'] for r in rows]
    if action['action'] == 'scrap':
        conn.execute('UPDATE public.product_instance SET scrapped_at=NULL, scrapped_step_id=NULL '
                     'WHERE id=ANY(%s)', ([r['item_id'] for r in rows],))
        conn.execute("""UPDATE public.corrective_request SET resolved_at=clock_timestamp(),
            resolved_by=%s, resolution='closed', resolution_note=%s
            WHERE request_id=%s AND resolved_at IS NULL""",
            (reversed_by, 'Scrap reversed: ' + reason, action['request_id']))
    else:
        column = {'start': 'start_time', 'complete': 'completion_time', 'skip': 'skipped_at'}[action['action']]
        conn.execute(f"""UPDATE public.process_step_execution
            SET {column}=NULL, last_update_time=clock_timestamp() WHERE id=ANY(%s)""", (ids,))
    conn.execute("""UPDATE public.supervisor_action
        SET reversed_at=clock_timestamp(), reversed_by=%s, reversal_reason=%s WHERE request_id=%s""",
        (reversed_by, reason, action['request_id']))


def reopen_order(conn, order_id):
    conn.execute('UPDATE public.work_order SET completion_time=NULL WHERE id=%s', (order_id,))


def get_order_actions(conn, order_id):
    """Every recorded floor action on one order, newest first, for the correction list."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT action.request_id, action.action, action.quantity, action.created_at,
                   action.reversed_at, action.reversal_reason,
                   step.name AS step_name, link.sequence_number,
                   who.name || ' ' || who.surname AS supervisor_name,
                   reverser.name || ' ' || reverser.surname AS reversed_by_name,
                   EXISTS (SELECT 1 FROM public.supervisor_action_item i
                           WHERE i.request_id = action.request_id) AS reversible
            FROM public.supervisor_action action
            JOIN public.process_step step ON step.id = action.process_step_id
            JOIN public.process_definition_process_step link
              ON link.process_definition_id = action.process_def_id
             AND link.process_step_id = action.process_step_id
            JOIN public.employee who ON who.id = action.supervisor_id
            LEFT JOIN public.employee reverser ON reverser.id = action.reversed_by
            WHERE action.work_order_id = %s
            ORDER BY action.created_at DESC""", (order_id,))
        return cur.fetchall()


def get_open_pauses(conn, order_ids):
    """Open pauses for these orders, keyed by (order, process, step)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT pause.work_order_id, pause.process_def_id, pause.process_step_id,
                   pause.reason, pause.note, pause.paused_at,
                   who.name || ' ' || who.surname AS paused_by_name
            FROM public.step_pause pause JOIN public.employee who ON who.id = pause.paused_by
            WHERE pause.resumed_at IS NULL AND pause.work_order_id = ANY(%s)""", (list(order_ids),))
        return {(r['work_order_id'], r['process_def_id'], r['process_step_id']): r
                for r in cur.fetchall()}


def add_pause(conn, order_id, process_id, step_id, reason, note, paused_by):
    conn.execute("""INSERT INTO public.step_pause
        (work_order_id, process_def_id, process_step_id, reason, note, paused_by)
        VALUES (%s,%s,%s,%s,%s,%s)""", (order_id, process_id, step_id, reason, note, paused_by))


def end_pause(conn, order_id, process_id, step_id, resumed_by):
    return conn.execute("""UPDATE public.step_pause SET resumed_at=clock_timestamp(), resumed_by=%s
        WHERE work_order_id=%s AND process_def_id=%s AND process_step_id=%s AND resumed_at IS NULL
        RETURNING id""", (resumed_by, order_id, process_id, step_id)).fetchone() is not None
