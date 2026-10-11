"""Read-only statistics queries. Services authorize and apply the visibility scope.

Every query takes an explicit unit scope: ``None`` means "all authorized processes"
(manager/planner), and a list restricts rows to those production units (supervisor).
An empty list selects nothing, so an unassigned supervisor sees no records rather
than every record.
"""
from psycopg.rows import dict_row

# The immediately preceding route step's completion, or its skip timestamp when the
# piece was marked already prepared. A missing upstream execution row stays NULL:
# unknown travel time is never treated as an instant transfer.
_PREDECESSOR = """(
    SELECT COALESCE(prev.completion_time, prev.skipped_at)
    FROM public.process_definition_process_step earlier
    LEFT JOIN public.process_step_execution prev
           ON prev.product_instance_id = item.id
          AND prev.process_step_id = earlier.process_step_id
    WHERE earlier.process_definition_id = item.process_def_id
      AND earlier.sequence_number < link.sequence_number
    ORDER BY earlier.sequence_number DESC LIMIT 1)"""

# Minutes of this execution's working time that fell inside a pause of its order step
# (migration 027). Unfinished executions are measured up to now.
_PAUSED_MINUTES = """(
    SELECT COALESCE(sum(EXTRACT(EPOCH FROM
        LEAST(COALESCE(pause.resumed_at, clock_timestamp()),
              COALESCE(execution.completion_time, clock_timestamp()))
        - GREATEST(pause.paused_at, execution.start_time))) / 60, 0)::float
    FROM public.step_pause pause
    WHERE pause.work_order_id = item.work_order_id
      AND pause.process_def_id = item.process_def_id
      AND pause.process_step_id = execution.process_step_id
      AND execution.start_time IS NOT NULL
      AND pause.paused_at < COALESCE(execution.completion_time, clock_timestamp())
      AND COALESCE(pause.resumed_at, clock_timestamp()) > execution.start_time)"""

_HAS_PREDECESSOR = """EXISTS (
    SELECT 1 FROM public.process_definition_process_step earlier
    WHERE earlier.process_definition_id = item.process_def_id
      AND earlier.sequence_number < link.sequence_number)"""

_EXECUTION_SOURCE = """
    FROM public.process_step_execution execution
    JOIN public.product_instance item ON item.id = execution.product_instance_id
    JOIN public.work_order orders ON orders.id = item.work_order_id
    JOIN public.contractor contractor ON contractor.id = orders.contractor_id
    JOIN public.process_definition_process_step link
      ON link.process_definition_id = item.process_def_id
     AND link.process_step_id = execution.process_step_id
    JOIN public.process_step step ON step.id = execution.process_step_id
    JOIN public.production_unit unit ON unit.id = step.unit_id
    JOIN public.product_type product ON product.id = item.product_type_id
    JOIN public.process_definition route ON route.id = item.process_def_id
"""

_EXECUTION_COLUMNS = f"""
    execution.id AS execution_id, item.id AS item_id, item.work_order_id,
    orders.order_number, orders.creation_time AS order_created,
    orders.completion_time AS order_completed, orders.due_date, orders.created_by,
    orders.is_cancelled, contractor.id AS contractor_id, contractor.name AS contractor_name,
    item.process_def_id, route.name AS process_name, route.version,
    product.id AS product_id, product.name AS product_name, product.reference_code,
    execution.process_step_id AS step_id, step.name AS step_name,
    link.sequence_number, step.standard_time_seconds,
    unit.id AS unit_id, unit.name AS unit_name,
    execution.start_time, execution.completion_time, execution.skipped_at,
    {_PREDECESSOR} AS predecessor_finished_at,
    {_HAS_PREDECESSOR} AS has_predecessor,
    {_PAUSED_MINUTES} AS paused_minutes
"""

# Only these filters reach SQL; the service rejects anything else before calling.
_FILTER_COLUMNS = {
    'product_id': 'product.id', 'process_def_id': 'item.process_def_id',
    'step_id': 'execution.process_step_id', 'unit_id': 'unit.id',
    'contractor_id': 'contractor.id', 'work_order_id': 'orders.id',
    'created_by': 'orders.created_by',
}


def _conditions(scope_unit_ids, filters):
    """Compose the shared scope and filter predicates as parameterized SQL."""
    clauses = ['NOT orders.is_cancelled']
    params = []
    if scope_unit_ids is not None:
        clauses.append('unit.id = ANY(%s)')
        params.append(list(scope_unit_ids))
    for key, column in _FILTER_COLUMNS.items():
        value = filters.get(key)
        if value is not None:
            clauses.append(f'{column} = %s')
            params.append(value)
    return clauses, params


