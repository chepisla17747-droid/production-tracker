"""Operations Administrator page: employees, accounts, units, products and processes.

Every callback reads its actor and pool from the authenticated request. The catalog
editor keeps its whole draft in a browser store and writes nothing until Apply.
"""
from datetime import date
from uuid import uuid4

from dash import html, dcc, Input, Output, State, MATCH, ALL, ctx, no_update

from frontend.auth import protect_callback
from frontend.i18n import translate
from frontend.common import (HANDLED_ERRORS, caller, clicked, duration, failure, field, notice,
                             optional_text, page_label, product_picture, role_label, turn_page)
from frontend.login import top_bar
from frontend import supervision
from backend.service import catalog_service as catalog
from backend.service.employee_service import (
    EMPLOYEE_PAGE_SIZE, create_employee_service, edit_employee_service, list_employees_service,
    mark_employee_left_service, reinstate_employee_service)
from backend.service.user_account_service import (
    create_user_account_service, list_user_accounts_service,
    reissue_activation_code_service, reset_account_password_service,
    revoke_activation_codes_service, set_account_active_service)
from backend.service.role_service import (
    employee_roles_service, get_assignable_roles_service, get_employee_history_service,
    set_employee_roles_service)

ROLE = 'operations_admin'
# Where the employee list is: page number (for the label) and the cursor to read from.
PAGE_START = {'number': 1, 'after': None, 'before': None}
TABS = ('employees', 'supervision', 'units', 'products', 'processes')


def operations_page(actor=None):
    return html.Div(className='planner-page persistent-planner operations-page', children=[
        top_bar('Operations administration', actor, 'operations'),
        html.Div(className='planner-content', children=[
            html.Div([html.Div([html.H1('Set up the factory'),
                html.P('People, their accounts and units, and the product catalog.',
                       className='planner-muted')]),
                html.Span('Operations', className='planner-badge')], className='planner-heading'),
            dcc.Tabs(id='operations-tab', value='employees', children=[
                dcc.Tab(label='Employees', value='employees'),
                dcc.Tab(label='Unit supervisors', value='supervision'),
                dcc.Tab(label='Production units', value='units'),
                dcc.Tab(label='Products', value='products'),
                dcc.Tab(label='Processes', value='processes'),
            ]),
            employees_section(),
            supervision.supervision_section('operations-supervision-section', {'display': 'none'}),
            units_section(), products_section(), processes_section(),
        ]),
    ])


# --------------------------------------------------------------------- employees

def employee_form(prefix):
    return html.Div([
        html.Div([
            field('First name *', dcc.Input(id=f'{prefix}-name', className='form-input', maxLength=256)),
            field('Surname *', dcc.Input(id=f'{prefix}-surname', className='form-input', maxLength=256)),
        ], className='two-column'),
        html.Div([
            field('Email', dcc.Input(id=f'{prefix}-email', type='email', className='form-input', maxLength=256)),
            field('Phone', dcc.Input(id=f'{prefix}-phone', type='tel', className='form-input', maxLength=16)),
        ], className='two-column'),
        field('Date of birth', dcc.DatePickerSingle(id=f'{prefix}-birth', display_format='D MMM YYYY',
                                                    max_date_allowed=date.today())),
        html.P('An email address is optional: the activation code is handed over in person.',
               className='planner-muted'),
        html.Button('Add employee', id=f'{prefix}-save', className='planner-secondary'),
        html.Div(id=f'{prefix}-message', **{'aria-live': 'polite'}),
        dcc.Store(id=f'{prefix}-saved'),
    ])


def employees_section():
    return html.Div(id='operations-employees-section', children=[
        html.Div([html.H2('Employees'),
            html.P('Select someone to expand their record. Changes save when you click Apply.',
                   className='planner-muted'),
            dcc.Input(id='employee-search', placeholder='Search name, email or phone',
                      className='form-input', debounce=True),
            dcc.Checklist(id='employees-show-left', value=[], className='role-checklist',
                          options=[{'label': ' Show employees who have left', 'value': 'left'}]),
            html.Details([html.Summary('+ Add employee'), employee_form('new-employee')],
                         className='contractor-add'),
            html.Button('Refresh list', id='refresh-employees', className='planner-text-button'),
            html.Div(id='employee-list'),
            html.Div([
                html.Button('‹ Previous', id='employees-prev', className='planner-text-button'),
                html.Span(id='employees-page-label', className='planner-muted'),
                html.Button('Next ›', id='employees-next', className='planner-text-button'),
            ], className='overview-pages'),
            dcc.Store(id='employees-page', data=PAGE_START), dcc.Store(id='employees-data'),
        ], className='form-card'),
    ])


def employee_summary(row, roles=()):
    left = row.get('left_at')
    return [html.Span(f"{row['name']} {row['surname']}", className='contractor-name'),
            html.Span(translate('Left on {date}').format(date=left.astimezone().strftime('%d %b %Y')),
                      className='request-badge') if left else None,
            html.Span(', '.join(role_label(role) for role in roles) or 'No website role',
                      className='employee-roles'),
            html.Span(row['email'] or row['phone_number'] or 'No contact details yet',
                      className='contractor-contact')]


def account_state(account):
    """One word for where an account stands, matching what its owner can do."""
    if account is None:
        return 'none'
    if not account['is_active']:
        return 'disabled'
    return 'active' if account['has_password'] else 'pending'


STATE_LABELS = {'none': 'No account yet', 'pending': 'Waiting for activation',
                'active': 'Active', 'disabled': 'Disabled'}


def account_block(row, account, editable=True):
    """Every control is always rendered, so its callback inputs never disappear.

    Dash only dispatches a pattern-matching callback when each of its inputs exists for
    that row, so the inapplicable actions are disabled rather than left out.
    """
    def ident(kind):
        return {'type': f'employee-{kind}', 'index': row['id']}
    state = account_state(account)
    outstanding = bool(account and account['has_live_code'])
    detail = []
    if account is not None:
        detail = [html.Span(f"Username {account['username']}", className='planner-muted'),
                  html.Span(' · code outstanding' if outstanding else
                            (' · no code outstanding' if state == 'pending' else ''),
                            className='planner-muted')]
    return [
        html.Div([html.Span(STATE_LABELS[state], className=f'account-state {state}'), *detail],
                 className='account-state-line'),
        field('Username for a new account',
              dcc.Input(id=ident('new-username'), className='form-input', maxLength=256,
                        disabled=account is not None or not editable,
                        placeholder='Only for an employee without an account')),
        html.Div([
            html.Button('Create account', id=ident('create-account'), className='planner-secondary',
                        disabled=account is not None or not editable),
            html.Button('Reissue code', id=ident('reissue'), className='planner-secondary',
                        disabled=state != 'pending' or not editable),
            html.Button('Revoke code', id=ident('revoke'), className='planner-text-button',
                        disabled=not outstanding or not editable),
            html.Button('Reset password', id=ident('reset'), className='planner-text-button',
                        disabled=state not in ('active', 'disabled') or not editable),
            html.Button('Enable account' if state == 'disabled' else 'Disable account',
                        id=ident('toggle-active'), className='planner-text-button',
                        disabled=account is None or not editable),
        ], className='account-actions'),
        html.P('Resetting a password does not set one: the account returns to waiting for '
               'activation with a fresh code, and its owner chooses the password.'
               if editable else 'This is your own account. Use your profile page.',
               className='planner-muted'),
        html.Div(id=ident('account-message'), **{'aria-live': 'polite'}),
    ]


