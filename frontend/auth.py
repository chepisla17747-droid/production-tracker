"""Label callback access, and translate what a callback returns.

FastAPI performs the access checks before callbacks run; the labels below only say which
roles a callback belongs to. Translation is applied here so every page and every callback
output goes through it, rather than each string being wrapped at its call site.
"""
import logging
from functools import wraps

from dash.exceptions import PreventUpdate

from backend.service.auth_service import WEBSITE_ROLES
from frontend.i18n import translate_tree

logger = logging.getLogger(__name__)


def protect_callback(*roles):
    # This is a label, not a second security check. Unlabelled callbacks are blocked.
    # Several roles mean any one of them may run the callback.
    if not roles or any(role not in WEBSITE_ROLES for role in roles):
        raise ValueError('Unknown website role')

    def label(function):
        translated = _translating(function)
        translated._tracker_access = roles[0] if len(roles) == 1 else roles
        return translated

    return label


def public_page_callback(function):
    # The login router is public, but checks the user before showing a private page.
    translated = _translating(function)
    translated._tracker_access = 'public-page'
    return translated


def public_credential_callback(username_id):
    """A public callback that checks a secret, such as an activation code.

    FastAPI counts each call as a sign-in attempt, by client address and by the username
    in component `username_id`, before the callback runs.
    """
    def label(function):
        translated = public_page_callback(function)
        translated._tracker_throttle = username_id
        return translated

    return label


def _translating(function):
    """Return the callback's output in the reader's language.

    Styles, numbers and stores pass through untouched; only text with an entry in the
    catalogue is replaced, so an untranslated string stays readable in English.
    """
    @wraps(function)
    def translated(*args, **kwargs):
        try:
            return translate_tree(function(*args, **kwargs))
        except PreventUpdate:
            raise
        except Exception:
            # Dash answers 500 without logging, so the error log would never see it.
            logger.exception('Callback %s failed', function.__name__)
            raise

    return translated
