"""Manager factory overview, order summary panel and the per-order step page.

Order status, week and progress rules live in `backend.service.overview_service`.
"""
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs

from dash import ALL, MATCH, Input, Output, State, ctx, dcc, html, no_update

from frontend.auth import protect_callback
from frontend.login import top_bar
from frontend.common import (HANDLED_ERRORS, caller, clicked, duration, failure, notice,
                             product_picture, scrap_badge)
from backend.service.overview_service import (
    get_manager_alerts_service, get_order_detail_service, get_order_summary_service,
    get_overview_service,
)
from backend.service.supervisor_service import reverse_action_service
from frontend.i18n import translate

# Supervisors share this page; the service narrows what they see to their units.
ROLES = ('manager', 'supervisor')
STATUS_LABELS = {'not_started': 'Not started', 'in_process': 'In process',
                 'delayed': 'Delayed', 'complete': 'Complete'}
STEP_LABELS = {'waiting': 'Waiting', 'ready': 'Ready', 'in_process': 'In process',
               'partial': 'Partly finished', 'completed': 'Finished'}


def _parse(value):
    """Values arrive as Python objects from services or ISO strings from a store."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value) if 'T' in value or ' ' in value else date.fromisoformat(value)
        except ValueError:
            return value
    return value


def when(value, empty='N/A'):
    value = _parse(value)
    if value is None:
        return empty
    if isinstance(value, datetime):
        return value.astimezone().strftime('%d %b %Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d %b %Y')
    return str(value)


def week_label(data):
    start, end = date.fromisoformat(data['week_start']), date.fromisoformat(data['week_end'])
    label = f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    return label + (' · this week' if data['is_current_week'] else '')


def status_badge(status):
    return html.Span(STATUS_LABELS[status], className=f'order-status {status}')


def step_line(card):
    """The card's current process step, e.g. Welding · 4 / 20 pieces."""
    step = card['current_step']
    if card['status'] == 'complete' or (card['steps'] and step is None):
        return 'All steps finished', f"{card['pieces']} pieces"
    if step is None:
        return 'No process steps', ''
    # Units are often named after their step; avoid "Cutting · Cutting".
    unit = '' if step['unit_name'] == step['name'] else f" · {step['unit_name']}"
    return f"{step['name']}{unit}", f"{step['finished']} / {step['total']} pieces"


def forecast_line(forecast):
    """Expected finish of an open order, e.g. "Expected finish 14 Oct 2026 15:30 · 2 days late"."""
    if not forecast:
        return None
    text = translate('Expected finish {when}').format(when=when(forecast['finish']))
    if not forecast['on_time']:
        text += translate(' · {n} days late').format(n=forecast['late_days'])
    return html.Span(text, className='order-forecast late' if not forecast['on_time'] else 'order-forecast',
                     title=translate(FORECAST_BASIS[forecast['basis']]))


FORECAST_BASIS = {
    'history': 'Forecast from recent production at each step, in working hours.',
    'standard': 'Forecast from standard step times, in working hours: too little history yet.',
    'mixed': 'Forecast from recent production where there is enough history, and standard '
             'step times elsewhere, in working hours.',
}


def order_card(card, selected):
    label, count = step_line(card)
    return html.Button([
        html.Div([html.Strong(card['order_number']), status_badge(card['status']),
                  scrap_badge(card.get('scrapped'))], className='part-card-top'),
        html.Div([product_picture(card['product_type_id'], card['product_image_version']), html.Div([
            html.H3(card['product_name'] or 'No product'),
            html.P(card['contractor_name'], className='planner-muted'),
        ])], className='part-product'),
        html.Div([html.Span(label), html.Strong(f"{card['percent']}%")], className='part-progress-label'),
        html.Progress(value=card['percent'], max=100, className=f"order-progress {card['status']}",
                      **{'aria-label': 'Progress of the current step'}),
        html.Div([html.Span(count),
                  html.Span(f"Due {when(card['due_date'])}" if card['due_date'] else 'No due date')],
                 className='part-card-footer order-card-footer'),
        forecast_line(card.get('forecast')),
    ], id={'type': 'overview-card', 'index': card['work_order_id']}, n_clicks=0,
       className='part-card selected' if card['work_order_id'] == selected else 'part-card',
       # The card's visible text is its accessible name; pressed marks the chosen order.
       **{'aria-pressed': 'true' if card['work_order_id'] == selected else 'false'})


