from backend.annotations import Email, PhoneNumber, Name, PositiveInt, UNSET, UnsetType, editable
from backend.validation import validate_call
from psycopg import Connection
from datetime import date, datetime
from typing import Annotated

from psycopg.rows import dict_row, tuple_row

from backend.operations.dbops_core import add_query_compose, edit_query_compose, get_query_compose, like_pattern

USER_ACCOUNT_PUBLIC_FIELDS = ("id", "employee_id", "username", "is_active", "last_login_at")
# Every account column a read may name. The hash is only for trusted internal callers.
USER_ACCOUNT_FIELDS = (*USER_ACCOUNT_PUBLIC_FIELDS, "password_hash", "password_set_at")
EMPLOYEE_FIELDS = ("id", "name", "surname", "email", "phone_number", "birth_date", "regist_date",
                   "left_at")


def _known_fields(fields, allowed, record):
    """Refuse a column that is not on the record's list, whoever supplied the names."""
    unknown = set(fields) - set(allowed)
    if unknown:
        raise ValueError(f"Unknown {record} field: {', '.join(sorted(unknown))}")
    return fields


def get_employees(conn: Connection, *, search: str = "", include_left: bool = True,
                  employee_ids=None, after=None, before=None, limit=None) -> list[dict]:
    """Employee records by surname, name and id, optionally one page at a time.

    ``search`` matches name, surname, email or phone ignoring case; ``employee_ids`` keeps
    just those employees. ``after``/``before`` are the (surname, name, id) of a row already
    shown: the next page is read from the index from there (see backend.service.paging).
    """
    clauses, params = [], []
    if not include_left:
        clauses.append("left_at IS NULL")
    if employee_ids is not None:
        clauses.append("id = ANY(%s)")
        params.append(list(employee_ids))
    if search.strip():
        clauses.append("(name ILIKE %s OR surname ILIKE %s OR email ILIKE %s OR phone_num ILIKE %s)")
        params += [like_pattern(search)] * 4
    order = "surname, name, id"
    if after is not None:
        clauses.append("(surname, name, id) > (%s, %s, %s)")
        params += list(after)
    elif before is not None:
        clauses.append("(surname, name, id) < (%s, %s, %s)")
        params += list(before)
        order = "surname DESC, name DESC, id DESC"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT id, name, surname, email, phone_num AS phone_number, birth_date, regist_date, left_at
            FROM public.employee WHERE {' AND '.join(clauses) or 'TRUE'}
            ORDER BY {order} {'LIMIT %s' if limit else ''}""", params + ([limit] if limit else []))
        rows = cur.fetchall()
    return rows[::-1] if before is not None else rows


# Add a new employee to the database. Returns the ID of the newly created employee.
@validate_call
def add_employee(conn: Connection,
                 name: Annotated[Name, editable],
                 surname: Annotated[Name, editable],
                 *,
                 email: Annotated[Email | None, editable] = None,
                 phone_number: Annotated[PhoneNumber | None, editable] = None,
                 birth_date: Annotated[date | None, editable] = None) -> int:
    return add_query_compose(
        conn, add_employee, locals(), "employee",
        column_names={"phone_number": "phone_num"},
    )


# Edit an employee by their ID. Returns False if they do not exist.
@validate_call
def edit_employee(
    conn: Connection,
    employee_id: PositiveInt,
    *,
    name: Annotated[Name | UnsetType, editable] = UNSET,
    surname: Annotated[Name | UnsetType, editable] = UNSET,
    email: Annotated[Email | None | UnsetType, editable] = UNSET,
    phone_number: Annotated[PhoneNumber | None | UnsetType, editable] = UNSET,
    birth_date: Annotated[date | None | UnsetType, editable] = UNSET,
) -> bool:
    return edit_query_compose(
        conn, employee_id, edit_employee, locals(), "employee",
        column_names={"phone_number": "phone_num"},
    )


# Get a list of employees fields and their values as a dictionary, or None if the employee does not exist
@validate_call
def get_employee_info(conn: Connection,
                      employee_id: PositiveInt,
                      fields: tuple[str, ...]) -> dict | None:
    return get_query_compose(
        conn, employee_id, "employee",
        fields=_known_fields(fields, EMPLOYEE_FIELDS, "employee"),
        column_names={"phone_number": "phone_num"},
    )


@validate_call
def add_pending_user_account(conn: Connection, employee_id: PositiveInt, username: Name) -> int:
    """Create an account without a password; login must reject pending accounts."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO user_account (employee_id, username, password_hash)
            VALUES (%s, %s, NULL)
            RETURNING id
            """,
            (employee_id, username),
        )
        return cur.fetchone()[0]


@validate_call
def get_user_account(
    conn: Connection,
    account_id: PositiveInt | None = None,
    fields: tuple[str, ...] = USER_ACCOUNT_PUBLIC_FIELDS,
    *, employee_id: PositiveInt | None = None,
) -> dict | None:
    """Read by exactly one account ID or employee ID.

    Default fields exclude hashes. Password checks may explicitly select password_hash.
    Fields must be chosen by backend code. Hashes are for internal use only
    and must never be included in browser-facing responses or callback outputs.
    """
    if (account_id is None) == (employee_id is None):
        raise ValueError("Provide exactly one account ID or employee ID")
    return get_query_compose(
        conn, employee_id if account_id is None else account_id, "user_account",
        fields=_known_fields(fields, USER_ACCOUNT_FIELDS, "account"),
        key_column="id" if employee_id is None else "employee_id",
    )


def get_account_directory(conn: Connection, employee_ids=None) -> list[dict]:
    """Accounts plus whether a password exists, which is what "invited" really means.

    password_set_at is unknown for accounts that predate migration 001, so the hash's
    presence decides. The hash itself is never selected.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT a.id, a.employee_id, a.username, a.is_active, a.last_login_at,
                   a.password_hash IS NOT NULL AS has_password,
                   EXISTS (SELECT 1 FROM account_private.account_token AS t
                           WHERE t.account_id = a.id AND t.purpose = 'invitation'
                             AND t.consumed_at IS NULL AND t.revoked_at IS NULL
                             AND t.expires_at > CURRENT_TIMESTAMP) AS has_live_code
            FROM public.user_account AS a
            WHERE %(ids)s::bigint[] IS NULL OR a.employee_id = ANY(%(ids)s)
            ORDER BY a.username, a.id
            """, {"ids": None if employee_ids is None else list(employee_ids)}
        )
        return cur.fetchall()


@validate_call
def edit_user_account(
    conn: Connection,
    account_id: PositiveInt,
    *,
    username: Annotated[Name | UnsetType, editable] = UNSET,
    password_hash: Annotated[str | None | UnsetType, editable] = UNSET,
    is_active: Annotated[bool | UnsetType, editable] = UNSET,
    last_login_at: Annotated[datetime | None | UnsetType, editable] = UNSET,
    password_set_at: Annotated[datetime | None | UnsetType, editable] = UNSET,
    expected_values: dict | None = None,
) -> bool:
    """Edit supplied fields; authorize fields in the caller, as for employees.

    The owning employee is fixed at creation: an account is never moved to someone else.

    Omitted fields stay unchanged. Expected values optionally guard concurrent
    edits. The caller owns the transaction and provides already hashed passwords.
    """
    return edit_query_compose(
        conn, account_id, edit_user_account, locals(), "user_account",
        expected_values=expected_values,
    )


def get_roles(conn: Connection) -> list[dict]:
    """List application roles in name/ID order; return an empty list if none."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, name, description, is_system_role, is_default
            FROM public.role
            ORDER BY name, id
            """
        )
        return cur.fetchall()


# Get all permissions associated with an employee through their roles
@validate_call
def get_employee_permissions(conn: Connection, employee_id: PositiveInt) -> set[str]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT p.name
            FROM employee_role AS er
            JOIN role_permission AS rp
                ON rp.role_id = er.role_id
            JOIN permission AS p
                ON p.id = rp.permission_id
            WHERE er.employee_id = %s
            """,
            (employee_id,),
        )
        return {row[0] for row in cur.fetchall()}
    


