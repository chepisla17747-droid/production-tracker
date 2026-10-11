"""JSON routes for the core production flows: orders, the overview and supervisor actions.

They call the same services as the Dash pages, which do their own permission checks.
Every route needs a valid session; writes also need the site's Origin and the session's
CSRF token. Errors are mapped to status codes by the handlers in `post.py`.
"""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.service import overview_service as overview
from backend.service import production_service as production
from backend.service.supervisor_service import update_part_service

OrderNumber = Annotated[str, Field(min_length=1, max_length=128)]
Id = Annotated[int, Field(gt=0)]


class NewOrder(BaseModel):
    model_config = ConfigDict(extra='forbid')
    order_number: OrderNumber
    contractor_id: Id
    product_type_id: Id
    process_def_id: Id
    quantity: Annotated[int, Field(gt=0, le=production.MAX_ORDER_QUANTITY)]
    start_date: date | None = None
    due_date: date | None = None
    notes: Annotated[str, Field(max_length=4000)] | None = None


class OrderChanges(BaseModel):
    """Only the fields present in the request are changed."""
    model_config = ConfigDict(extra='forbid')
    order_number: OrderNumber = None
    contractor_id: Id = None
    start_date: date | None = None
    due_date: date | None = None
    notes: Annotated[str, Field(max_length=4000)] | None = None


class PartAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    order_id: Id
    process_id: Id
    step_id: Id
    action: Literal['start', 'complete', 'skip']
    quantity: Id
    # Chosen by the client once per submission, so a retried request is applied once.
    request_id: UUID


def api_router(current_actor, require_csrf):
    """Build the router around post.py's session and CSRF dependencies."""
    router = APIRouter(prefix='/api', dependencies=[Depends(current_actor)])
    writes = [Depends(require_csrf)]

    def caller(request: Request):
        return request.state.actor, request.state.business_pool

    @router.get('/orders')
    def list_orders(request: Request, search: str = '', after: str | None = None,
                    before: str | None = None):
        # Pages are read from a cursor: pass back the 'next' or 'previous' value of a page.
        return production.list_work_orders_service(*caller(request), search=search,
                                                    after=after, before=before)

    @router.post('/orders', status_code=201, dependencies=writes)
    def create_order(body: NewOrder, request: Request):
        return {'id': production.create_work_order_service(*caller(request), **body.model_dump())}

    @router.patch('/orders/{order_id}', dependencies=writes)
    def edit_order(order_id: Id, body: OrderChanges, request: Request):
        changes = body.model_dump(exclude_unset=True)
        # An explicit null clears a date or the notes, but never the number or contractor.
        if any(changes.get(key, '') is None for key in ('order_number', 'contractor_id')):
            raise ValueError('The order number and contractor cannot be empty')
        production.edit_work_order_service(*caller(request), order_id, **changes)
        return production.list_work_orders_service(*caller(request), order_id=order_id)['orders'][0]

    @router.post('/orders/{order_id}/cancel', dependencies=writes)
    def cancel_order(order_id: Id, request: Request):
        production.cancel_work_order_service(*caller(request), order_id)
        return production.list_work_orders_service(*caller(request), order_id=order_id)['orders'][0]

    @router.get('/orders/{order_id}/summary')
    def order_summary(order_id: Id, request: Request):
        return overview.get_order_summary_service(*caller(request), order_id)

    @router.get('/orders/{order_id}/eta')
    def order_eta(order_id: Id, request: Request):
        # Replaces POST /api/calculate-eta of the old standalone ETA server.
        return overview.get_order_forecast_service(*caller(request), order_id)

    @router.get('/overview')
    def factory_overview(request: Request, week: date | None = None, search: str = '',
                         status: str = 'all', page: Id = 1):
        return overview.get_overview_service(*caller(request), week_start=week, search=search,
                                             status=status, page=page)

    @router.post('/supervisor/actions', dependencies=writes)
    def part_action(body: PartAction, request: Request):
        values = body.model_dump()
        values['request_id'] = str(values['request_id'])
        return {'quantity': update_part_service(*caller(request), **values)}

    return router
