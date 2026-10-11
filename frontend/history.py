"""Order history: completed orders, newest first, filtered by completion date.

The Supervisor page shows orders completed in the last month; older ones are found here.
Scope follows the overview: managers see every order, supervisors the orders with a step
in a unit they supervise now. Pages are read with a cursor, twenty orders at a time.
"""
from datetime import date

from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from frontend.auth import protect_callback
from frontend.common import (HANDLED_ERRORS, PERIODS, caller, clicked, failure, field, page_label,
                             period_range, product_picture, turn_page)
from frontend.i18n import translate
from frontend.login import top_bar
from frontend.manager import order_summary, when
from backend.service.overview_service import (HISTORY_PAGE_SIZE, get_order_history_service,
                                              get_order_summary_service)

ROLES = ('manager', 'supervisor')
PAGE_START = {'number': 1, 'after': None, 'before': None}
HISTORY_PERIODS = ('all', 'last_month', 'last_3_months', 'last_year', 'custom')


def history_page(actor=None):
    return html.Div(className='planner-page persistent-planner manager-page', children=[
        top_bar('Order history', actor, 'history'),
        html.Div(className='planner-content', children=[
            html.Div([html.Div([html.H1('Order history'),
                                html.P('Completed work orders, most recently completed first.',
                                       className='planner-muted')]),
                      html.Span('History', className='planner-badge')], className='planner-heading'),
            html.Div(className='stat-filters', children=[
                field('Completed', dcc.Dropdown(id='history-period', value='all', clearable=False,
                      options=[{'label': PERIODS[key], 'value': key} for key in HISTORY_PERIODS])),
                field('Between', dcc.DatePickerRange(id='history-dates', display_format='D MMM YYYY')),
                field('Search', dcc.Input(id='history-search', type='search', debounce=True,
                                          className='form-input',
                                          placeholder='Search order, product or contractor')),
            ]),
            html.P(id='history-scope', className='planner-muted'),
            html.Div(id='history-message', **{'aria-live': 'polite'}),
            html.Div([
                html.Div([
                    html.Div(id='history-list', className='part-list'),
                    html.Div([
                        html.Button('‹ Previous', id='history-prev', className='planner-text-button'),
                        html.Span(id='history-page-label', className='planner-muted'),
                        html.Button('Next ›', id='history-next', className='planner-text-button'),
                    ], className='overview-pages'),
                ], className='info-card'),
                html.Div(id='history-summary', className='info-card part-detail', children=[
                    html.H2('Select a work order'),
                    html.P('Choose an order to see its details and progress per process step.',
                           className='planner-muted')]),
            ], className='supervisor-grid'),
        ]),
        dcc.Store(id='history-page', data=PAGE_START), dcc.Store(id='history-data'),
        dcc.Store(id='history-selected'),
    ])


def history_row(order, selected):
    # Rows come back from the page's store, so dates are text here; when() reads either.
    return html.Button([
        html.Div([html.Strong(order['order_number']),
                  html.Span('Late' if order['late'] else 'On time' if order['due_date'] else 'No due date',
                            className='order-status ' + ('delayed' if order['late'] else 'complete'))],
                 className='part-card-top'),
        html.Div([product_picture(order['product_type_id'], order['product_image_version']), html.Div([
            html.H3(order['product_name'] or 'No product'),
            html.P(order['contractor_name'], className='planner-muted'),
        ])], className='part-product'),
        html.Div([html.Span(translate('{n} pieces').format(n=order['pieces'])),
                  html.Span(translate('Completed {date}').format(date=when(order['completion_time'])))],
                 className='part-card-footer history-card-footer'),
    ], id={'type': 'history-card', 'index': order['work_order_id']}, n_clicks=0,
       className='part-card selected' if order['work_order_id'] == selected else 'part-card',
       **{'aria-pressed': 'true' if order['work_order_id'] == selected else 'false'})


def _day(value):
    return date.fromisoformat(value) if value else None


def register_callbacks(app):
    # The preset fills in the dates, and picking dates by hand makes the preset "custom".
    @app.callback(Output('history-period', 'value'), Output('history-dates', 'start_date'),
                  Output('history-dates', 'end_date'),
                  Input('history-period', 'value'), Input('history-dates', 'start_date'),
                  Input('history-dates', 'end_date'), prevent_initial_call=True)
    @protect_callback(*ROLES)
    def sync_period(period, start, end):
        if ctx.triggered_id == 'history-period':
            if period == 'custom':
                return no_update, no_update, no_update
            first, last = period_range(period)
            return no_update, first and first.isoformat(), last and last.isoformat()
        return 'custom', no_update, no_update

    @app.callback(Output('history-page', 'data'),
                  Input('history-prev', 'n_clicks'), Input('history-next', 'n_clicks'),
                  Input('history-dates', 'start_date'), Input('history-dates', 'end_date'),
                  Input('history-search', 'value'), State('history-data', 'data'),
                  prevent_initial_call=True)
    @protect_callback(*ROLES)
    def change_page(previous, following, start, end, search, data):
        # Changing a filter starts again at the newest orders.
        if ctx.triggered_id not in ('history-prev', 'history-next') or not data:
            return PAGE_START
        return turn_page(data, forward=ctx.triggered_id == 'history-next')

    @app.callback(Output('history-data', 'data'), Output('history-message', 'children'),
                  Output('history-scope', 'children'),
                  Input('history-page', 'data'), State('history-dates', 'start_date'),
                  State('history-dates', 'end_date'), State('history-search', 'value'))
    @protect_callback(*ROLES)
    def load(page, start, end, search):
        page = page or PAGE_START
        try:
            data = get_order_history_service(
                *caller(app), completed_from=_day(start), completed_to=_day(end),
                search=search or '', after=page['after'], before=page['before'])
        except HANDLED_ERRORS as exc:
            return None, failure(exc), ''
        scope = ('Only work orders with a step in a unit you supervise are shown.'
                 if data['unit_scoped'] else 'Every completed work order in the factory.')
        return dict(data, number=page['number']), '', scope

    @app.callback(Output('history-list', 'children'), Output('history-page-label', 'children'),
                  Output('history-prev', 'disabled'), Output('history-next', 'disabled'),
                  Input('history-data', 'data'), Input('history-selected', 'data'))
    @protect_callback(*ROLES)
    def render(data, selected):
        if not data:
            return html.P('The history is unavailable. Retry shortly.', className='planner-muted'), '', True, True
        rows = [history_row(order, selected) for order in data['orders']] or html.P(
            'No completed work orders match these filters.', className='planner-muted overview-empty')
        return (rows, page_label(data['number'], len(data['orders']), HISTORY_PAGE_SIZE),
                not data['previous'], not data['next'])

    @app.callback(Output('history-selected', 'data'),
                  Input({'type': 'history-card', 'index': ALL}, 'n_clicks'), prevent_initial_call=True)
    @protect_callback(*ROLES)
    def select(clicks):
        return ctx.triggered_id['index'] if clicked() else no_update

    @app.callback(Output('history-summary', 'children'), Input('history-selected', 'data'),
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
