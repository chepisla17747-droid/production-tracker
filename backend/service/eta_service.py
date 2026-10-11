"""Estimated finish time for open work orders (the "AI part", formerly server.py).

The standalone ETA server read an Excel file; this module does the same job from the
website's own database, so the forecast always matches what supervisors record.

How a forecast is made
----------------------
Every unfinished piece is followed along the rest of its route, one step after another,
and the order is expected to finish when its last piece does. Pieces move independently,
as batches did in the Excel model. For each step a piece still has to do:

* **Processing time** is learned from the most recent finished pieces at that same
  process step: the median of their working minutes from start to completion, minus
  paused minutes. With fewer than ``MIN_SAMPLES`` pieces of history, the step's standard
  time is used instead. A learned value is kept between ``PACE_LIMITS`` times the
  standard, so a handful of odd recordings cannot make the forecast absurd.
* **Waiting time** before a step (moving, queueing) is learned the same way, from the
  gap between the previous step's completion and this step's start. Without history the
  old rule applies: ``QUEUE_DELAY_MINUTES`` when another order is being worked on at
  that unit right now (the old Resource_Queue "Busy" status), otherwise none.
* A piece already started at a step is expected to need what is left of its processing
  time; one already over it is expected to finish now.

Times are counted in working hours only (``SHIFT_BLOCKS`` on ``WORK_DAYS``, server local
time), the same shift calendar as the old server: 08:00-17:00 with a 12:00-13:00 break,
Monday to Friday. Change the two constants below if the factory's shift changes.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta
from statistics import median

# Working calendar: Monday=0 ... Sunday=6. Add 5 to work Saturdays.
WORK_DAYS = frozenset({0, 1, 2, 3, 4})
SHIFT_BLOCKS = ((time(8, 0), time(12, 0)), (time(13, 0), time(17, 0)))

MIN_SAMPLES = 5
PACE_LIMITS = (0.5, 3.0)
QUEUE_DELAY_MINUTES = 15
# A forecast further away than this is not credible; the search stops there.
MAX_CALENDAR_DAYS = 3660


# ------------------------------------------------------------------- working calendar

def _local_naive(moment):
    """Wall-clock time in the server's zone; naive values are taken as already local."""
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo else moment


def _restore(naive, like):
    """Back to an aware local time when the input was aware."""
    return naive.astimezone() if like.tzinfo else naive


def _blocks(day):
    if day.weekday() not in WORK_DAYS:
        return ()
    return tuple((datetime.combine(day, start), datetime.combine(day, end))
                 for start, end in SHIFT_BLOCKS)


def add_working_minutes(start, minutes):
    """The moment ``minutes`` of working time after ``start``, skipping breaks and days off."""
    remaining = max(0.0, float(minutes))
    if remaining == 0:
        return start
    current = _local_naive(start)
    day = current.date()
    for _ in range(MAX_CALENDAR_DAYS):
        for begin, end in _blocks(day):
            if current >= end:
                continue
            current = max(current, begin)
            available = (end - current).total_seconds() / 60
            if remaining <= available:
                return _restore(current + timedelta(minutes=remaining), start)
            remaining -= available
            current = end
        day += timedelta(days=1)
    raise ValueError('The forecast is more than ten years away')


def working_minutes_between(start, end):
    """Working minutes from ``start`` to ``end``; zero when ``end`` is not later."""
    start, end = _local_naive(start), _local_naive(end)
    if end <= start:
        return 0.0
    total, day = 0.0, start.date()
    for _ in range(MAX_CALENDAR_DAYS):
        if day > end.date():
            break
        for begin, finish in _blocks(day):
            overlap = (min(finish, end) - max(begin, start)).total_seconds()
            if overlap > 0:
                total += overlap / 60
        day += timedelta(days=1)
    return total


# ------------------------------------------------------------------ learning from history

def learn_profiles(history, standards):
    """Per process step: learned processing and waiting minutes, or None for each.

    ``history`` rows come from ``eta_operations.get_step_history``; ``standards`` maps a
    step id to its standard minutes (or None) so learned processing can be kept sensible.
    """
    process, wait = defaultdict(list), defaultdict(list)
    for row in history:
        step = row['process_step_id']
        worked = working_minutes_between(row['start_time'], row['completion_time'])
        process[step].append(max(0.0, worked - (row.get('paused_minutes') or 0.0)))
        if row.get('has_predecessor') and row.get('predecessor_finished_at'):
            wait[step].append(working_minutes_between(row['predecessor_finished_at'], row['start_time']))
    profiles = {}
    for step in set(process) | set(wait):
        learned = median(process[step]) if len(process[step]) >= MIN_SAMPLES else None
        standard = standards.get(step)
        if learned is not None and standard:
            low, high = PACE_LIMITS
            learned = min(max(learned, low * standard), high * standard)
        profiles[step] = {
            'process': learned,
            'wait': median(wait[step]) if len(wait[step]) >= MIN_SAMPLES else None,
            'samples': len(process[step]),
        }
    return profiles