@validate_call
def assign_employee_role(conn: Connection, employee_id: PositiveInt, role_id: PositiveInt) -> bool:
    """Assign an existing role; return False if the assignment already exists."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO public.employee_role (employee_id, role_id)
            VALUES (%s, %s)
            ON CONFLICT (employee_id, role_id) DO NOTHING
            RETURNING employee_id
            """,
            (employee_id, role_id),
        )
        return cur.fetchone() is not None


@validate_call
def get_employee_roles(conn: Connection, employee_id: PositiveInt) -> list[dict]:
    """List assigned roles; empty for no assignments or a missing employee."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT r.id, r.name, r.description, r.is_system_role, r.is_default
            FROM public.role AS r
            JOIN public.employee_role AS er ON er.role_id = r.id
            WHERE er.employee_id = %s
            ORDER BY r.name, r.id
            """,
            (employee_id,),
        )
        return cur.fetchall()


@validate_call
def remove_employee_role(conn: Connection, employee_id: PositiveInt, role_id: PositiveInt) -> bool:
    """Remove only the link; callers must enforce default/system-role policies."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            DELETE FROM public.employee_role
            WHERE employee_id = %s AND role_id = %s
            RETURNING employee_id
            """,
            (employee_id, role_id),
        )
        return cur.fetchone() is not None


