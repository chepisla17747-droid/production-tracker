from backend.operations.database_operations import get_employee_permissions


class NotFound(LookupError):
    """A record is missing, or is outside what the caller may see. Its message is shown."""


def actor_permissions(conn, actor):
    """The actor's action permissions, taken from the database.

    A website session already carries them (read with the session, once per request);
    internal callers without a session, such as scripts and tests, have them read here.
    """
    permissions = getattr(actor, 'permissions', None)
    return get_employee_permissions(conn, actor.employee_id) if permissions is None else permissions


def require_permission(conn, actor, permission):
    """Raise PermissionError unless the actor holds this action permission."""
    if permission not in actor_permissions(conn, actor):
        raise PermissionError(f"Actor {actor} lacks permission: {permission}")
