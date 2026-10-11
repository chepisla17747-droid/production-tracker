"""Execution workflow scoped to the supervisor’s current unit assignments."""
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from backend.annotations import PositiveInt, NonBlankText
from backend.validation import validate_call
from backend.service.permissions_service import NotFound, require_permission
from backend.operations import supervisor_operations as db


ACTIONS = ('start', 'complete', 'skip', 'scrap')
# What a supervisor asks for when scrapping: replacement pieces, a review, or nothing.
CORRECTIVE_CHOICES = ('replace', 'review', 'none')


def _scrapped_here(row):
    return row.get('scrapped_sequence') is not None and row['sequence_number'] == row['scrapped_sequence']


def _reaches_step(row):
    """A piece scrapped at an earlier step never arrives at this one."""
    return row.get('scrapped_sequence') is None or row['sequence_number'] <= row['scrapped_sequence']


def part_cards(rows):
    """Group execution rows into one card per order process step, with status and timing.

    A piece scrapped at this step counts as resolved here (neither finished nor waiting),
    so the step can still finish; it is left out of every later step.
    """
    groups = defaultdict(list)
    for row in rows:
        if _reaches_step(row):
            groups[(row['work_order_id'], row['process_def_id'], row['process_step_id'])].append(row)
    now = datetime.now(timezone.utc)
    cards = []
    for key, items in groups.items():
        card = {k: v for k, v in items[0].items() if k not in ('id', 'item_id', 'start_time', 'completion_time', 'skipped_at', 'predecessor_finished_at', 'upstream_complete', 'scrapped_at', 'scrapped_sequence')}
        total = len(items)
        live = [r for r in items if not _scrapped_here(r)]
        scrapped = total - len(live)
        completed = sum(r['completion_time'] is not None or r['skipped_at'] is not None for r in live)
        skipped = sum(r['skipped_at'] is not None for r in live)
        unstarted = sum(r['start_time'] is None and r['skipped_at'] is None for r in live)
        running = sum(r['start_time'] is not None and r['completion_time'] is None for r in live)
        ready = sum(r['start_time'] is None and r['skipped_at'] is None and r['upstream_complete'] for r in live)
        starts = [r['start_time'] for r in items if r['start_time'] is not None]
        start = min(starts) if starts else None
        done = completed + scrapped == total
        end = max([r['completion_time'] or r['skipped_at'] for r in live]
                  + [r['scrapped_at'] for r in items if _scrapped_here(r)]) if done else None
        elapsed = max(0, int(((end or now) - start).total_seconds())) if start else 0
        status = 'completed' if done else 'partial' if completed or scrapped else 'in_process' if start else 'ready' if ready else 'waiting'
        standard = card['standard_time_seconds']
        transfers = [(r['start_time']-r['predecessor_finished_at']).total_seconds() for r in items
                     if r['start_time'] and r['predecessor_finished_at']]
        cards.append(dict(card, total=total, completed=completed, skipped=skipped, unstarted=unstarted, running=running, ready=ready,
            scrapped=scrapped, scrappable=running + ready, remaining=total - completed - scrapped,
            transfer_seconds=round(sum(transfers)/len(transfers)) if transfers else None,
            status=status, started_at=start, finished_at=end, elapsed_seconds=elapsed,
            expected_seconds=standard * total if standard else None,
            overdue=bool(card['due_date'] and card['due_date'] < now.date() and not done)))
    return cards


@validate_call
def get_supervisor_work(actor, pool, *, unit_id: PositiveInt | None = None,
                        search: str = '', status: str = 'all', sort: str = 'due_asc'):
    if status not in ('all','waiting','ready','in_process','partial','completed'):
        raise ValueError('Unknown status filter')
    if sort not in ('due_asc','due_desc','created_asc','created_desc'):
        raise ValueError('Unknown sort order')
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, 'production.execute')
        rows = db.get_assigned_executions(conn, actor.employee_id)
        db.sync_notifications(conn, actor.employee_id)
        notifications = db.get_notifications(conn, actor.employee_id)
        pauses = db.get_open_pauses(conn, {r['work_order_id'] for r in rows})
    cards = part_cards(rows)
    for card in cards:
        card['pause'] = pauses.get((card['work_order_id'], card['process_def_id'], card['process_step_id']))
    units = {c['unit_id']: c['unit_name'] for c in cards}
    query = search.strip().casefold()
    cards = [c for c in cards if (unit_id is None or c['unit_id'] == unit_id)
             and (status == 'all' or c['status'] == status)
             and query in ' '.join(str(c.get(k) or '') for k in
                 ('order_number','name','instructions','product_name','description','process_name')).casefold()]
    # Stable ID tie-breakers; undated orders remain last in either due-date direction.
    cards.sort(key=lambda c: (c['work_order_id'],c['process_def_id'],c['process_step_id']))
    field = 'due_date' if sort.startswith('due') else 'creation_time'
    dated = [c for c in cards if c[field] is not None]
    undated = [c for c in cards if c[field] is None]
    dated.sort(key=lambda c:c[field], reverse=sort.endswith('desc'))
    return {'cards': dated + undated, 'units': units, 'notifications': notifications}


