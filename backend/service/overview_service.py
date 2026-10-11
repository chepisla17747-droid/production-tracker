"""Factory overview, order summaries and the per-order step page.

Managers see every order. Supervisors see the same overview narrowed to orders with a
step in a unit they supervise now, and its counts are taken from that narrower list.

Order status, one per order, in this precedence:

* **Complete** — the order has a completion time.
* **Delayed** — still open and its due date is before the as-of date. An order without
  a due date is never delayed. This is only the due-date rule, not a standard overrun.
* **In process** — open, not delayed, and some piece has started, finished or been
  skipped at any step.
* **Not started** — everything else.

A week's overview is judged "as of" now for the current week, and as of the end of the
week for a past week, reconstructed from the recorded timestamps. Cancelled orders are
excluded everywhere; cancellations carry no timestamp, so they also leave past weeks.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import ceil

from backend.annotations import PositiveInt
from backend.validation import validate_call
from backend.operations import overview_operations as db
from backend.operations import statistics_operations as statistics_db
from backend.operations.supervisor_operations import get_assigned_executions, get_order_actions
from backend.service import paging
from backend.service.eta_service import forecast_orders
from backend.service.permissions_service import NotFound, actor_permissions, require_permission
from backend.service.supervisor_service import _reaches_step, _scrapped_here, part_cards

STATUSES = ('not_started', 'in_process', 'delayed', 'complete')
PAGE_SIZE = 20
HISTORY_PAGE_SIZE = 20
OVERVIEW_PERMISSION = 'work_order.overview'


def _overview_scope(conn, actor):
    """None for every order, or the supervisor whose current units bound the overview."""
    permissions = actor_permissions(conn, actor)
    if OVERVIEW_PERMISSION in permissions:
        return None
    if 'production.execute' in permissions:
        return actor.employee_id
    raise PermissionError('Overview permission required')


def _now(conn):
    return conn.execute('SELECT clock_timestamp()').fetchone()[0]


def _monday(day):
    return day - timedelta(days=day.weekday())


def _midnight(day):
    """Start of a calendar day in the server's local time zone."""
    return datetime.combine(day, time.min).astimezone()


def _finished_at(row):
    return row['completion_time'] or row['skipped_at']


def order_status(order, rows, at):
    """The order's status at the instant ``at``, using only events before it."""
    completed = order['completion_time']
    if completed is not None and completed < at:
        return 'complete'
    if order['due_date'] is not None and order['due_date'] < at.astimezone().date():
        return 'delayed'
    for row in rows:
        if any(moment is not None and moment < at
               for moment in (row['start_time'], row['completion_time'], row['skipped_at'])):
            return 'in_process'
    return 'not_started'


def step_progress(rows, at):
    """Pieces that finished each route step before ``at``, in route order.

    A piece finishes a step when it is completed or skipped (Already prepared). Steps are
    keyed by their position in this order's route, so a step definition shared with other
    products is never merged with them.
    """
    grouped = defaultdict(list)
    for row in rows:
        # A piece scrapped earlier never reaches later steps.
        if _reaches_step(row):
            grouped[row['sequence_number']].append(row)
    steps = []
    for sequence in sorted(grouped):
        members = grouped[sequence]
        # A piece scrapped at this step is resolved here, like a finished one.
        scrapped = sum(_scrapped_here(r) and r['scrapped_at'] < at for r in members)
        finished = sum(not _scrapped_here(r) and _finished_at(r) is not None and _finished_at(r) < at
                       for r in members)
        steps.append({'sequence_number': sequence, 'step_id': members[0]['process_step_id'],
                      'name': members[0]['name'], 'unit_name': members[0]['unit_name'],
                      'finished': finished + scrapped, 'scrapped': scrapped, 'total': len(members)})
    return steps


def order_card(order, rows, at):
    """Everything an overview card or order summary shows, judged at ``at``."""
    status = order_status(order, rows, at)
    steps = step_progress(rows, at)
    # The current step is the first one in route order that not every piece has finished.
    current = next((step for step in steps if step['finished'] < step['total']), None)
    if status == 'complete' or (steps and current is None):
        current, percent = None, 100
    elif current is None:
        percent = 0
    else:
        percent = round(100 * current['finished'] / current['total'])
    return dict(order, status=status, steps=steps, current_step=current, percent=percent)


def _group(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['work_order_id']].append(row)
    return grouped


def _week(value, current):
    if value is None:
        return current
    if isinstance(value, str):
        value = date.fromisoformat(value)
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError('Choose a week')
    if value.weekday() != 0:
        raise ValueError('A week starts on Monday')
    if value > current:
        raise ValueError('Future weeks have no overview yet')
    return value


