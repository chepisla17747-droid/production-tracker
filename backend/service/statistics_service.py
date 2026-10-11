"""Production statistics for managers, planners and supervisors.

Timing definitions used throughout this module, applied to completed piece-step
executions because standard times are per piece:

* **Travel time** — this step's start minus the previous route step's completion.
  It covers everything in that interval: movement, waiting, queueing and breaks.
  When the previous step was marked *Already prepared*, its skip timestamp is used.
  The first route step has no travel time and reports as unknown, never zero.
* **Process time** — this step's completion minus its own start, including every
  elapsed minute in between.
* **Combined duration** — travel plus process, derived only where both exist. It is
  a total, not a third independent category.

All durations are elapsed clock time; nights and breaks are never subtracted. Every
duration leaves this module in minutes.
"""
import threading
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import ceil, exp, floor, pi, sqrt
from time import monotonic

from backend.operations import statistics_operations as db
from backend.service.permissions_service import actor_permissions

METRICS = ('travel', 'process', 'combined')
METRIC_LABELS = {'travel': 'Travel time', 'process': 'Process time', 'combined': 'Combined duration'}

# Robust upper-outlier rule: Tukey's upper fence, Q3 + 1.5 x IQR, computed inside each
# comparable (process version, step) group. Only unusually large durations are excluded;
# short durations are legitimate. Groups below the minimum sample size get no threshold
# at all, because a fence from three points would be arbitrary.
OUTLIER_MULTIPLIER = 1.5
MIN_OUTLIER_SAMPLE = 5

# Percentage over the standard process time. Bands are inclusive of their upper bound.
SEVERITY_BANDS = (('Minor', 10.0), ('Moderate', 25.0), ('Major', 50.0), ('Severe', None))

MAX_HISTOGRAM_BINS = 80

_FILTER_IDS = ('product_id', 'process_def_id', 'step_id', 'unit_id',
               'contractor_id', 'work_order_id')
_FILTER_KEYS = _FILTER_IDS + ('date_from', 'date_to', 'my_units', 'my_orders')


def resolve_scope(conn, actor):
    """(visible unit ids or None for all, label). Managers and planners see every
    authorized process; supervisors see their units.

    The scope is decided from database permissions and current assignments only, never
    from the selected website view.
    """
    permissions = actor_permissions(conn, actor)
    if 'statistics.view.all' in permissions:
        return None, 'All authorized processes'
    if 'statistics.view.unit' not in permissions:
        raise PermissionError('Statistics permission required')
    # An empty assignment list selects nothing, rather than falling back to everything.
    return (db.get_supervised_unit_ids(conn, actor.employee_id),
            'Processes in your currently assigned production units')


def _clean_filters(filters):
    unknown = set(filters) - set(_FILTER_KEYS)
    if unknown:
        raise ValueError(f"Unknown statistics filter: {', '.join(sorted(unknown))}")
    cleaned = {}
    for key in _FILTER_IDS:
        value = filters.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f'{key} must be a positive record identifier')
        cleaned[key] = value
    for key in ('date_from', 'date_to'):
        value = filters.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = date.fromisoformat(value)
        if not isinstance(value, date) or isinstance(value, datetime):
            raise ValueError(f'{key} must be a calendar date')
        cleaned[key] = value
    if cleaned.get('date_from') and cleaned.get('date_to') and cleaned['date_from'] > cleaned['date_to']:
        raise ValueError('The date range ends before it starts')
    for key in ('my_units', 'my_orders'):
        if filters.get(key):
            cleaned[key] = True
    return cleaned


def _bounds(filters):
    """Half-open [from, to) timestamps in the server's local zone."""
    start = filters.get('date_from')
    end = filters.get('date_to')
    return (datetime.combine(start, time.min).astimezone() if start else None,
            datetime.combine(end + timedelta(days=1), time.min).astimezone() if end else None)


def _quantile(ordered, q):
    """Linear-interpolation quantile, matching PostgreSQL's percentile_cont."""
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _summary(minutes):
    """Average, median and 90th percentile with the sample size they came from."""
    ordered = sorted(minutes)
    if not ordered:
        return {'count': 0, 'average': None, 'median': None, 'p90': None}
    return {'count': len(ordered), 'average': sum(ordered) / len(ordered),
            'median': _quantile(ordered, 0.5), 'p90': _quantile(ordered, 0.9)}