def order_facts(summary):
    process = f"{summary['process_name'] or 'Production'} v{summary['version']}" if summary['version'] else '—'
    rows = (('Product', summary['product_name'] or '—'), ('Contractor', summary['contractor_name']),
            ('Process', process), ('Pieces', summary['pieces']),
            ('Created', when(summary['creation_time'])), ('Planned start', when(summary['start_date'])),
            ('Due', when(summary['due_date'], 'No due date')),
            ('Completed', when(summary['completion_time'], 'Not yet')))
    if summary['completion_time'] is None:
        forecast = summary.get('forecast')
        rows += (('Expected finish', forecast_line(forecast) if forecast else 'Not available'),)
    return html.Dl([item for name, value in rows for item in (html.Dt(name), html.Dd(value))],
                   className='order-facts')


def order_summary(summary, link=True):
    """Shared by the manager panel and the Supervisor part detail (without the link)."""
    steps = [html.Li([html.Span(f"{step['sequence_number']}. {step['name']}"),
                      html.Span([f"{step['finished']} / {step['total']}",
                                 scrap_badge(step.get('scrapped'))])],
                     className='current' if summary['current_step'] and
                     step['sequence_number'] == summary['current_step']['sequence_number'] else None)
             for step in summary['steps']]
    return html.Div([
        html.Div([html.H3(f"Work order {summary['order_number']}"), status_badge(summary['status'])],
                 className='order-summary-top'),
        order_facts(summary),
        html.H4('Pieces finished per process step'),
        html.Ul(steps, className='order-step-counts') if steps else
        html.P('This order has no process steps.', className='planner-muted'),
        dcc.Link('Open order →', href=f"/manager?order={summary['work_order_id']}",
                 className='planner-secondary order-open-link') if link else None,
    ], className='order-summary')


ACTION_LABELS = {'start': 'Started', 'complete': 'Completed', 'skip': 'Already prepared',
                 'scrap': 'Scrapped'}


def action_row(action, can_correct):
    """One recorded floor action; a manager may reverse it once, giving a reason."""
    def ident(kind):
        return {'type': f'action-{kind}', 'index': action['request_id']}
    if action['reversed_at']:
        state = html.Span(translate('Reversed by {name}: {reason}').format(
            name=action['reversed_by_name'], reason=action['reversal_reason']), className='planner-muted')
    elif not action['reversible']:
        state = html.Span('Recorded before corrections were possible', className='planner-muted')
    elif can_correct:
        state = html.Div([
            dcc.Input(id=ident('reason'), placeholder='Reason for reversing', maxLength=500,
                      className='form-input'),
            html.Button('Reverse', id=ident('reverse'), className='planner-text-button danger'),
            html.Div(id=ident('message'), **{'aria-live': 'polite'}),
        ], className='action-reverse')
    else:
        state = ''
    return html.Tr([html.Td(when(action['created_at'])), html.Td(action['supervisor_name']),
                    html.Td(f"{action['sequence_number']}. {action['step_name']}"),
                    html.Td(ACTION_LABELS[action['action']]), html.Td(action['quantity']),
                    html.Td(state)], className='stat-outlier-row' if action['reversed_at'] else None)


