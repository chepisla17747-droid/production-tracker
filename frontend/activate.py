"""Public first sign-in: an activation code, a chosen password, and a details check.

The code is the only credential, so every callback here is public and the service
re-checks the username and code on each call. Unusable codes all report one message.
"""
from dash import html, dcc, Input, Output, State, no_update

from frontend.auth import public_credential_callback
from backend.service.auth_service import WEBSITE_ROLES
from frontend.common import HANDLED_ERRORS, failure, notice, optional_text, role_label


def activate_page(username=''):
    return html.Div(className='login-page', children=[
        html.Div(className='header', children=[
            html.Div('⚙', className='logo'),
            html.H1('Production Tracking System'),
            html.P('Set up your account.'),
        ]),
        html.Div(className='login-card', children=[
            html.H2('First sign-in'),
            html.P('Enter the username and activation code your administrator gave you.',
                   className='subtitle'),
            html.Div(id='activate-step-code', children=[
                html.Label('Username', className='label'), html.Span(' *', className='required'),
                dcc.Input(id='activate-username', value=username, className='input',
                          placeholder='Your username'),
                html.Label('Activation code', className='label'),
                html.Span(' *', className='required'),
                dcc.Input(id='activate-code', className='input activation-code',
                          placeholder='XXXX-XXXX'),
                html.Button('Continue', id='activate-check', className='login-button'),
            ]),
            html.Div(id='activate-step-details', style={'display': 'none'}, children=[
                html.Div(id='activate-details', className='activate-details'),
                html.Label('Choose a password', className='label'),
                html.Span(' *', className='required'),
                dcc.Input(id='activate-password', type='password', className='input',
                          placeholder='At least 8 characters'),
                html.Label('Repeat password', className='label'),
                html.Span(' *', className='required'),
                dcc.Input(id='activate-repeat', type='password', className='input',
                          placeholder='Type it again'),
                html.P('Check your contact details and correct them if they are wrong.',
                       className='planner-muted'),
                html.Label('Email', className='label'),
                dcc.Input(id='activate-email', type='email', className='input', maxLength=256),
                html.Label('Phone', className='label'),
                dcc.Input(id='activate-phone', type='tel', className='input', maxLength=16),
                html.Button('Finish and sign in', id='activate-finish', className='login-button'),
            ]),
            html.Div(id='activate-message', **{'aria-live': 'polite'}),
            dcc.Store(id='activate-role'),
        ]),
    ])


def details_panel(details):
    employee = details['employee'] or {}
    roles = details['roles']
    return html.Dl([
        html.Div([html.Dt('Name'),
                  html.Dd(f"{employee.get('name', '')} {employee.get('surname', '')}".strip()
                          or 'Not recorded')], className='profile-detail'),
        html.Div([html.Dt('Username'), html.Dd(details['username'])], className='profile-detail'),
        html.Div([html.Dt('Roles'),
                  html.Dd(', '.join(role_label(role) for role in roles) if roles
                          else 'None yet. Your administrator gives you these.')],
                 className='profile-detail'),
    ])


def register_callbacks(app):
    def pool():
        # Activation writes to account_private, which only the privileged role may touch.
        state = app.server.state
        return state.admin_pool or state.db_pool

    @app.callback(Output('activate-step-code', 'style'), Output('activate-step-details', 'style'),
                  Output('activate-details', 'children'), Output('activate-email', 'value'),
                  Output('activate-phone', 'value'), Output('activate-message', 'children'),
                  Input('activate-check', 'n_clicks'), State('activate-username', 'value'),
                  State('activate-code', 'value'), prevent_initial_call=True,
                  running=[(Output('activate-check', 'disabled'), True, False)])
    @public_credential_callback('activate-username')
    def check_code(clicks, username, code):
        from backend.service.user_account_service import describe_activation_service
        if not clicks:
            return (no_update,) * 6
        try:
            details = describe_activation_service(pool(), username, code)
            employee = details['employee'] or {}
            return ({'display': 'none'}, {}, details_panel(details),
                    employee.get('email'), employee.get('phone_number'), '')
        except HANDLED_ERRORS as exc:
            return no_update, no_update, no_update, no_update, no_update, failure(exc)

    @app.callback(Output('activate-message', 'children', allow_duplicate=True),
                  Output('activate-role', 'data'),
                  Input('activate-finish', 'n_clicks'), State('activate-username', 'value'),
                  State('activate-code', 'value'), State('activate-password', 'value'),
                  State('activate-repeat', 'value'), State('activate-email', 'value'),
                  State('activate-phone', 'value'), prevent_initial_call=True,
                  running=[(Output('activate-finish', 'disabled'), True, False)])
    @public_credential_callback('activate-username')
    def finish(clicks, username, code, password, repeated, email, phone):
        from backend.service.user_account_service import complete_account_setup_service
        if not clicks:
            return no_update, no_update
        try:
            if not password:
                raise ValueError('Choose a password.')
            if password != repeated:
                raise ValueError('The two passwords do not match.')
            done = complete_account_setup_service(
                pool(), username, code, password,
                email=optional_text(email), phone_number=optional_text(phone))
            # Default roles such as `employee` open no page and cannot be signed in with.
            roles = [role for role in done['roles'] if role in WEBSITE_ROLES]
            if not roles:
                return html.Div([
                    notice(f"Your account {done['username']} is ready. Your administrator "
                           'still has to give you access to a page before you can sign in.'),
                    html.A('Back to sign in', href='/', className='nav-link'),
                ]), None
            # The browser now signs in with the password just chosen.
            return notice('Signing you in…'), {'role': roles[0]}
        except HANDLED_ERRORS as exc:
            return failure(exc), None

    # Reuses the ordinary login endpoint, so activation grants no session of its own.
    app.clientside_callback(
        """
        async function(ready, username, password) {
            const keep = window.dash_clientside.no_update;
            if (!ready || !ready.role) return [keep, keep, keep];
            try {
                const response = await fetch("/auth/login", {
                    method: "POST", credentials: "same-origin",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({username, password, role: ready.role})
                });
                const data = await response.json();
                if (!response.ok) {
                    return [keep, keep,
                            "Your password is set. Please sign in with it."];
                }
                return ["/" + (data.page || data.role), data.csrf_token, ""];
            } catch (error) {
                return [keep, keep, "Your password is set. Please sign in with it."];
            }
        }
        """,
        Output('url', 'pathname'), Output('csrf-token', 'data'),
        Output('activate-message', 'children', allow_duplicate=True),
        Input('activate-role', 'data'), State('activate-username', 'value'),
        State('activate-password', 'value'), prevent_initial_call=True,
    )