@validate_call
def get_overview_service(actor, pool, *, week_start=None, search: str = '', status: str = 'all',
                         page: PositiveInt = 1):
    """Weekly counts plus a searchable, filterable, paged list of order cards."""
    if status not in ('all',) + STATUSES:
        raise ValueError('Unknown status filter')
    with pool.connection() as conn, conn.transaction():
        supervisor_id = _overview_scope(conn, actor)
        now = _now(conn)
        current_week = _monday(now.astimezone().date())
        week = _week(week_start, current_week)
        start, end = _midnight(week), _midnight(week + timedelta(days=7))
        at = now if week == current_week else end
        # Open orders plus those completed during or after this week.
        orders = [o for o in db.get_orders(conn, active_since=start, supervisor_id=supervisor_id)
                  if o['creation_time'] < at]
        rows = _group(db.get_order_steps(conn, [o['work_order_id'] for o in orders]))
        # A finish-time forecast is about now, so past weeks show none.
        forecasts = forecast_orders(conn, orders, rows, now) if week == current_week else {}

    cards = [dict(order_card(order, rows.get(order['work_order_id'], []), at),
                  forecast=forecasts.get(order['work_order_id'])) for order in orders]
    counts = {name: sum(card['status'] == name for card in cards)
              for name in ('complete', 'in_process', 'delayed')}
    query = search.strip().casefold()
    if query:
        cards = [card for card in cards if query in ' '.join(
            str(card[key] or '') for key in ('order_number', 'product_name', 'contractor_name')).casefold()]
    chips = {'all': len(cards), **{name: sum(c['status'] == name for c in cards) for name in STATUSES}}
    if status != 'all':
        cards = [card for card in cards if card['status'] == status]
    # Nearest due date first; undated orders last; order ID keeps ties stable.
    cards.sort(key=lambda c: (c['due_date'] is None, c['due_date'] or date.max, c['work_order_id']))
    pages = max(1, ceil(len(cards) / PAGE_SIZE))
    page = min(page, pages)
    first = (page - 1) * PAGE_SIZE
    return {
        'week_start': week.isoformat(), 'week_end': (week + timedelta(days=6)).isoformat(),
        'is_current_week': week == current_week, 'as_of': at,
        'unit_scoped': supervisor_id is not None,
        'counts': counts, 'chips': chips, 'orders': cards[first:first + PAGE_SIZE],
        'total': len(cards), 'page': page, 'pages': pages,
        'first': first + 1 if cards else 0, 'last': min(first + PAGE_SIZE, len(cards)),
    }


@validate_call
def get_order_history_service(actor, pool, *, completed_from: date | None = None,
                              completed_to: date | None = None, search: str = '',
                              after: str | None = None, before: str | None = None):
    """Completed orders, most recently completed first, a page at a time.

    Managers see every order; supervisors the orders with a step in a unit they supervise
    now, as on the overview. Dates are local calendar days, both included.
    """
    if completed_from and completed_to and completed_from > completed_to:
        raise ValueError('The date range ends before it starts')
    with pool.connection() as conn, conn.transaction():
        supervisor_id = _overview_scope(conn, actor)
        rows = db.get_orders(
            conn, supervisor_id=supervisor_id, search=search, order_by='completed',
            completed_from=_midnight(completed_from) if completed_from else None,
            completed_to=_midnight(completed_to + timedelta(days=1)) if completed_to else None,
            after=paging.decode(after, paging.MOMENT, paging.KEY),
            before=paging.decode(before, paging.MOMENT, paging.KEY), limit=HISTORY_PAGE_SIZE + 1)
    result = paging.page(rows, HISTORY_PAGE_SIZE, lambda o: (o['completion_time'], o['work_order_id']),
                         after=after, before=before)
    # Late means finished after its due date, by the server's local calendar, as on the overview.
    orders = [dict(order, late=order['due_date'] is not None
                   and order['completion_time'].astimezone().date() > order['due_date'])
              for order in result.pop('rows')]
    return dict(orders=orders, **result, unit_scoped=supervisor_id is not None)


def _load_order(conn, order_id):
    orders = db.get_orders(conn, order_id=order_id)
    if not orders:
        raise NotFound('This work order does not exist or was cancelled.')
    return orders[0], db.get_order_steps(conn, [order_id])


@validate_call
def get_order_summary_service(actor, pool, order_id: PositiveInt):
    """Order summary for managers/admins, or for a supervisor of one of its units.

    Supervisors see only orders with a step in a production unit they supervise now.
    ``can_open_order`` says whether the caller may open the full order page.
    """
    with pool.connection() as conn, conn.transaction():
        permissions = actor_permissions(conn, actor)
        full_access = OVERVIEW_PERMISSION in permissions
        if not full_access and not ('production.execute' in permissions
                                    and get_assigned_executions(conn, actor.employee_id, order_id)):
            raise PermissionError('This work order is not in your production units')
        order, rows = _load_order(conn, order_id)
        now = _now(conn)
        forecast = forecast_orders(conn, [order], {order_id: rows}, now).get(order_id)
    return dict(order_card(order, rows, now), can_open_order=full_access, forecast=forecast)