def code_handout(username, code, message):
    return html.Div([
        notice(message),
        html.Div([
            html.Div([html.Dt('Username'), html.Dd(username)], className='profile-detail'),
            html.Div([html.Dt('Activation code'), html.Dd(code, className='activation-code')],
                     className='profile-detail'),
        ], className='activation-handout'),
    ])


def employee_row(row, assignable=(), roles=(), account=None, editable=True):
    def ident(kind):
        return {'type': f'employee-{kind}', 'index': row['id']}
    held = [role for role in roles if role in {item['name'] for item in assignable}]
    return html.Details([
        html.Summary(employee_summary(row, roles), id=ident('summary')),
        html.Div([
            html.Div([
                field('First name *', dcc.Input(id=ident('name'), value=row['name'],
                                                className='form-input', maxLength=256)),
                field('Surname *', dcc.Input(id=ident('surname'), value=row['surname'],
                                             className='form-input', maxLength=256)),
            ], className='two-column'),
            html.Div([
                field('Email', dcc.Input(id=ident('email'), value=row['email'], type='email',
                                         className='form-input', maxLength=256)),
                field('Phone', dcc.Input(id=ident('phone'), value=row['phone_number'], type='tel',
                                         className='form-input', maxLength=16)),
            ], className='two-column'),
            html.P(f"Registered {row['regist_date'].date().isoformat()}"
                   + (f" · born {row['birth_date'].isoformat()}" if row['birth_date'] else ''),
                   className='planner-muted'),
            html.Button('Apply', id=ident('apply'), className='planner-secondary'),
            html.Div(id=ident('message'), **{'aria-live': 'polite'}),
            html.H3('User account'),
            html.Div(account_block(row, account, editable), id=ident('account')),
            html.H3('Website roles'),
            html.P('These decide which pages this person can open. The administrator role '
                   'is set in the database, not here.' if editable else
                   'You cannot change your own roles. Ask another administrator.',
                   className='planner-muted'),
            dcc.Checklist(id=ident('roles'), value=held, className='role-checklist',
                          options=[{'label': ' ' + role_label(item['name']), 'value': item['name'],
                                    'disabled': not editable} for item in assignable]),
            html.Button('Save roles', id=ident('save-roles'), className='planner-secondary',
                        disabled=not editable),
            html.Div(id=ident('roles-message'), **{'aria-live': 'polite'}),
            html.H3('Employment'),
            html.P('Marking someone as left disables their account, ends their unit assignments '
                   'and hides them from selectors. Their record and history stay.'
                   if not row.get('left_at') else
                   'This person has left. Reinstating does not re-enable their account.',
                   className='planner-muted'),
            html.Div([
                html.Button('Mark as left', id=ident('leave'), className='planner-text-button danger',
                            disabled=bool(row.get('left_at')) or not editable),
                html.Button('Yes, mark as left', id=ident('confirm-leave'),
                            className='planner-secondary danger', style={'display': 'none'}),
                html.Button('Reinstate', id=ident('reinstate'), className='planner-text-button',
                            disabled=not row.get('left_at') or not editable),
            ], className='account-actions'),
            html.Div(id=ident('employment-message'), **{'aria-live': 'polite'}),
            html.H3('History'),
            html.Button('Show history', id=ident('show-history'), className='planner-text-button'),
            html.Div(id=ident('history'), **{'aria-live': 'polite'}),
        ], className='contractor-fields'),
    ], className='contractor-row')


HISTORY_LABELS = {
    'role_granted': 'Role granted', 'role_revoked': 'Role removed',
    'employee_created': 'Employee added', 'employee_details_edited': 'Details edited',
    'employee_left': 'Marked as left', 'employee_returned': 'Reinstated',
    'account_created': 'Account created', 'account_edited': 'Account edited',
    'activation_code_reissued': 'Activation code reissued',
    'activation_code_revoked': 'Activation code revoked', 'password_reset': 'Password reset',
    'account_disabled': 'Account disabled', 'account_enabled': 'Account enabled',
}


def history_list(entries):
    """Who did what to this person's roles, account and record, newest first."""
    if not entries:
        return html.P('Nothing has been recorded for this person yet.', className='planner-muted')
    return html.Ul([html.Li([
        html.Time(entry['changed_at'].astimezone().strftime('%d %b %Y %H:%M'),
                  dateTime=entry['changed_at'].isoformat(), className='history-time'),
        html.Span(HISTORY_LABELS[entry['action']], className='history-action'),
        html.Span(role_label(entry['role_name']), className='history-role')
        if entry['role_name'] else None,
        html.Span(f"{entry['actor_name']} {entry['actor_surname']}", className='planner-muted'),
    ], className='history-entry') for entry in entries], className='history-list')


# ------------------------------------------------------------------------ units

def units_section():
    return html.Div(id='operations-units-section', style={'display': 'none'}, children=[
        html.Div([html.H2('Production units'),
            html.P('Inactive units are hidden from the step editor and the supervisor list, but '
                   'nothing that uses them is deleted: steps, orders and history keep them.',
                   className='planner-muted'),
            html.Details([html.Summary('+ Add production unit'), html.Div([
                html.Div([
                    field('Name *', dcc.Input(id='new-unit-name', className='form-input', maxLength=256)),
                    field('Location', dcc.Input(id='new-unit-location', className='form-input', maxLength=256)),
                ], className='two-column'),
                html.Button('Add unit', id='create-unit', className='planner-secondary'),
                html.Div(id='new-unit-message', **{'aria-live': 'polite'}),
            ])], className='contractor-add'),
            dcc.Interval(id='units-load', interval=300, max_intervals=1),
            dcc.Store(id='units-revision'),
            html.Div(id='units-message', **{'aria-live': 'polite'}),
            html.Div(id='unit-list'),
        ], className='form-card'),
    ])


