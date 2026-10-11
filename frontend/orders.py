"""Orders page: managers edit or cancel any work order, planners the ones they created.

Which orders a caller may see and change is decided by `production_service`; this page
only renders what the service returns. Rows expand like the Operations employee list.
"""
from datetime import date
from urllib.parse import parse_qs, quote

import segno

from dash import Input, MATCH, Output, State, ctx, dcc, html, no_update

from frontend.auth import protect_callback
from frontend.common import (HANDLED_ERRORS, caller, clicked, failure, field, notice, optional_text,
                             page_label, scrap_badge, turn_page)
from frontend.i18n import translate
from frontend.login import top_bar
from frontend.manager import STATUS_LABELS, when
from backend.service.production_service import (
    ORDER_PAGE_SIZE, cancel_work_order_service, edit_work_order_service, list_work_orders_service,
    resolve_corrective_request_service, search_order_contractors_service)

ROLES = ('manager', 'planner')
# Where the list is: page number (for the label) and the cursor to read from.
PAGE_START = {'number': 1, 'after': None, 'before': None}
LABELS = {**STATUS_LABELS, 'cancelled': 'Cancelled'}
DUPLICATE = 'This work order number already exists. Use a different number. Nothing was saved.'
HIDDEN = {'display': 'none'}


def orders_page(actor=None):
    return html.Div(className='planner-page persistent-planner orders-page', children=[
        top_bar('Work orders', actor, 'orders'),
        html.Div(id='orders-sheet-section', style=HIDDEN),
        html.Div(id='orders-list-section', className='planner-content', children=[
            html.Div([html.Div([html.H1('Manage work orders'),
                html.P(id='orders-scope', className='planner-muted')]),
                html.Span('Orders', className='planner-badge')], className='planner-heading'),
            html.Div([
                dcc.Input(id='orders-search', placeholder='Search order, product or contractor',
                          className='form-input', debounce=True, type='search'),
                html.Div(id='orders-message', **{'aria-live': 'polite'}),
                html.Div(id='order-list'),
                html.Div([
                    html.Button('‹ Previous', id='orders-page-prev', className='planner-text-button'),
                    html.Span(id='orders-page-label', className='planner-muted'),
                    html.Button('Next ›', id='orders-page-next', className='planner-text-button'),
                ], className='overview-pages'),
            ], className='form-card'),
        ]),
        dcc.Interval(id='orders-load', interval=300, max_intervals=1),
        dcc.Store(id='orders-page', data=PAGE_START), dcc.Store(id='orders-data'),
    ])


def status_badge(status):
    return html.Span(LABELS[status], className=f'order-status {status}')


def order_summary(order):
    dates = (f"{translate(when(order['start_date'], 'No start date'))} → "
             f"{translate(when(order['due_date'], 'No due date'))}")
    return [
        html.Div([html.Strong(order['order_number']), status_badge(order['status']),
                  scrap_badge(order['scrapped']),
                  html.Span(translate('Action requested ({n})').format(n=order['open_requests']),
                            className='request-badge') if order['open_requests'] else None,
                  html.Span('Edit' if order['editable'] else 'View', className='order-row-action')],
                 className='order-row-top'),
        html.Span(translate('{product} · {n} pieces · {contractor}').format(
            product=order['product_name'] or translate('No product'), n=order['pieces'],
            contractor=order['contractor_name']), className='contractor-contact'),
        html.Span(dates, className='contractor-contact'),
        html.Span(translate('Predicted finish: {eta}').format(eta=when(order['predicted_eta'])),
                  className='contractor-contact') if order['predicted_eta'] else None,
    ]


