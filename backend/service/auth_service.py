"""Database authentication and revocable sessions, independent of HTTP frameworks."""
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import compare_digest, token_urlsafe

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from backend.annotations import Name
from backend.validation import validate_call
from backend.operations import auth_operations as db
from backend.operations.database_operations import edit_user_account, get_employee_roles

WEBSITE_ROLES = ('planner', 'supervisor', 'manager', 'admin', 'hr', 'operations_admin')
# Roles whose page is not named after them, keeping the address readable.
ROLE_PAGES = {'operations_admin': 'operations'}
# Website pages and the roles allowed to open them. Most pages belong to one role;
# statistics is shared, and the backend still narrows each caller's visible records.
PAGE_ROLES = {**{ROLE_PAGES.get(role, role): (role,) for role in WEBSITE_ROLES},
              'statistics': ('manager', 'planner', 'supervisor'),
              # Supervisors see the overview narrowed to their own units.
              'manager': ('manager', 'supervisor'),
              # Managers edit or cancel any order; planners the ones they created.
              'orders': ('manager', 'planner'),
              # Completed orders; supervisors see those with a step in their units.
              'history': ('manager', 'supervisor'),
              # Every signed-in employee has a profile, whatever role they chose.
              'profile': WEBSITE_ROLES}
# Public pages have no role; the page itself authorizes what it shows.
PUBLIC_PAGES = ('activate',)
# Roles whose work needs the privileged database role: employee, account,
# account_private and catalog writes are granted to production_tracker_admin only.
PRIVILEGED_ROLES = ('admin', 'operations_admin')


def role_page(role):
    return ROLE_PAGES.get(role, role)


SESSION_LIFETIME = timedelta(hours=8)
LOGIN_WINDOW = timedelta(minutes=15)
HASHER = PasswordHash.recommended()
# Use the same password verifier for missing/disabled/pending accounts.
DUMMY_HASH = HASHER.hash(token_urlsafe(32))


class InvalidCredentials(Exception):
    pass


class InvalidSession(Exception):
    pass


class RoleDenied(Exception):
    pass


class AccountDisabled(Exception):
    """Correct credentials for an account an administrator has switched off."""
    pass


class LoginThrottled(Exception):
    pass


@dataclass(frozen=True)
class SessionActor:
    account_id: int
    employee_id: int
    username: Name
    role: str
    allowed_roles: tuple[str, ...]
    expires_at: datetime
    # Action permissions from the database, read with the session once per request so the
    # services need no second lookup. Never sent to the browser. None (an actor from login,
    # not read with a session) makes the services read them themselves.
    permissions: frozenset[str] | None = field(default=None, repr=False)


def token_digest(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    # Domain separation; knowing the CSRF value cannot recover the session token.
    return token_digest('tracker-csrf:' + token)


def _website_roles(names):
    # An administrator may open every website role; everyone else only the roles they hold.
    names = set(names)
    return WEBSITE_ROLES if 'admin' in names else tuple(role for role in WEBSITE_ROLES if role in names)


def allowed_roles(conn, employee_id):
    return _website_roles(row['name'] for row in get_employee_roles(conn, employee_id))


def limit_credential_attempts(pool, username, client_address):
    """Count one attempt at a secret (a password or an activation code); raise when over.

    Sign-in and activation share these counters, so neither is a way around the other.
    Commits the counters even when the attempt later fails.
    """
    with pool.connection() as conn, conn.transaction():
        db.prune_expired_auth_records(conn)
        address_count = db.reserve_login_attempt(
            conn, token_digest('address:' + client_address), LOGIN_WINDOW,
        )
        # An already-blocked address cannot create unlimited username buckets.
        denied = address_count > 100
        if not denied:
            denied = db.reserve_login_attempt(
                conn, token_digest('username:' + username.lower()), LOGIN_WINDOW,
            ) > 20
    if denied:
        raise LoginThrottled()


@validate_call
def login(pool, *, username: Name, password, role, client_address, previous_token=None):
    """Verify credentials/role and atomically rotate the session and last-login time."""
    limit_credential_attempts(pool, username, client_address)
    with pool.connection() as conn, conn.transaction():
        account = db.get_account_for_login(conn, username)
        # A pending account has no password at all and stays indistinguishable.
        known = account is not None and account['password_hash'] is not None
        stored_hash = account['password_hash'] if known else DUMMY_HASH
        try:
            verified = HASHER.verify(password, stored_hash)
        except (UnknownHashError, ValueError):
            verified = False
        if not known or not password or not verified:
            raise InvalidCredentials()
        # Only someone who has just proved they know the password is told this much.
        if not account['is_active']:
            raise AccountDisabled()

        # Determine the roles the user is allowed to assume.
        roles = allowed_roles(conn, account['employee_id'])
        # Check if the requested role is among the assigned roles.
        if role not in roles:
            raise RoleDenied()

        token = token_urlsafe(32)
        # Memorize the session in the database so the user does not have to re-login until the session expires.
        expires = db.add_session(
            conn, token_digest=token_digest(token), account_id=account['id'],
            employee_id=account['employee_id'], credential_digest=token_digest(stored_hash),
            role=role, lifetime=SESSION_LIFETIME,
        )

        # Try to edit the last-login time of the account. If it fails, the account disappeared while it was logging in.
        if not edit_user_account(conn, account['id'], last_login_at=datetime.now(timezone.utc)):
            raise RuntimeError('Account disappeared during login')

        # If the user had a previous session, delete it.
        if previous_token:
            db.delete_session(conn, token_digest(previous_token))

        # Return the actor so that the caller can use it to authorize further actions, and return the session token so that the caller can set it in a cookie.
        actor = SessionActor(account['id'], account['employee_id'], account['username'], role, roles, expires)
    return actor, token


def _resolve_session(conn, token):
    if not token or len(token) != 43:
        raise InvalidSession()
    row = db.get_session(conn, token_digest(token))
    if (row is None or not row['is_active'] or row['password_hash'] is None
            or row['session_employee_id'] != row['employee_id']
            or not compare_digest(row['credential_digest'], token_digest(row['password_hash']))):
        raise InvalidSession()
    roles = _website_roles(row['role_names'])
    if row['selected_role'] not in roles:
        raise RoleDenied()
    return SessionActor(row['account_id'], row['employee_id'], row['username'],
                        row['selected_role'], roles, row['expires_at'], frozenset(row['permissions']))


def authenticate_session(pool, token):
    with pool.connection() as conn:
        return _resolve_session(conn, token)


def switch_role(pool, token, role):
    with pool.connection() as conn, conn.transaction():
        actor = _resolve_session(conn, token)
        if role not in actor.allowed_roles:
            raise RoleDenied()
        if not db.update_session_role(conn, token_digest(token), role):
            raise InvalidSession()
        return replace(actor, role=role)


def logout(pool, token):
    if token:
        with pool.connection() as conn, conn.transaction():
            db.delete_session(conn, token_digest(token))