@validate_call
def assign_employee_to_unit(
    conn: Connection,
    employee_id: Annotated[PositiveInt, editable],
    unit_id: Annotated[PositiveInt, editable],
    valid_from: Annotated[datetime, editable],
    *, valid_until: Annotated[datetime | None, editable] = None,
    is_supervisor: Annotated[bool, editable] = False,
) -> int:
    """Create a dated assignment; foreign keys, dates and uniqueness use DB constraints."""
    return add_query_compose(conn, assign_employee_to_unit, locals(), "employee_unit_assignment")


@validate_call
def end_employee_unit_assignment(
    conn: Connection, assignment_id: PositiveInt,
    valid_until: Annotated[datetime, editable],
) -> bool:
    """End an open assignment; False if missing/already ended. Preserve history."""
    return edit_query_compose(
        conn, assignment_id, end_employee_unit_assignment, locals(), "employee_unit_assignment",
        expected_values={"valid_until": None},
    )


def get_units_with_current_supervisor(conn: Connection) -> list[dict]:
    """List every production unit with its current supervisor, or None when free."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT u.id, u.name, u.active, a.employee_id AS supervisor_id, a.valid_from AS supervisor_since,
                   e.name AS supervisor_name, e.surname AS supervisor_surname
            FROM public.production_unit AS u
            LEFT JOIN public.employee_unit_assignment AS a
                ON a.unit_id = u.id AND a.is_supervisor AND a.valid_until IS NULL
            LEFT JOIN public.employee AS e ON e.id = a.employee_id
            ORDER BY u.name, u.id
            """
        )
        return cur.fetchall()


@validate_call
def get_employees_with_role(conn: Connection, role_name: Name) -> list[dict]:
    """List employees holding a role, for selectors that must not offer anyone else."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT e.id, e.name, e.surname
            FROM public.employee AS e
            JOIN public.employee_role AS er ON er.employee_id = e.id
            JOIN public.role AS r ON r.id = er.role_id
            WHERE r.name = %s AND e.left_at IS NULL
            ORDER BY e.surname, e.name, e.id
            """,
            (role_name,),
        )
        return cur.fetchall()


@validate_call
def get_current_units_for_employee(conn: Connection, employee_id: PositiveInt) -> list[dict]:
    """Units this employee is assigned to now, and whether they supervise each one."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT u.id, u.name, u.location, a.is_supervisor, a.valid_from
            FROM public.employee_unit_assignment AS a
            JOIN public.production_unit AS u ON u.id = a.unit_id
            WHERE a.employee_id = %s AND a.valid_until IS NULL
            ORDER BY u.name, u.id
            """,
            (employee_id,),
        )
        return cur.fetchall()


def get_employee_role_names(conn: Connection, employee_ids=None) -> dict[int, list[str]]:
    """Role names per employee, for a directory page (or everyone without ``employee_ids``)."""
    grouped: dict[int, list[str]] = {}
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT er.employee_id, r.name
            FROM public.employee_role AS er
            JOIN public.role AS r ON r.id = er.role_id
            WHERE %(ids)s::bigint[] IS NULL OR er.employee_id = ANY(%(ids)s)
            ORDER BY er.employee_id, r.name
            """, {"ids": None if employee_ids is None else list(employee_ids)}
        )
        for employee_id, role in cur.fetchall():
            grouped.setdefault(employee_id, []).append(role)
    return grouped


@validate_call
def lock_employee(conn: Connection, employee_id: PositiveInt) -> dict | None:
    """Serialize concurrent edits to one employee; None when the record is missing.

    Returns the row's departure time too, which is what the locking services check next.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, left_at FROM public.employee WHERE id = %s FOR UPDATE", (employee_id,))
        return cur.fetchone()