def order_row(order):
    """Every control is always rendered and disabled when it does not apply, because Dash
    only dispatches a pattern-matching callback when all of its inputs exist in the row."""
    def ident(kind):
        return {'type': f'order-{kind}', 'index': order['work_order_id']}
    locked = not order['editable']
    return html.Details([
        html.Summary(order_summary(order), id=ident('summary')),
        html.Div([
            html.Div([
                field('Work order *', dcc.Input(id=ident('number'), value=order['order_number'],
                                                className='form-input', maxLength=128, disabled=locked)),
                # Only the current contractor is sent; typing searches the rest on the server.
                field('Contractor *', dcc.Dropdown(
                    id=ident('contractor'), value=order['contractor_id'], clearable=False,
                    disabled=locked, searchable=True, placeholder='Type to search contractors',
                    options=[{'label': order['contractor_name'], 'value': order['contractor_id']}])),
            ], className='two-column'),
            html.Div([
                field('Start date', dcc.DatePickerSingle(
                    id=ident('start'), date=_iso(order['start_date']), display_format='D MMM YYYY',
                    clearable=True, disabled=locked)),
                field('Due date', dcc.DatePickerSingle(
                    id=ident('due'), date=_iso(order['due_date']), display_format='D MMM YYYY',
                    clearable=True, disabled=locked)),
            ], className='two-column'),
            field('Notes', dcc.Textarea(id=ident('notes'), value=order['notes'] or '',
                                        className='form-input', disabled=locked)),
            html.P('The product, process and quantity cannot change once pieces exist. To '
                   'change them, cancel this order and create a new one.'
                   if not locked else 'Complete and cancelled orders can no longer be changed.',
                   className='planner-muted'),
            html.Div([
                html.Button('Apply', id=ident('apply'), className='planner-secondary', disabled=locked),
                html.Button('Cancel order', id=ident('cancel'), className='planner-text-button danger',
                            disabled=locked),
                html.Button('Yes, cancel this order', id=ident('confirm'), style=HIDDEN,
                            className='planner-secondary danger'),
                html.A('Print sheet with QR code', href=f"/orders?sheet={order['work_order_id']}",
                       target='_blank', className='planner-text-button'),
            ], className='account-actions'),
            html.Div(id=ident('message'), **{'aria-live': 'polite'}),
            *([html.H3('Scrapped pieces: action requested')]
              + [corrective_block(request) for request in order['corrective_requests']]
              if order['corrective_requests'] else []),
        ], className='contractor-fields'),
    ], className='contractor-row')


REQUEST_KINDS = {'replace': 'Replacement pieces requested', 'review': 'Review requested'}


def corrective_block(request):
    """One open scrap request, answered by adding replacements or closing it."""
    def ident(kind):
        return {'type': f'corrective-{kind}', 'index': request['id']}
    return html.Div([
        html.Div([html.Strong(translate('{n} pieces scrapped at {step}').format(
                      n=request['quantity'], step=request['step_name'])),
                  html.Span(REQUEST_KINDS[request['kind']], className='request-badge')],
                 className='order-row-top'),
        html.P(request['note'], className='step-instructions') if request['note'] else None,
        html.Small(f"{request['requested_by_name']} · {when(request['requested_at'])}",
                   className='planner-muted'),
        html.Div([
            field('Replacement pieces', dcc.Input(id=ident('quantity'), type='number', min=1,
                                                  step=1, value=request['quantity'],
                                                  className='form-input')),
            field('Note (optional)', dcc.Input(id=ident('note'), className='form-input',
                                               maxLength=1000)),
        ], className='two-column'),
        html.Div([
            html.Button('Add replacement pieces', id=ident('replace'), className='planner-secondary'),
            html.Button('Close without replacements', id=ident('close'),
                        className='planner-text-button'),
        ], className='account-actions'),
        html.Div(id=ident('message'), **{'aria-live': 'polite'}),
    ], className='corrective-request')


def order_sheet(order, origin):
    """A printable sheet that travels with the parts. Its QR code opens this order on the
    supervisor page, where the usual sign-in and unit checks still apply."""
    link = f"{origin}/supervisor?order={quote(order['order_number'])}"
    facts = (('Product', order['product_name'] or '—'),
             ('Process', f"{order['process_name'] or 'Production'} v{order['version']}"),
             ('Contractor', order['contractor_name']), ('Pieces', order['pieces']),
             ('Start date', when(order['start_date'], 'No start date')),
             ('Due date', when(order['due_date'], 'No due date')), ('Notes', order['notes'] or '—'))
    return html.Div([
        html.Div([
            html.Div([html.H1(translate('Work order {number}').format(number=order['order_number'])),
                      html.Dl([item for name, value in facts
                               for item in (html.Dt(name), html.Dd(value))], className='order-facts')]),
            html.Figure([html.Img(src=segno.make(link, error='m').svg_data_uri(scale=6),
                                  alt=translate('QR code for work order {number}').format(
                                      number=order['order_number'])),
                         html.Figcaption('Scan to open this order on the supervisor page.')],
                        className='sheet-qr'),
        ], className='order-sheet'),
        html.Button('Print', id='orders-print', className='planner-secondary no-print'),
    ], className='planner-content')


