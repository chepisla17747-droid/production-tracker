"""Interface language: English and Thai, chosen by the reader and kept in a cookie.

Every page and callback output passes through `translate_tree` from the access decorators
in `frontend/auth.py`, so pages are written in English and translated on the way out. A
string with no entry in the catalogue is left as it is, which keeps a missing translation
readable rather than blank. Text that comes from the database, such as a product name,
normally has no entry either and so passes through untouched.
"""
import copy

from dash import ctx

from frontend.translations import CATALOG

LANGUAGE_COOKIE = 'tracker_language'
DEFAULT_LANGUAGE = 'en'
LANGUAGES = ('en', 'th')
LANGUAGE_NAMES = {'en': 'English', 'th': 'ไทย'}
# Props that hold text a reader sees. Anything else is an identifier or a number.
TEXT_PROPS = ('placeholder', 'title', 'label', 'alt')
# Text a screen reader announces; Dash keeps these as wildcard attributes, not props.
ARIA_TEXT = ('aria-label',)


def current_language():
    """The reader's language, from the cookie the switch sets; English by default."""
    try:
        chosen = (ctx.cookies or {}).get(LANGUAGE_COOKIE)
    except Exception:
        chosen = None
    return chosen if chosen in LANGUAGES else DEFAULT_LANGUAGE


def translate(text, language=None):
    language = language or current_language()
    if language == DEFAULT_LANGUAGE or not isinstance(text, str):
        return text
    return CATALOG.get(text, {}).get(language, text)


def _walk(value, language):
    if isinstance(value, str):
        return translate(value, language)
    if isinstance(value, list):
        return [_walk(item, language) for item in value]
    if isinstance(value, tuple):
        return tuple(_walk(item, language) for item in value)
    if isinstance(value, dict):
        # Dropdown and checklist options carry their text under "label".
        return {key: (_walk(item, language) if key in ('label', 'children') else item)
                for key, item in value.items()}
    if hasattr(value, '_prop_names'):
        if getattr(value, 'children', None) is not None:
            value.children = _walk(value.children, language)
        for prop in TEXT_PROPS + ('options',):
            if prop in value._prop_names and getattr(value, prop, None) is not None:
                setattr(value, prop, _walk(getattr(value, prop), language))
        for prop in ARIA_TEXT:
            if isinstance(getattr(value, prop, None), str):
                setattr(value, prop, translate(getattr(value, prop), language))
        return value
    return value


def translate_tree(value, language=None):
    """Return a translated copy, leaving the caller's components untouched.

    Page layouts are built once and reused, so the tree is copied before any text is
    replaced; translating in place would leave one reader's language on a shared layout.
    """
    language = language or current_language()
    if language == DEFAULT_LANGUAGE:
        return value
    return _walk(copy.deepcopy(value), language)