def unit_row(row):
    return html.Div([
        html.Div([html.Strong(row['name']),
                  html.Span(row['location'] or 'No location', className='contractor-contact'),
                  html.Span('Active' if row['active'] else 'Inactive',
                            className='account-state ' + ('active' if row['active'] else 'disabled'))],
                 className='unit-heading'),
        html.Button('Deactivate' if row['active'] else 'Activate',
                    # The id carries the state the button sets, so the label is never parsed.
                    id={'type': 'unit-active', 'index': row['id'], 'activate': not row['active']},
                    className='planner-text-button' + (' danger' if row['active'] else '')),
    ], className='unit-row')


# ---------------------------------------------------------------------- products

def products_section():
    return html.Div(id='operations-products-section', style={'display': 'none'}, children=[
        html.Div([html.H2('Products'),
            html.P('A product needs a name. Its picture is uploaded here, stored in the database '
                   'and shown on the Planner, Supervisor and Overview pages.', className='planner-muted'),
            html.Details([html.Summary('+ Add product'), html.Div([
                field('Name *', dcc.Input(id='new-product-name', className='form-input', maxLength=256)),
                field('Reference code', dcc.Input(id='new-product-code', className='form-input', maxLength=64)),
                field('Description', dcc.Textarea(id='new-product-description', className='form-input',
                                                  style={'height': '90px'})),
                html.Div([
                    field('First process name *', dcc.Input(id='new-product-process', value='Standard production',
                                                            className='form-input', maxLength=256)),
                    field('Process reference code', dcc.Input(id='new-product-process-code',
                                                              className='form-input', maxLength=64)),
                ], className='two-column'),
                upload_control('new-product'),
                html.P('The product is created with an empty process. Add its steps on the '
                       'Processes tab.', className='planner-muted'),
                html.Button('Create product', id='create-product', className='planner-secondary'),
                html.Div(id='new-product-message', **{'aria-live': 'polite'}),
            ])], className='contractor-add'),
            dcc.Interval(id='products-load', interval=300, max_intervals=1),
            dcc.Store(id='products-revision'),
            html.Div(id='products-message', **{'aria-live': 'polite'}),
            html.Div(id='product-list'),
        ], className='form-card'),
    ])


def upload_control(prefix, has_image=False):
    return html.Div([
        dcc.Upload(id=f'{prefix}-upload', className='image-upload', accept='image/*', children=html.Div([
            html.Span('Drag a picture here or '), html.A('choose a file'),
            html.Div('PNG, JPEG or WebP. Large photos are shrunk and re-encoded before storage.',
                     className='planner-muted'),
        ])),
        html.Div(id=f'{prefix}-preview', className='image-preview'),
        html.Button('Remove picture', id=f'{prefix}-clear', className='planner-text-button',
                    style={} if has_image else {'display': 'none'}),
    ], className='image-field')


def product_row(row):
    def ident(kind):
        return {'type': f'product-{kind}', 'index': row['id']}
    picture = (product_picture(row['id'], row['image_version'], className='product-thumb')
               or html.Div('No picture', className='product-thumb empty'))
    return html.Details([
        html.Summary([picture, html.Span(row['name'], className='contractor-name'),
                      html.Span(row['reference_code'] or 'No reference code',
                                className='contractor-contact')], id=ident('summary')),
        html.Div([
            html.Div([
                field('Name *', dcc.Input(id=ident('name'), value=row['name'],
                                          className='form-input', maxLength=256)),
                field('Reference code', dcc.Input(id=ident('code'), value=row['reference_code'],
                                                  className='form-input', maxLength=64)),
            ], className='two-column'),
            field('Description', dcc.Textarea(id=ident('description'), value=row['description'],
                                              className='form-input', style={'height': '90px'})),
            dcc.Checklist(id=ident('orderable'), options=[{'label': ' Available to order', 'value': 'yes'}],
                          value=['yes'] if row['is_orderable'] else []),
            html.Div([
                dcc.Upload(id=ident('upload'), className='image-upload', accept='image/*',
                           children=html.Div([html.Span('Replace the picture: '), html.A('choose a file')])),
                html.Button('Remove picture', id=ident('clear'), className='planner-text-button',
                            style={} if row['image_version'] else {'display': 'none'}),
            ], className='image-field'),
            html.Button('Apply', id=ident('apply'), className='planner-secondary'),
        ], className='contractor-fields'),
    ], className='contractor-row')


# --------------------------------------------------------------------- processes

def processes_section():
    return html.Div(id='operations-processes-section', style={'display': 'none'}, children=[
        html.Div([html.H2('Production processes'),
            html.P('Applying an edit saves a new process version with its own step details. '
                   'Existing work orders keep the route they were created with.',
                   className='planner-muted'),
            html.Div([
                field('Product *', dcc.Dropdown(id='process-product', options=[],
                                                placeholder='Select a product')),
                field('Process version *', dcc.Dropdown(id='process-version', options=[],
                                                        placeholder='Select a product first')),
            ], className='two-column'),
            html.Div([
                html.Button('Edit this process', id='open-process', className='planner-secondary'),
                html.Button('Start a new process for this product', id='new-process',
                            className='planner-text-button'),
            ], className='process-actions'),
            html.Div(id='process-message', **{'aria-live': 'polite'}),
            dcc.Store(id='process-draft'),
            dcc.Store(id='step-library'),
            html.Div(id='process-editor'),
        ], className='form-card'),
    ])


def draft_step_row(step, selected, position, total):
    def ident(kind):
        return {'type': f'draft-{kind}', 'index': step['key']}
    shared = step.get('source_step_id') is not None and not step.get('make_independent_copy', True)
    return html.Div([
        html.Button([html.Span(str(position), className='step-number'),
                     html.Span(step.get('name') or 'Unnamed step', className='draft-step-name'),
                     html.Span(duration(step.get('standard_time_seconds')), className='planner-muted'),
                     html.Span('Shared step', className='planner-badge') if shared else None],
                    id=ident('select'), className='draft-step' + (' selected' if selected else ''),
                    **{'aria-pressed': 'true' if selected else 'false'}),
        html.Div([
            # The arrows alone would be read as symbols; the label names the action.
            html.Button('▲', id=ident('up'), className='planner-text-button', disabled=position == 1,
                        title='Move earlier', **{'aria-label': 'Move earlier'}),
            html.Button('▼', id=ident('down'), className='planner-text-button', disabled=position == total,
                        title='Move later', **{'aria-label': 'Move later'}),
            html.Button('Remove', id=ident('remove'), className='planner-text-button'),
        ], className='draft-step-actions'),
    ], className='draft-step-row')


