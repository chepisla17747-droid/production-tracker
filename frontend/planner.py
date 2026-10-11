"""Persistent Planner page. Every callback uses the authenticated request context."""
from datetime import date
from uuid import uuid4

from dash import html, dcc, Input, Output, State, MATCH, ctx, no_update

from frontend.auth import protect_callback
from frontend.common import (HANDLED_ERRORS, caller, duration, failure as report, field, notice,
                             optional_text, page_label, product_picture, turn_page)
from frontend.login import top_bar
from frontend import supervision
from backend.service import planner_service as service
from backend.service.production_service import create_work_order_service


# Where the contractor directory is: page number (for the label) and the cursor to read from.
PAGE_START = {'number': 1, 'after': None, 'before': None}


def failure(exc):
    return report(exc, 'This work order number already exists. Use a different number. Nothing was added.')


def contractor_form(prefix):
    return html.Div([
        field('Name *', dcc.Input(id=f'{prefix}-name', className='form-input', maxLength=256)),
        html.Div([
            field('Email', dcc.Input(id=f'{prefix}-email', type='email', className='form-input', maxLength=256)),
            field('Phone', dcc.Input(id=f'{prefix}-phone', type='tel', className='form-input', maxLength=16)),
        ], className='two-column'),
        html.P('Saved contractors are available for future orders.', className='planner-muted'),
        html.Button('Save & select' if prefix == 'inline-contractor' else 'Add contractor',
                    id=f'{prefix}-save', className='planner-secondary'),
        html.Div(id=f'{prefix}-message', **{'aria-live': 'polite'}),
        dcc.Store(id=f'{prefix}-saved'),
    ], className='contractor-fields')


def planner_page(actor=None):
    return html.Div(className='planner-page persistent-planner', children=[
        top_bar('Production planning', actor, 'planner'),
        html.Div(className='planner-content', children=[
            html.Div([html.Div([html.H1('Plan the next order'),
                html.P('Choose a product, review its process and schedule production.', className='planner-muted')]),
                html.Span('Planner', className='planner-badge')], className='planner-heading'),
            dcc.Tabs(id='planner-tab', value='orders', children=[
                dcc.Tab(label='New work order', value='orders'),
                dcc.Tab(label='Contractors', value='contractors'),
                dcc.Tab(label='Unit supervisors', value='supervision'),
            ]),
            html.Div(id='planner-order-section', children=[
                html.Div(id='catalog-message'),
                html.Div(className='planner-grid', children=[
                    html.Div(className='form-card', children=[
                        html.H2('Order details'),
                        field('Work order *', dcc.Input(id='work-order', placeholder='e.g. WO-2026-001', className='form-input', maxLength=128)),
                        field('Contractor *', dcc.Dropdown(id='contractor', options=[], placeholder='Search or select a contractor')),
                        html.Div(id='contractor-options-message'),
                        html.Details([html.Summary('+ Add a new contractor'), contractor_form('inline-contractor')], className='contractor-add'),
                        field('Product *', dcc.Dropdown(id='product', options=[], placeholder='Select a product')),
                        field('Production process *', dcc.Dropdown(id='process', options=[], placeholder='Select a product first')),
                        # Dash 4.4.1's stepper parses an omitted max as NaN when min is set.
                        # Explicit null preserves an unbounded maximum and working +/- buttons.
                        field('Quantity *', dcc.Input(id='quantity', type='number', min=1, max=None, step=1, value=50, className='form-input')),
                        html.Div([
                            field('Start date *', dcc.DatePickerSingle(id='start-date', date=date.today().isoformat(), display_format='D MMM YYYY')),
                            field('Due date *', dcc.DatePickerSingle(id='due-date', display_format='D MMM YYYY',
                                                                     min_date_allowed=date.today())),
                        ], className='two-column'),
                        html.Button('Create Work Order', id='create-work-order', className='create-button'),
                        html.Div(id='create-message', **{'aria-live': 'polite'}),
                    ]),
                    html.Div([
                        html.Div([html.H2('Product details'), html.Div(id='product-spec')], className='info-card'),
                        html.Div([html.H2('Production process'), html.Div(id='process-routing', children='Select a product and process.')], className='info-card'),
                        html.Button('Refresh catalog', id='refresh-catalog', className='planner-text-button'),
                    ]),
                ]),
            ]),
            html.Div(id='planner-contractor-section', style={'display': 'none'}, children=[
                html.Div([html.H2('Contractors'), html.P('Select a contractor to expand their details. Changes save when you click Apply.', className='planner-muted'),
                    dcc.Input(id='contractor-search', placeholder='Search name, email or phone', className='form-input', debounce=True),
                    html.Details([html.Summary('+ Add contractor'), contractor_form('directory-contractor')], className='contractor-add'),
                    html.Div(id='contractor-list'),
                    html.Div([
                        html.Button('‹ Previous', id='contractors-prev', className='planner-text-button'),
                        html.Span(id='contractors-page-label', className='planner-muted'),
                        html.Button('Next ›', id='contractors-next', className='planner-text-button'),
                    ], className='overview-pages'),
                    dcc.Store(id='contractors-page', data=PAGE_START), dcc.Store(id='contractors-data'),
                ], className='form-card'),
            ]),
            supervision.supervision_section('planner-supervision-section', {'display': 'none'}),
        ]),
    ])


