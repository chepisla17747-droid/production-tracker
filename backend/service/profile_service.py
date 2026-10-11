"""The authenticated employee's own profile: their record, account, roles and units.

Everything here is about the caller. No identifier is taken from the browser, so one
employee's page can never be pointed at another's record.
"""
from backend.operations.database_operations import (
    get_current_units_for_employee, get_employee_info, get_employee_roles, get_user_account,
    USER_ACCOUNT_PUBLIC_FIELDS)
from backend.service.permissions_service import require_permission

PROFILE_FIELDS = ("id", "name", "surname", "email", "phone_number", "birth_date", "regist_date")


def get_own_profile_service(actor, pool):
    """Return the caller's record, account, roles and current units; never a hash."""
    with pool.connection() as conn:
        # Reading one's own employee record needs no permission; the account does.
        require_permission(conn, actor, "user_account.view.self")
        employee = get_employee_info(conn, actor.employee_id, PROFILE_FIELDS)
        if employee is None:
            raise ValueError("This employee record no longer exists.")
        account = get_user_account(
            conn, employee_id=actor.employee_id,
            fields=(*USER_ACCOUNT_PUBLIC_FIELDS, "password_set_at"),
        )
        return {
            "employee": employee,
            "account": account,
            "roles": [row["name"] for row in get_employee_roles(conn, actor.employee_id)],
            "units": get_current_units_for_employee(conn, actor.employee_id),
        }
