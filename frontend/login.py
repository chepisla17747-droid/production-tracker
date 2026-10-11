"""Login page and callbacks from the standalone frontend prototype."""
from urllib.parse import parse_qs, urlsplit

from dash import ALL, html, dcc, Input, Output, State



# =====================================
# LOGIN PAGE
# =====================================



def login_page():
    return html.Div(
        className="login-page",
        children=[
            html.Div(
                className="header",
                children=[
                    html.Div("⚙", className="logo"),
                    html.H1("Production Tracking System"),
                    html.P("Track Today. Build Tomorrow."),
                ],
            ),
            html.Div(
                className="login-card",
                children=[
                    html.H2("Welcome"),
                    html.P("Sign in to continue", className="subtitle"),
                    # User Role
                    html.Label("User Role", className="label"),
                    html.Span(" *", className="required"),
                    dcc.Dropdown(
                        id="role",
                        options=[
                            {"label": "Planner", "value": "planner"},
                            {"label": "Supervisor", "value": "supervisor"},
                            {"label": "Manager", "value": "manager"},
                            {"label": "Operations Administrator", "value": "operations_admin"},
                        ],
                        placeholder="Select role",
                        className="dropdown",
                    ),
                    # Username
                    html.Label("Username", className="label"),
                    html.Span(" *", className="required"),
                    dcc.Input(
                        id="username",
                        type="text",
                        placeholder="Enter your username",
                        className="input",
                    ),
                    # Password
                    html.Label("Password", className="label"),
                    html.Span(" *", className="required"),
                    html.Div(
                        className="password-wrapper",
                        children=[
                            dcc.Input(
                                id="password",
                                type="password",
                                placeholder="Enter your password",
                                className="input password-input",
                            ),
                            html.Button(
                                "👁", id="toggle-password", className="password-eye"
                            ),
                        ],
                    ),
                    # Sign In
                    html.Button(
                        ["Sign In ", html.Span("→")],
                        id="login-button",
                        className="login-button",
                    ),
                    html.Div(id="login-message"),
                    language_switch(),
                    html.P([
                        "First time here? ",
                        html.A("Activate your account", href="/activate", className="nav-link"),
                        " with the code your administrator gave you.",
                    ], className="login-help"),
                ],
            ),
            html.Div(
                className="footer",
                children=[
                    html.P(
                        "BETTER PRODUCTION  •  HIGHER EFFICIENCY  •",
                        className="footer-main",
                    ),
                    html.P("A STRONGER TOMORROW", className="footer-main"),
                    html.P(
                        "Industrial Terminal v2.4.1 • Station Safe-Mode Active",
                        className="footer-sub",
                    ),
                ],
            ),
        ],
    )


def username_from_search(search):
    """Prefill the activation form when the address carries a username."""
    values = parse_qs(urlsplit(search or '').query).get('username', [])
    return values[0] if values else ''


PAGE_LINKS = (('manager', 'Overview'), ('planner', 'Planning'), ('orders', 'Orders'),
              ('supervisor', 'My work'), ('history', 'Order history'),
              ('operations', 'Administration'), ('statistics', 'Statistics'),
              ('profile', 'Profile'))


def browser_messages():
    """Text the sign-in callback needs in the browser, translated before it is sent.

    That callback runs in the browser and cannot reach the catalogue, so its messages,
    including the ones the server returns as `detail`, are looked up here.
    """
    from frontend.i18n import translate

    sources = (
        'Please fill in all required fields.',
        'Please check your login details.',
        'Could not contact the server. Please try again.',
        'Invalid username or password',
        'Your account has been disabled. Please contact the administration if you '
        'think this is a mistake.',
        'No access to the requested role',
        'Too many login attempts',
        'Authentication required',
        'Logout failed. Please try again.',
        'Could not log out. Check your connection and try again.',
    )
    return {source: translate(source) for source in sources}


def language_switch():
    """Switch the interface language. The chosen one is shown as pressed."""
    from frontend.i18n import LANGUAGES, LANGUAGE_NAMES, current_language

    chosen = current_language()
    return html.Div([
        html.Button(
            html.Img(src=f'/assets/images/flag-{code}.svg', alt=LANGUAGE_NAMES[code]),
            id={'type': 'language', 'index': code}, title=LANGUAGE_NAMES[code],
            className='language-button' + (' chosen' if code == chosen else ''),
            **{'aria-pressed': 'true' if code == chosen else 'false'})
        for code in LANGUAGES
    ], className='language-switch', role='group', **{'aria-label': 'Language'})