def _iso(value):
    return value.isoformat() if value else None


def _day(value):
    return date.fromisoformat(value) if value else None


def register_callbacks(app):

    @app.callback(Output('orders-page', 'data'),
                  Input('orders-page-prev', 'n_clicks'), Input('orders-page-next', 'n_clicks'),
                  Input('orders-search', 'value'), State('orders-data', 'data'),
                  prevent_initial_call=True)
    @protect_callback(*ROLES)
    def change_page(previous, following, search, data):
        # A new search starts again at the first page, which also reloads the list.
        if ctx.triggered_id not in ('orders-page-prev', 'orders-page-next') or not data:
            return PAGE_START
        return turn_page(data, forward=ctx.triggered_id == 'orders-page-next')

    @app.callback(Output('order-list', 'children'), Output('orders-message', 'children'),
                  Output('orders-scope', 'children'), Output('orders-page-label', 'children'),
                  Output('orders-page-prev', 'disabled'), Output('orders-page-next', 'disabled'),
                  Output('orders-data', 'data'),
                  Input('orders-load', 'n_intervals'), Input('orders-page', 'data'),
                  State('orders-search', 'value'), prevent_initial_call=True)
    @protect_callback(*ROLES)
    def load(_tick, page, search):
        page = page or PAGE_START
        try:
            data = list_work_orders_service(*caller(app), search=search or '',
                                            after=page['after'], before=page['before'])
        except HANDLED_ERRORS as exc:
            return [], failure(exc), '', '', True, True, None
        scope = ('Every work order in the factory. Select one to edit or cancel it.'
                 if data['all_orders'] else
                 'The work orders you created. Select one to edit or cancel it.')
        rows = [order_row(order) for order in data['orders']] or html.P(
            'No work orders match this search.', className='planner-muted overview-empty')
        return (rows, '', scope, page_label(page['number'], len(data['orders']), ORDER_PAGE_SIZE),
                not data['previous'], not data['next'],
                {'number': page['number'], 'previous': data['previous'], 'next': data['next']})

    @app.callback(Output({'type': 'order-contractor', 'index': MATCH}, 'options'),
                  Input({'type': 'order-contractor', 'index': MATCH}, 'search_value'),
                  State({'type': 'order-contractor', 'index': MATCH}, 'value'),
                  State({'type': 'order-contractor', 'index': MATCH}, 'options'),
                  prevent_initial_call=True)
    @protect_callback(*ROLES)
    def contractor_options(search, value, options):
        if not search:
            return no_update
        try:
            rows = search_order_contractors_service(*caller(app), search)
        except HANDLED_ERRORS:
            return no_update
        # The chosen contractor stays selectable while other names are searched.
        current = [option for option in options or () if option['value'] == value]
        return current + [{'label': row['name'], 'value': row['id']} for row in rows if row['id'] != value]

    # All outputs stay inside the row, as pattern-matching callbacks require.
    @app.callback(Output({'type': 'order-message', 'index': MATCH}, 'children'),
                  Output({'type': 'order-summary', 'index': MATCH}, 'children'),
                  Output({'type': 'order-confirm', 'index': MATCH}, 'style'),
                  Output({'type': 'order-apply', 'index': MATCH}, 'disabled'),
                  Output({'type': 'order-cancel', 'index': MATCH}, 'disabled'),
                  Input({'type': 'order-apply', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'order-cancel', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'order-confirm', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'order-apply', 'index': MATCH}, 'id'),
                  State({'type': 'order-number', 'index': MATCH}, 'value'),
                  State({'type': 'order-contractor', 'index': MATCH}, 'value'),
                  State({'type': 'order-start', 'index': MATCH}, 'date'),
                  State({'type': 'order-due', 'index': MATCH}, 'date'),
                  State({'type': 'order-notes', 'index': MATCH}, 'value'),
                  prevent_initial_call=True)
    @protect_callback(*ROLES)
    def manage(apply, cancel, confirm, identifier, number, contractor, start, due, notes):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not clicked():
            return (no_update,) * 5
        order_id, action = identifier['index'], trigger['type']
        if action == 'order-cancel':
            return (notice('Cancelling removes this order from every queue and overview. '
                           'It cannot be undone.', True), no_update, {}, no_update, no_update)
        try:
            actor, pool = caller(app)
            if action == 'order-confirm':
                cancel_work_order_service(actor, pool, order_id)
                message = notice('Work order cancelled.')
            else:
                if not (number or '').strip():
                    raise ValueError('Enter a work order number.')
                if not contractor:
                    raise ValueError('Select a contractor.')
                edit_work_order_service(actor, pool, order_id, order_number=number,
                                        contractor_id=contractor, start_date=_day(start),
                                        due_date=_day(due), notes=optional_text(notes))
                message = notice('Changes saved.')
            # Re-read so the summary shows the stored order, not the submitted form.
            order = list_work_orders_service(actor, pool, order_id=order_id)['orders'][0]
            locked = not order['editable']
            return message, order_summary(order), HIDDEN, locked, locked
        except HANDLED_ERRORS as exc:
            return failure(exc, DUPLICATE), no_update, HIDDEN, no_update, no_update

    @app.callback(Output({'type': 'corrective-message', 'index': MATCH}, 'children'),
                  Output({'type': 'corrective-replace', 'index': MATCH}, 'disabled'),
                  Output({'type': 'corrective-close', 'index': MATCH}, 'disabled'),
                  Input({'type': 'corrective-replace', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'corrective-close', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'corrective-replace', 'index': MATCH}, 'id'),
                  State({'type': 'corrective-quantity', 'index': MATCH}, 'value'),
                  State({'type': 'corrective-note', 'index': MATCH}, 'value'),
                  prevent_initial_call=True)
    @protect_callback(*ROLES)
    def answer_request(replace, close, identifier, quantity, note):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not clicked():
            return no_update, no_update, no_update
        try:
            replacing = trigger['type'] == 'corrective-replace'
            if replacing and (not isinstance(quantity, (int, float)) or quantity < 1
                              or quantity != int(quantity)):
                raise ValueError('Enter how many replacement pieces to make.')
            added = resolve_corrective_request_service(
                *caller(app), identifier['index'], action='replace' if replacing else 'close',
                quantity=int(quantity) if replacing else None, note=note)
            message = (translate('{n} replacement pieces added. They start at the first step.')
                       .format(n=added) if added else translate('Request closed.'))
            return notice(message), True, True
        except HANDLED_ERRORS as exc:
            return failure(exc), no_update, no_update

    @app.callback(Output('orders-list-section', 'style'), Output('orders-sheet-section', 'style'),
                  Output('orders-sheet-section', 'children'), Input('url', 'search'))
    @protect_callback(*ROLES)
    def show_sheet(search):
        values = parse_qs((search or '').lstrip('?')).get('sheet', [])
        if not values:
            return {}, HIDDEN, []
        try:
            request = app.backend.request_adapter().context
            orders = list_work_orders_service(request.actor, request.business_pool,
                                              order_id=int(values[0]))['orders']
            if not orders:
                raise ValueError('This work order does not exist or is not yours to manage.')
            return HIDDEN, {}, order_sheet(orders[0], request.public_origin)
        except (ValueError, *HANDLED_ERRORS) as exc:
            return HIDDEN, {}, html.Div(failure(exc), className='planner-content')

    app.clientside_callback("""function(clicks) { if (clicks) { window.print(); }
        return window.dash_clientside.no_update; }""",
        Output('orders-print', 'title'), Input('orders-print', 'n_clicks'), prevent_initial_call=True)
