"""FastAPI application, lifecycle, request models and authentication routes."""
from contextlib import ExitStack, asynccontextmanager
from dataclasses import asdict
import logging
import os
from pathlib import Path
from secrets import compare_digest
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
from psycopg.errors import UniqueViolation
from psycopg_pool import PoolTimeout
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from backend.annotations import Name
from backend.validation import validate_value
from backend.database import create_pool, read_database_config
from backend.fastapi.api import api_router
from backend.service.permissions_service import NotFound
from backend.service import auth_service as auth
from backend.service import catalog_service as catalog
from frontend.app import create_dash_app

logger = logging.getLogger(__name__)
COOKIE_NAME = 'tracker_session'
CSRF_COOKIE_NAME = 'tracker_csrf'
# Kept in step with the website roles so a new role needs no second list.
Role = Literal[auth.WEBSITE_ROLES]
ROOT = Path(__file__).resolve().parents[2]


# The largest legitimate body is a product picture: 8 MiB, about 11 MB as base64 text.
MAX_REQUEST_BYTES = 16 * 1024 * 1024


class RequestTooLarge(Exception):
    pass


class RequestSizeLimit:
    """Refuse a body over MAX_REQUEST_BYTES before anything reads it.

    Dash parses every JSON body before authentication runs, so without this limit one
    anonymous request could make the server hold an arbitrarily large document in memory.
    A declared length is refused at once; an undeclared (chunked) body stops being read.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        declared = dict(scope['headers']).get(b'content-length', b'0')
        if not declared.isdigit() or int(declared) > MAX_REQUEST_BYTES:
            response = JSONResponse(status_code=413, content={'detail': 'The request is too large'})
            return await response(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            if received > MAX_REQUEST_BYTES:
                raise RequestTooLarge()
            message = await receive()
            received += len(message.get('body', b''))
            if received > MAX_REQUEST_BYTES:
                raise RequestTooLarge()
            return message

        await self.app(scope, limited_receive, send)


def _public_origin(value):
    parts = urlsplit(value)
    if (parts.scheme not in ('http', 'https') or not parts.netloc or parts.username
            or parts.password or parts.path not in ('', '/') or parts.query or parts.fragment):
        raise ValueError('TRACKER_PUBLIC_ORIGIN must be one http(s) origin without a path')
    if parts.scheme == 'http' and parts.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('HTTP cookies are allowed only for local development; use HTTPS')
    return f'{parts.scheme}://{parts.netloc}'


@asynccontextmanager
async def lifespan(app: FastAPI):
    if app.state.db_pool is not None:
        # An explicitly supplied pool is owned by the caller (e.g. integration tests).
        yield
        return
    # Keep ordinary and administrative credentials separate throughout startup.
    app_settings = read_database_config(ROOT / '.env.app')
    admin_settings = read_database_config(ROOT / '.env.admin')
    if app.state.public_origin is None:
        origin = os.environ.get('TRACKER_PUBLIC_ORIGIN') or app_settings.get('TRACKER_PUBLIC_ORIGIN')
        if not origin:
            raise ValueError('Set TRACKER_PUBLIC_ORIGIN to the website address')
        app.state.public_origin = _public_origin(origin)
    with ExitStack() as cleanup:
        pool = create_pool(app_settings)
        cleanup.callback(pool.close)
        admin_pool = create_pool(admin_settings)
        cleanup.callback(admin_pool.close)
        try:
            pool.open(wait=True)
            admin_pool.open(wait=True)
            with pool.connection() as conn:
                # Stop early if the database is missing the login tables.
                conn.execute('SELECT password_set_at FROM public.user_account LIMIT 0')
                conn.execute('SELECT token_digest FROM auth_private.session LIMIT 0')
                conn.execute('SELECT subject_digest FROM auth_private.login_attempt LIMIT 0')
            with admin_pool.connection() as conn:
                conn.execute('SELECT 1')
            app.state.db_pool = pool
            app.state.admin_pool = admin_pool
            yield
        finally:
            app.state.db_pool = None
            app.state.admin_pool = None


class LoginBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: Name
    password: SecretStr = Field(max_length=1024)
    role: Role

    @field_validator('username', mode='before')
    @classmethod
    def username_uses_shared_name_rules(cls, value):
        # Pydantic does not execute our custom Annotated predicate metadata itself.
        validate_value(value, Name, 'username')
        return value


class RoleBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Role


def require_origin(request: Request):
    # Also prevents login CSRF, before a session/CSRF token exists.
    if request.headers.get('origin') != request.app.state.public_origin:
        raise HTTPException(403, 'Request origin is not allowed')


def require_csrf(request: Request):
    require_origin(request)
    require_csrf_token(request)


def require_csrf_token(request: Request):
    # Check that the browser sent the CSRF value belonging to this session.
    token = request.cookies.get(COOKIE_NAME)
    supplied = request.headers.get('x-csrf-token', '')
    if token and not compare_digest(supplied.encode(), auth.csrf_token(token).encode()):
        raise HTTPException(403, 'Invalid CSRF token')


def current_actor(request: Request):
    # Check the database once per request; later checks reuse the same identity.
    if not hasattr(request.state, 'actor'):
        request.state.actor = auth.authenticate_session(
            request.app.state.db_pool, request.cookies.get(COOKIE_NAME))
    # Only database-verified privileged roles select the privileged connection, which
    # they keep even while using the planner/supervisor view.
    # Pages that print links, such as the order sheet's QR code, need the public address.
    request.state.public_origin = request.app.state.public_origin
    request.state.business_pool = (request.app.state.admin_pool
        if set(auth.PRIVILEGED_ROLES) & set(request.state.actor.allowed_roles)
        else request.app.state.db_pool)
    return request.state.actor


def require_role(*roles: str):
    """Use Depends(require_role('planner')) on each future protected endpoint.

    Several roles mean any one of them is sufficient; the called service still checks
    its own action permission.
    """
    if not roles or any(role not in auth.WEBSITE_ROLES for role in roles):
        raise ValueError('Unknown website role')

    def check(actor: Annotated[auth.SessionActor, Depends(current_actor)]):
        if not set(roles) & set(actor.allowed_roles):
            raise auth.RoleDenied()
        return actor

    return check


def client_address(request: Request):
    return request.client.host if request.client else 'unknown'


def _limit_credential_callback(request, body, username_id):
    # A public callback that checks a secret shares the sign-in attempt limits.
    fields = [item for part in ('inputs', 'state') if isinstance(body.get(part), list)
              for item in body[part] if isinstance(item, dict)]
    username = next((item.get('value') for item in fields if item.get('id') == username_id), '')
    auth.limit_credential_attempts(request.app.state.db_pool,
                                   username if isinstance(username, str) else '', client_address(request))


def guard_website(request: Request):
    """One entrance check for Dash pages and callbacks; API routes use their dependencies."""
    path = request.url.path
    page = path.strip('/')
    if path == '/_dash-update-component':
        require_origin(request)
        # Dash has already read the request. Use its registered callback, not a browser role.
        body = getattr(request.state, 'json_body', None)
        if not isinstance(body, dict) or not isinstance(body.get('output'), str):
            raise HTTPException(400, 'Invalid callback request')
        callback = request.app.state.dash_app.callback_map.get(body['output'], {}).get('callback')
        access = getattr(callback, '_tracker_access', None)
        if access == 'public-page':
            username_id = getattr(callback, '_tracker_throttle', None)
            if username_id:
                _limit_credential_callback(request, body, username_id)
            try:
                current_actor(request)
            except (auth.InvalidSession, auth.RoleDenied):
                request.state.actor = None
            return
        roles = (access,) if isinstance(access, str) else tuple(access or ())
        if not roles or any(role not in auth.WEBSITE_ROLES for role in roles):
            raise HTTPException(403, 'This callback has no access rule')
        # The origin was checked above; check the CSRF token only once as well.
        require_csrf_token(request)
    elif request.method == 'GET' and page in auth.PAGE_ROLES:
        roles = auth.PAGE_ROLES[page]
    else:
        return
    try:
        require_role(*roles)(current_actor(request))
    except auth.InvalidSession:
        if request.method == 'GET':
            raise HTTPException(302, headers={'Location': '/'})
        raise


def _session_response(actor, token):
    # The page is not always named after the role, so the browser is told where to go.
    # Action permissions stay on the server.
    body = asdict(actor)
    del body['permissions']
    return {**body, 'page': auth.role_page(actor.role), 'csrf_token': auth.csrf_token(token)}


# One year: these URLs change whenever their content does, so a copy never goes stale.
IMMUTABLE = 'public, max-age=31536000, immutable'


def _cache_policy(request, response):
    """What a browser may keep. Pages, callbacks and API answers are never stored.

    Dash's scripts and styles are public, the same for everyone, and fingerprinted (the
    version is in the path, or an 'm' timestamp in /assets URLs), so they are cached for
    a year instead of being downloaded again on every page load (about 1.2 MB). A product
    picture requested with its current version may be kept privately by that browser.
    """
    path = request.url.path
    if path.startswith('/_dash-component-suites/') or (
            path.startswith('/assets/') and 'm' in request.query_params):
        return IMMUTABLE
    if path.startswith('/assets/'):
        return 'public, max-age=3600'
    if response.headers.get('cache-control', '').startswith('private,'):
        return response.headers['cache-control']
    return 'no-store'


def _cookie_options(request):
    # Cookies are sent only to this site, and only over HTTPS unless running locally.
    return dict(secure=request.app.state.public_origin.startswith('https://'),
                samesite='strict', path='/')


def _set_csrf_cookie(response, request, token):
    # Dash may read this value; the actual session cookie remains hidden from scripts.
    response.set_cookie(CSRF_COOKIE_NAME, auth.csrf_token(token), httponly=False,
                        max_age=int(auth.SESSION_LIFETIME.total_seconds()), **_cookie_options(request))


def create_app(*, pool=None, admin_pool=None, public_origin=None):
    application = FastAPI(lifespan=lifespan, dependencies=[Depends(guard_website)])
    application.state.db_pool = pool
    application.state.admin_pool = admin_pool
    application.state.public_origin = _public_origin(public_origin) if public_origin else None
    if pool is not None and public_origin is None:
        raise ValueError('An injected pool requires an explicit public_origin')
    if admin_pool is not None and pool is None:
        raise ValueError('An injected admin pool also requires an injected app pool')

    @application.middleware('http')
    async def prevent_auth_caching(request: Request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = _cache_policy(request, response)
        # No page is ever shown inside another site's frame (clickjacking), and a served
        # file is never reinterpreted as another type than the one declared.
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'none'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if getattr(request.state, 'actor', None) is not None:
            # Restore Dash's readable CSRF cookie after a refresh; the login cookie stays hidden.
            _set_csrf_cookie(response, request, request.cookies[COOKIE_NAME])
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Default validation errors can echo invalid inputs, including passwords.
        return JSONResponse(status_code=422, content={'detail': [
            {'loc': error['loc'], 'type': error['type'], 'msg': error['msg']}
            for error in exc.errors()
        ]})

    @application.exception_handler(auth.InvalidCredentials)
    async def invalid_credentials(request, exc):
        return JSONResponse(status_code=401, content={'detail': 'Invalid username or password'})

    @application.exception_handler(auth.InvalidSession)
    async def invalid_session(request, exc):
        return JSONResponse(status_code=401, content={'detail': 'Authentication required'})

    @application.exception_handler(auth.AccountDisabled)
    async def account_disabled(request, exc):
        return JSONResponse(status_code=403, content={'detail':
            'Your account has been disabled. Please contact the administration if you '
            'think this is a mistake.'})

    @application.exception_handler(auth.RoleDenied)
    async def role_denied(request, exc):
        return JSONResponse(status_code=403, content={'detail': 'No access to the requested role'})

    @application.exception_handler(auth.LoginThrottled)
    async def login_throttled(request, exc):
        return JSONResponse(status_code=429, content={'detail': 'Too many login attempts'},
                            headers={'Retry-After': str(int(auth.LOGIN_WINDOW.total_seconds()))})

    # Business errors from the services. Messages that could reveal an actor, SQL or a
    # submitted value are replaced by fixed text; service validation messages are safe.
    @application.exception_handler(PermissionError)
    async def permission_denied(request, exc):
        return JSONResponse(status_code=403, content={'detail': 'You do not have permission for this action'})

    @application.exception_handler(NotFound)
    async def not_found(request, exc):
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @application.exception_handler(ValueError)
    async def invalid_value(request, exc):
        detail = 'The request is not valid' if isinstance(exc, ValidationError) else str(exc)
        return JSONResponse(status_code=422, content={'detail': detail})

    @application.exception_handler(UniqueViolation)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={'detail': 'That value is already in use'})

    @application.exception_handler(DatabaseError)
    @application.exception_handler(PoolTimeout)
    async def database_unavailable(request, exc):
        # The log keeps the error class only: its text can quote SQL or values.
        logger.error('Database operation failed: %s', type(exc).__name__)
        return JSONResponse(status_code=503, content={'detail': 'The database is unavailable. Please retry.'})

    @application.exception_handler(RequestTooLarge)
    async def request_too_large(request, exc):
        return JSONResponse(status_code=413, content={'detail': 'The request is too large'})

    @application.exception_handler(Exception)
    async def unexpected_error(request, exc):
        # Anything unforeseen: the error log gets the traceback, the browser a fixed text.
        logger.error('Unhandled error on %s %s', request.method, request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content={'detail': 'Something went wrong. Please retry.'})

    @application.post('/auth/login', dependencies=[Depends(require_origin)])
    def login(body: LoginBody, request: Request, response: Response):
        actor, token = auth.login(
            request.app.state.db_pool, username=body.username,
            password=body.password.get_secret_value(), role=body.role,
            client_address=client_address(request),
            previous_token=request.cookies.get(COOKIE_NAME),
        )

        # Sets the session cookie, which keeps the user signed in until the session expires.
        # Scripts cannot read it (httponly); the separate CSRF cookie is the readable one.
        response.set_cookie(COOKIE_NAME, token, max_age=int(auth.SESSION_LIFETIME.total_seconds()),
                            httponly=True, **_cookie_options(request))
        _set_csrf_cookie(response, request, token)
        return _session_response(actor, token)

    @application.get('/products/{product_id}/image')
    def product_image(product_id: int, request: Request,
                      actor: Annotated[auth.SessionActor, Depends(current_actor)]):
        # Any signed-in employee may see a product picture; there is no narrower permission.
        stored = catalog.get_product_image_service(request.app.state.db_pool, product_id)
        if stored is None:
            raise HTTPException(404, 'No picture')
        image, media_type, version = stored
        # A URL naming the current version never changes content, so this browser may keep
        # it; pages link pictures with ?v=<version>. Anything else is fetched fresh.
        current = request.query_params.get('v') == str(version)
        return Response(content=image, media_type=media_type, headers={
            'Cache-Control': 'private, max-age=31536000, immutable' if current else 'no-store'})

    @application.get('/auth/session')
    def session(request: Request, response: Response, actor: Annotated[auth.SessionActor, Depends(current_actor)]):
        return _session_response(actor, request.cookies[COOKIE_NAME])

    @application.post('/auth/switch-role', dependencies=[Depends(require_csrf)])
    def switch_role(body: RoleBody, request: Request):
        token = request.cookies.get(COOKIE_NAME)
        actor = auth.switch_role(request.app.state.db_pool, token, body.role)
        return _session_response(actor, token)

    @application.post('/auth/logout', status_code=204, dependencies=[Depends(require_csrf)])
    def logout(request: Request):
        auth.logout(request.app.state.db_pool, request.cookies.get(COOKIE_NAME))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE_NAME, httponly=True, **_cookie_options(request))
        response.delete_cookie(CSRF_COOKIE_NAME, **_cookie_options(request))
        return response

    application.include_router(api_router(current_actor, require_csrf))

    # Dash and the API share one server and its pools; there is no Flask bridge.
    dash_app = create_dash_app(application)
    # Added after Dash's own middleware, so it runs first, before Dash reads any body.
    application.add_middleware(RequestSizeLimit)
    application.state.dash_app = dash_app
    # Use only checked HTTP callbacks; do not advertise or expose a second entrance.
    dash_app.backend.websocket_capability = False
    application.router.routes = [route for route in application.router.routes
                                 if getattr(route, 'path', None) != '/_dash-ws-callback']

    # Native FastAPI catch-all skips Dash's before-request asset discovery.
    dash_app._setup_server()
    # Register Dash's own page handler now, while this instance is the active Dash app.
    dash_app.backend._setup_catchall()

    return application


app = create_app()