def order_page(detail):
    header = html.Tr([html.Th(label) for label in (
        '#', 'Process step', 'Unit', 'Status', 'Pieces finished', 'Start', 'End', 'Elapsed',
        'Expected end')])
    body = [html.Tr([
        html.Td(step['sequence_number']), html.Td(step['name']), html.Td(step['unit_name']),
        html.Td(STEP_LABELS.get(step['status'], step['status'])),
        html.Td(f"{step['finished']} / {step['total']}"
                + (f" ({step['skipped']} already prepared)" if step['skipped'] else '')),
        html.Td(when(step['started_at'])),
        html.Td(when(step['finished_at'], 'Not finished' if step['started_at'] else 'N/A')),
        html.Td('N/A' if step['elapsed_seconds'] is None
                else (duration(step['elapsed_seconds']) or '0s')
                + ('' if step['finished_at'] else ' so far')),
        html.Td('—' if step['finished_at'] else when(step.get('expected_finish'), 'N/A')),
    ]) for step in detail['step_details']]
    return html.Div([
        dcc.Link('← Back to overview', href='/manager', className='planner-text-button'),
        html.Div([html.H2(f"Work order {detail['order_number']}"), status_badge(detail['status'])],
                 className='order-summary-top'),
        html.Div(order_facts(detail), className='info-card'),
        html.Div([
            html.H2('Process steps'),
            html.Div(html.Table([html.Thead(header), html.Tbody(body)], className='stat-table'),
                     className='stat-scroll') if body else
            html.P('This order has no process steps.', className='planner-muted'),
            html.P('Start is the first piece started at the step; end is when its last piece '
                   'finished. Elapsed time is clock time between them, including waiting between '
                   'batches. Already-prepared pieces count as finished without processing time.',
                   className='planner-muted'),
            html.P('Expected end is a forecast in working hours (08:00–17:00, Monday to Friday, '
                   'lunch break excluded), learned from recent production at each step and '
                   'using the standard time where there is too little history.',
                   className='planner-muted'),
        ], className='info-card'),
        html.Div([
            html.H2('Recorded floor actions'),
            html.P('Reversing undoes exactly the pieces that action changed, and is refused '
                   'when later work depends on them. The reason is kept.', className='planner-muted'),
            html.Div(html.Table([
                html.Thead(html.Tr([html.Th(label) for label in (
                    'When', 'Supervisor', 'Process step', 'Action', 'Pieces', 'Correction')])),
                html.Tbody([action_row(a, detail['can_correct']) for a in detail['actions']])],
                className='stat-table'), className='stat-scroll') if detail['actions'] else
            html.P('No floor actions have been recorded for this order yet.', className='planner-muted'),
        ], className='info-card'),
    ], className='order-page')


def manager_page(actor=None):
    manager = actor is None or 'manager' in actor.allowed_roles
    return html.Div(className='planner-page persistent-planner manager-page', children=[
        top_bar('Overview', actor, 'manager'),
        html.Div(className='planner-content', children=[
            html.Div([html.Div([html.Span('Manager console' if manager else 'Supervisor console',
                                          className='planner-muted'),
                                html.H1('Factory overview')]),
                      html.Span('Manager' if manager else 'Supervisor', className='planner-badge')],
                     className='planner-heading'),
            None if manager else html.P('Only work orders with a step in a unit you supervise '
                                        'are shown, and the counts cover those orders only.',
                                        className='planner-muted overview-scope'),
            html.Div(id='overview-message', **{'aria-live': 'polite'}),
            html.Div(id='overview-alerts'),
            html.Div(id='overview-list-section', children=[
                html.Div([
                    html.Button('‹ Previous week', id='overview-prev-week', className='planner-text-button'),
                    html.Strong(id='overview-week-label'),
                    html.Button('Next week ›', id='overview-next-week', className='planner-text-button'),
                ], className='overview-week'),
                dcc.Loading(html.Div(id='overview-tiles', className='overview-tiles'), type='default'),
                html.Div([
                    html.Div([
                        html.Div([html.H2('Work orders'), html.Span(id='overview-total', className='planner-badge')],
                                 className='order-summary-top'),
                        dcc.Input(id='overview-search', placeholder='Search order, product or contractor',
                                  debounce=True, className='form-input', type='search'),
                        dcc.RadioItems(id='overview-status', value='all', inline=True,
                                       className='supervisor-statuses overview-statuses',
                                       options=[{'label': 'All', 'value': 'all'}]),
                        html.Div(id='overview-cards', className='part-list'),
                        html.Div([
                            html.Button('‹ Previous', id='overview-page-prev', className='planner-text-button'),
                            html.Span(id='overview-page-label', className='planner-muted'),
                            html.Button('Next ›', id='overview-page-next', className='planner-text-button'),
                        ], className='overview-pages'),
                    ], className='info-card'),
                    html.Div(id='overview-summary', className='info-card part-detail', children=[
                        html.H2('Select a work order'),
                        html.P('Choose an order to see its details and progress per process step.',
                               className='planner-muted')]),
                ], className='supervisor-grid'),
            ]),
            html.Div(id='overview-order-section', style={'display': 'none'}),
        ]),
        dcc.Store(id='overview-week'), dcc.Store(id='overview-page', data=1),
        dcc.Store(id='overview-data'), dcc.Store(id='overview-selected'), dcc.Store(id='overview-scrolled'),
        dcc.Interval(id='overview-refresh', interval=60000),
    ])


