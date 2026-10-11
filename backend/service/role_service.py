"""Giving employees their website roles.

Two rules are enforced here rather than in the page, so a forged request cannot bypass
them: the administrator role is never granted through the website, and nobody edits
their own roles. Roles this service does not offer, such as the administrator role or a
non-website record role, are left exactly as they are on the target employee.
"""
from contextlib import contextmanager

from psycopg import Error as DatabaseError

from backend.annotations import PositiveInt
from backend.validation import validate_call
from backend.operations import database_operations as db
from backend.service.auth_service import WEBSITE_ROLES
from backend.service.permissions_service import require_permission

ASSIGN_PERMISSION = "role.assign"
# Website roles an employee can be given here. The administrator role is set directly in
# the database by whoever administers it, never through a browser.
UNGRANTABLE_ROLES = ("admin",)
ASSIGNABLE_ROLES = tuple(role for role in WEBSITE_ROLES if role not in UNGRANTABLE_ROLES)
# Someone must always be able to administer the website: see migration 023.
OPERATIONS_ADMIN = "operations_admin"
LAST_OPERATIONS_ADMIN = ("You cannot remove the only Operations Administrator. Please, assign "
                         "the role to another employee to remove the role from this user.")


@contextmanager
def keeping_one_operations_admin(message):
    """Turn migration 023's backstop (SQLSTATE CH001) into the caller's own message."""
    try:
        yield
    except DatabaseError as exc:
        if getattr(exc, "sqlstate", None) == "CH001":
            raise ValueError(message) from None
        raise


def require_other_operations_admin(conn, employee_id, message):
    """Refuse a change that would leave no usable Operations Administrator."""
    if not db.other_usable_role_holder_exists(conn, OPERATIONS_ADMIN, employee_id):
        raise ValueError(message)


def require_can_administer(conn, actor, target_employee_id):
    """Refuse to act on someone who holds a role the actor cannot grant and does not hold.

    An Operations Administrator cannot grant the administrator role, so they must not be
    able to reach an administrator's identity either: issuing a code for their account, or
    resetting it, would hand them a session as that administrator. Every service that acts
    on another employee's record or account calls this after its own permission check.
    Role assignment does not: it leaves the administrator role itself untouched.
    """
    protected = {row["name"] for row in db.get_employee_roles(conn, target_employee_id)} \
        & set(UNGRANTABLE_ROLES)
    if protected and protected - {row["name"] for row in db.get_employee_roles(conn, actor.employee_id)}:
        raise PermissionError("Only an administrator can change an administrator's record or account")


def get_assignable_roles_service(actor, pool):
    """The roles this page may offer, in the order they are defined."""
    with pool.connection() as conn:
        require_permission(conn, actor, ASSIGN_PERMISSION)
        stored = {row["name"]: row for row in db.get_roles(conn)}
        return [stored[name] for name in ASSIGNABLE_ROLES if name in stored]


@validate_call
def set_employee_roles_service(actor, pool, employee_id: PositiveInt, role_names) -> dict:
    """Make the employee's assignable roles exactly `role_names`; return what changed."""
    requested = set(role_names or ())
    forbidden = requested & set(UNGRANTABLE_ROLES)
    if forbidden:
        raise ValueError("The administrator role cannot be granted here")
    unknown = requested - set(ASSIGNABLE_ROLES)
    if unknown:
        raise ValueError(f"Unknown role: {', '.join(sorted(unknown))}")
    with keeping_one_operations_admin(LAST_OPERATIONS_ADMIN), \
            pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, ASSIGN_PERMISSION)
        # Checked after the permission so an unauthorized caller learns nothing else.
        if employee_id == actor.employee_id:
            raise ValueError("You cannot change your own roles. Ask another administrator.")
        if not db.lock_employee(conn, employee_id):
            raise ValueError("This employee no longer exists. Refresh the list.")
        stored = {row["name"]: row["id"] for row in db.get_roles(conn)}
        missing = requested - set(stored)
        if missing:
            raise ValueError(f"Role is not defined in the database: {', '.join(sorted(missing))}")
        held = {row["name"] for row in db.get_employee_roles(conn, employee_id)}
        # Only assignable roles are touched; anything else the employee holds stays.
        added = sorted(requested - held)
        removed = sorted((held & set(ASSIGNABLE_ROLES)) - requested)
        if OPERATIONS_ADMIN in removed:
            require_other_operations_admin(conn, employee_id, LAST_OPERATIONS_ADMIN)
        for name in added:
            db.assign_employee_role(conn, employee_id, stored[name])
        for name in removed:
            db.remove_employee_role(conn, employee_id, stored[name])
        # Recorded in the same transaction, so the change and its record cannot diverge.
        for name, action in [(role, "granted") for role in added] + \
                            [(role, "revoked") for role in removed]:
            db.add_role_change(conn, actor.employee_id, employee_id, name, action)
        return {"added": added, "removed": removed}


@validate_call
def get_employee_history_service(actor, pool, employee_id: PositiveInt) -> list[dict]:
    """Role changes and account administration for one employee, newest first."""
    with pool.connection() as conn:
        require_permission(conn, actor, ASSIGN_PERMISSION)
        entries = [{"changed_at": row["changed_at"], "action": f"role_{row['action']}",
                    "role_name": row["role_name"], "actor_name": row["actor_name"],
                    "actor_surname": row["actor_surname"]}
                   for row in db.get_role_changes(conn, employee_id)]
        entries += [{**row, "role_name": None} for row in db.get_account_changes(conn, employee_id)]
        return sorted(entries, key=lambda row: row["changed_at"], reverse=True)


def employee_roles_service(actor, pool, employee_ids=None):
    """Role names of the listed employees (everyone without ``employee_ids``), in one query."""
    with pool.connection() as conn:
        require_permission(conn, actor, ASSIGN_PERMISSION)
        return db.get_employee_role_names(conn, employee_ids)