@validate_call
def lock_user_account(conn: Connection, account_id: PositiveInt) -> dict | None:
    """Lock one account for an administrative action and return what those actions check.

    The owner's departure is joined in, so no second read is needed.
    The hash itself is never selected, only whether one exists.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT a.id, a.employee_id, a.is_active, a.password_hash IS NOT NULL AS has_password,
                   e.left_at
            FROM public.user_account AS a JOIN public.employee AS e ON e.id = a.employee_id
            WHERE a.id = %s FOR UPDATE OF a
            """,
            (account_id,),
        )
        return cur.fetchone()


@validate_call
def add_role_change(
    conn: Connection, actor_employee_id: PositiveInt, target_employee_id: PositiveInt,
    role_name: Name, action: str,
) -> int:
    """Append one role change. The table rejects any later update or deletion."""
    if action not in ("granted", "revoked"):
        raise ValueError("A role change is either granted or revoked")
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "INSERT INTO public.role_change "
            "(actor_employee_id, target_employee_id, role_name, action) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (actor_employee_id, target_employee_id, role_name, action),
        )
        return cur.fetchone()[0]


@validate_call
def get_role_changes(conn: Connection, target_employee_id: PositiveInt) -> list[dict]:
    """One employee's recorded role changes, newest first."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT c.id, c.changed_at, c.actor_employee_id, c.target_employee_id,
                   c.role_name, c.action,
                   actor.name AS actor_name, actor.surname AS actor_surname
            FROM public.role_change AS c
            JOIN public.employee AS actor ON actor.id = c.actor_employee_id
            WHERE c.target_employee_id = %s
            ORDER BY c.changed_at DESC, c.id DESC
            """,
            (target_employee_id,),
        )
        return cur.fetchall()


ACCOUNT_CHANGE_ACTIONS = (
    "employee_created", "employee_details_edited", "account_created", "account_edited",
    "activation_code_reissued", "activation_code_revoked", "password_reset",
    "account_disabled", "account_enabled", "employee_left", "employee_returned",
)


@validate_call
def add_account_change(
    conn: Connection, actor_employee_id: PositiveInt, target_employee_id: PositiveInt,
    action: str,
) -> int:
    """Append one account-administration action. Values themselves are never recorded."""
    if action not in ACCOUNT_CHANGE_ACTIONS:
        raise ValueError("Unknown account change")
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "INSERT INTO public.account_change (actor_employee_id, target_employee_id, action) "
            "VALUES (%s, %s, %s) RETURNING id",
            (actor_employee_id, target_employee_id, action),
        )
        return cur.fetchone()[0]


@validate_call
def get_account_changes(conn: Connection, target_employee_id: PositiveInt) -> list[dict]:
    """One employee's recorded account-administration actions, newest first."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT c.id, c.changed_at, c.action,
                   actor.name AS actor_name, actor.surname AS actor_surname
            FROM public.account_change AS c
            JOIN public.employee AS actor ON actor.id = c.actor_employee_id
            WHERE c.target_employee_id = %s
            ORDER BY c.changed_at DESC, c.id DESC
            """,
            (target_employee_id,),
        )
        return cur.fetchall()


@validate_call
def other_usable_role_holder_exists(conn: Connection, role_name: Name,
                                    employee_id: PositiveInt) -> bool:
    """Whether someone else holds the role on an active account with a password.

    Takes the transaction-scoped lock that migration 023's trigger also takes, so the
    answer stays true until the caller's change commits.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('tracker.' || %s))", (role_name,))
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM public.employee_role AS er
                JOIN public.role AS r ON r.id = er.role_id AND r.name = %s
                JOIN public.user_account AS a ON a.employee_id = er.employee_id
                WHERE er.employee_id <> %s AND a.is_active AND a.password_hash IS NOT NULL)
            """,
            (role_name, employee_id),
        )
        return cur.fetchone()[0]


@validate_call
def set_employee_left(conn: Connection, employee_id: PositiveInt, left: bool) -> bool:
    """Record that someone left (now), or clear it when they return."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("UPDATE public.employee SET left_at = CASE WHEN %s THEN clock_timestamp() END "
                    "WHERE id = %s RETURNING id", (left, employee_id))
        return cur.fetchone() is not None


@validate_call
def end_current_unit_assignments(conn: Connection, employee_id: PositiveInt) -> int:
    """Close every open unit assignment now; the history of past ones is kept."""
    with conn.cursor() as cur:
        cur.execute("UPDATE public.employee_unit_assignment SET valid_until = clock_timestamp() "
                    "WHERE employee_id = %s AND valid_until IS NULL", (employee_id,))
        return cur.rowcount