def step_editor(step, units):
    if step is None:
        return html.P('Select a step to edit it, or add one.', className='planner-muted')
    # Standards are stored in seconds, so minutes may be fractional (1392 s = 23.2 min).
    minutes = round((step.get('standard_time_seconds') or 0) / 60, 2) or None
    return html.Div([
        field('Step name *', dcc.Input(id='draft-name', value=step.get('name'),
                                       className='form-input', maxLength=256)),
        # Inactive units are offered only when this step already uses one.
        field('Production unit *', dcc.Dropdown(id='draft-unit', value=step.get('unit_id'),
              options=[{'label': unit['name'] + ('' if unit['active'] else translate(' · Inactive')),
                        'value': unit['id']} for unit in units
                       if unit['active'] or unit['id'] == step.get('unit_id')],
              placeholder='Select a production unit')),
        field('Standard time (minutes)', dcc.Input(id='draft-minutes', type='number', min=0.01, max=None,
                                                   step='any', value=minutes, className='form-input')),
        field('Instructions', dcc.Textarea(id='draft-instructions', value=step.get('instructions'),
              className='form-input', style={'height': '140px'},
              placeholder='Describe the smaller operations of this step, one per line.')),
        html.P('Record operations such as tack welding inside their parent step rather than as '
               'separate steps.', className='planner-muted'),
        html.Button('Keep changes', id='draft-keep', className='planner-secondary'),
    ], className='step-editor')


def version_options(rows):
    """Process versions for a selector, with their reference code when one is set."""
    return [{'label': f"{row['name'] or 'Production'} · v{row['version']}"
             + (f" · {row['reference_code']}" if row['reference_code'] else '')
             + ('' if row['is_active'] else ' · Inactive'), 'value': row['id']} for row in rows]


def process_editor(draft, units, library):
    steps = draft['steps']
    selected = next((step for step in steps if step['key'] == draft.get('selected')), None)
    version = ('a new process' if draft.get('process_id') is None
               else f"version {draft['version']} of {draft['product_name']}")
    return html.Div([
        notice(f"Editing {version}. Nothing is saved until you click Apply."),
        html.Div([
            field('Process name *', dcc.Input(id='draft-process-name', value=draft.get('name'),
                                              className='form-input', maxLength=256)),
            field('Reference code', dcc.Input(id='draft-process-code', value=draft.get('reference_code'),
                                              className='form-input', maxLength=64)),
        ], className='two-column'),
        html.P(translate('Reference codes are unique: version {version} keeps {code}, so a new '
                         'version needs its own code or none.').format(
                   version=draft['version'], code=draft['current_code'])
               if draft.get('current_code') else
               'Reference codes are unique across every process and version. Leave it empty if not needed.',
               className='planner-muted'),
        html.Div([
            html.Div([
                html.H3('Steps in order'),
                html.Div([draft_step_row(step, step is selected, index, len(steps))
                          for index, step in enumerate(steps, 1)]
                         or html.P('No steps yet. A process may be saved empty.',
                                   className='planner-muted')),
                html.Button('+ Add a step', id='draft-add', className='planner-text-button'),
                html.Details([html.Summary('+ Add an existing step'), html.Div([
                    dcc.Dropdown(id='draft-library', placeholder='Select a stored step', options=[
                        {'label': f"{row['name']} · {duration(row['standard_time_seconds'])}",
                         'value': row['id']} for row in library]),
                    dcc.Checklist(id='draft-copy', value=['copy'], options=[
                        {'label': ' Make independent copy', 'value': 'copy'}]),
                    html.P('A copy lets you change this step without affecting the other processes '
                           'that use it.', className='planner-muted'),
                    html.Button('Add selected step', id='draft-add-existing',
                                className='planner-text-button'),
                ])], className='contractor-add'),
            ], className='draft-list'),
            step_editor(selected, units),
        ], className='draft-grid'),
        html.P('Removing a step removes it from this process only. Reordering never changes '
               'another process that uses the same step.', className='planner-muted'),
        html.Div([
            html.Button('Apply', id='draft-apply', className='planner-secondary'),
            html.Button('Cancel', id='draft-cancel', className='planner-text-button'),
        ], className='process-actions'),
        html.Div(id='draft-message', **{'aria-live': 'polite'}),
    ])


