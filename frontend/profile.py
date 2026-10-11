"""Every employee's own profile: read-only identity, editable contacts, password change.

Name, surname, date of birth, username and roles are shown but never editable here; the
services behind this page accept no employee identifier from the browser.
"""
from dash import html, dcc, Input, Output, State, no_update

from frontend.auth import protect_callback
from frontend.common import HANDLED_ERRORS, caller, failure, field, notice, optional_text, role_label
from frontend.login import top_bar
from backend.service.auth_service import WEBSITE_ROLES
from backend.service.employee_service import edit_own_contact_details_service
from backend.service.profile_service import get_own_profile_service
from backend.service.user_account_service import (
    WRONG_CURRENT_PASSWORD, edit_user_account_service)

def profile_page(actor=None):
    return html.Div(className='planner-page persistent-planner profile-page', children=[
        top_bar('Your profile', actor, 'profile'),
        html.Div(className='planner-content', children=[
            html.Div([html.Div([html.H1('Your profile'),
                html.P('Your details, and the two things you can change yourself.',
                       className='planner-muted')]),
                html.Span(role_label(actor.role) if actor else 'Profile',
                          className='planner-badge')], className='planner-heading'),
            dcc.Interval(id='profile-load', interval=300, max_intervals=1),
            html.Div(className='profile-grid', children=[
                html.Div([html.H2('Your details'), html.Div(id='profile-details')],
                         className='info-card'),
                html.Div([
                    html.Div([html.H2('Contact details'),
                        html.P('Keep these current: your email address is where account '
                               'messages are sent.', className='planner-muted'),
                        html.Div(id='profile-contact-fields'),
                        html.Button('Apply', id='profile-apply', className='planner-secondary'),
                        html.Div(id='profile-contact-message', **{'aria-live': 'polite'}),
                    ], className='form-card'),
                    html.Div([html.H2('Change your password'),
                        field('Current password *', dcc.Input(
                            id='profile-current', type='password', className='form-input')),
                        field('New password *', dcc.Input(
                            id='profile-new', type='password', className='form-input',
                            placeholder='At least 8 characters')),
                        field('Repeat new password *', dcc.Input(
                            id='profile-repeat', type='password', className='form-input')),
                        html.P('Choose something long and unusual. Common or predictable '
                               'passwords are refused.', className='planner-muted'),
                        html.Button('Change password', id='profile-change',
                                    className='planner-secondary'),
                        html.Div(id='profile-password-message', **{'aria-live': 'polite'}),
                    ], className='form-card'),
                ], className='profile-forms'),
            ]),
        ]),
    ])


def detail(label, value):
    return html.Div([html.Dt(label), html.Dd(value or 'Not recorded')], className='profile-detail')


def profile_details(profile):
    employee, account = profile['employee'], profile['account']
    units = profile['units']
    stations = [f"{row['name']}" + (' (supervisor)' if row['is_supervisor'] else '')
                for row in units]
    return html.Dl([
        detail('Name', f"{employee['name']} {employee['surname']}"),
        detail('Username', account['username'] if account else None),
        detail('Roles', ', '.join(role_label(role) for role in profile['roles']) or None),
        detail('Date of birth', employee['birth_date'].isoformat() if employee['birth_date'] else None),
        detail('Employed since', employee['regist_date'].date().isoformat()
               if employee['regist_date'] else None),
        detail('Current units', ', '.join(stations) or 'None assigned'),
        detail('Last signed in', account['last_login_at'].strftime('%Y-%m-%d %H:%M')
               if account and account['last_login_at'] else 'Never'),
        html.P('Your name, date of birth, username and roles are maintained by your '
               'administrator. Ask them if any of these is wrong.', className='planner-muted'),
    ], className='profile-list')


def contact_fields(employee):
    return [
        field('Email', dcc.Input(id='profile-email', value=employee['email'], type='email',
                                 className='form-input', maxLength=256)),
        field('Phone', dcc.Input(id='profile-phone', value=employee['phone_number'], type='tel',
                                 className='form-input', maxLength=16)),
    ]


def register_callbacks(app):

    @app.callback(Output('profile-details', 'children'), Output('profile-contact-fields', 'children'),
                  Input('profile-load', 'n_intervals'), Input('profile-contact-message', 'children'),
                  prevent_initial_call=True)
    @protect_callback(*WEBSITE_ROLES)
    def load_profile(_loaded, _saved):
        try:
            profile = get_own_profile_service(*caller(app))
            return profile_details(profile), contact_fields(profile['employee'])
        except HANDLED_ERRORS as exc:
            return failure(exc), ''

    @app.callback(Output('profile-contact-message', 'children'), Input('profile-apply', 'n_clicks'),
                  State('profile-email', 'value'), State('profile-phone', 'value'),
                  prevent_initial_call=True,
                  running=[(Output('profile-apply', 'disabled'), True, False)])
    @protect_callback(*WEBSITE_ROLES)
    def save_contacts(clicks, email, phone):
        if not clicks:
            return no_update
        try:
            edit_own_contact_details_service(*caller(app), email=optional_text(email),
                                             phone_number=optional_text(phone))
            return notice('Contact details saved.')
        except HANDLED_ERRORS as exc:
            return failure(exc, 'That email address already belongs to another employee.')

    @app.callback(Output('profile-password-message', 'children'),
                  Output('profile-current', 'value'), Output('profile-new', 'value'),
                  Output('profile-repeat', 'value'), Input('profile-change', 'n_clicks'),
                  State('profile-current', 'value'), State('profile-new', 'value'),
                  State('profile-repeat', 'value'), prevent_initial_call=True,
                  running=[(Output('profile-change', 'disabled'), True, False)])
    @protect_callback(*WEBSITE_ROLES)
    def change_password(clicks, current, new, repeated):
        if not clicks:
            return (no_update,) * 4
        try:
            if not current or not new:
                raise ValueError('Enter your current password and the new one.')
            if new != repeated:
                raise ValueError('The two new passwords do not match.')
            actor, pool = caller(app)
            # The service verifies the current password and rejects a pending account.
            edit_user_account_service(actor, actor.employee_id, pool,
                                      new_password=new, current_password=current)
            return notice('Password changed. It applies the next time you sign in.'), '', '', ''
        except PermissionError as exc:
            # Only their own password is wrong here; that is not an authorization problem.
            if str(exc) == WRONG_CURRENT_PASSWORD:
                return (notice('Your current password is not correct.', True),
                        no_update, no_update, no_update)
            return failure(exc), no_update, no_update, no_update
        except HANDLED_ERRORS as exc:
            return failure(exc), no_update, no_update, no_update
