"""Authentication SQL. Callers own transactions; raw session tokens never enter SQL."""
from datetime import timedelta

from psycopg.rows import dict_row
from backend.annotations import Name
from backend.validation import validate_call


def reserve_login_attempt(conn, subject_digest, window):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO auth_private.login_attempt (subject_digest, attempts)
            VALUES (%s, 1)
            ON CONFLICT (subject_digest) DO UPDATE SET
                attempts = CASE WHEN login_attempt.window_started_at <= CURRENT_TIMESTAMP - %s
                    THEN 1 ELSE LEAST(login_attempt.attempts + 1, 101) END,
                window_started_at = CASE WHEN login_attempt.window_started_at <= CURRENT_TIMESTAMP - %s
                    THEN CURRENT_TIMESTAMP ELSE login_attempt.window_started_at END
            RETURNING attempts
        """, (subject_digest, window, window))
        return cur.fetchone()[0]


def prune_expired_auth_records(conn):
    conn.execute("DELETE FROM auth_private.session WHERE expires_at <= CURRENT_TIMESTAMP")
    conn.execute("DELETE FROM auth_private.login_attempt WHERE window_started_at < CURRENT_TIMESTAMP - %s",
                 (timedelta(days=1),))


@validate_call
def get_account_for_login(conn, username: Name):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT id, employee_id, username, password_hash, is_active
            FROM public.user_account WHERE LOWER(username) = LOWER(%s)
            FOR UPDATE
        """, (username,))
        return cur.fetchone()


def add_session(conn, *, token_digest, account_id, employee_id, credential_digest, role, lifetime):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO auth_private.session
                (token_digest, account_id, employee_id, credential_digest, selected_role, expires_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP + %s)
            RETURNING expires_at
        """, (token_digest, account_id, employee_id, credential_digest, role, lifetime))
        return cur.fetchone()[0]


def get_session(conn, token_digest):
    """The session, its account, and the employee's role and permission names in one query.

    Every request resolves its session here, so roles and permissions are read together
    rather than in separate round trips.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.account_id, s.employee_id AS session_employee_id,
                   s.credential_digest, s.selected_role, s.expires_at,
                   a.employee_id, a.username, a.password_hash, a.is_active,
                   ARRAY(SELECT r.name FROM public.employee_role er
                         JOIN public.role r ON r.id = er.role_id
                         WHERE er.employee_id = a.employee_id) AS role_names,
                   ARRAY(SELECT DISTINCT p.name FROM public.employee_role er
                         JOIN public.role_permission rp ON rp.role_id = er.role_id
                         JOIN public.permission p ON p.id = rp.permission_id
                         WHERE er.employee_id = a.employee_id) AS permissions
            FROM auth_private.session s
            JOIN public.user_account a ON a.id = s.account_id
            WHERE s.token_digest = %s AND s.expires_at > CURRENT_TIMESTAMP
        """, (token_digest,))
        return cur.fetchone()


def delete_session(conn, token_digest):
    conn.execute("DELETE FROM auth_private.session WHERE token_digest = %s", (token_digest,))


def update_session_role(conn, token_digest, role):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE auth_private.session SET selected_role = %s
            WHERE token_digest = %s AND expires_at > CURRENT_TIMESTAMP RETURNING token_digest
        """, (role, token_digest))
        return cur.fetchone() is not None