@validate_call
def get_order_forecast_service(actor, pool, order_id: PositiveInt):
    """Just the finish-time forecast, for the JSON API; same access as the summary."""
    summary = get_order_summary_service(actor, pool, order_id)
    return {'order_id': order_id, 'order_number': summary['order_number'],
            'status': summary['status'], 'due_date': summary['due_date'],
            'completed_at': summary['completion_time'], 'forecast': summary['forecast']}


@validate_call
def get_order_detail_service(actor, pool, order_id: PositiveInt):
    """The manager order page: start, end, status and elapsed time for every step.

    Step timing reuses the Supervisor rules: start is the earliest piece start, end is
    the latest completion or skip once every piece has finished, and elapsed time runs
    from start to end (or to now), including waiting between batches.
    """
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, OVERVIEW_PERMISSION)
        order, rows = _load_order(conn, order_id)
        now = _now(conn)
        actions = get_order_actions(conn, order_id)
        can_correct = 'production.correct' in actor_permissions(conn, actor)
        forecast = forecast_orders(conn, [order], {order_id: rows}, now).get(order_id)
    summary = dict(order_card(order, rows, now), forecast=forecast)
    expected = {s['sequence_number']: s['finish'] for s in (forecast or {}).get('step_finish', [])}
    progress = {step['sequence_number']: step for step in summary['steps']}
    steps = []
    for card in part_cards(rows):
        step = progress[card['sequence_number']]
        steps.append({
            'sequence_number': card['sequence_number'], 'name': card['name'],
            'unit_name': card['unit_name'], 'status': card['status'],
            'started_at': card['started_at'], 'finished_at': card['finished_at'],
            # Elapsed time needs a real start; skipped-only steps were never processed.
            'elapsed_seconds': card['elapsed_seconds'] if card['started_at'] else None,
            'finished': step['finished'], 'total': step['total'], 'skipped': card['skipped'],
            'standard_time_seconds': card['standard_time_seconds'],
            'expected_finish': expected.get(card['sequence_number']),
        })
    steps.sort(key=lambda s: s['sequence_number'])
    for action in actions:
        action['request_id'] = str(action['request_id'])
    return dict(summary, step_details=steps, actions=actions, can_correct=can_correct)


# When the Needs attention panel flags something for a manager.
LONG_PAUSE_MINUTES = 60
SLOW_FACTOR = 2


def get_manager_alerts_service(actor, pool):
    """What a manager should look at now, most urgent first; each item links to its order.

    Delayed orders, orders forecast to finish after their due date, unanswered scrap
    requests, pauses open for over an hour, and pieces whose active time is more than
    twice their step standard. Computed live, so an alert
    disappears as soon as its cause is dealt with.
    """
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, OVERVIEW_PERMISSION)
        now = _now(conn)
        orders = db.get_orders(conn, open_only=True)
        requests = db.get_open_requests(conn)
        pauses = db.get_long_pauses(conn, LONG_PAUSE_MINUTES)
        live = statistics_db.get_live_executions(conn, scope_unit_ids=None, filters={})
        today = now.astimezone().date()
        # Orders not yet past due that the forecast expects to miss their due date.
        upcoming = [o for o in orders if o['due_date'] is not None and o['due_date'] >= today]
        forecasts = forecast_orders(conn, upcoming, _group(db.get_order_steps(
            conn, [o['work_order_id'] for o in upcoming])), now) if upcoming else {}
    alerts = [dict(kind='delayed', order_id=o['work_order_id'], order_number=o['order_number'],
                   days=(today - o['due_date']).days)
              for o in sorted(orders, key=lambda o: o['due_date'] or date.max)
              if o['due_date'] is not None and o['due_date'] < today]
    alerts += [dict(kind='forecast', order_id=o['work_order_id'], order_number=o['order_number'],
                    days=forecasts[o['work_order_id']]['late_days'])
               for o in sorted(upcoming, key=lambda o: o['due_date'])
               if forecasts.get(o['work_order_id']) and not forecasts[o['work_order_id']]['on_time']]
    alerts += [dict(kind='request', order_id=r['work_order_id'], order_number=r['order_number'],
                    step=r['step_name'], quantity=r['quantity'], request=r['kind']) for r in requests]
    alerts += [dict(kind='pause', order_id=p['work_order_id'], order_number=p['order_number'],
                    step=p['step_name'], reason=p['reason'], minutes=round(p['minutes']))
               for p in pauses]
    slow = defaultdict(int)
    names = {}
    for row in live:
        standard = row['standard_time_seconds']
        if row['start_time'] is None or not standard:
            continue
        active = (now - row['start_time']).total_seconds() / 60 - (row['paused_minutes'] or 0)
        if active > SLOW_FACTOR * standard / 60:
            key = (row['work_order_id'], row['step_id'])
            slow[key] += 1
            names[key] = (row['order_number'], row['step_name'])
    alerts += [dict(kind='slow', order_id=order_id, order_number=names[(order_id, step_id)][0],
                    step=names[(order_id, step_id)][1], quantity=count)
               for (order_id, step_id), count in slow.items()]
    return alerts