def _upper_fence(minutes):
    """Tukey upper fence, or None when the group is too small to judge."""
    ordered = sorted(minutes)
    if len(ordered) < MIN_OUTLIER_SAMPLE:
        return None
    q1, q3 = _quantile(ordered, 0.25), _quantile(ordered, 0.75)
    return q3 + OUTLIER_MULTIPLIER * (q3 - q1)


def _severity(percent_over):
    for name, limit in SEVERITY_BANDS:
        if limit is None or percent_over <= limit:
            return name
    return SEVERITY_BANDS[-1][0]


def _minutes(delta):
    return delta.total_seconds() / 60 if delta is not None else None


def _observe(row):
    """Derive the three durations and the standard comparison for one execution."""
    start, done = row['start_time'], row['completion_time']
    predecessor = row['predecessor_finished_at']
    # The first route step has no travel time; a missing upstream timestamp is unknown.
    travel = _minutes(start - predecessor) if start and predecessor and row['has_predecessor'] else None
    # Active process time: paused minutes are taken out here and reported on their own.
    paused = row.get('paused_minutes') or 0.0
    process = max(0.0, _minutes(done - start) - paused) if start and done else None
    combined = travel + process if travel is not None and process is not None else None
    standard = row['standard_time_seconds']
    standard_minutes = standard / 60 if standard else None
    observation = dict(row, travel=travel, process=process, combined=combined, paused=paused,
                       standard_minutes=standard_minutes)
    # The standard is a per-piece process expectation; it never applies to travel.
    if standard_minutes is None or process is None:
        observation.update(assessable=False, over_standard=None, excess_minutes=None,
                           percent_over=None, severity=None)
    else:
        excess = process - standard_minutes
        over = excess > 0
        observation.update(assessable=True, over_standard=over,
                           excess_minutes=excess if over else 0.0,
                           percent_over=(excess / standard_minutes * 100) if over else 0.0,
                           severity=_severity(excess / standard_minutes * 100) if over else None)
    observation['travel_known'] = travel is not None or not row['has_predecessor']
    return observation


def _group_key(observation):
    """Comparable group: the same step inside the same product process version."""
    return (observation['process_def_id'], observation['step_id'])


def _flag_outliers(observations):
    """Attach per-metric outlier flags and return each group's thresholds."""
    grouped = defaultdict(list)
    for observation in observations:
        grouped[_group_key(observation)].append(observation)
    fences = {}
    for key, members in grouped.items():
        fences[key] = {metric: _upper_fence([m[metric] for m in members if m[metric] is not None])
                       for metric in METRICS}
    for observation in observations:
        limits = fences[_group_key(observation)]
        flags = {metric: (observation[metric] is not None and limits[metric] is not None
                          and observation[metric] > limits[metric]) for metric in METRICS}
        observation['outlier_metrics'] = [metric for metric, flagged in flags.items() if flagged]
        observation['is_outlier'] = bool(observation['outlier_metrics'])
    return fences


def _timing_block(observations):
    """Raw and adjusted summaries per metric, with included/excluded counts."""
    block = {}
    for metric in METRICS:
        present = [o for o in observations if o[metric] is not None]
        kept = [o for o in present if metric not in o['outlier_metrics']]
        block[metric] = {
            'label': METRIC_LABELS[metric],
            'raw': _summary([o[metric] for o in present]),
            'adjusted': _summary([o[metric] for o in kept]),
            'included': len(kept), 'excluded': len(present) - len(kept),
        }
    return block