def get_execution_observations(conn, *, scope_unit_ids, filters, completed_from=None,
                               completed_to=None, completed_only=True):
    """One row per piece-step execution, with the timestamps timing is derived from.

    ``completed_only`` selects finished processing (a completion timestamp), which is
    the historical statistics population. Skipped pieces are never included as
    completed work: they have no start or completion timestamp by schema constraint.
    """
    clauses, params = _conditions(scope_unit_ids, filters)
    if completed_only:
        clauses.append('execution.completion_time IS NOT NULL')
    if completed_from is not None:
        clauses.append('execution.completion_time >= %s')
        params.append(completed_from)
    if completed_to is not None:
        clauses.append('execution.completion_time < %s')
        params.append(completed_to)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT {_EXECUTION_COLUMNS} {_EXECUTION_SOURCE}
            WHERE {' AND '.join(clauses)}
            ORDER BY execution.completion_time NULLS LAST, execution.id""", params)
        return cur.fetchall()


def get_live_executions(conn, *, scope_unit_ids, filters):
    """Unfinished executions of open orders, for the separate live at-risk section."""
    clauses, params = _conditions(scope_unit_ids, filters)
    clauses += ['execution.completion_time IS NULL', 'execution.skipped_at IS NULL',
                'item.scrapped_at IS NULL']
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT {_EXECUTION_COLUMNS} {_EXECUTION_SOURCE}
            WHERE {' AND '.join(clauses)}
            ORDER BY execution.start_time NULLS LAST, execution.id""", params)
        return cur.fetchall()


def get_order_durations(conn, *, scope_unit_ids, filters, completed_from=None, completed_to=None):
    """Order-level lead times. Production start is the earliest actual step start.

    Orders are counted once even when their pieces span several units; a supervisor's
    scope selects orders that have at least one step in their units.
    """
    clauses, params = _conditions(scope_unit_ids, filters)
    if completed_from is not None:
        clauses.append('orders.completion_time >= %s')
        params.append(completed_from)
    if completed_to is not None:
        clauses.append('orders.completion_time < %s')
        params.append(completed_to)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT orders.id AS work_order_id, orders.order_number,
                   orders.creation_time AS order_created, orders.completion_time AS order_completed,
                   orders.due_date, orders.created_by,
                   min(product.name) AS product_name, min(contractor.name) AS contractor_name,
                   min(execution.start_time) AS production_started,
                   count(DISTINCT item.id) AS pieces
            {_EXECUTION_SOURCE}
            WHERE {' AND '.join(clauses)}
            GROUP BY orders.id, orders.order_number, orders.creation_time,
                     orders.completion_time, orders.due_date, orders.created_by
            ORDER BY orders.completion_time NULLS LAST, orders.id""", params)
        return cur.fetchall()


def get_open_orders(conn, *, scope_unit_ids, filters):
    """Uncompleted orders, used for the live overdue count."""
    clauses, params = _conditions(scope_unit_ids, filters)
    clauses.append('orders.completion_time IS NULL')
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT orders.id AS work_order_id, orders.order_number, orders.due_date,
                   orders.creation_time AS order_created, min(product.name) AS product_name,
                   min(contractor.name) AS contractor_name, count(DISTINCT item.id) AS pieces,
                   count(*) FILTER (WHERE execution.completion_time IS NOT NULL
                                       OR execution.skipped_at IS NOT NULL) AS finished_steps,
                   count(*) AS total_steps
            {_EXECUTION_SOURCE}
            WHERE {' AND '.join(clauses)}
            GROUP BY orders.id, orders.order_number, orders.due_date, orders.creation_time
            ORDER BY orders.due_date NULLS LAST, orders.id""", params)
        return cur.fetchall()


def _period(column, completed_from, completed_to):
    clauses, params = [], []
    if completed_from is not None:
        clauses.append(f'{column} >= %s')
        params.append(completed_from)
    if completed_to is not None:
        clauses.append(f'{column} < %s')
        params.append(completed_to)
    return clauses, params