ALERT_TEXT = {
    'delayed': '{order} is {days} days past its due date.',
    'forecast': '{order} is expected to finish {days} days after its due date.',
    'request': '{quantity} pieces scrapped at {step} on {order}: {request}.',
    'pause': '{step} on {order} has been paused for {minutes} minutes ({reason}).',
    'slow': '{quantity} pieces at {step} on {order} have run more than twice their standard time.',
}
REQUEST_TEXT = {'replace': 'replacement pieces requested', 'review': 'review requested'}
ALERT_TAGS = {'delayed': 'Delayed', 'forecast': 'At risk', 'request': 'Scrap', 'pause': 'Long pause', 'slow': 'Slow'}


def alerts_panel(alerts):
    """Needs attention: every open problem, each linking to its order page."""
    from frontend.supervisor import PAUSE_REASONS
    if not alerts:
        return html.Div([html.H2('Needs attention'),
                         html.P('Nothing needs attention right now.', className='planner-muted')],
                        className='info-card alerts-card')
    items = []
    for alert in alerts:
        values = dict(alert, order=alert['order_number'])
        if alert['kind'] == 'request':
            values['request'] = translate(REQUEST_TEXT[alert['request']])
        if alert['kind'] == 'pause':
            values['reason'] = translate(PAUSE_REASONS[alert['reason']])
        items.append(html.Li([
            html.Span(ALERT_TAGS[alert['kind']], className=f"alert-tag {alert['kind']}"),
            dcc.Link(translate(ALERT_TEXT[alert['kind']]).format(**values),
                     href=f"/manager?order={alert['order_id']}"),
        ]))
    return html.Details([
        html.Summary(html.H2(translate('Needs attention ({n})').format(n=len(alerts)))),
        html.Ul(items, className='alert-list'),
    ], open=True, className='info-card alerts-card')


def _order_id(search):
    values = parse_qs((search or '').lstrip('?')).get('order', [])
    if not values:
        return None
    try:
        value = int(values[0])
    except ValueError:
        return 0
    return value if value > 0 else 0


