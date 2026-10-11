"""Unit supervisor assignment, shared by the Planner and Operations pages.

Both pages mount the same component ids, and only one page is rendered at a time,
so a single set of callbacks serves both. The section loads itself once on render
rather than reacting to a tab, because the two pages name their tabs differently.
"""
from dash import html, dcc, Input, Output, State, MATCH, ctx, no_update

from frontend.auth import protect_callback
from frontend.i18n import translate
from frontend.common import HANDLED_ERRORS, caller, failure, notice
from backend.service.unit_supervisor_service import (
    assign_unit_supervisor_service, get_unit_supervision_service)

ROLES = ('planner', 'operations_admin')


def supervision_section(container_id, style=None):
    """The shared section inside a page-owned container, which that page shows or hides."""
    return html.Div(id=container_id, style=style or {}, children=[
        html.Div([html.H2('Unit supervisors'),
            html.P('Each production unit has at most one current supervisor. Unassign the '
                   'present supervisor before assigning someone else; past assignments are kept.',
                   className='planner-muted'),
            # Loads once when the page renders; the button refreshes it afterwards.
            dcc.Interval(id='supervision-load', interval=300, max_intervals=1),
            html.Button('Refresh units', id='refresh-supervision', className='planner-text-button'),
            dcc.Checklist(id='supervision-show-inactive', value=[], className='role-checklist',
                          options=[{'label': ' Show inactive units', 'value': 'inactive'}]),
            html.Div(id='supervision-message'),
            html.Div(id='unit-supervisor-list'),
        ], className='form-card'),
    ])


def supervisor_options(candidates):
    # The service orders candidates by surname; the label matches the assigned-supervisor line.
    return [{'label': f"{row['name']} {row['surname']}".strip(), 'value': row['id']} for row in candidates]


def supervision_status(row):
    if row['supervisor_id'] is None:
        return html.Span('No supervisor assigned', className='planner-muted')
    name = f"{row['supervisor_name']} {row['supervisor_surname']}".strip()
    since = row['supervisor_since'].date().isoformat() if row['supervisor_since'] else None
    return html.Span(f'Supervised by {name}' + (f' since {since}' if since else ''),
                     className='unit-supervisor-name')


def unit_row(row, candidates):
    """Both controls always exist so their callback inputs stay present after a change."""
    def ident(kind):
        return {'type': f'unit-{kind}', 'index': row['id']}
    occupied = row['supervisor_id'] is not None
    return html.Div([
        html.Div([html.Strong(row['name'] + ('' if row.get('active', True) else translate(' · Inactive'))),
                  html.Div(supervision_status(row), id=ident('status'))], className='unit-heading'),
        html.Div([
            dcc.Dropdown(id=ident('choice'), options=supervisor_options(candidates), value=None,
                         placeholder='Select a supervisor', disabled=occupied),
            html.Button('Assign', id=ident('assign'), className='planner-secondary', disabled=occupied),
            html.Button('Unassign', id=ident('unassign'), className='planner-text-button', disabled=not occupied),
        ], className='unit-controls'),
        html.Div(id=ident('message'), **{'aria-live': 'polite'}),
    ], className='unit-row')


def register_callbacks(app):

    @app.callback(Output('unit-supervisor-list', 'children'), Output('supervision-message', 'children'),
                  Input('supervision-load', 'n_intervals'), Input('refresh-supervision', 'n_clicks'),
                  Input('supervision-show-inactive', 'value'),
                  prevent_initial_call=True)
    @protect_callback(*ROLES)
    def unit_supervisors(_loaded, _clicked, show_inactive):
        try:
            units, candidates = get_unit_supervision_service(*caller(app))
            # Inactive units stay hidden unless asked for; the service returns every unit.
            if 'inactive' not in (show_inactive or ()):
                units = [unit for unit in units if unit['active']]
            if not units:
                return [], notice('No production units exist yet. Ask an administrator to add them.')
            warning = ('' if candidates else
                       notice('No employee holds the supervisor role, so units cannot be assigned yet.', True))
            return [unit_row(row, candidates) for row in units], warning
        except HANDLED_ERRORS as exc:
            return [], failure(exc)

    @app.callback(Output({'type': 'unit-status', 'index': MATCH}, 'children'),
                  Output({'type': 'unit-message', 'index': MATCH}, 'children'),
                  Output({'type': 'unit-choice', 'index': MATCH}, 'value'),
                  Output({'type': 'unit-choice', 'index': MATCH}, 'disabled'),
                  Output({'type': 'unit-assign', 'index': MATCH}, 'disabled'),
                  Output({'type': 'unit-unassign', 'index': MATCH}, 'disabled'),
                  Input({'type': 'unit-assign', 'index': MATCH}, 'n_clicks'),
                  Input({'type': 'unit-unassign', 'index': MATCH}, 'n_clicks'),
                  State({'type': 'unit-assign', 'index': MATCH}, 'id'),
                  State({'type': 'unit-choice', 'index': MATCH}, 'value'), prevent_initial_call=True)
    @protect_callback(*ROLES)
    def change_unit_supervisor(assign_clicks, unassign_clicks, identifier, supervisor_id):
        if not (assign_clicks or unassign_clicks) or not isinstance(ctx.triggered_id, dict):
            return (no_update,) * 6
        assigning = ctx.triggered_id['type'] == 'unit-assign'
        unit_id = identifier['index']
        try:
            if assigning and supervisor_id is None:
                raise ValueError('Select a supervisor before assigning.')
            actor, pool = caller(app)
            assign_unit_supervisor_service(actor, pool, unit_id=unit_id,
                                           supervisor_id=supervisor_id if assigning else None)
            # Re-read so the row shows the stored assignment rather than the submitted form.
            units, _ = get_unit_supervision_service(actor, pool)
            row = next((unit for unit in units if unit['id'] == unit_id), None)
            if row is None:
                raise ValueError('This production unit no longer exists. Refresh the list.')
            occupied = row['supervisor_id'] is not None
            message = notice('Supervisor assigned.' if occupied else 'The unit now has no supervisor.')
            return supervision_status(row), message, None, occupied, occupied, not occupied
        except HANDLED_ERRORS as exc:
            return no_update, failure(exc), no_update, no_update, no_update, no_update