def top_bar(title, actor, page):
    """The brand and page title, followed by the page links and log-out controls."""
    return html.Div(className='top-bar', children=[
        html.Div([html.Div('▰', className='brand-icon'), html.Div([
            html.Div('FLOOR OPS', className='brand-name'),
            html.Div(title, className='brand-title'),
        ])], className='brand'), logout_controls(actor, page),
    ])


def logout_controls(actor=None, current=None):
    """Log out, preceded by links to the other pages this session may open.

    The links are convenience only: the server rechecks access for every page and
    callback, so hiding a link never acts as the access control.
    """
    from backend.service.auth_service import PAGE_ROLES

    links = [html.A(label, href='/' + page,
                    className='nav-link active' if page == current else 'nav-link')
             for page, label in PAGE_LINKS
             if actor and set(PAGE_ROLES[page]) & set(actor.allowed_roles)]
    return html.Div([
        html.Nav(links, className='page-nav') if links else None,
        html.Button('Log out', id='logout-button', type='button'),
        language_switch(),
        html.Span(id='logout-message', role='alert'),
    ], className='logout-controls')


def register_callbacks(app):
    """Register this page's callbacks on the supplied Dash app."""

    # The language lives in a cookie so the server can read it while rendering a page.
    # Reloading is what applies it: every page and callback output is translated on the
    # way out, and the current page was already rendered in the previous language.
    app.clientside_callback(
        """
        function(clicks) {
            const chosen = window.dash_clientside.callback_context.triggered_id;
            if (!chosen || !clicks || !clicks.some(Boolean)) {
                return window.dash_clientside.no_update;
            }
            document.cookie = "tracker_language=" + chosen.index
                + "; path=/; max-age=31536000; samesite=strict";
            window.location.reload();
            return chosen.index;
        }
        """,
        Output('language-sink', 'data'),
        Input({'type': 'language', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )

    # Replaces the original login callback with a clientside callback that calls the backend.
    # It sends requests to the /auth/login endpoint, and attempts login.
    # Keeps the separate CSRF value for later actions; the cookie identifies the session.

    app.clientside_callback(
        """
        async function(clicks, role, username, password, strings) {
            const keep = window.dash_clientside.no_update;
            const say = (text) => (strings && strings[text]) || text;
            // The page is inserted after load, which can fire this without a click.
            if (!clicks) return [keep, keep, keep, keep];

            if (!role || !username || !password) {
                return [
                    keep, keep,
                    say("Please fill in all required fields."),
                    keep
                ];
            }

            try {
                // Ask the backend to check the password and selected role.
                const response = await fetch("/auth/login", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({username, password, role})
                });

                const data = await response.json();

                if (!response.ok) {
                    const message = typeof data.detail === "string"
                        ? say(data.detail)
                        : say("Please check your login details.");

                    return [keep, keep, message, keep];
                }

                // The browser keeps the session cookie automatically.
                // Use the role and page confirmed by the backend.
                return [
                    "/" + (data.page || data.role),
                    data.role,
                    "",
                    data.csrf_token
                ];
            } catch (error) {
                return [
                    keep, keep,
                    say("Could not contact the server. Please try again."),
                    keep
                ];
            }
        }
        """,
        Output("url", "pathname"),
        Output("user-role", "data"),
        Output("login-message", "children"),
        Output("csrf-token", "data"),
        Input("login-button", "n_clicks"),
        State("role", "value"),
        State("username", "value"),
        State("password", "value"),
        State("app-strings", "data"),
        prevent_initial_call=True,
    )

    # The server ends the session first; only then do we leave the private page.
    app.clientside_callback(
        """
        async function(clicks, strings) {
            const say = (text) => (strings && strings[text]) || text;
            if (!clicks) return window.dash_clientside.no_update;
            try {
                const cookie = document.cookie.split('; ').find(c => c.startsWith('tracker_csrf='));
                const token = cookie ? decodeURIComponent(cookie.slice('tracker_csrf='.length)) : '';
                const response = await fetch('/auth/logout', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'X-CSRF-Token': token}
                });
                if (!response.ok) return say('Logout failed. Please try again.');
                // Forget this tab's previous page. Reload also clears the in-memory login stores.
                sessionStorage.removeItem('last-page');
                sessionStorage.removeItem('last-page-timestamp');
                window.location.replace('/');
                return '';
            } catch (error) {
                return say('Could not log out. Check your connection and try again.');
            }
        }
        """,
        Output('logout-message', 'children'), Input('logout-button', 'n_clicks'),
        State('app-strings', 'data'), prevent_initial_call=True,
    )

    # Showing the password needs no server access or signed-in account.
    app.clientside_callback(
        "function(clicks) { return clicks && clicks % 2 ? 'text' : 'password'; }",
        Output("password", "type"), Input("toggle-password", "n_clicks"),
    )