def _over_standard(observations):
    """Overrun statistics from every completed execution, outliers included.

    Genuine long runs are real operational delays, so they stay in these counts even
    though the adjusted timing summaries exclude them.
    """
    assessable = [o for o in observations if o['assessable']]
    over = [o for o in assessable if o['over_standard']]
    bands = {name: sum(o['severity'] == name for o in over) for name, _ in SEVERITY_BANDS}
    return {
        'executions': len(observations),
        'assessable': len(assessable),
        'not_assessable': len(observations) - len(assessable),
        'over_count': len(over),
        'over_percent': (len(over) / len(assessable) * 100) if assessable else None,
        'affected_orders': len({o['work_order_id'] for o in over}),
        'average_excess_minutes': (sum(o['excess_minutes'] for o in over) / len(over)) if over else None,
        'average_percent_over': (sum(o['percent_over'] for o in over) / len(over)) if over else None,
        'severity': bands,
        # No historical standard is stored, so past executions are compared with the
        # standard configured today. This is labelled rather than invented.
        'standard_source': 'current',
    }


def _bottlenecks(observations, live):
    """Compare steps within one product process version, never across versions."""
    grouped = defaultdict(list)
    for observation in observations:
        grouped[_group_key(observation)].append(observation)
    ready = defaultdict(int)
    for row in live:
        # Ready means upstream finished (or it is the first step) and work has not started.
        if row['start_time'] is None and (row['predecessor_finished_at'] is not None
                                          or not row['has_predecessor']):
            ready[(row['process_def_id'], row['step_id'])] += 1
    rows = []
    for key, members in grouped.items():
        first = members[0]
        over = [o for o in members if o['assessable'] and o['over_standard']]
        rows.append({
            'process_def_id': key[0], 'step_id': key[1], 'step_name': first['step_name'],
            'unit_name': first['unit_name'], 'product_name': first['product_name'],
            'process_name': first['process_name'], 'version': first['version'],
            'sequence_number': first['sequence_number'],
            'group_label': f"{first['product_name']} · {first['process_name'] or 'Production'}"
                           f" v{first['version']}",
            'travel': _summary([o['travel'] for o in members if o['travel'] is not None]),
            'process': _summary([o['process'] for o in members if o['process'] is not None]),
            'executions': len(members), 'over_count': len(over),
            'over_percent': (len(over) / len([o for o in members if o['assessable']]) * 100)
                            if any(o['assessable'] for o in members) else None,
            'ready_quantity': ready.get(key, 0),
        })
    rows.sort(key=lambda r: (r['group_label'], r['sequence_number']))
    return rows


def _bucket(moment, grain):
    if grain == 'month':
        return moment.date().replace(day=1).isoformat()
    monday = moment.date() - timedelta(days=moment.date().weekday())
    return monday.isoformat()


def _period_totals(observations):
    over = [o for o in observations if o['assessable'] and o['over_standard']]
    assessable = [o for o in observations if o['assessable']]
    return {
        'executions': len(observations),
        'travel': _summary([o['travel'] for o in observations if o['travel'] is not None]),
        'process': _summary([o['process'] for o in observations if o['process'] is not None]),
        'combined': _summary([o['combined'] for o in observations if o['combined'] is not None]),
        'over_percent': (len(over) / len(assessable) * 100) if assessable else None,
    }


def _trends(observations, grain):
    buckets = defaultdict(list)
    for observation in observations:
        buckets[_bucket(observation['completion_time'], grain)].append(observation)
    return [dict(_period_totals(members), period=period)
            for period, members in sorted(buckets.items())]