def _supervised_step(conn, actor, order_id, process_id, step_id):
    """Lock the order and step's unit, and return the step's rows if the actor supervises it.

    Supervision is read from current assignments while the unit is locked, so a
    concurrent move to another supervisor cannot slip between the check and the change.
    """
    require_permission(conn, actor, 'production.execute')
    if not db.lock_order(conn, order_id):
        raise ValueError('Order is unavailable')
    # Unit moves and actions take the same unit lock; history never owns access.
    unit = conn.execute('SELECT unit_id FROM process_step WHERE id=%s', (step_id,)).fetchone()
    if unit:
        db.lock_supervised_units(conn, [unit[0]])
    rows = [r for r in db.get_assigned_executions(conn, actor.employee_id, order_id)
            if r['process_def_id'] == process_id and r['process_step_id'] == step_id]
    if not rows:
        raise PermissionError('You do not supervise this part’s production unit')
    return rows


@validate_call
def update_part_service(actor, pool, *, order_id: PositiveInt, process_id: PositiveInt,
                        step_id: PositiveInt, quantity: PositiveInt,
                        action: NonBlankText, request_id: NonBlankText,
                        corrective: str = 'none', note: str | None = None):
    """Record one quantity action. Scrapping also files the chosen corrective request."""
    if action not in ACTIONS:
        raise ValueError('Choose Start, Complete, Already prepared or Scrap')
    if corrective not in CORRECTIVE_CHOICES or (corrective != 'none' and action != 'scrap'):
        raise ValueError('Choose what should happen to the scrapped pieces')
    note = (note or '').strip()[:1000] or None
    try:
        token = UUID(request_id)
    except ValueError:
        raise ValueError('Invalid submission identifier') from None
    with pool.connection() as conn, conn.transaction():
        rows = _supervised_step(conn, actor, order_id, process_id, step_id)
        if action in ('start', 'complete') and (order_id, process_id, step_id) in db.get_open_pauses(conn, [order_id]):
            raise ValueError('This step is paused. Resume it before starting or completing pieces.')
        # A scrapped piece takes no further action anywhere.
        rows = [r for r in rows if r['scrapped_at'] is None]
        previous = db.get_action(conn, token)
        details = dict(supervisor_id=actor.employee_id, work_order_id=order_id,
                       process_def_id=process_id, process_step_id=step_id, action=action, quantity=quantity)
        if previous:
            if any(previous[k] != v for k,v in details.items()):
                raise ValueError('Submission identifier has already been used')
            return quantity
        if action == 'scrap':
            # Pieces physically at this step: running ones first, then those ready to start.
            eligible = sorted((r for r in rows if r['completion_time'] is None and r['skipped_at'] is None
                               and (r['start_time'] is not None or r['upstream_complete'])),
                              key=lambda r: (r['start_time'] is None, r['id']))
        else:
            eligible = [r for r in rows if (
                r['start_time'] is not None and r['completion_time'] is None if action == 'complete'
                else r['start_time'] is None and r['skipped_at'] is None
                     and (action == 'skip' or r['upstream_complete']))]
        if quantity > len(eligible):
            raise ValueError(f'Only {len(eligible)} pieces are eligible. Refresh and choose a valid quantity.')
        # Insert the receipt before mutation; any collision or later error rolls back everything.
        db.record_action(conn, token, actor.employee_id, order_id, process_id, step_id, action, quantity)
        changed = db.update_executions(conn, eligible[:quantity], action, step_id)
        # Which rows changed is what lets a manager reverse this action exactly.
        db.record_action_items(conn, token, changed)
        if action == 'scrap' and corrective != 'none':
            db.add_corrective_request(conn, token, order_id, process_id, step_id, quantity,
                                      corrective, note, actor.employee_id)
        if action in ('complete','skip','scrap'):
            db.complete_order_if_finished(conn, order_id)
            db.sync_notifications(conn, None, order_id)
        return quantity


