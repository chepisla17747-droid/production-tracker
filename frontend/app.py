"""Build the Dash website on the same FastAPI server as the login API."""
from pathlib import Path

from dash import Dash, Input, Output, State, dcc, html, set_props

from frontend import (activate, history, login, manager, operations, orders, planner, profile,
                      statistics, supervision, supervisor)
from frontend.auth import public_page_callback
from backend.service.auth_service import PAGE_ROLES, PUBLIC_PAGES, role_page

# The private pages and the function that renders each for the signed-in actor.
PAGES = {'planner': planner.planner_page, 'supervisor': supervisor.supervisor_page,
         'statistics': statistics.statistics_page, 'manager': manager.manager_page,
         'orders': orders.orders_page, 'history': history.history_page,
         'operations': operations.operations_page,
         'profile': profile.profile_page}


def create_dash_app(server):
    app = Dash(
        __name__, server=server, suppress_callback_exceptions=True,
        assets_folder=str(Path(__file__).resolve().parent / 'assets'),
        title='Production Tracker',
        csrf_token_name='tracker_csrf', csrf_header_name='X-CSRF-Token',
    )
    app.layout = html.Div([
        dcc.Location(id='url', refresh=False),
        dcc.Store(id='user-role'),
        dcc.Store(id='last-page', storage_type='session'),
        dcc.Store(id='csrf-token', storage_type='memory'),
        dcc.Store(id='language-sink'),
        # Text the browser-side sign-in and log-out callbacks need, in the reader's
        # language. It lives here so those callbacks always find it, whatever page shows.
        dcc.Store(id='app-strings', data=login.browser_messages()),
        html.Div(id='page-content', children=login.login_page()),
    ])

    for page in (login, planner, supervisor, statistics, manager, orders, history, supervision,
                 operations, activate, profile):
        page.register_callbacks(app)

    @app.callback(Output('page-content', 'children'), Output('app-strings', 'data'),
                  Input('url', 'pathname'), State('last-page', 'data'), State('url', 'search'))
    @public_page_callback
    def display_page(pathname, last_page, search):
        # Every return below is paired with the browser-side text for this language.
        def shown(content):
            return content, login.browser_messages()
        # FastAPI has already checked the cookie; this identity lasts one request.
        actor = app.backend.request_adapter().context.actor
        page = (pathname or '/').strip('/')
        # Public pages authorize themselves; a new employee has no session yet.
        if page in PUBLIC_PAGES:
            return shown(activate.activate_page(login.username_from_search(search)))
        if not page:
            if actor:
                # Back to login means return to this tab's last page, if still allowed.
                allowed = ['/' + name for name, roles in PAGE_ROLES.items()
                           if set(roles) & set(actor.allowed_roles)]
                target = last_page if last_page in allowed else '/' + role_page(actor.role)
                # Reload so the main router runs too; an invisible URL alone leaves a blank page.
                return shown(dcc.Location(id='session-redirect', pathname=target, refresh=True))
            return shown(login.login_page())
        if page not in PAGE_ROLES:
            return shown(html.Div(['Page not found. ', html.A('Return to login', href='/')]))
        if actor is None:
            return shown(login.login_page())
        # Typing a different address cannot give someone access to another page.
        if not set(PAGE_ROLES[page]) & set(actor.allowed_roles):
            return shown(html.Div(['Access denied. ', html.A('Return to login', href='/')]))
        # Remember only pages the server has allowed this user to see.
        set_props('last-page', {'data': '/' + page})
        if page in PAGES:
            return shown(PAGES[page](actor))
        # Roles such as HR have a page address but no view yet.
        return shown(html.Div([login.logout_controls(actor, page),
                               html.P(f'The {page} view is not available yet.')]))

    return app


if __name__ == '__main__':
    raise SystemExit('Start the combined website with: uv run uvicorn main:app')