def register_callbacks(app):

    @app.callback(Output('overview-week', 'data'),
                  Input('overview-prev-week', 'n_clicks'), Input('overview-next-week', 'n_clicks'),
                  State('overview-data', 'data'), prevent_initial_call=True)
    @protect_callback(*ROLES)
    def change_week(previous, following, data):
        if not data:
            return no_update
        shift = -7 if ctx.triggered_id == 'overview-prev-week' else 7
        if shift > 0 and data['is_current_week']:
            return no_update
        return (date.fromisoformat(data['week_start']) + timedelta(days=shift)).isoformat()

    @app.callback(Output('overview-page', 'data'),
                  Input('overview-page-prev', 'n_clicks'), Input('overview-page-next', 'n_clicks'),
                  Input('overview-search', 'value'), Input('overview-status', 'value'),
                  Input('overview-week', 'data'), State('overview-data', 'data'),
                  prevent_initial_call=True)
    @protect_callback(*ROLES)
    def change_page(previous, following, search, status, week, data):
        # Changing any filter starts again at the first page.
        if ctx.triggered_id not in ('overview-page-prev', 'overview-page-next') or not data:
            return 1
        step = -1 if ctx.triggered_id == 'overview-page-prev' else 1
        return min(max(1, data['page'] + step), data['pages'])

    @app.callback(Output('overview-data', 'data'), Output('overview-message', 'children'),
                  Input('overview-week', 'data'), Input('overview-page', 'data'),
                  Input('overview-search', 'value'), Input('overview-status', 'value'),
                  Input('overview-refresh', 'n_intervals'))
    @protect_callback(*ROLES)
    def load(week, page, search, status, _tick):
        try:
            return get_overview_service(*caller(app), week_start=week, page=page or 1,
                                        search=search or '', status=status or 'all'), ''
        except HANDLED_ERRORS as exc:
            return None, failure(exc)

    @app.callback(Output('overview-tiles', 'children'), Output('overview-week-label', 'children'),
                  Output('overview-next-week', 'disabled'), Output('overview-cards', 'children'),
                  Output('overview-total', 'children'), Output('overview-status', 'options'),
                  Output('overview-page-label', 'children'), Output('overview-page-prev', 'disabled'),
                  Output('overview-page-next', 'disabled'),
                  Input('overview-data', 'data'), Input('overview-selected', 'data'))
    @protect_callback(*ROLES)
    def render(data, selected):
        if not data:
            return ([], '', True, html.P('The overview is unavailable. Retry shortly.', className='planner-muted'),
                    '', [{'label': 'All', 'value': 'all'}], '', True, True)
        counts = data['counts']
        tiles = [html.Div([html.Strong(counts[key]), html.Span(label)], className=f'overview-tile {key}')
                 for key, label in (('complete', 'Complete'), ('in_process', 'In process'), ('delayed', 'Delayed'))]
        chips = data['chips']
        options = [{'label': f"All ({chips['all']})", 'value': 'all'}] + [
            {'label': f"{label} ({chips[key]})", 'value': key} for key, label in STATUS_LABELS.items()]
        cards = [order_card(card, selected) for card in data['orders']] or html.P(
            'No work orders match this week and these filters.', className='planner-muted overview-empty')
        pages = (f"Showing {data['first']}–{data['last']} of {data['total']} orders"
                 if data['total'] else 'No orders to show')
        return (tiles, week_label(data), data['is_current_week'], cards, f"{data['total']} total",
                options, pages, data['page'] <= 1, data['page'] >= data['pages'])

    @app.callback(Output('overview-selected', 'data'),
                  Input({'type': 'overview-card', 'index': ALL}, 'n_clicks'), prevent_initial_call=True)
    @protect_callback(*ROLES)
    def select(clicks):
        if not clicked():
            return no_update
        return ctx.triggered_id['index']

    @app.callback(Output('overview-summary', 'children'), Input('overview-selected', 'data'),
                  prevent_initial_call=True)
    @protect_callback(*ROLES)
    def summary(order_id):
        if not order_id:
            return no_update
        try:
            summary = get_order_summary_service(*caller(app), order_id)
            return order_summary(summary, link=summary['can_open_order'])
        except HANDLED_ERRORS as exc:
            return failure(exc)

    # On phones the summary sits below the list; bring it into view after a card tap.
    app.clientside_callback("""function(children) {
        const panel = document.getElementById('overview-summary');
        if (panel && window.innerWidth <= 720 && panel.querySelector('.order-summary')) {
            panel.scrollIntoView({behavior: 'smooth', block: 'start'});
        }
        return window.dash_clientside.no_update;
    }""", Output('overview-scrolled', 'data'), Input('overview-summary', 'children'),
        prevent_initial_call=True)

    @app.callback(Output('overview-list-section', 'style'), Output('overview-order-section', 'style'),
                  Output('overview-order-section', 'children'), Input('url', 'search'))
    @protect_callback(*ROLES)
    def show_order(search):
        order_id = _order_id(search)
        if order_id is None:
            return {}, {'display': 'none'}, []
        back = dcc.Link('← Back to overview', href='/manager', className='planner-text-button')
        if order_id == 0:
            return {'display': 'none'}, {}, [back, notice('This work order does not exist or was cancelled.', True)]
        try:
            return {'display': 'none'}, {}, order_page(get_order_detail_service(*caller(app), order_id))
        except HANDLED_ERRORS as exc:
            return {'display': 'none'}, {}, [back, failure(exc)]

    @app.callback(Output({'type': 'action-message', 'index': MATCH}, 'children'),
                  Output({'type': 'action-reverse', 'index': MATCH}, 'disabled'),
                  Input({'type': 'action-reverse', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'action-reverse', 'index': MATCH}, 'id'),
                  State({'type': 'action-reason', 'index': MATCH}, 'value'),
                  prevent_initial_call=True)
    @protect_callback('manager')
    def reverse(clicks, identifier, reason):
        if not clicks:
            return no_update, no_update
        try:
            if not (reason or '').strip():
                raise ValueError('Give a reason before reversing an action.')
            quantity = reverse_action_service(*caller(app), request_id=identifier['index'],
                                              reason=reason)
            return notice(translate('Reversed: {n} pieces are back as they were before this '
                                    'action.').format(n=quantity)), True
        except HANDLED_ERRORS as exc:
            return failure(exc), no_update

    @app.callback(Output('overview-alerts', 'children'), Input('overview-refresh', 'n_intervals'))
    @protect_callback(*ROLES)
    def alerts(_tick):
        try:
            return alerts_panel(get_manager_alerts_service(*caller(app)))
        except PermissionError:
            return None  # supervisors see their own notifications instead
        except HANDLED_ERRORS as exc:
            return failure(exc)
