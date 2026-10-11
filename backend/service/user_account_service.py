from backend.annotations import PositiveInt, Name, PositiveDuration, UNSET, editable
from backend.validation import validate_call, validate_operation_fields
from datetime import datetime, timezone

from psycopg import Connection

from backend.operations.database_operations import (
    add_account_change, add_pending_user_account, edit_employee, get_account_directory, get_employee_info,
    get_employee_roles, get_user_account, edit_user_account, lock_user_account,
)
from backend.service.auth_service import HASHER
from backend.service.activation_service import (
    DEFAULT_LIFETIME, REFUSED, consume_activation, create_activation_code, lock_activation)
from backend.service.permissions_service import actor_permissions, require_permission
from backend.service.role_service import (
    OPERATIONS_ADMIN, keeping_one_operations_admin, require_can_administer,
    require_other_operations_admin)
from zxcvbn import zxcvbn

# Failing this check is a wrong credential, not a missing permission, so a page
# that lets someone change their own password can say so plainly.
WRONG_CURRENT_PASSWORD = "Current password is incorrect"
LAST_OPERATIONS_ADMIN_ACCOUNT = (
    "You cannot disable or reset the only Operations Administrator's account. "
    "Please, assign the role to another employee first.")

# Account fields a request may carry. last_login_at is deliberately absent: it records
# when the server saw a successful login, so login writes it from the server clock and no
# caller, admin form or API body may submit it. Enabling and disabling go only through
# set_account_active_service, which records the change and protects the last Operations
# Administrator; an account is never moved to another employee.
SUBMITTABLE_ACCOUNT_FIELDS = ("username",)
SERVER_MANAGED_ACCOUNT_FIELDS = ("last_login_at", "password_hash", "password_set_at")


def _require_account_edit_permission(conn, actor, target_employee_id, *, basic):
    """Editing one's own account and a colleague's are separate permissions.

    A basic edit (a password change alone) on one's own account also accepts basic.edit.self.
    """
    if target_employee_id != actor.employee_id:
        allowed = {"user_account.complete.edit.other"}
    else:
        allowed = {"user_account.complete.edit.self"} | ({"user_account.basic.edit.self"} if basic else set())
    if actor_permissions(conn, actor).isdisjoint(allowed):
        raise PermissionError("Account permission required")


@validate_call
def edit_user_account_service(
    actor, target_employee_id: PositiveInt, pool, *,
    new_password=UNSET, current_password=None, **changes,
) -> bool:
    """Authorize account edits; callers supply a session-derived actor.

    Basic edits allow a password change only. Complete edits also allow the username.
    Hashes, password timestamps and the last login time
    remain backend-managed and are rejected here. Password changes retain
    current-password verification; pending account setup still requires the
    invitation flow.
    """
    if not changes and new_password is UNSET:
        raise ValueError("No account changes supplied")
    submitted_server_fields = changes.keys() & set(SERVER_MANAGED_ACCOUNT_FIELDS)
    if submitted_server_fields:
        raise ValueError(
            f"{', '.join(sorted(submitted_server_fields))} is recorded by the server "
            "and cannot be submitted"
        )
    if changes.keys() - set(SUBMITTABLE_ACCOUNT_FIELDS):
        raise ValueError("Unsupported account fields")
    if changes:
        validate_operation_fields(edit_user_account, changes, editable)
    with pool.connection() as conn, conn.transaction():
        # Only a password change on one's own account counts as a basic edit.
        _require_account_edit_permission(conn, actor, target_employee_id, basic=not changes)
        if target_employee_id != actor.employee_id:
            require_can_administer(conn, actor, target_employee_id)
        # Locks the account, keeping ownership and password/metadata updates atomic.
        account = conn.execute(
            "SELECT id, password_hash IS NULL FROM public.user_account "
            "WHERE employee_id = %s FOR UPDATE", (target_employee_id,)).fetchone()
        if account is None:
            return False
        account_id, pending = account
        if new_password is not UNSET:
            if pending:
                raise PermissionError("Initial password setup requires an invitation")
            if not add_or_change_password(
                conn, account_id, new_password, current_password=current_password,
            ):
                return False
        if changes:
            if target_employee_id != actor.employee_id:
                add_account_change(conn, actor.employee_id, target_employee_id, "account_edited")
            return edit_user_account(conn, account_id, **changes)
        return True


