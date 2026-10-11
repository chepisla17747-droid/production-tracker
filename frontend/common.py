"""Presentation helpers shared by the role pages.

Every page reports service failures the same way, so a denied permission or an
unavailable database never looks like a silent no-op.
"""
import logging
from datetime import date, timedelta

from dash import ctx, html
from psycopg import Error as DatabaseError
from psycopg.errors import UniqueViolation
from psycopg_pool import PoolTimeout

logger = logging.getLogger(__name__)
# LookupError is a missing or out-of-scope record; its message is safe to show.
HANDLED_ERRORS = (ValueError, PermissionError, LookupError, DatabaseError, PoolTimeout)


# Role names as people read them; any other role is shown capitalized.
ROLE_LABELS = {'operations_admin': 'Operations Administrator', 'hr': 'HR'}


def role_label(role):
    return ROLE_LABELS.get(role, role.capitalize())


def caller(app):
    """The signed-in actor and the database pool FastAPI chose for this request.

    FastAPI has already validated the session before any callback runs; this only reads
    the identity it stored on the request, so no browser value is trusted here.
    """
    state = app.backend.request_adapter().context
    return state.actor, state.business_pool


def clicked():
    """Whether a real click started this callback.

    Dash also runs a callback when its buttons are first rendered (n_clicks 0 or None), so
    that trigger value decides whether anything should happen.
    """
    return bool(ctx.triggered and ctx.triggered[0].get('value'))


# Date-range presets offered by Statistics and Order history. Rolling windows end today.
# The date pickers always show the exact days a preset covers.
PERIODS = {'this_month': 'This month', 'last_week': 'Last week', 'last_month': 'Last month',
           'last_3_months': 'Last three months', 'last_year': 'Last year', 'all': 'All time',
           'custom': 'Custom dates'}


def period_range(period, today=None):
    """(first day, last day) of a preset, both included; (None, None) for all time."""
    today = today or date.today()
    days = {'last_week': 6, 'last_month': 29, 'last_3_months': 89, 'last_year': 364}
    if period == 'this_month':
        return today.replace(day=1), today
    if period in days:
        return today - timedelta(days=days[period]), today
    return None, None


def product_picture(product_id, version, alt='', className=None):
    """A product picture, or None without one. The version in the URL lets the browser keep
    the picture until it is replaced, instead of fetching it for every card."""
    if not version:
        return None
    return html.Img(src=f'/products/{product_id}/image?v={version}', alt=alt, className=className)


def turn_page(data, forward):
    """The next or previous page of a cursor-paged list, from the page shown now."""
    cursor = data['next'] if forward else data['previous']
    if not cursor:
        return {'number': data['number'], 'after': None, 'before': None}
    return {'number': data['number'] + (1 if forward else -1),
            'after': cursor if forward else None, 'before': None if forward else cursor}


def page_label(number, shown, size):
    """'Showing 21–40', counted from the page number, so no total count is needed."""
    from frontend.i18n import translate
    if not shown:
        return translate('Nothing to show')
    first = (number - 1) * size + 1
    return translate('Showing {first}–{last}').format(first=first, last=first + shown - 1)


def notice(message, error=False):
    return html.Div(message, className='planner-notice error' if error else 'planner-notice',
                    role='alert' if error else 'status')


def failure(exc, duplicate='That value is already taken. Use a different one; nothing was saved.'):
    if isinstance(exc, PermissionError):
        return notice('You do not have permission for this action. Contact your administrator.', True)
    if isinstance(exc, UniqueViolation):
        return notice(duplicate, True)
    if isinstance(exc, (DatabaseError, PoolTimeout)):
        logger.exception('Database operation failed')
        return notice('The database is unavailable or not ready. Your form has been kept; please retry.', True)
    return notice(str(exc), True)


def scrap_badge(count):
    """Scrapped pieces stand out wherever a step or order is shown."""
    from frontend.i18n import translate
    return html.Span(translate('{n} scrapped').format(n=count), className='scrap-badge') if count else None


def field(label, component):
    return html.Div([html.Label(label, htmlFor=component.id if isinstance(component.id, str) else None,
                                className='form-label'), component], className='planner-field')


def duration(seconds):
    if seconds is None:
        return 'Standard time unknown'
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return ' '.join(f'{value}{unit}' for value, unit in ((hours, 'h'), (minutes, 'm'), (secs, 's')) if value)


def optional_text(value):
    """Translate blank browser inputs to absent values before typed service calls."""
    return (value.strip() or None) if isinstance(value, str) else value
