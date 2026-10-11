"""Keyset ("cursor") paging for every long list: orders, history, employees, contractors.

A page is read from an index range that starts at the last row already shown, so the
hundredth page costs the same as the first, and no total count over every row is taken.
The browser keeps only opaque cursors: a JSON list of the sort values of a shown row.
"""
import json
from datetime import datetime


def _moment(value):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError
    return moment


def _key(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError
    return value


def _text(value):
    if not isinstance(value, str):
        raise ValueError
    return value


# How each part of a cursor is checked and restored, per kind of sort key.
MOMENT, KEY, TEXT = _moment, _key, _text


def decode(cursor, *kinds):
    """The sort values in a cursor, checked against their kinds; None without a cursor."""
    if cursor is None:
        return None
    try:
        values = json.loads(cursor)
        if not isinstance(values, list) or len(values) != len(kinds):
            raise ValueError
        return tuple(kind(value) for kind, value in zip(kinds, values))
    except (ValueError, TypeError):
        raise ValueError('Invalid page position. Reload the list.') from None


def page(rows, size, key, *, after=None, before=None):
    """Turn ``size + 1`` rows read after/before a cursor into one page and its neighbours.

    The extra row only says whether another page exists in the reading direction. Rows read
    before a cursor arrive already reversed into display order, with the extra row first.
    """
    more = len(rows) > size
    shown = (rows[1:] if more else rows) if before is not None else rows[:size]

    def cursor(row):
        return json.dumps([value.isoformat() if isinstance(value, datetime) else value
                           for value in key(row)])

    has_previous = more if before is not None else after is not None
    has_next = True if before is not None else more
    return {'rows': shown,
            'previous': cursor(shown[0]) if shown and has_previous else None,
            'next': cursor(shown[-1]) if shown and has_next else None}