@validate_call
def create_user_account_service(
    actor,
    pool,
    employee_id: PositiveInt,
    username: Name,
    *,
    invitation_lifetime: PositiveDuration = DEFAULT_LIFETIME,
) -> tuple[int, str]:
    """Create a pending account and its activation code in one transaction.

    Returns (account id, code). The code is shown to its issuer once and never stored
    in readable form, so a lost code is replaced rather than recovered. No email
    address is needed: the administrator hands the code over in person.
    """
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "user_account.create")

        if get_employee_info(conn, employee_id, fields=("id",)) is None:
            raise ValueError("Employee does not exist")
        # The code is a credential for this employee's roles, so it follows the same rule.
        require_can_administer(conn, actor, employee_id)
        account_id = add_pending_user_account(conn, employee_id, username)
        code = create_activation_code(conn, account_id=account_id, lifetime=invitation_lifetime)
        add_account_change(conn, actor.employee_id, employee_id, "account_created")
        return account_id, code


def list_user_accounts_service(actor, pool, employee_ids=None):
    """Accounts of the listed employees (all without ``employee_ids``); hashes never selected."""
    with pool.connection() as conn:
        require_permission(conn, actor, "user_account.complete.view.other")
        return get_account_directory(conn, employee_ids)


def describe_activation_service(pool, username, code) -> dict:
    """Check a username and activation code, and return the details to confirm.

    Public: the code is the sole credential, so only this person's own record is
    returned and every unusable code produces one indistinguishable error.
    """
    with pool.connection() as conn, conn.transaction():
        activation = lock_activation(conn, username, code)
        employee = get_employee_info(
            conn, activation["employee_id"],
            fields=("name", "surname", "email", "phone_number"),
        )
        return {"username": activation["username"], "employee": employee,
                "roles": [row["name"] for row in get_employee_roles(
                    conn, activation["employee_id"])]}


def complete_account_setup_service(pool, username, code, new_password, *,
                                   email=UNSET, phone_number=UNSET) -> dict:
    """Set the first password, save corrected contacts, and consume the code.

    Public, code-authorized: no session exists yet. The whole activation is one
    transaction, so a code cannot be spent twice or leave an account half set up.
    Only the contact fields an employee may change on their own profile are accepted.
    """
    with pool.connection() as conn, conn.transaction():
        activation = lock_activation(conn, username, code)
        if not add_or_change_password(conn, activation["account_id"], new_password):
            raise ValueError(REFUSED)
        contacts = {field: value for field, value in
                    (("email", email), ("phone_number", phone_number)) if value is not UNSET}
        if contacts:
            validate_operation_fields(edit_employee, contacts, editable)
            edit_employee(conn, activation["employee_id"], **contacts)
        consume_activation(conn, activation["token_id"])
        roles = [row["name"] for row in get_employee_roles(conn, activation["employee_id"])]
        return {"username": activation["username"], "roles": roles}


def validate_password(new_password: str) -> None:
    """Apply the shared new-password rules without modifying the supplied text."""
    if not isinstance(new_password, str) or not new_password:
        raise ValueError("Password must be a nonempty string")

    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if len(new_password) > 72:
        raise ValueError("Password must be at most 72 characters long")

    if zxcvbn(new_password)["score"] < 3:
        raise ValueError("Password is too weak")


@validate_call
def add_or_change_password(
    conn: Connection, account_id: PositiveInt, new_password: str,
    *, current_password: str | None = None,
) -> bool:
    """Validate, hash, and save a password; verify the current one when set.

    Internal helper: callers must authorize initial setup with an invitation or
    obtain the account ID from an authenticated session for a password change.
    Pending accounts accept no current password; existing passwords cannot be
    overwritten by omitting it. Recovery needs a separate token-authorized flow.
    Callers own the transaction and token/session invalidation. Returns False
    for missing accounts or a concurrent password change; never enables accounts.
    """
    validate_password(new_password)
    account = get_user_account(conn, account_id, fields=("password_hash",))
    if account is None:
        return False

    stored_hash = account["password_hash"]
    if stored_hash is not None:
        if (
            not isinstance(current_password, str)
            or not current_password
            or not HASHER.verify(current_password, stored_hash)
        ):
            raise PermissionError(WRONG_CURRENT_PASSWORD)
    elif current_password is not None:
        raise PermissionError("Account has no current password")

    password_hash = HASHER.hash(new_password)
    return edit_user_account(
        conn, account_id,
        password_hash=password_hash,
        password_set_at=datetime.now(timezone.utc),
        expected_values={"password_hash": stored_hash},
    )