def register_callbacks(app):

    @app.callback(*[Output(f'operations-{name}-section', 'style') for name in TABS],
                  Input('operations-tab', 'value'))
    @protect_callback(ROLE)
    def switch_tab(tab):
        return tuple({} if tab == name else {'display': 'none'} for name in TABS)

    # ------------------------------------------------------------------ units

    @app.callback(Output('unit-list', 'children'), Input('units-load', 'n_intervals'),
                  Input('units-revision', 'data'),
                  prevent_initial_call=True)
    @protect_callback(ROLE)
    def units(*_):
        try:
            rows = catalog.get_production_units_service(*caller(app))
            return [unit_row(row) for row in rows] or html.P('No production units yet.',
                                                             className='planner-muted')
        except HANDLED_ERRORS as exc:
            return failure(exc)

    @app.callback(Output('new-unit-message', 'children'), Output('units-revision', 'data'),
                  Input('create-unit', 'n_clicks'), State('new-unit-name', 'value'),
                  State('new-unit-location', 'value'), prevent_initial_call=True,
                  running=[(Output('create-unit', 'disabled'), True, False)])
    @protect_callback(ROLE)
    def create_unit(clicks, name, location):
        if not clicks:
            return no_update, no_update
        try:
            if not (name or '').strip():
                raise ValueError('Enter a name for the unit.')
            catalog.create_production_unit_service(*caller(app), name=name, location=optional_text(location))
            return notice('Production unit added.'), uuid4().hex
        except HANDLED_ERRORS as exc:
            return failure(exc, 'A unit with this name already exists at this location.'), no_update

    @app.callback(Output('units-message', 'children'),
                  Output('units-revision', 'data', allow_duplicate=True),
                  Input({'type': 'unit-active', 'index': ALL, 'activate': ALL}, 'n_clicks'),
                  prevent_initial_call=True)
    @protect_callback(ROLE)
    def toggle_unit(clicks):
        if not isinstance(ctx.triggered_id, dict) or not clicked():
            return no_update, no_update
        activate = bool(ctx.triggered_id['activate'])
        try:
            catalog.set_production_unit_active_service(*caller(app), ctx.triggered_id['index'], activate)
            return notice('Unit activated.' if activate else 'Unit deactivated.'), uuid4().hex
        except HANDLED_ERRORS as exc:
            return failure(exc), no_update

    # ----------------------------------------------------------------- employees

    @app.callback(Output('employees-page', 'data'),
                  Input('employees-prev', 'n_clicks'), Input('employees-next', 'n_clicks'),
                  Input('employee-search', 'value'), Input('employees-show-left', 'value'),
                  Input('new-employee-saved', 'data'), Input('refresh-employees', 'n_clicks'),
                  State('employees-data', 'data'), prevent_initial_call=True)
    @protect_callback(ROLE)
    def change_employee_page(previous, following, search, show_left, saved, refresh, data):
        # A new search, filter, employee or refresh starts again at the first page.
        if ctx.triggered_id not in ('employees-prev', 'employees-next') or not data:
            return PAGE_START
        return turn_page(data, forward=ctx.triggered_id == 'employees-next')

    @app.callback(Output('employee-list', 'children'), Output('employees-page-label', 'children'),
                  Output('employees-prev', 'disabled'), Output('employees-next', 'disabled'),
                  Output('employees-data', 'data'), Input('employees-page', 'data'),
                  State('employee-search', 'value'), State('employees-show-left', 'value'))
    @protect_callback(ROLE)
    def employees(page, search, show_left):
        page = page or PAGE_START
        try:
            actor, pool = caller(app)
            data = list_employees_service(actor, pool, search=search or '',
                                          include_left='left' in (show_left or ()),
                                          after=page['after'], before=page['before'])
            rows = data['employees']
            # Roles and accounts are read for this page's employees only.
            ids = [row['id'] for row in rows]
            assignable = get_assignable_roles_service(actor, pool)
            held = employee_roles_service(actor, pool, ids)
            accounts = {row['employee_id']: row for row in list_user_accounts_service(actor, pool, ids)}
        except HANDLED_ERRORS as exc:
            return failure(exc), '', True, True, None
        listing = [employee_row(row, assignable, held.get(row['id'], ()),
                                accounts.get(row['id']), row['id'] != actor.employee_id)
                   for row in rows] or html.P(
            'No employees match.' if (search or '').strip() else 'No employees yet. Add the first one above.',
            className='planner-muted')
        return (listing, page_label(page['number'], len(rows), EMPLOYEE_PAGE_SIZE),
                not data['previous'], not data['next'],
                {'number': page['number'], 'previous': data['previous'], 'next': data['next']})

    # Every output stays inside this row: Dash does not dispatch a pattern-matching
    # callback that also writes a plain output, so the summary is refreshed here.
    @app.callback(Output({'type': 'employee-roles-message', 'index': MATCH}, 'children'),
                  Output({'type': 'employee-summary', 'index': MATCH}, 'children'),
                  Input({'type': 'employee-save-roles', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'employee-save-roles', 'index': MATCH}, 'id'),
                  State({'type': 'employee-roles', 'index': MATCH}, 'value'),
                  prevent_initial_call=True)
    @protect_callback(ROLE)
    def save_roles(clicks, identifier, roles):
        if not clicks:
            return no_update, no_update
        employee_id = identifier['index']
        try:
            actor, pool = caller(app)
            changed = set_employee_roles_service(actor, pool, employee_id, roles or [])
            # Re-read so the summary shows the stored roles, not the submitted boxes.
            row = next(iter(list_employees_service(actor, pool, employee_ids=[employee_id])['employees']), None)
            held = employee_roles_service(actor, pool, [employee_id]).get(employee_id, ())
            summary = employee_summary(row, held) if row else no_update
            if not changed['added'] and not changed['removed']:
                return notice('No role changes to save.'), summary
            parts = [f"Added {', '.join(role_label(r) for r in changed['added'])}."
                     if changed['added'] else '',
                     f"Removed {', '.join(role_label(r) for r in changed['removed'])}."
                     if changed['removed'] else '']
            return notice(' '.join(part for part in parts if part)), summary
        except HANDLED_ERRORS as exc:
            return failure(exc), no_update

    @app.callback(Output('new-employee-saved', 'data'), Output('new-employee-message', 'children'),
                  Input('new-employee-save', 'n_clicks'), State('new-employee-name', 'value'),
                  State('new-employee-surname', 'value'), State('new-employee-email', 'value'),
                  State('new-employee-phone', 'value'), State('new-employee-birth', 'date'),
                  prevent_initial_call=True,
                  running=[(Output('new-employee-save', 'disabled'), True, False)])
    @protect_callback(ROLE)
    def add_employee(clicks, name, surname, email, phone, birth):
        if not clicks:
            return no_update, no_update
        try:
            if not (name or '').strip() or not (surname or '').strip():
                raise ValueError('Enter both a first name and a surname.')
            key = create_employee_service(*caller(app), name=name.strip(), surname=surname.strip(),
                                          email=optional_text(email), phone_number=optional_text(phone),
                                          birth_date=date.fromisoformat(birth) if birth else None)
            return {'id': key, 'revision': uuid4().hex}, notice('Employee added.')
        except HANDLED_ERRORS as exc:
            return no_update, failure(exc, 'That email address already belongs to another employee.')

    @app.callback(Output({'type': 'employee-message', 'index': MATCH}, 'children'),
                  Output({'type': 'employee-summary', 'index': MATCH}, 'children'),
                  Input({'type': 'employee-apply', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'employee-apply', 'index': MATCH}, 'id'),
                  State({'type': 'employee-name', 'index': MATCH}, 'value'),
                  State({'type': 'employee-surname', 'index': MATCH}, 'value'),
                  State({'type': 'employee-email', 'index': MATCH}, 'value'),
                  State({'type': 'employee-phone', 'index': MATCH}, 'value'), prevent_initial_call=True)
    @protect_callback(ROLE)
    def edit_employee(clicks, identifier, name, surname, email, phone):
        if not clicks:
            return no_update, no_update
        try:
            if not (name or '').strip() or not (surname or '').strip():
                raise ValueError('Enter both a first name and a surname.')
            actor, pool = caller(app)
            changes = dict(name=name.strip(), surname=surname.strip(),
                           email=optional_text(email), phone_number=optional_text(phone))
            edit_employee_service(actor, identifier['index'], pool, **changes)
            return notice('Changes saved.'), employee_summary(
                {**changes, 'phone_number': changes['phone_number']})
        except HANDLED_ERRORS as exc:
            return failure(exc, 'That email address already belongs to another employee.'), no_update

    @app.callback(Output({'type': 'employee-history', 'index': MATCH}, 'children'),
                  Input({'type': 'employee-show-history', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'employee-show-history', 'index': MATCH}, 'id'),
                  prevent_initial_call=True)
    @protect_callback(ROLE)
    def show_history(clicks, identifier):
        if not clicks:
            return no_update
        try:
            actor, pool = caller(app)
            return history_list(get_employee_history_service(actor, pool, identifier['index']))
        except HANDLED_ERRORS as exc:
            return failure(exc)

    @app.callback(Output({'type': 'employee-employment-message', 'index': MATCH}, 'children'),
                  Output({'type': 'employee-confirm-leave', 'index': MATCH}, 'style'),
                  Output({'type': 'employee-leave', 'index': MATCH}, 'disabled'),
                  Output({'type': 'employee-reinstate', 'index': MATCH}, 'disabled'),
                  Input({'type': 'employee-leave', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'employee-confirm-leave', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'employee-reinstate', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'employee-leave', 'index': MATCH}, 'id'),
                  prevent_initial_call=True)
    @protect_callback(ROLE)
    def employment(leave, confirm, reinstate, identifier):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not clicked():
            return no_update, no_update, no_update, no_update
        hidden = {'display': 'none'}
        if trigger['type'] == 'employee-leave':
            return (notice('Their account will be disabled and their unit assignments will end '
                           'now. Confirm to continue.', True), {}, no_update, no_update)
        try:
            if trigger['type'] == 'employee-confirm-leave':
                mark_employee_left_service(*caller(app), identifier['index'])
                return (notice('Marked as left. Refresh the list to update it.'),
                        hidden, True, False)
            reinstate_employee_service(*caller(app), identifier['index'])
            return (notice('Reinstated. Enable their account when they need to sign in again.'),
                    hidden, False, True)
        except HANDLED_ERRORS as exc:
            return failure(exc), hidden, no_update, no_update

    # ------------------------------------------------------- accounts, per employee

    @app.callback(Output({'type': 'employee-account', 'index': MATCH}, 'children'),
                  Output({'type': 'employee-account-message', 'index': MATCH}, 'children'),
                  Input({'type': 'employee-create-account', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'employee-reissue', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'employee-revoke', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'employee-reset', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'employee-toggle-active', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'employee-create-account', 'index': MATCH}, 'id'),
                  State({'type': 'employee-new-username', 'index': MATCH}, 'value'),
                  prevent_initial_call=True)
    @protect_callback(ROLE)
    def administer_account(*values):
        *clicks, identifier, new_username = values
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not any(clicks):
            return no_update, no_update
        employee_id, action = identifier['index'], trigger['type']
        try:
            actor, pool = caller(app)
            account = next(iter(list_user_accounts_service(actor, pool, [employee_id])), None)
            message = ''
            if action == 'employee-create-account':
                if account is not None:
                    raise ValueError('This employee already has an account.')
                if not (new_username or '').strip():
                    raise ValueError('Enter a username for the new account.')
                name = new_username.strip()
                _, code = create_user_account_service(actor, pool, employee_id, name)
                message = code_handout(name, code, 'Account created. Hand over the username '
                                       'and code; the code works once and expires in 7 days.')
            elif account is None:
                raise ValueError('This employee has no account yet.')
            elif action == 'employee-reissue':
                code = reissue_activation_code_service(actor, pool, account['id'])
                message = code_handout(account['username'], code,
                                       'A new code was issued. Any earlier code no longer works.')
            elif action == 'employee-revoke':
                revoked = revoke_activation_codes_service(actor, pool, account['id'])
                message = notice(f"{revoked} code(s) revoked. This person cannot activate "
                                 'their account until you issue a new one.'
                                 if revoked else 'There was no code left to revoke.')
            elif action == 'employee-reset':
                code = reset_account_password_service(actor, pool, account['id'])
                message = code_handout(account['username'], code,
                                       'The password was cleared and the account is waiting '
                                       'for activation again. Hand over this code.')
            elif action == 'employee-toggle-active':
                enabled = not account['is_active']
                set_account_active_service(actor, pool, account['id'], enabled)
                message = notice('Account enabled.' if enabled else
                                 'Account disabled. Their sessions stop at the next request.')
            # Re-read so the panel shows the stored state rather than the action taken.
            refreshed = next(iter(list_user_accounts_service(actor, pool, [employee_id])), None)
            return account_block({'id': employee_id}, refreshed), message
        except HANDLED_ERRORS as exc:
            return no_update, failure(exc, 'That username is already taken.')

    # ------------------------------------------------------------------ products

    @app.callback(Output('product-list', 'children'), Output('process-product', 'options'),
                  Input('products-load', 'n_intervals'), Input('products-revision', 'data'),
                  prevent_initial_call=True)
    @protect_callback(ROLE)
    def products(*_):
        try:
            rows = catalog.get_catalog_service(*caller(app))
            options = [{'label': row['name'] + ('' if row['is_orderable'] else ' · Unavailable'),
                        'value': row['id']} for row in rows]
            listing = [product_row(row) for row in rows] or html.P(
                'No products yet. Add the first one above.', className='planner-muted')
            return listing, options
        except HANDLED_ERRORS as exc:
            return failure(exc), []

    @app.callback(Output('new-product-preview', 'children'), Input('new-product-upload', 'contents'))
    @protect_callback(ROLE)
    def preview_new_product(contents):
        return html.Img(src=contents, alt='Selected picture') if contents else ''

    @app.callback(Output('new-product-message', 'children'), Output('products-revision', 'data'),
                  Input('create-product', 'n_clicks'), State('new-product-name', 'value'),
                  State('new-product-code', 'value'), State('new-product-description', 'value'),
                  State('new-product-process', 'value'), State('new-product-process-code', 'value'),
                  State('new-product-upload', 'contents'), prevent_initial_call=True,
                  running=[(Output('create-product', 'disabled'), True, False)])
    @protect_callback(ROLE)
    def create_product(clicks, name, code, description, process_name, process_code, contents):
        if not clicks:
            return no_update, no_update
        try:
            if not (name or '').strip() or not (process_name or '').strip():
                raise ValueError('Enter a product name and a name for its first process.')
            actor, pool = caller(app)
            created = catalog.create_product_with_process_service(
                actor, pool,
                product=dict(name=name.strip(), reference_code=optional_text(code),
                             description=optional_text(description)),
                process=dict(name=process_name.strip(), reference_code=optional_text(process_code)))
            if contents:
                # A rejected picture must not hide the fact that the product was created.
                try:
                    catalog.set_product_image_service(actor, pool, created['product_id'], contents)
                except HANDLED_ERRORS as exc:
                    return html.Div([notice('Product created without its picture.'), failure(exc)]), uuid4().hex
            return notice('Product created. Add its process steps on the Processes tab.'), uuid4().hex
        except HANDLED_ERRORS as exc:
            return failure(exc, 'That product or process reference code is already used.'), no_update

    @app.callback(Output('products-message', 'children'),
                  Output('products-revision', 'data', allow_duplicate=True),
                  Input({'type': 'product-apply', 'index': ALL}, 'n_clicks'),
                  Input({'type': 'product-upload', 'index': ALL}, 'contents'),
                  Input({'type': 'product-clear', 'index': ALL}, 'n_clicks'),
                  State({'type': 'product-apply', 'index': ALL}, 'id'),
                  State({'type': 'product-name', 'index': ALL}, 'value'),
                  State({'type': 'product-code', 'index': ALL}, 'value'),
                  State({'type': 'product-description', 'index': ALL}, 'value'),
                  State({'type': 'product-orderable', 'index': ALL}, 'value'),
                  prevent_initial_call=True)
    @protect_callback(ROLE)
    def edit_product(applies, uploads, clears, ids, names, codes, descriptions, orderables):
        # Every product change re-renders the list, so the reply goes to the section,
        # not to a row that is about to be replaced.
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update, no_update
        product_id = trigger['index']
        row = next((index for index, ident in enumerate(ids) if ident['index'] == product_id), None)
        if row is None:
            return no_update, no_update
        try:
            actor, pool = caller(app)
            if trigger['type'] == 'product-upload':
                if not uploads[row]:
                    return no_update, no_update
                catalog.set_product_image_service(actor, pool, product_id, uploads[row])
                return notice('Picture updated.'), uuid4().hex
            if trigger['type'] == 'product-clear':
                if not clears[row]:
                    return no_update, no_update
                catalog.set_product_image_service(actor, pool, product_id, None)
                return notice('Picture removed.'), uuid4().hex
            if not applies[row]:
                return no_update, no_update
            if not (names[row] or '').strip():
                raise ValueError('Enter a product name.')
            catalog.edit_product_type_service(
                actor, pool, product_id, name=names[row].strip(),
                reference_code=optional_text(codes[row]),
                description=optional_text(descriptions[row]),
                is_orderable=bool(orderables[row]))
            return notice('Changes saved.'), uuid4().hex
        except HANDLED_ERRORS as exc:
            return failure(exc, 'That product name or reference code is already used.'), no_update

    # ----------------------------------------------------------------- processes

    @app.callback(Output('process-version', 'options'), Output('process-version', 'value'),
                  Output('process-version', 'placeholder'), Input('process-product', 'value'))
    @protect_callback(ROLE)
    def process_versions(product_id):
        if product_id is None:
            return [], None, 'Select a product first'
        try:
            rows = catalog.get_product_processes_service(*caller(app), product_id)
            options = version_options(rows)
            return (options, rows[0]['id'] if len(rows) == 1 else None,
                    'Select a process version' if options else 'This product has no process yet')
        except HANDLED_ERRORS:
            # The editor callback reports the associated read error.
            return [], None, 'Select a product first'

    def capture(draft, name, unit_id, minutes, instructions):
        """Fold the open editor's values into the draft so switching steps keeps them."""
        step = next((s for s in draft['steps'] if s['key'] == draft.get('selected')), None)
        if step is None or name is None and unit_id is None and minutes is None and instructions is None:
            return draft
        step['name'] = (name or '').strip() or None
        step['unit_id'] = unit_id
        step['instructions'] = (instructions or '').strip() or None
        step['standard_time_seconds'] = round(minutes * 60) if minutes else None
        return draft

    # Loading owns its own callback because its inputs must exist before the editor does.
    @app.callback(Output('process-draft', 'data'), Output('process-message', 'children'),
                  Output('step-library', 'data'),
                  Input('open-process', 'n_clicks'), Input('new-process', 'n_clicks'),
                  State('process-product', 'value'), State('process-version', 'value'),
                  prevent_initial_call=True)
    @protect_callback(ROLE)
    def load_draft(_open, _new, product_id, process_id):
        if not isinstance(ctx.triggered_id, str):
            return (no_update,) * 3
        try:
            actor, pool = caller(app)
            if product_id is None:
                raise ValueError('Select a product first.')
            library = catalog.get_step_library_service(actor, pool)
            product_name = next((row['name'] for row in catalog.get_catalog_service(actor, pool)
                                 if row['id'] == product_id), 'this product')
            if ctx.triggered_id == 'new-process':
                return ({'product_id': product_id, 'process_id': None, 'name': '', 'version': None,
                         'reference_code': '', 'current_code': None,
                         'product_name': product_name, 'steps': [], 'selected': None}, '', library)
            if process_id is None:
                raise ValueError('Select the process version to edit.')
            versions = catalog.get_product_processes_service(actor, pool, product_id)
            current = next((row for row in versions if row['id'] == process_id), None)
            if current is None:
                raise ValueError('That process belongs to another product. Refresh the list.')
            steps = [{'key': uuid4().hex, 'association_id': row['association_id'],
                      'source_step_id': None, 'make_independent_copy': True,
                      'name': row['name'], 'unit_id': row['unit_id'],
                      'instructions': row['instructions'],
                      'standard_time_seconds': row['standard_time_seconds']}
                     for row in catalog.get_process_steps_service(actor, pool, process_id)]
            return ({'product_id': product_id, 'process_id': process_id,
                     'name': current['name'] or '', 'version': current['version'],
                     # A saved edit is a new version, which cannot reuse this version's code.
                     'reference_code': '', 'current_code': current['reference_code'],
                     'product_name': product_name, 'steps': steps,
                     'selected': steps[0]['key'] if steps else None}, '', library)
        except HANDLED_ERRORS as exc:
            return no_update, failure(exc), no_update

    # Every input below lives inside the rendered editor, so this callback only ever
    # runs while that editor exists.
    @app.callback(Output('process-draft', 'data', allow_duplicate=True),
                  Output('process-message', 'children', allow_duplicate=True),
                  Input('draft-add', 'n_clicks'), Input('draft-add-existing', 'n_clicks'),
                  Input('draft-keep', 'n_clicks'), Input('draft-cancel', 'n_clicks'),
                  Input({'type': 'draft-select', 'index': ALL}, 'n_clicks'),
                  Input({'type': 'draft-up', 'index': ALL}, 'n_clicks'),
                  Input({'type': 'draft-down', 'index': ALL}, 'n_clicks'),
                  Input({'type': 'draft-remove', 'index': ALL}, 'n_clicks'),
                  State('process-draft', 'data'), State('step-library', 'data'),
                  State('draft-process-name', 'value'), State('draft-process-code', 'value'),
                  State('draft-name', 'value'),
                  State('draft-unit', 'value'), State('draft-minutes', 'value'),
                  State('draft-instructions', 'value'), State('draft-library', 'value'),
                  State('draft-copy', 'value'), prevent_initial_call=True)
    @protect_callback(ROLE)
    def edit_draft(_add, _existing, _keep, _cancel, _select, _up, _down, _remove,
                   draft, library, process_name, process_code, name, unit_id, minutes, instructions,
                   library_choice, make_copy):
        trigger = ctx.triggered_id
        if trigger is None or draft is None:
            return no_update, no_update
        action = trigger['type'] if isinstance(trigger, dict) else trigger
        try:
            if action == 'draft-cancel':
                return None, notice('Draft discarded. Nothing was saved.')
            draft = capture(dict(draft, steps=[dict(s) for s in draft['steps']]),
                            name, unit_id, minutes, instructions)
            draft['name'] = (process_name or '').strip()
            draft['reference_code'] = (process_code or '').strip()
            if action == 'draft-add':
                step = {'key': uuid4().hex, 'association_id': None, 'source_step_id': None,
                        'make_independent_copy': True, 'name': None, 'unit_id': None,
                        'instructions': None, 'standard_time_seconds': None}
                draft['steps'].append(step)
                draft['selected'] = step['key']
            elif action == 'draft-add-existing':
                source = next((row for row in (library or []) if row['id'] == library_choice), None)
                if source is None:
                    raise ValueError('Select a stored step to add.')
                step = {'key': uuid4().hex, 'association_id': None, 'source_step_id': source['id'],
                        'make_independent_copy': 'copy' in (make_copy or []),
                        'name': source['name'], 'unit_id': source['unit_id'],
                        'instructions': source['instructions'],
                        'standard_time_seconds': source['standard_time_seconds']}
                draft['steps'].append(step)
                draft['selected'] = step['key']
            elif action == 'draft-select':
                draft['selected'] = trigger['index']
            elif action == 'draft-remove':
                draft['steps'] = [s for s in draft['steps'] if s['key'] != trigger['index']]
                if draft['selected'] == trigger['index']:
                    draft['selected'] = draft['steps'][0]['key'] if draft['steps'] else None
            elif action in ('draft-up', 'draft-down'):
                keys = [s['key'] for s in draft['steps']]
                position = keys.index(trigger['index'])
                target = position - 1 if action == 'draft-up' else position + 1
                if 0 <= target < len(keys):
                    steps = draft['steps']
                    steps[position], steps[target] = steps[target], steps[position]
                draft['selected'] = trigger['index']
            return draft, ''
        except HANDLED_ERRORS as exc:
            return no_update, failure(exc)

    @app.callback(Output('process-editor', 'children'), Input('process-draft', 'data'),
                  State('step-library', 'data'))
    @protect_callback(ROLE)
    def render_editor(draft, library):
        if not draft:
            return ''
        try:
            units = catalog.get_production_units_service(*caller(app))
            return process_editor(draft, units, library or [])
        except HANDLED_ERRORS as exc:
            return failure(exc)

    def step_payload(step, new_process):
        entry = {}
        if not new_process and step.get('association_id'):
            entry['association_id'] = step['association_id']
        elif step.get('source_step_id'):
            entry['source_step_id'] = step['source_step_id']
            entry['make_independent_copy'] = bool(step.get('make_independent_copy', True))
        entry.update(name=step.get('name'), unit_id=step.get('unit_id'),
                     instructions=step.get('instructions') or None,
                     standard_time_seconds=step.get('standard_time_seconds'))
        return entry

    # A successful Apply closes the editor, so its confirmation belongs to the section.
    @app.callback(Output('draft-message', 'children'),
                  Output('process-message', 'children', allow_duplicate=True),
                  Output('process-draft', 'data', allow_duplicate=True),
                  Output('process-version', 'options', allow_duplicate=True),
                  Input('draft-apply', 'n_clicks'), State('process-draft', 'data'),
                  State('draft-process-name', 'value'), State('draft-process-code', 'value'),
                  State('draft-name', 'value'),
                  State('draft-unit', 'value'), State('draft-minutes', 'value'),
                  State('draft-instructions', 'value'), prevent_initial_call=True,
                  running=[(Output('draft-apply', 'disabled'), True, False)])
    @protect_callback(ROLE)
    def apply_draft(clicks, draft, process_name, process_code, name, unit_id, minutes, instructions):
        if not clicks or not draft:
            return (no_update,) * 4
        try:
            draft = capture(dict(draft, steps=[dict(s) for s in draft['steps']]),
                            name, unit_id, minutes, instructions)
            process_name = (process_name or '').strip()
            if not process_name:
                raise ValueError('Enter a name for this process.')
            for position, step in enumerate(draft['steps'], 1):
                if not (step.get('name') or '').strip():
                    raise ValueError(f'Step {position} needs a name.')
                if step.get('unit_id') is None:
                    raise ValueError(f"Step {position} needs a production unit.")
            new_process = draft.get('process_id') is None
            steps = [step_payload(step, new_process) for step in draft['steps']]
            actor, pool = caller(app)
            if new_process:
                catalog.create_product_process_service(
                    actor, pool, draft['product_id'],
                    process=dict(name=process_name, reference_code=optional_text(process_code)), steps=steps)
                saved = 'Process created.'
            else:
                result = catalog.save_process_service(
                    actor, pool, draft['process_id'], steps=steps, name=process_name,
                    reference_code=optional_text(process_code))
                saved = f"Saved as version {result['process']['version']}."
            versions = catalog.get_product_processes_service(actor, pool, draft['product_id'])
            options = version_options(versions)
            return ('', notice(saved + ' Earlier versions and existing orders are unchanged.'),
                    None, options)
        except HANDLED_ERRORS as exc:
            return (failure(exc, 'That process reference code is already used.'),
                    '', no_update, no_update)