def contractor_summary(row):
    return [html.Span(row['name'], className='contractor-name'),
            html.Span(row['email'] or row['phone_number'] or 'No contact details yet', className='contractor-contact')]


def contractor_row(row):
    def ident(kind):
        return {'type': f'contractor-{kind}', 'index': row['id']}
    return html.Details([
        html.Summary(contractor_summary(row), id=ident('summary')),
        html.Div([
            field('Name *', dcc.Input(id=ident('name'), value=row['name'], className='form-input', maxLength=256)),
            html.Div([
                field('Email', dcc.Input(id=ident('email'), value=row['email'], type='email', className='form-input', maxLength=256)),
                field('Phone', dcc.Input(id=ident('phone'), value=row['phone_number'], type='tel', className='form-input', maxLength=16)),
            ], className='two-column'),
            html.Button('Apply', id=ident('apply'), className='planner-secondary'),
            html.Div(id=ident('message'), **{'aria-live': 'polite'}),
        ], className='contractor-fields'),
    ], className='contractor-row')


def register_callbacks(app):

    @app.callback(Output('planner-order-section', 'style'), Output('planner-contractor-section', 'style'),
                  Output('planner-supervision-section', 'style'), Input('planner-tab', 'value'))
    @protect_callback('planner')
    def switch_tab(tab):
        hidden = {'display': 'none'}
        return tuple({} if tab == name else hidden for name in ('orders', 'contractors', 'supervision'))

    @app.callback(Output('due-date', 'min_date_allowed'), Output('due-date', 'date'),
                  Input('start-date', 'date'), State('due-date', 'date'))
    @protect_callback('planner')
    def due_date_follows_start(start, due):
        """An earlier due date cannot be picked, and a stale one is cleared."""
        if not start:
            return no_update, no_update
        return start, (None if due and due < start else no_update)

    @app.callback(Output('product', 'options'), Output('catalog-message', 'children'), Input('refresh-catalog', 'n_clicks'))
    @protect_callback('planner')
    def load_catalog(_):
        try:
            rows = service.get_planner_catalog(*caller(app))
            options = [{'label': p['name'] + ('' if p['is_orderable'] else ' · Unavailable'), 'value': p['id'], 'disabled': not p['is_orderable']} for p in rows]
            return options, '' if options else notice('No products are available yet. Ask an administrator to load the catalog.')
        except HANDLED_ERRORS as exc:
            return [], failure(exc)

    @app.callback(Output('product-spec', 'children'), Input('product', 'value'))
    @protect_callback('planner')
    def product_spec(product_id):
        if product_id is None:
            return html.P('Select a product to see its details.', className='planner-muted')
        try:
            product, _ = service.get_planner_product(*caller(app), product_id)
            return html.Div([product_picture(product['id'], product['image_version'], product['name'])] + [
                html.H3(product['name']), html.P(product['description'] or 'No description provided.'),
                html.Span(product['reference_code'] or '', className='planner-badge')], className='planner-product')
        except HANDLED_ERRORS as exc:
            return failure(exc)

    @app.callback(Output('process', 'options'), Output('process', 'value'), Input('product', 'value'))
    @protect_callback('planner')
    def processes(product_id):
        if product_id is None:
            return [], None
        try:
            _, rows = service.get_planner_product(*caller(app), product_id)
            eligible = [row for row in rows if row['is_active']]
            return [{'label': f"{row['name'] or 'Production'} · v{row['version']}" + ('' if row['is_active'] else ' · Inactive'),
                     'value': row['id'], 'disabled': not row['is_active']} for row in rows], eligible[0]['id'] if len(eligible) == 1 else None
        except HANDLED_ERRORS:
            return [], None  # The product-details callback shows the associated read error.

    @app.callback(Output('process-routing', 'children'), Input('process', 'value'), Input('product', 'value'))
    @protect_callback('planner')
    def routing(process_id, product_id):
        if product_id is None or process_id is None:
            return html.P('Select an available production process.', className='planner-muted')
        try:
            process, rows = service.get_planner_process(*caller(app), product_id, process_id)
            return ([notice('This process is inactive.', True)] if not process['is_active'] else []) + [
                html.Div([html.Span(str(i), className='step-number'), html.Div([
                    html.Strong(row['name']), html.Div(duration(row['standard_time_seconds']), className='planner-muted'),
                    html.P(row['instructions'], className='step-instructions') if row['instructions'] else None,
                ])], className='planner-step') for i, row in enumerate(rows, 1)
            ] or html.P('This process has no steps yet.', className='planner-muted')
        except HANDLED_ERRORS as exc:
            return failure(exc)

    @app.callback(Output('contractor', 'options'), Output('contractor', 'value'), Output('contractor-options-message', 'children'),
                  Input('inline-contractor-saved', 'data'), Input('directory-contractor-saved', 'data'), Input('planner-tab', 'value'),
                  State('contractor', 'value'))
    @protect_callback('planner')
    def contractor_options(inline, directory, tab, selected):
        try:
            rows = service.get_contractors_service(*caller(app))
            if ctx.triggered_id == 'inline-contractor-saved' and inline:
                selected = inline['id']
            elif ctx.triggered_id == 'directory-contractor-saved' and directory:
                selected = directory['id']
            if selected not in {r['id'] for r in rows}:
                selected = None
            return [{'label': r['name'], 'value': r['id']} for r in rows], selected, ''
        except HANDLED_ERRORS as exc:
            return [], no_update, failure(exc)

    @app.callback(Output('contractors-page', 'data'),
                  Input('contractors-prev', 'n_clicks'), Input('contractors-next', 'n_clicks'),
                  Input('contractor-search', 'value'), Input('directory-contractor-saved', 'data'),
                  Input('inline-contractor-saved', 'data'), State('contractors-data', 'data'),
                  prevent_initial_call=True)
    @protect_callback('planner')
    def change_contractor_page(previous, following, search, directory, inline, data):
        # A new search or contractor starts again at the first page.
        if ctx.triggered_id not in ('contractors-prev', 'contractors-next') or not data:
            return PAGE_START
        return turn_page(data, forward=ctx.triggered_id == 'contractors-next')

    @app.callback(Output('contractor-list', 'children'), Output('contractors-page-label', 'children'),
                  Output('contractors-prev', 'disabled'), Output('contractors-next', 'disabled'),
                  Output('contractors-data', 'data'), Input('contractors-page', 'data'),
                  State('contractor-search', 'value'))
    @protect_callback('planner')
    def contractors(page, search):
        page = page or PAGE_START
        try:
            data = service.list_contractors_service(*caller(app), search=search or '',
                                                    after=page['after'], before=page['before'])
        except HANDLED_ERRORS as exc:
            return failure(exc), '', True, True, None
        rows = data['contractors']
        listing = [contractor_row(row) for row in rows] or html.P(
            'No contractors match.' if (search or '').strip() else
            'No contractors yet. Add your first contractor above.', className='planner-muted')
        return (listing, page_label(page['number'], len(rows), service.CONTRACTOR_PAGE_SIZE),
                not data['previous'], not data['next'],
                {'number': page['number'], 'previous': data['previous'], 'next': data['next']})

    def register_create_contractor(prefix):
        @app.callback(Output(f'{prefix}-saved', 'data'), Output(f'{prefix}-message', 'children'),
                      Input(f'{prefix}-save', 'n_clicks'), State(f'{prefix}-name', 'value'),
                      State(f'{prefix}-email', 'value'), State(f'{prefix}-phone', 'value'), prevent_initial_call=True,
                      running=[(Output(f'{prefix}-save', 'disabled'), True, False)])
        @protect_callback('planner')
        def save_contractor(clicks, name, email, phone):
            if not clicks:
                return no_update, no_update
            try:
                key = service.create_contractor_service(*caller(app), name=name, email=optional_text(email), phone_number=optional_text(phone))
                return {'id': key, 'revision': str(uuid4())}, notice('Contractor saved and selected for the order.')
            except HANDLED_ERRORS as exc:
                return no_update, failure(exc)
    register_create_contractor('inline-contractor')
    register_create_contractor('directory-contractor')

    @app.callback(Output({'type': 'contractor-message', 'index': MATCH}, 'children'),
                  Output({'type': 'contractor-summary', 'index': MATCH}, 'children'),
                  Input({'type': 'contractor-apply', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'contractor-apply', 'index': MATCH}, 'id'),
                  State({'type': 'contractor-name', 'index': MATCH}, 'value'),
                  State({'type': 'contractor-email', 'index': MATCH}, 'value'),
                  State({'type': 'contractor-phone', 'index': MATCH}, 'value'), prevent_initial_call=True)
    @protect_callback('planner')
    def edit_contractor(clicks, identifier, name, email, phone):
        if not clicks:
            return no_update, no_update
        try:
            saved = service.edit_contractor_service(*caller(app), identifier['index'], name=name, email=optional_text(email), phone_number=optional_text(phone))
            return notice('Changes saved.'), contractor_summary(saved)
        except HANDLED_ERRORS as exc:
            return failure(exc), no_update

    @app.callback(Output('create-message', 'children'), Input('create-work-order', 'n_clicks'),
                  State('work-order', 'value'), State('contractor', 'value'), State('product', 'value'),
                  State('process', 'value'), State('quantity', 'value'), State('start-date', 'date'), State('due-date', 'date'),
                  prevent_initial_call=True, running=[(Output('create-work-order', 'disabled'), True, False)])
    @protect_callback('planner')
    def create_order(clicks, number, contractor_id, product_id, process_id, quantity, start, due):
        if not clicks:
            return no_update
        try:
            if not all((number, contractor_id, product_id, process_id, start, due)):
                raise ValueError('Fill in the work order, contractor, product, process and both dates.')
            if not isinstance(number, str) or not number.strip():
                raise ValueError('Enter a work order number.')
            number = number.strip()
            # Dash passes JSON numbers; the service rejects fractional, boolean or nonpositive quantities.
            actor, pool = caller(app)
            product, _ = service.get_planner_product(actor, pool, product_id)
            process, _ = service.get_planner_process(actor, pool, product_id, process_id)
            contractor = next((row for row in service.get_contractors_service(actor, pool)
                               if row['id'] == contractor_id), None)
            if contractor is None:
                raise ValueError('Select an existing contractor or save a new one first.')
            key = create_work_order_service(actor, pool, order_number=number, contractor_id=contractor_id,
                product_type_id=product_id, process_def_id=process_id, quantity=quantity,
                start_date=date.fromisoformat(start), due_date=date.fromisoformat(due))
            return notice([html.Strong('Work order saved'), html.P(f'{number} · {quantity} pieces'),
                html.P(f"Contractor: {contractor['name']}"),
                html.P(f"Product: {product['name']} · Process: {process['name'] or 'Production'} v{process['version']}"),
                html.P(f'Start: {start} · Due: {due}'), html.Span(f'Confirmation #{key}')])
        except HANDLED_ERRORS as exc:
            return failure(exc)