# Administering someone else's account: a new code, no code, a forced reset, or no access.
# None of these touch the caller's own account, which the profile page is for.
def _manage_account(conn, actor, account_id, permission, action, *, locks_out=False):
    """Authorize, lock and record one administrative action on another's account.

    `locks_out` marks actions that stop the account signing in, which must never take
    away the last usable Operations Administrator.
    """
    require_permission(conn, actor, permission)
    # One locking read returns everything the actions below need about the account.
    account = lock_user_account(conn, account_id)
    if account is None:
        raise ValueError("That account no longer exists. Refresh the list.")
    if account["employee_id"] == actor.employee_id:
        raise ValueError("You cannot administer your own account here. Use your profile page.")
    require_can_administer(conn, actor, account["employee_id"])
    if locks_out and OPERATIONS_ADMIN in {
            row["name"] for row in get_employee_roles(conn, account["employee_id"])}:
        require_other_operations_admin(conn, account["employee_id"],
                                       LAST_OPERATIONS_ADMIN_ACCOUNT)
    add_account_change(conn, actor.employee_id, account["employee_id"], action)
    return account


def _revoke_live_codes(conn, account_id) -> int:
    """Retire every code still outstanding for an account; returns how many."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE account_private.account_token SET revoked_at = CURRENT_TIMESTAMP "
            "WHERE account_id = %s AND purpose = 'invitation' "
            "AND consumed_at IS NULL AND revoked_at IS NULL",
            (account_id,),
        )
        return cur.rowcount


@validate_call
def revoke_activation_codes_service(actor, pool, account_id: PositiveInt) -> int:
    """Make any outstanding activation code unusable, issuing nothing in its place."""
    with pool.connection() as conn, conn.transaction():
        _manage_account(conn, actor, account_id, "user_account.create",
                        "activation_code_revoked")
        return _revoke_live_codes(conn, account_id)


@validate_call
def reissue_activation_code_service(actor, pool, account_id: PositiveInt,
                                    *, lifetime: PositiveDuration = DEFAULT_LIFETIME) -> str:
    """Replace an unused account's code with a fresh one, shown to its issuer once."""
    with pool.connection() as conn, conn.transaction():
        account = _manage_account(conn, actor, account_id, "user_account.create",
                                  "activation_code_reissued")
        if account["has_password"]:
            raise ValueError("This account is already active. Reset its password instead.")
        _revoke_live_codes(conn, account_id)
        return create_activation_code(conn, account_id=account_id, lifetime=lifetime)


@validate_call
def reset_account_password_service(actor, pool, account_id: PositiveInt,
                                   *, lifetime: PositiveDuration = DEFAULT_LIFETIME) -> str:
    """Return an account to waiting-for-activation and issue a fresh code.

    No administrator picks someone else's password: clearing the stored hash ends every
    session for that account, and its owner chooses a new password with the code.
    """
    with keeping_one_operations_admin(LAST_OPERATIONS_ADMIN_ACCOUNT), \
            pool.connection() as conn, conn.transaction():
        account = _manage_account(conn, actor, account_id, "user_account.complete.edit.other",
                                  "password_reset", locks_out=True)
        _revoke_live_codes(conn, account_id)
        # Session checks reject an account whose stored hash is gone, so access stops here.
        edit_user_account(conn, account_id, password_hash=None, password_set_at=None)
        return create_activation_code(conn, account_id=account_id, lifetime=lifetime)


@validate_call
def set_account_active_service(actor, pool, account_id: PositiveInt, is_active: bool) -> bool:
    """Enable or disable an account. Disabling ends its sessions at the next request."""
    with keeping_one_operations_admin(LAST_OPERATIONS_ADMIN_ACCOUNT), \
            pool.connection() as conn, conn.transaction():
        account = _manage_account(conn, actor, account_id, "user_account.complete.edit.other",
                                  "account_enabled" if is_active else "account_disabled",
                                  locks_out=not is_active)
        if is_active and account["left_at"]:
            raise ValueError("This person has left. Reinstate them before enabling the account.")
        return edit_user_account(conn, account_id, is_active=is_active)
