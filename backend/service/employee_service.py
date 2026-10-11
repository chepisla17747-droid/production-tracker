"""Employee records: creation, edits, the directory and departures."""
from backend.annotations import PositiveInt, editable
from backend.validation import validate_call, validate_operation_fields
from backend.operations.database_operations import (
    add_account_change, add_employee, edit_employee, get_employees)
from backend.operations import database_operations as db
from backend.service import paging
from backend.service.permissions_service import require_permission
from backend.service.role_service import (
    OPERATIONS_ADMIN, keeping_one_operations_admin, require_can_administer,
    require_other_operations_admin)


def create_employee_service(actor, pool, **employee_data):
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "employee.create")
        validate_operation_fields(add_employee, employee_data, editable)
        employee_id = add_employee(conn, **employee_data)
        add_account_change(conn, actor.employee_id, employee_id, "employee_created")
        return employee_id


@validate_call
def edit_employee_service(actor, target_employee_id: PositiveInt, pool, **changes):
    with pool.connection() as conn, conn.transaction():
        # Editing oneself and editing a colleague are separate permissions.
        require_permission(conn, actor, "employee.edit.self"
                           if target_employee_id == actor.employee_id else "employee.edit.other")
        if target_employee_id != actor.employee_id:
            require_can_administer(conn, actor, target_employee_id)
        validate_operation_fields(edit_employee, changes, editable)
        changed = edit_employee(conn, target_employee_id, **changes)
        if changed:
            add_account_change(conn, actor.employee_id, target_employee_id,
                               "employee_details_edited")
        return changed


# The only fields an employee may correct on their own profile. Name, surname and date of
# birth are identity fields; only someone with employee.edit.other may change those.
SELF_EDITABLE_FIELDS = ("email", "phone_number")


def edit_own_contact_details_service(actor, pool, **changes):
    """Update the actor's own contact details, and nothing else.

    The target is always the session's own employee id, so no identifier is accepted
    from the browser, and the field list is checked before any permission or write.
    """
    unsupported = set(changes) - set(SELF_EDITABLE_FIELDS)
    if unsupported:
        raise ValueError("Only an email address and phone number can be changed here")
    if not changes:
        raise ValueError("No changes supplied")
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "employee.edit.self")
        validate_operation_fields(edit_employee, changes, editable)
        return edit_employee(conn, actor.employee_id, **changes)


EMPLOYEE_PAGE_SIZE = 50


def list_employees_service(actor, pool, *, search="", include_left=True, employee_ids=None,
                           after=None, before=None):
    """One page of employee records by surname and name, or exactly ``employee_ids``.

    ``after``/``before`` are the ``next``/``previous`` cursors of a page already shown.
    """
    kinds = (paging.TEXT, paging.TEXT, paging.KEY)
    with pool.connection() as conn:
        require_permission(conn, actor, "employee.view.other")
        rows = get_employees(conn, search=search, include_left=include_left, employee_ids=employee_ids,
                             after=paging.decode(after, *kinds), before=paging.decode(before, *kinds),
                             limit=None if employee_ids is not None else EMPLOYEE_PAGE_SIZE + 1)
    if employee_ids is not None:
        return {"employees": rows, "next": None, "previous": None}
    result = paging.page(rows, EMPLOYEE_PAGE_SIZE, lambda e: (e["surname"], e["name"], e["id"]),
                         after=after, before=before)
    return {"employees": result.pop("rows"), **result}


LAST_OPERATIONS_ADMIN_LEAVING = (
    "You cannot mark the only Operations Administrator as left. "
    "Please, assign the role to another employee first.")


def _lock_other_employee(conn, actor, employee_id):
    require_permission(conn, actor, "employee.edit.other")
    if employee_id == actor.employee_id:
        raise ValueError("You cannot change your own employment here. Ask another administrator.")
    employee = db.lock_employee(conn, employee_id)
    if employee is None:
        raise ValueError("This employee no longer exists. Refresh the list.")
    require_can_administer(conn, actor, employee_id)
    return employee


@validate_call
def mark_employee_left_service(actor, pool, employee_id: PositiveInt) -> None:
    """Someone has left: keep their record and history, end their access and units.

    Their account is disabled (which ends their sessions), any outstanding activation code
    is revoked, and their current unit assignments end now. They disappear from selectors.
    """
    with keeping_one_operations_admin(LAST_OPERATIONS_ADMIN_LEAVING), \
            pool.connection() as conn, conn.transaction():
        employee = _lock_other_employee(conn, actor, employee_id)
        if employee["left_at"] is not None:
            raise ValueError("This person is already marked as left.")
        if OPERATIONS_ADMIN in {row["name"] for row in db.get_employee_roles(conn, employee_id)}:
            require_other_operations_admin(conn, employee_id, LAST_OPERATIONS_ADMIN_LEAVING)
        db.set_employee_left(conn, employee_id, True)
        account = db.get_user_account(conn, employee_id=employee_id, fields=("id", "is_active"))
        if account is not None:
            if account["is_active"]:
                db.edit_user_account(conn, account["id"], is_active=False)
            conn.execute("UPDATE account_private.account_token SET revoked_at = CURRENT_TIMESTAMP "
                         "WHERE account_id = %s AND consumed_at IS NULL AND revoked_at IS NULL",
                         (account["id"],))
        db.end_current_unit_assignments(conn, employee_id)
        add_account_change(conn, actor.employee_id, employee_id, "employee_left")


@validate_call
def reinstate_employee_service(actor, pool, employee_id: PositiveInt) -> None:
    """Someone returns. Their account stays disabled until an administrator enables it."""
    with pool.connection() as conn, conn.transaction():
        employee = _lock_other_employee(conn, actor, employee_id)
        if employee["left_at"] is None:
            raise ValueError("This person has not left.")
        db.set_employee_left(conn, employee_id, False)
        add_account_change(conn, actor.employee_id, employee_id, "employee_returned")