@validate_call
def read_notification_service(actor, pool, notification_id: PositiveInt):
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, 'production.execute')
        if not db.mark_notification_read(conn, actor.employee_id, notification_id):
            raise PermissionError('Notification is not available to you')


@validate_call
def reverse_action_service(actor, pool, *, request_id: NonBlankText, reason: NonBlankText):
    """Undo one mistaken floor action exactly, for managers, with the reason recorded.

    Refused when later work already depends on it (a started piece was completed, or a
    completed piece moved on), or when replacements were already made for a scrap.
    """
    try:
        token = UUID(request_id)
    except ValueError:
        raise ValueError('Invalid action identifier') from None
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, 'production.correct')
        action = db.get_action(conn, token)
        if action is None:
            raise NotFound('This action no longer exists.')
        if not db.lock_order(conn, action['work_order_id']):
            raise ValueError('This work order was cancelled; its actions can no longer change.')
        if action['reversed_at'] is not None:
            raise ValueError('This action was already reversed.')
        rows = db.get_action_rows(conn, token)
        if not rows:
            raise ValueError('This action was recorded before corrections were possible, '
                             'so it cannot be reversed here.')
        kind = action['action']
        if kind == 'start' and any(r['completion_time'] or r['scrapped_at'] for r in rows):
            raise ValueError('Some of these pieces were completed or scrapped since. '
                             'Reverse those actions first.')
        if kind in ('complete', 'skip') and any(r['later_activity'] or r['scrapped_at'] for r in rows):
            raise ValueError('Some of these pieces have moved on to a later step or were scrapped. '
                             'Reverse those actions first.')
        if kind == 'scrap':
            if not all(r['scrapped_here'] for r in rows):
                raise ValueError('These pieces are no longer scrapped at this step.')
            if conn.execute("SELECT 1 FROM public.corrective_request WHERE request_id=%s "
                            "AND resolution='replaced'", (token,)).fetchone():
                raise ValueError('Replacement pieces were already added for this scrap, '
                                 'so it cannot be reversed.')
        db.reverse_action(conn, action, rows, actor.employee_id, reason.strip())
        if kind != 'start':
            # Unfinished pieces again: the order cannot stay complete.
            db.reopen_order(conn, action['work_order_id'])
        db.sync_notifications(conn, None, action['work_order_id'])
        return action['quantity']


PAUSE_REASONS = ('break', 'machine', 'material', 'quality', 'other')


@validate_call
def pause_step_service(actor, pool, *, order_id: PositiveInt, process_id: PositiveInt,
                       step_id: PositiveInt, reason: NonBlankText, note: str | None = None):
    """Pause every running piece of one order step, for a stated reason.

    A pause changes no due date. Paused time is shown separately in Statistics, and a
    pause longer than an hour is flagged to managers, so it cannot quietly hide slow work.
    """
    if reason not in PAUSE_REASONS:
        raise ValueError('Choose why the step is paused')
    with pool.connection() as conn, conn.transaction():
        rows = _supervised_step(conn, actor, order_id, process_id, step_id)
        if not any(r['start_time'] and not r['completion_time'] and r['scrapped_at'] is None
                   for r in rows):
            raise ValueError('Only a step with pieces in progress can be paused.')
        if (order_id, process_id, step_id) in db.get_open_pauses(conn, [order_id]):
            raise ValueError('This step is already paused.')
        db.add_pause(conn, order_id, process_id, step_id, reason,
                     (note or '').strip()[:500] or None, actor.employee_id)


@validate_call
def resume_step_service(actor, pool, *, order_id: PositiveInt, process_id: PositiveInt,
                        step_id: PositiveInt):
    with pool.connection() as conn, conn.transaction():
        _supervised_step(conn, actor, order_id, process_id, step_id)
        if not db.end_pause(conn, order_id, process_id, step_id, actor.employee_id):
            raise ValueError('This step is not paused.')
