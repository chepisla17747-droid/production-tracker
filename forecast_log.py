"""Record the AI's finish-time forecasts during the pilot, then measure how accurate they were.

Run from the project folder, next to main.py, while the website is running:

    .venv\\Scripts\\python.exe forecast_log.py              # record every 30 minutes
    .venv\\Scripts\\python.exe forecast_log.py --every 15   # record every 15 minutes
    .venv\\Scripts\\python.exe forecast_log.py report       # accuracy report

Recording writes forecast_log.csv: for each open order and each unfinished step, the
expected end the website shows ("ai") and, for comparison, the expected end from
Standard Time alone ("standard"). The report compares those with the moment each step
actually finished and writes forecast_report.csv. Both files open in Excel.
Nothing in the database is changed.
"""
import argparse
import csv
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.database import read_database_config  # noqa: E402
from backend.operations import eta_operations, overview_operations  # noqa: E402
from backend.service.eta_service import (  # noqa: E402
    SHIFT_BLOCKS, WORK_DAYS, forecast_order, learn_profiles, working_minutes_between)

LOG = ROOT / 'forecast_log.csv'
REPORT = ROOT / 'forecast_report.csv'
LOG_FIELDS = ['logged_at', 'method', 'order_number', 'product', 'sequence', 'step', 'unit',
              'predicted_end', 'order_finish', 'due_date', 'basis']
# Forecasts made this close to the real finish are left out: a few minutes' error would
# look like a huge percentage.
MIN_LEAD_MINUTES = 15


def connect():
    s = read_database_config(ROOT / '.env.app')
    return psycopg.connect(host=s['DB_HOST'], port=s['DB_PORT'], dbname=s['DB_NAME'],
                           user=s['DB_USER'], password=s['DB_PASSWORD'], connect_timeout=5)


def stamp(moment):
    return moment.astimezone().strftime('%Y-%m-%d %H:%M') if moment else ''


def parse(text):
    return datetime.strptime(text, '%Y-%m-%d %H:%M').astimezone() if text else None


# ----------------------------------------------------------------------------- recording

def snapshot(conn):
    """Rows for the log: every unfinished step of every open order, AI and Standard Time."""
    now = datetime.now().astimezone()
    orders = overview_operations.get_orders(conn, open_only=True)
    if not orders:
        return []
    by_order = defaultdict(list)
    for row in overview_operations.get_order_steps(conn, [o['work_order_id'] for o in orders]):
        by_order[row['work_order_id']].append(row)
    standards = {r['process_step_id']: (r['standard_time_seconds'] / 60 if r['standard_time_seconds'] else None)
                 for rows in by_order.values() for r in rows}
    learned = learn_profiles(eta_operations.get_step_history(conn, list(standards)), standards)
    busy = eta_operations.get_busy_units(conn)
    out = []
    for order in orders:
        rows = by_order.get(order['work_order_id'], [])
        names = {r['sequence_number']: (r['name'], r['unit_name'], r['product_name']) for r in rows}
        for method, profiles in (('ai', learned), ('standard', {})):
            forecast = forecast_order(order, rows, now, profiles, busy)
            if not forecast:
                continue
            for step in forecast['step_finish']:
                name, unit, product = names[step['sequence_number']]
                out.append({'logged_at': stamp(now), 'method': method,
                            'order_number': order['order_number'], 'product': product,
                            'sequence': step['sequence_number'], 'step': name, 'unit': unit,
                            'predicted_end': stamp(step['finish']), 'order_finish': stamp(forecast['finish']),
                            'due_date': order['due_date'] or '', 'basis': forecast['basis']})
    return out


def working_now():
    now = datetime.now()
    return now.weekday() in WORK_DAYS and any(a <= now.time() < b for a, b in SHIFT_BLOCKS)


def record(every):
    print(f'Recording forecasts every {every} minutes into {LOG.name}. Press Ctrl+C to stop.')
    while True:
        if not working_now():
            # Outside the shift nothing moves; recording then would only repeat itself.
            time.sleep(60)
            continue
        try:
            with connect() as conn:
                rows = snapshot(conn)
            new = not LOG.exists()
            with LOG.open('a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, LOG_FIELDS)
                if new:
                    writer.writeheader()
                writer.writerows(rows)
            print(f'{stamp(datetime.now().astimezone())}  saved {len(rows)} forecasts')
        except Exception as error:  # keep recording through a dropped connection
            print(f'{stamp(datetime.now().astimezone())}  could not record: {error}')
        time.sleep(every * 60)


# ------------------------------------------------------------------------------- report

def actual_step_ends(conn, order_numbers):
    """(order number, sequence) -> when the step's last unscrapped piece finished."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT orders.order_number, link.sequence_number,
                   bool_and(COALESCE(execution.completion_time, execution.skipped_at) IS NOT NULL) AS done,
                   max(COALESCE(execution.completion_time, execution.skipped_at)) AS finished
            FROM public.work_order orders
            JOIN public.product_instance item ON item.work_order_id = orders.id AND item.scrapped_at IS NULL
            JOIN public.process_definition_process_step link ON link.process_definition_id = item.process_def_id
            LEFT JOIN public.process_step_execution execution
              ON execution.product_instance_id = item.id AND execution.process_step_id = link.process_step_id
            WHERE orders.order_number = ANY(%s) AND NOT orders.is_cancelled
            GROUP BY orders.order_number, link.sequence_number""", (list(order_numbers),))
        return {(r['order_number'], r['sequence_number']): r['finished'] for r in cur.fetchall() if r['done']}


def report():
    if not LOG.exists():
        sys.exit(f'{LOG.name} not found: run the recorder during the pilot first.')
    with LOG.open(encoding='utf-8-sig') as f:
        logged = list(csv.DictReader(f))
    with connect() as conn:
        actual = actual_step_ends(conn, {r['order_number'] for r in logged})
    results = []
    for r in logged:
        end = actual.get((r['order_number'], int(r['sequence'])))
        made, predicted = parse(r['logged_at']), parse(r['predicted_end'])
        if end is None or made >= end:
            continue  # step not finished yet, or the forecast came after it finished
        lead = working_minutes_between(made, end)
        if lead < MIN_LEAD_MINUTES:
            continue
        error = working_minutes_between(min(predicted, end), max(predicted, end))
        results.append({**r, 'actual_end': stamp(end), 'lead_hours': round(lead / 60, 2),
                        'error_hours': round(error / 60, 2),
                        'accuracy_pct': round(max(0.0, 100 - 100 * error / lead), 1)})
    if not results:
        sys.exit('No finished steps to compare yet.')
    with REPORT.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f'Wrote {len(results)} comparisons to {REPORT.name}\n')
    for method, label in (('ai', 'AI (website)'), ('standard', 'Standard Time only')):
        rows = [r for r in results if r['method'] == method]
        if rows:
            steps = {(r['order_number'], r['sequence']) for r in rows}
            print(f'{label:20} accuracy {mean(r["accuracy_pct"] for r in rows):5.1f}%   '
                  f'MAE {mean(r["error_hours"] for r in rows):.2f} working hours   '
                  f'n = {len(rows)} forecasts on {len(steps)} steps')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('mode', nargs='?', default='record', choices=['record', 'report'])
    parser.add_argument('--every', type=int, default=30, help='minutes between recordings')
    args = parser.parse_args()
    report() if args.mode == 'report' else record(args.every)