def get_quality_counts(conn, *, scope_unit_ids, filters, completed_from=None, completed_to=None):
    """Counts of records deliberately excluded from timing, so they are never silent.

    Skipped pieces are finished requirements without processing, and cancelled orders
    are excluded everywhere else; both are reported rather than counted as zero. Each count
    is reached through its own index: cancelled orders are few (a partial index), and
    skipped pieces are found by when they were skipped.
    """
    clauses, params = _conditions(scope_unit_ids, filters)
    # clauses[0] is the shared cancelled-order exclusion, replaced for the cancelled count.
    skipped, skip_params = _period('execution.skipped_at', completed_from, completed_to)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT cancelled.executions AS cancelled, cancelled.orders AS cancelled_orders,
                   (SELECT count(*) {_EXECUTION_SOURCE}
                    WHERE {' AND '.join(clauses + ['execution.skipped_at IS NOT NULL'] + skipped)}) AS skipped
            FROM (SELECT count(*) AS executions, count(DISTINCT orders.id) AS orders {_EXECUTION_SOURCE}
                  WHERE {' AND '.join(['orders.is_cancelled'] + clauses[1:])}) cancelled""",
                    # The skipped subquery comes first in the text; clauses[0] has no parameter.
                    params + skip_params + params)
        return cur.fetchone()


# Each filter list: its key, and the scoped columns it is built from (id and name first).
_OPTION_LISTS = (
    ('products', 'product_id AS id, product_name AS name'),
    ('processes', 'process_id AS id, process_name AS name, product_name'),
    ('steps', 'step_id AS id, step_name AS name, unit_name'),
    ('units', 'unit_id AS id, unit_name AS name'),
    ('contractors', 'contractor_id AS id, contractor_name AS name'),
    ('orders', 'order_id AS id, order_number AS name'),
)
_OPTION_COLUMNS = """product.id AS product_id, product.name AS product_name, route.id AS process_id,
    coalesce(route.name, 'Production') || ' v' || route.version AS process_name,
    step.id AS step_id, step.name AS step_name, unit.id AS unit_id, unit.name AS unit_name,
    contractor.id AS contractor_id, contractor.name AS contractor_name,
    orders.id AS order_id, orders.order_number"""


def get_filter_options(conn, *, scope_unit_ids, completed_from=None, completed_to=None):
    """Selectable filter values: what the caller's units completed in the period, plus the
    open orders the live section shows.

    Both halves are reached through indexes (completion time, open orders), so the lists stay
    as long as the period, not as long as the history. The joined rows are read once; every
    list is drawn from them and ordered by name as the database sorts text, in one round trip.
    """
    clauses, params = _conditions(scope_unit_ids, {})
    period, period_params = _period('execution.completion_time', completed_from, completed_to)
    lists = ',\n'.join(
        f"(SELECT coalesce(json_agg(o ORDER BY o.name), '[]') FROM (SELECT DISTINCT {columns} "
        f"FROM scoped) o) AS {key}" for key, columns in _OPTION_LISTS)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            WITH scoped AS MATERIALIZED (
                SELECT {_OPTION_COLUMNS} {_EXECUTION_SOURCE}
                WHERE {' AND '.join(clauses + ['execution.completion_time IS NOT NULL'] + period)}
                UNION
                SELECT {_OPTION_COLUMNS} {_EXECUTION_SOURCE}
                WHERE {' AND '.join(clauses + ['orders.completion_time IS NULL'])})
            SELECT {lists}""", params + period_params + params)
        return cur.fetchone()


def get_supervised_unit_ids(conn, employee_id):
    """Current supervision only; ended assignments never grant statistics access."""
    rows = conn.execute("""SELECT unit_id FROM public.employee_unit_assignment
        WHERE employee_id = %s AND is_supervisor AND valid_until IS NULL
          AND valid_from <= CURRENT_TIMESTAMP""", (employee_id,)).fetchall()
    return [row[0] for row in rows]


def get_pause_totals(conn, *, scope_unit_ids, filters, completed_from=None, completed_to=None):
    """Paused minutes per reason, for pauses that began in the period and the scope."""
    clauses, params = _conditions(scope_unit_ids, {k: v for k, v in filters.items()
                                                   if k != 'step_id'})
    clauses = [c.replace('execution.process_step_id', 'pause.process_step_id') for c in clauses]
    if filters.get('step_id') is not None:
        clauses.append('pause.process_step_id = %s')
        params.append(filters['step_id'])
    if completed_from is not None:
        clauses.append('pause.paused_at >= %s')
        params.append(completed_from)
    if completed_to is not None:
        clauses.append('pause.paused_at < %s')
        params.append(completed_to)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT pause.reason, count(*) AS pauses,
                   sum(EXTRACT(EPOCH FROM COALESCE(pause.resumed_at, clock_timestamp())
                                          - pause.paused_at)) / 60 AS minutes
            FROM public.step_pause pause
            JOIN public.work_order orders ON orders.id = pause.work_order_id
            JOIN public.contractor contractor ON contractor.id = orders.contractor_id
            JOIN public.process_definition route ON route.id = pause.process_def_id
            JOIN public.product_type product ON product.id = route.product_type_id
            JOIN public.process_step step ON step.id = pause.process_step_id
            JOIN public.production_unit unit ON unit.id = step.unit_id
            WHERE {' AND '.join(c.replace('item.process_def_id', 'pause.process_def_id')
                                for c in clauses)}
            GROUP BY pause.reason ORDER BY minutes DESC""", params)
        return cur.fetchall()
