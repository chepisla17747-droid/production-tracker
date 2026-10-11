"""Shared SQL composers for simple single-table reads and writes.

Table, column and field names always come from trusted backend code; only values are
passed as parameters. Writes take the calling operation and its `locals()`, and store
exactly the parameters that operation marks `editable`.
"""
from backend.annotations import UNSET, PositiveInt, editable
from backend.validation import get_marked_parameter_annotations, validate_value, validate_operation_fields
from psycopg import sql
from psycopg.rows import dict_row


def _collect_fields(func, values, column_names):
    """The operation's editable arguments that were supplied, keyed by column name."""
    annotations = get_marked_parameter_annotations(func, editable)
    # Checks every editable value's type as well, including those without a rule.
    validate_operation_fields(func, {name: values[name] for name in annotations if name in values}, editable)
    return {column_names.get(name, name): values[name]
            for name in annotations if name in values and values[name] is not UNSET}


def like_pattern(text):
    """An ILIKE pattern matching ``text`` anywhere; wildcards the user typed match literally."""
    return "%" + text.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _select_query(table_name, fields, column_names):
    if isinstance(fields, str) or not fields:
        raise ValueError("Provide a non-empty sequence of field names")
    selections = sql.SQL(", ").join(
        sql.SQL("{} AS {}").format(sql.Identifier(column_names.get(field, field)), sql.Identifier(field))
        for field in fields)
    return sql.SQL("SELECT {} FROM {}").format(selections, sql.Identifier(table_name))


def get_query_compose(conn, key, table_name, fields, column_names=None, *, key_column="id"):
    """Fetch one row by a unique key, or None."""
    if key_column == "id":
        validate_value(key, PositiveInt, "ID")
    query = _select_query(table_name, fields, column_names or {})
    query += sql.SQL(" WHERE {} = %s").format(sql.Identifier(key_column))
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (key,))
        return cur.fetchone()


def list_query_compose(conn, table_name, fields, column_names=None, *, filters=None, order_by=("id",)):
    """List selected fields with optional equality filters and a stable order."""
    column_names = column_names or {}
    query = _select_query(table_name, fields, column_names)
    filters = filters or {}
    if filters:
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(
            sql.SQL("{} IS NOT DISTINCT FROM %s").format(sql.Identifier(column_names.get(field, field)))
            for field in filters)
    query += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(
        sql.Identifier(column_names.get(field, field)) for field in order_by)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, tuple(filters.values()))
        return cur.fetchall()


def add_query_compose(conn, func, values, table_name, column_names=None):
    """Insert the operation's supplied editable fields and return the new row's id."""
    fields = _collect_fields(func, values, column_names or {})
    if fields:
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(
            sql.Identifier(table_name),
            sql.SQL(", ").join(sql.Identifier(column) for column in fields),
            sql.SQL(", ").join(sql.Placeholder() for _ in fields))
    else:
        query = sql.SQL("INSERT INTO {} DEFAULT VALUES RETURNING id").format(sql.Identifier(table_name))
    with conn.cursor() as cur:
        cur.execute(query, tuple(fields.values()))
        return cur.fetchone()[0]


def edit_query_compose(conn, key, func, values, table_name, column_names=None, *, expected_values=None):
    """Update the supplied fields; False when the row is missing or no longer as expected.

    `expected_values` guards a concurrent change: the row is updated only while those
    backend-chosen fields still hold the values read earlier.
    """
    validate_value(key, PositiveInt, "ID")
    column_names = column_names or {}
    fields = _collect_fields(func, values, column_names)
    if not fields:
        raise ValueError("Provide at least one field to update")
    expected_values = expected_values or {}
    query = sql.SQL("UPDATE {} SET {} WHERE id = %s{} RETURNING id").format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(column)) for column in fields),
        sql.SQL("").join(sql.SQL(" AND {} IS NOT DISTINCT FROM %s").format(
            sql.Identifier(column_names.get(field, field))) for field in expected_values))
    with conn.cursor() as cur:
        cur.execute(query, (*fields.values(), key, *expected_values.values()))
        return cur.fetchone() is not None