def _histogram(observations, step_id, metric, use_adjusted):
    """Counts per one-standard-deviation interval, with an optional fitted curve.

    The bars are one sample standard deviation wide and anchored on the mean, so the
    familiar plus/minus one sigma bands line up with bin edges.
    """
    if metric not in METRICS:
        raise ValueError('Choose travel, process or combined duration')
    selected = [o for o in observations if o['step_id'] == step_id and o[metric] is not None]
    if use_adjusted:
        selected = [o for o in selected if metric not in o['outlier_metrics']]
    values = sorted(o[metric] for o in selected)
    standards = {o['standard_minutes'] for o in selected if o['standard_minutes'] is not None}
    result = {
        'step_id': step_id, 'metric': metric, 'label': METRIC_LABELS[metric],
        'count': len(values), 'bins': [], 'curve': [], 'mean': None, 'median': None,
        # A note is an English template; the page translates it, then fills note_values.
        'stdev': None, 'note': None, 'note_values': {}, 'adjusted': bool(use_adjusted),
        # A standard applies only to process time, and only when every selected
        # execution shares one configured value.
        'standard': standards.pop() if metric == 'process' and len(standards) == 1 else None,
    }
    if not values:
        result['note'] = 'No completed executions match these filters.'
        return result
    mean = sum(values) / len(values)
    result.update(mean=mean, median=_quantile(values, 0.5))
    if len(values) < 2:
        result['note'] = 'Only one execution: a distribution needs more observations.'
        return result
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    stdev = sqrt(variance)
    result['stdev'] = stdev
    if stdev == 0:
        result['bins'] = [{'start': mean, 'end': mean, 'count': len(values), 'percent': 100.0}]
        result['note'] = 'Every execution took the same time, so the distribution has no width.'
        return result
    width = stdev
    lowest = floor((values[0] - mean) / width)
    highest = ceil((values[-1] - mean) / width)
    needed = max(1, highest - lowest)
    if needed > MAX_HISTOGRAM_BINS:
        # Keep the chart readable when a few extreme values stretch the range.
        width *= ceil(needed / MAX_HISTOGRAM_BINS)
        lowest = floor((values[0] - mean) / width)
        highest = ceil((values[-1] - mean) / width)
        result['note'] = ('Bars widened to {n} standard deviations so the '
                          'full range stays readable.')
        result['note_values'] = {'n': f'{width / stdev:.0f}'}
    edges = [mean + step * width for step in range(lowest, max(highest, lowest + 1) + 1)]
    counts = [0] * (len(edges) - 1)
    for value in values:
        index = min(int((value - edges[0]) // width), len(counts) - 1)
        counts[max(index, 0)] += 1
    result['bins'] = [{'start': edges[i], 'end': edges[i + 1], 'count': count,
                       'percent': count / len(values) * 100}
                      for i, count in enumerate(counts)]
    # Scale the fitted normal density to histogram counts: N x bin width x density.
    points = 120
    span = edges[-1] - edges[0]
    result['curve'] = [{'x': x, 'y': len(values) * width / (stdev * sqrt(2 * pi))
                        * exp(-0.5 * ((x - mean) / stdev) ** 2)}
                       for x in (edges[0] + span * i / points for i in range(points + 1))]
    skew = (sum(((value - mean) / stdev) ** 3 for value in values) / len(values))
    if abs(skew) > 1 and not result['note']:
        result['note'] = ('These durations are noticeably skewed, so the fitted normal curve '
                          'is only a rough reference.')
    return result


def _throughput(observations, order_rows, grain):
    """Per-step completions and finished products, counted without double-counting.

    Each completed execution is counted once for its own step, so a piece passing six
    steps contributes to six step counts and to exactly one finished-product count.
    """
    per_step = defaultdict(lambda: defaultdict(int))
    for observation in observations:
        per_step[_bucket(observation['completion_time'], grain)][
            (observation['step_id'], observation['step_name'])] += 1
    # A piece is finished when its last route step is complete.
    last = {}
    for observation in observations:
        key = observation['item_id']
        if key not in last or observation['sequence_number'] > last[key]['sequence_number']:
            last[key] = observation
    finished = defaultdict(int)
    for observation in last.values():
        finished[_bucket(observation['completion_time'], grain)] += 1
    orders = defaultdict(int)
    for row in order_rows:
        if row['order_completed']:
            orders[_bucket(row['order_completed'], grain)] += 1
    periods = sorted(set(per_step) | set(finished) | set(orders))
    return [{'period': period,
             'steps': [{'step_id': key[0], 'step_name': key[1], 'count': count}
                       for key, count in sorted(per_step[period].items(), key=lambda kv: kv[0][1])],
             'step_total': sum(per_step[period].values()),
             'finished_pieces': finished.get(period, 0),
             'completed_orders': orders.get(period, 0)} for period in periods]


def _lead_times(order_rows):
    """Order lead times and due-date delivery, separate from step-standard overruns."""
    completed = [r for r in order_rows if r['order_completed']]
    creation = [_minutes(r['order_completed'] - r['order_created']) for r in completed]
    production = [_minutes(r['order_completed'] - r['production_started'])
                  for r in completed if r['production_started']]
    dated = [r for r in completed if r['due_date']]
    on_time = [r for r in dated if r['order_completed'].date() <= r['due_date']]
    return {
        'completed_orders': len(completed),
        'creation_to_completion': _summary(creation),
        'production_to_completion': _summary(production),
        'no_recorded_start': len(completed) - len(production),
        'due_dated_orders': len(dated),
        'delivered_on_time': len(on_time),
        'on_time_percent': (len(on_time) / len(dated) * 100) if dated else None,
    }


def _at_risk(live, open_orders, now):
    """Live work, deliberately kept apart from completed-execution statistics."""
    running = []
    waiting = []
    for row in live:
        if row['start_time'] is not None:
            standard = row['standard_time_seconds']
            elapsed = max(0.0, _minutes(now - row['start_time']) - (row.get('paused_minutes') or 0.0))
            if standard and elapsed > standard / 60:
                running.append(dict(row, elapsed_minutes=elapsed, standard_minutes=standard / 60,
                                    excess_minutes=elapsed - standard / 60))
        elif row['predecessor_finished_at'] is not None and row['has_predecessor']:
            waiting.append(dict(row, travel_minutes=_minutes(now - row['predecessor_finished_at'])))
    running.sort(key=lambda r: r['excess_minutes'], reverse=True)
    waiting.sort(key=lambda r: r['travel_minutes'], reverse=True)
    today = now.date()
    overdue = [dict(r, days_late=(today - r['due_date']).days)
               for r in open_orders if r['due_date'] and r['due_date'] < today]
    overdue.sort(key=lambda r: r['days_late'], reverse=True)
    return {'running_over_standard': running[:50], 'running_count': len(running),
            'waiting_longest': waiting[:50], 'waiting_count': len(waiting),
            'overdue_orders': overdue[:50], 'overdue_count': len(overdue)}


def _data_quality(observations, quality_counts, pauses=()):
    """Surface gaps instead of letting them become silent zeros."""
    missing_travel = [o for o in observations if o['has_predecessor'] and o['travel'] is None]
    return {
        'paused_executions': sum(o['paused'] > 0 for o in observations),
        'paused_minutes': sum(o['paused'] for o in observations),
        'pauses_by_reason': [dict(r, minutes=float(r['minutes'] or 0)) for r in pauses],
        'executions': len(observations),
        'missing_travel_timestamp': len(missing_travel),
        'missing_standard': sum(not o['assessable'] for o in observations),
        'skipped_executions': quality_counts['skipped'],
        'cancelled_executions': quality_counts['cancelled'],
        'cancelled_orders': quality_counts['cancelled_orders'],
    }


def _record(observation):
    """One drill-down/export row, including its outlier status and standard."""
    return {
        'order_number': observation['order_number'],
        'work_order_id': observation['work_order_id'],
        'item_id': observation['item_id'],
        'product_name': observation['product_name'],
        'process': f"{observation['process_name'] or 'Production'} v{observation['version']}",
        'step_name': observation['step_name'],
        'sequence_number': observation['sequence_number'],
        'unit_name': observation['unit_name'],
        'contractor_name': observation['contractor_name'],
        'predecessor_finished_at': observation['predecessor_finished_at'],
        'start_time': observation['start_time'],
        'completion_time': observation['completion_time'],
        'travel_minutes': observation['travel'],
        'process_minutes': observation['process'],
        'combined_minutes': observation['combined'],
        'standard_minutes': observation['standard_minutes'],
        'excess_minutes': observation['excess_minutes'],
        'percent_over': observation['percent_over'],
        'severity': observation['severity'],
        'over_standard': observation['over_standard'],
        'outlier': observation['is_outlier'],
        'outlier_metrics': ', '.join(observation['outlier_metrics']),
    }


RECORD_COLUMNS = (
    ('order_number', 'Work order'), ('product_name', 'Product'), ('process', 'Process'),
    ('step_name', 'Step'), ('sequence_number', 'Position'), ('unit_name', 'Production unit'),
    ('contractor_name', 'Contractor'), ('item_id', 'Piece'),
    ('predecessor_finished_at', 'Previous step finished'), ('start_time', 'Started'),
    ('completion_time', 'Completed'), ('travel_minutes', 'Travel (min)'),
    ('process_minutes', 'Process (min)'), ('combined_minutes', 'Combined (min)'),
    ('standard_minutes', 'Standard (min)'), ('excess_minutes', 'Excess (min)'),
    ('percent_over', 'Over standard (%)'), ('severity', 'Severity'),
    ('over_standard', 'Over standard'), ('outlier', 'Outlier'), ('outlier_metrics', 'Outlier metrics'),
)


# Statistics are the heaviest read: every figure comes from all scoped executions. The rows
# behind one selection are kept for a minute, so switching tabs, turning record pages,
# drilling down or exporting, and colleagues looking at the same scope, reuse them.
CACHE_SECONDS = 60
CACHE_ENTRIES = 32
_cache = {}
_cache_lock = threading.Lock()


def clear_cache():
    with _cache_lock:
        _cache.clear()


def _dataset(conn, pool, actor, filters):
    """Scope, filters and every row the statistics are derived from, for one selection.

    The cache key holds the database pool, the resolved unit scope and the effective filters
    (including the caller's own id for "orders I created"), so callers who may see different
    records never share an entry. The permission check itself runs on every call, before the lookup.
    """
    unit_ids, label = resolve_scope(conn, actor)
    cleaned = _clean_filters(filters)
    query_filters = {key: cleaned[key] for key in _FILTER_IDS if key in cleaned}
    if cleaned.get('my_orders'):
        query_filters['created_by'] = actor.employee_id
    # A supervisor's scope already is their own units; only a wider scope narrows here.
    if cleaned.get('my_units') and unit_ids is None:
        unit_ids = db.get_supervised_unit_ids(conn, actor.employee_id)
    key = (id(pool), None if unit_ids is None else tuple(sorted(unit_ids)), tuple(sorted(query_filters.items())),
           cleaned.get('date_from'), cleaned.get('date_to'))
    clock = monotonic()
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None and hit[0] > clock:
        return dict(hit[1], label=label, cleaned=cleaned)
    completed_from, completed_to = _bounds(cleaned)
    scoped = dict(scope_unit_ids=unit_ids, filters=query_filters)
    period = dict(completed_from=completed_from, completed_to=completed_to)
    observations = [_observe(row) for row in db.get_execution_observations(conn, **scoped, **period)]
    _flag_outliers(observations)
    data = dict(unit_ids=unit_ids, observations=observations,
                live=db.get_live_executions(conn, **scoped),
                open_orders=db.get_open_orders(conn, **scoped),
                order_rows=db.get_order_durations(conn, **scoped, **period),
                options=db.get_filter_options(conn, scope_unit_ids=unit_ids, **period),
                quality_counts=db.get_quality_counts(conn, **scoped, **period),
                pauses=db.get_pause_totals(conn, **scoped, **period),
                now=conn.execute('SELECT clock_timestamp()').fetchone()[0], previous=None)
    # A closed date range is compared with the equally long period just before it.
    if cleaned.get('date_from') and cleaned.get('date_to'):
        length = cleaned['date_to'] - cleaned['date_from'] + timedelta(days=1)
        earlier = [_observe(row) for row in db.get_execution_observations(
            conn, **scoped, completed_from=completed_from - length, completed_to=completed_from)]
        data['previous'] = dict(_period_totals(earlier),
                                date_from=(cleaned['date_from'] - length).isoformat(),
                                date_to=(cleaned['date_from'] - timedelta(days=1)).isoformat())
    with _cache_lock:
        for stale in [k for k, (expires, _) in _cache.items() if expires <= clock]:
            del _cache[stale]
        if len(_cache) >= CACHE_ENTRIES:
            del _cache[min(_cache, key=lambda k: _cache[k][0])]
        _cache[key] = (clock + CACHE_SECONDS, data)
    return dict(data, label=label, cleaned=cleaned)


RECORDS_PAGE_SIZE = 50


def get_statistics_service(actor, pool, *, distribution_step_id=None,
                           distribution_metric='process', distribution_adjusted=True,
                           grain='week', **filters):
    """Every statistics section for one filter selection, in minutes.

    Historical sections count executions *completed* within the selected period. The
    live section is deliberately unfiltered by date and says so in its own labels. The
    figures may be up to a minute old; ``generated_at`` says when they were read.
    """
    if grain not in ('week', 'month'):
        raise ValueError('Choose a weekly or monthly grain')
    with pool.connection() as conn, conn.transaction():
        data = _dataset(conn, pool, actor, filters)
    observations, cleaned = data['observations'], data['cleaned']
    steps = sorted({(o['step_id'], o['step_name']) for o in observations}, key=lambda s: s[1])
    if distribution_step_id is None and steps:
        distribution_step_id = steps[0][0]
    return {
        'scope_label': data['label'],
        'scope_unit_ids': data['unit_ids'],
        'filters': {k: (v.isoformat() if isinstance(v, date) else v) for k, v in cleaned.items()},
        'period_label': _period_label(cleaned),
        'timing': _timing_block(observations),
        'over_standard': _over_standard(observations),
        'bottlenecks': _bottlenecks(observations, data['live']),
        'trends': _trends(observations, grain),
        'previous_period': data['previous'],
        'throughput': _throughput(observations, data['order_rows'], grain),
        'lead_times': _lead_times(data['order_rows']),
        'at_risk': _at_risk(data['live'], data['open_orders'], data['now']),
        'data_quality': _data_quality(observations, data['quality_counts'], data['pauses']),
        'distribution': _histogram(observations, distribution_step_id, distribution_metric,
                                   distribution_adjusted) if distribution_step_id else None,
        'distribution_steps': [{'id': key, 'name': name} for key, name in steps],
        # A template, like the distribution note, so the page can translate it.
        'outlier_rule': ('Tukey upper fence: Q3 + {multiplier} x IQR, computed for each '
                         'process version and step with at least {minimum} observations. '
                         'Excluded executions are kept and can be inspected.'),
        'outlier_values': {'multiplier': OUTLIER_MULTIPLIER, 'minimum': MIN_OUTLIER_SAMPLE},
        'options': data['options'],
        'grain': grain,
        # The first page only; the records tab reads further pages with get_records_service.
        'records': [_record(o) for o in observations[:RECORDS_PAGE_SIZE]],
        'record_total': len(observations),
        'generated_at': data['now'],
    }


def _period_label(cleaned):
    start, end = cleaned.get('date_from'), cleaned.get('date_to')
    if start and end:
        return f'Executions completed between {start} and {end}'
    if start:
        return f'Executions completed from {start}'
    if end:
        return f'Executions completed up to {end}'
    return 'Executions completed at any time'


def get_records_service(actor, pool, *, only_outliers=False, only_over_standard=False,
                        step_id=None, offset=0, limit=None, **filters):
    """Contributing records behind a metric or chart, under the same access rules.

    Excluded outliers are always inspectable; nothing is deleted or hidden. ``offset`` and
    ``limit`` select a page; the rows come from the same minute-long cache as the page.
    """
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError('Invalid page position. Reload the records.')
    with pool.connection() as conn, conn.transaction():
        observations = _dataset(conn, pool, actor, filters)['observations']
    if step_id is not None:
        observations = [o for o in observations if o['step_id'] == step_id]
    if only_outliers:
        observations = [o for o in observations if o['is_outlier']]
    if only_over_standard:
        observations = [o for o in observations if o['assessable'] and o['over_standard']]
    observations = observations[offset:offset + limit] if limit else observations[offset:]
    return [_record(o) for o in observations]


def export_records_csv(actor, pool, **filters):
    """Filtered export using the same scope, filters and calculations as the page."""
    import csv
    import io

    records = get_records_service(actor, pool, **filters)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for _, label in RECORD_COLUMNS])
    for record in records:
        writer.writerow([_csv_value(record[key]) for key, _ in RECORD_COLUMNS])
    return buffer.getvalue()


# A spreadsheet runs a cell starting with one of these as a formula, and CSV quoting does
# not stop it. Order, product and contractor names come from other users, so such text is
# exported with a leading apostrophe, which spreadsheets read as "this is literal text".
FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _csv_value(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, float):
        return f'{value:.2f}'
    if isinstance(value, datetime):
        return value.isoformat(sep=' ', timespec='seconds')
    return value
