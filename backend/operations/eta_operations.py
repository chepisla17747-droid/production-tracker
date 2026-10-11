"""Read-only queries behind the finish-time forecast. The service authorizes callers."""
from psycopg.rows import dict_row

from backend.operations.statistics_operations import _HAS_PREDECESSOR, _PAUSED_MINUTES, _PREDECESSOR

# How many recent finished pieces per process step the forecast learns from.
HISTORY_PER_STEP = 200
HISTORY_DAYS = 180


def get_step_history(conn, step_ids):
    """The most recent finished executions of these process steps, newest first.

    Each row carries what the forecast learns from: start, completion, when the piece's
    previous step finished (for waiting time) and the minutes it spent paused.
    """
    if not step_ids:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT * FROM (
                SELECT execution.process_step_id, execution.start_time, execution.completion_time,
                       {_PREDECESSOR} AS predecessor_finished_at,
                       {_HAS_PREDECESSOR} AS has_predecessor,
                       {_PAUSED_MINUTES} AS paused_minutes,
                       row_number() OVER (PARTITION BY execution.process_step_id
                                          ORDER BY execution.completion_time DESC) AS recent
                FROM public.process_step_execution execution
                JOIN public.product_instance item ON item.id = execution.product_instance_id
                JOIN public.work_order orders ON orders.id = item.work_order_id
                JOIN public.process_definition_process_step link
                  ON link.process_definition_id = item.process_def_id
                 AND link.process_step_id = execution.process_step_id
                WHERE NOT orders.is_cancelled
                  AND execution.process_step_id = ANY(%s)
                  AND execution.start_time IS NOT NULL
                  AND execution.completion_time IS NOT NULL
                  AND execution.completion_time >= clock_timestamp() - make_interval(days => %s)
            ) history
            WHERE recent <= %s""", (list(step_ids), HISTORY_DAYS, HISTORY_PER_STEP))
        return cur.fetchall()


def get_busy_units(conn):
    """Production units with a piece being worked on now, and the orders that piece is for.

    This replaces the Resource_Queue sheet of the old Excel file: a unit is busy while
    any open order has a started, unfinished, unscrapped piece there.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT step.unit_id, item.work_order_id
            FROM public.process_step_execution execution
            JOIN public.product_instance item ON item.id = execution.product_instance_id
            JOIN public.work_order orders ON orders.id = item.work_order_id
            JOIN public.process_step step ON step.id = execution.process_step_id
            WHERE execution.start_time IS NOT NULL AND execution.completion_time IS NULL
              AND item.scrapped_at IS NULL
              AND NOT orders.is_cancelled AND orders.completion_time IS NULL""")
        busy = {}
        for unit_id, order_id in cur.fetchall():
            busy.setdefault(unit_id, set()).add(order_id)
        return busy
