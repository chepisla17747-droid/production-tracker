"""Current unit supervision with preserved assignment history and safe moves."""
from datetime import datetime, timezone
from psycopg.errors import UniqueViolation

from backend.annotations import PositiveInt
from backend.validation import validate_call
from backend.operations import database_operations as db
from backend.operations.supervisor_operations import lock_supervised_units
from backend.service.permissions_service import require_permission

# Deliberately narrower than 'production_unit.manage': assigning supervision must not
# also authorize creating or renaming units. Migration 015 grants it to planners.
ASSIGN_PERMISSION = 'production_unit.assign_supervisor'


@validate_call
def assign_unit_supervisor_service(actor, pool, *, unit_id: PositiveInt,
                                   supervisor_id: PositiveInt | None,
                                   previous_unit_id: PositiveInt | None = None):
    """Assign/unassign a unit, optionally moving from another in one transaction.

    A supervisor can cover multiple units. An occupied destination is rejected,
    never silently replaced. Passing None leaves the unit without a supervisor.
    """
    if previous_unit_id is not None and (supervisor_id is None or previous_unit_id == unit_id):
        raise ValueError('A move needs a supervisor and two different units')
    try:
        with pool.connection() as conn, conn.transaction():
            require_permission(conn, actor, ASSIGN_PERMISSION)
            units = sorted({unit_id} | ({previous_unit_id} if previous_unit_id else set()))
            found = lock_supervised_units(conn, units)
            if len(found) != len(units):
                raise ValueError('Production unit does not exist')
            if supervisor_id is not None and not {'supervisor','admin'} & {r['name'] for r in db.get_employee_roles(conn, supervisor_id)}:
                raise ValueError('Employee must have the supervisor role')
            current = {r[1]: (r[0], r[2]) for r in conn.execute(
                'SELECT id,unit_id,employee_id FROM employee_unit_assignment '
                'WHERE unit_id=ANY(%s) AND is_supervisor AND valid_until IS NULL', (units,))}
            target = current.get(unit_id)
            if target and supervisor_id is not None and target[1] != supervisor_id:
                raise ValueError('This unit already has a supervisor; end that assignment first')
            if previous_unit_id and (previous_unit_id not in current or current[previous_unit_id][1] != supervisor_id):
                raise ValueError('The supervisor is not assigned to the previous unit')
            now = datetime.now(timezone.utc)
            if previous_unit_id:
                db.end_employee_unit_assignment(conn, current[previous_unit_id][0], now)
            if supervisor_id is None:
                if target:
                    db.end_employee_unit_assignment(conn, target[0], now)
                return None
            if target:
                return target[0]
            return db.assign_employee_to_unit(conn, supervisor_id, unit_id, now, is_supervisor=True)
    except UniqueViolation as exc:
        if exc.diag.constraint_name == 'unit_one_current_supervisor':
            raise ValueError('This unit already has a supervisor; end that assignment first') from None
        raise


def get_unit_supervision_service(actor, pool):
    """Units with their current supervisor, plus the employees who may be assigned."""
    with pool.connection() as conn:
        require_permission(conn, actor, ASSIGN_PERMISSION)
        return db.get_units_with_current_supervisor(conn), db.get_employees_with_role(conn, 'supervisor')