# --------------------------------------------------------------------------- forecasting

def _planned_start(order, now):
    """Work cannot begin before the order's planned start day (at the shift start)."""
    start_date = order.get('start_date')
    if start_date is None:
        return now
    planned = datetime.combine(start_date, SHIFT_BLOCKS[0][0])
    planned = planned.astimezone() if now.tzinfo else planned
    return max(now, planned)


def forecast_order(order, rows, now, profiles, busy_units):
    """The order's expected finish, judged at ``now``; None when it cannot be forecast.

    ``rows`` are the order's piece-step rows (``overview_operations.get_order_steps``).
    """
    if order.get('completion_time') is not None or not rows:
        return None
    pieces = defaultdict(list)
    for row in rows:
        pieces[row['item_id']].append(row)
    floor = _planned_start(order, now)
    finish, step_finish, sources, unknown_standard = None, {}, set(), False

    for piece_rows in pieces.values():
        piece_rows.sort(key=lambda r: r['sequence_number'])
        # A scrapped piece has left its route; any replacement is a new piece.
        if any(r.get('scrapped_sequence') is not None for r in piece_rows):
            continue
        clock, at_current_step = None, True
        for row in piece_rows:
            if row['completion_time'] is not None or row['skipped_at'] is not None:
                continue
            step = row['process_step_id']
            profile = profiles.get(step, {})
            standard = row['standard_time_seconds'] / 60 if row['standard_time_seconds'] else None
            processing = profile.get('process') or standard
            sources.add('history' if profile.get('process') else 'standard')
            if processing is None:
                processing, unknown_standard = 0.0, True
            if row['start_time'] is not None:
                done = working_minutes_between(row['start_time'], now)
                clock = add_working_minutes(now, max(0.0, processing - done))
            else:
                waiting = profile.get('wait')
                if waiting is None:
                    others = busy_units.get(row['unit_id'], set()) - {order['work_order_id']}
                    waiting = QUEUE_DELAY_MINUTES if at_current_step and others else 0.0
                if at_current_step and row.get('predecessor_finished_at'):
                    # Time already spent waiting counts against the expected wait.
                    waiting = max(0.0, waiting - working_minutes_between(
                        row['predecessor_finished_at'], now))
                clock = add_working_minutes(clock or floor, waiting + processing)
            at_current_step = False
            sequence = row['sequence_number']
            step_finish[sequence] = max(step_finish.get(sequence, clock), clock)
        if clock is not None:
            finish = clock if finish is None else max(finish, clock)

    if finish is None:
        return None  # every piece is finished or scrapped; completion is only not recorded yet
    due = order.get('due_date')
    late_days = (_local_naive(finish).date() - due).days if due is not None else None
    return {
        'finish': finish,
        'remaining_minutes': round(working_minutes_between(now, finish)),
        'on_time': late_days is None or late_days <= 0,
        'late_days': max(0, late_days) if late_days is not None else None,
        'basis': sources.pop() if len(sources) == 1 else 'mixed',
        'unknown_standard': unknown_standard,
        'step_finish': [{'sequence_number': s, 'finish': step_finish[s]} for s in sorted(step_finish)],
    }


def forecast_orders(conn, orders, rows_by_order, now):
    """Forecasts for these orders, keyed by order id, from one pair of database reads."""
    from backend.operations import eta_operations as db
    open_orders = [o for o in orders if o.get('completion_time') is None]
    standards = {}
    for order in open_orders:
        for row in rows_by_order.get(order['work_order_id'], ()):
            seconds = row['standard_time_seconds']
            standards[row['process_step_id']] = seconds / 60 if seconds else None
    if not standards:
        return {}
    profiles = learn_profiles(db.get_step_history(conn, list(standards)), standards)
    busy = db.get_busy_units(conn)
    return {o['work_order_id']: forecast_order(o, rows_by_order.get(o['work_order_id'], []),
                                               now, profiles, busy) for o in open_orders}
