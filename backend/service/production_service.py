"""Authorized production actions built from the existing database helpers.

Managing an order after creation: managers may edit or cancel any order, planners only
the orders they created. Only an order's details change (number, contractor, dates and
notes); its product, process and quantity are fixed once pieces exist, so a wrong one is
cancelled and ordered again. Complete and cancelled orders are read-only.
"""
from datetime import date, datetime, time, timedelta

from backend.operations import catalog_operations as catalog
from backend.operations import production_operations as db
from backend.operations import overview_operations as overview_db
from backend.operations.supervisor_operations import (
    create_order_executions, reopen_order, sync_notifications)
from backend.annotations import NonBlankText, PositiveInt, UNSET, UnsetType, editable
from backend.service import paging
from backend.service.overview_service import order_status
from backend.service.permissions_service import NotFound, actor_permissions, require_permission
from backend.service.supervisor_service import part_cards
from backend.validation import validate_call, validate_operation_fields


def _check_dates(start_date, due_date):
    if start_date is not None and due_date is not None and due_date < start_date:
        raise ValueError("Due date cannot precede start date")


# Delay prediction: a heuristic estimate, not a schedule guarantee. It projects the
# order's remaining standard time, any overrun already run up on its current step, and
# a flat allowance when that step's unit is busy with another order right now, onto the
# factory's working calendar (no nights, lunch or weekends).
WORK_DAY_START = time(8, 0)
WORK_DAY_END = time(17, 0)
LUNCH_START = time(12, 0)
LUNCH_END = time(13, 0)
QUEUE_DELAY_SECONDS = 15 * 60


def _add_working_seconds(start, seconds):
    """Project ``seconds`` forward from ``start``, skipping nights, lunch and weekends.

    Working hours are the server's local time, like the due-date comparisons in
    ``overview_service``, so ``start`` is converted to local time first.
    """
    current = start.astimezone()
    remaining = seconds
    while remaining > 0:
        if current.weekday() >= 5:
            current = datetime.combine(current.date() + timedelta(days=1), WORK_DAY_START, current.tzinfo)
            continue
        work_start = datetime.combine(current.date(), WORK_DAY_START, current.tzinfo)
        work_end = datetime.combine(current.date(), WORK_DAY_END, current.tzinfo)
        lunch_start = datetime.combine(current.date(), LUNCH_START, current.tzinfo)
        lunch_end = datetime.combine(current.date(), LUNCH_END, current.tzinfo)
        if current < work_start:
            current = work_start
        if current >= work_end:
            current = datetime.combine(current.date() + timedelta(days=1), WORK_DAY_START, current.tzinfo)
            continue
        if lunch_start <= current < lunch_end:
            current = lunch_end
            continue
        block_end = lunch_start if current < lunch_start else work_end
        available = (block_end - current).total_seconds()
        if remaining <= available:
            current += timedelta(seconds=remaining)
            remaining = 0
        else:
            remaining -= available
            current = block_end
    return current


def predict_order_eta(cards, busy_counts, now):
    """Predicted completion for an order still in progress, or ``None`` once nothing
    is left to predict (no steps, or every step already finished)."""
    pending = sorted((c for c in cards if c["status"] != "completed"), key=lambda c: c["sequence_number"])
    if not pending:
        return None
    current, *future = pending
    standard = current["standard_time_seconds"] or 0
    remaining_current = max(standard - current["elapsed_seconds"], 0)
    overrun = max(current["elapsed_seconds"] - standard, 0)
    elsewhere = busy_counts.get(current["unit_id"], 0) - current["running"]
    queue_delay = QUEUE_DELAY_SECONDS if elsewhere > 0 else 0
    remaining_future = sum(c["standard_time_seconds"] or 0 for c in future)
    return _add_working_seconds(now, remaining_current + overrun + queue_delay + remaining_future)


# One order expands into a row per piece and one per piece and step, all inserted in one
# transaction under the catalog lock. These caps keep a single request from filling the
# shared database or holding that lock for long, whichever page or API submitted it.
MAX_ORDER_QUANTITY = 100_000
MAX_ORDER_EXECUTIONS = 1_000_000


# Create one order and its requested number of items; any failure rolls back both.
@validate_call
def create_work_order_service(
    actor, pool, *, order_number: NonBlankText, contractor_id: PositiveInt,
    product_type_id: PositiveInt, process_def_id: PositiveInt, quantity: PositiveInt,
    start_date: date | None = None, due_date: date | None = None,
    notes: str | None = None,
) -> int:
    """Return the new order ID. Actor comes from authentication, never the form.

    Creates individual items and execution rows; it never starts work.
    """
    if quantity > MAX_ORDER_QUANTITY:
        raise ValueError(f"An order can have at most {MAX_ORDER_QUANTITY:,} pieces")
    with pool.connection() as conn, conn.transaction():
        require_permission(conn, actor, "work_order.create")
        order = {
            "order_number": order_number, "contractor_id": contractor_id,
            "created_by": actor.employee_id, "start_date": start_date,
            "due_date": due_date, "notes": notes,
        }
        validate_operation_fields(db.add_work_order, order, editable)
        _check_dates(start_date, due_date)
        if db.get_contractor(conn, contractor_id, fields=("id",)) is None:
            raise ValueError("Selected contractor does not exist")

        # Keep catalog edits from changing eligibility while this order is created.
        catalog.lock_catalog(conn)
        product = catalog.get_product_type(conn, product_type_id, ("id", "is_orderable"))
        if product is None:
            raise ValueError("Selected product does not exist")
        if not product["is_orderable"]:
            raise ValueError("Selected product is unavailable for orders")
        process = catalog.get_process_definition(
            conn, process_def_id, ("product_type_id", "is_active"),
        )
        if process is None:
            raise ValueError("Selected process does not exist")
        if process["product_type_id"] != product_type_id:
            raise ValueError("Selected process does not belong to the product")
        if not process["is_active"]:
            raise ValueError("Selected process is inactive")
        if quantity * len(catalog.get_steps_for_process(conn, process_def_id)) > MAX_ORDER_EXECUTIONS:
            raise ValueError("This order is too large for one work order. Split it into smaller orders.")

        order_id = db.add_work_order(conn, **order)
        db.add_product_instances(conn, order_id, product_type_id, process_def_id, quantity)
        create_order_executions(conn, order_id)
        sync_notifications(conn, None, order_id)
        return order_id


ORDER_PAGE_SIZE = 20


def _order_scope(conn, actor):
    """None when the caller manages every order, else their own id as the creator filter."""
    permissions = actor_permissions(conn, actor)
    if "work_order.edit.all" in permissions:
        return None
    if "work_order.edit.own" in permissions:
        return actor.employee_id
    raise PermissionError("Order management permission required")


@validate_call
def list_work_orders_service(actor, pool, *, search: str = "", after: str | None = None,
                             before: str | None = None, order_id: PositiveInt | None = None) -> dict:
    """The caller's manageable orders, newest first, one page of ``ORDER_PAGE_SIZE`` at a time.

    ``after``/``before`` are the ``next``/``previous`` cursors returned with a page; each
    page is read straight from the index, however many orders exist. ``order_id`` narrows
    the list to that one order, to refresh a single row. Cancelled orders are listed too, so
    a cancellation stays visible to whoever made it. Each order carries its own contractor;
    the edit form finds others with ``search_order_contractors_service``.
    """
    with pool.connection() as conn, conn.transaction():
        creator = _order_scope(conn, actor)
        rows = overview_db.get_orders(
            conn, created_by=creator, include_cancelled=True, order_id=order_id, search=search,
            order_by="created", after=paging.decode(after, paging.MOMENT, paging.KEY),
            before=paging.decode(before, paging.MOMENT, paging.KEY), limit=ORDER_PAGE_SIZE + 1)
        page = paging.page(rows, ORDER_PAGE_SIZE, lambda o: (o["creation_time"], o["work_order_id"]),
                           after=after, before=before)
        shown = page.pop("rows")
        now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
        rows = {}
        for row in overview_db.get_order_steps(conn, [o["work_order_id"] for o in shown]):
            rows.setdefault(row["work_order_id"], []).append(row)
        requests = {}
        for request in db.get_open_corrective_requests(conn, [o["work_order_id"] for o in shown]):
            requests.setdefault(request["work_order_id"], []).append(request)
        cards = {order_id: part_cards(order_rows) for order_id, order_rows in rows.items()}
        unit_ids = {card["unit_id"] for order_cards in cards.values() for card in order_cards}
        busy_counts = db.get_running_counts_by_unit(conn, unit_ids)
    for order in shown:
        order["status"] = ("cancelled" if order["is_cancelled"]
                           else order_status(order, rows.get(order["work_order_id"], []), now))
        order["editable"] = order["status"] not in ("cancelled", "complete")
        order["corrective_requests"] = requests.get(order["work_order_id"], [])
        order["predicted_eta"] = (predict_order_eta(cards.get(order["work_order_id"], []), busy_counts, now)
                                   if order["status"] in ("not_started", "in_process", "delayed") else None)
    return dict(page, orders=shown, all_orders=creator is None)


CONTRACTOR_MATCHES = 20


@validate_call
def search_order_contractors_service(actor, pool, search: str = "") -> list[dict]:
    """Contractors whose name, email or phone matches, for an order's contractor selector.

    Whoever may manage orders may choose their contractor (managers hold no contractor.view),
    so this uses the order-management permission. At most CONTRACTOR_MATCHES are returned.
    """
    with pool.connection() as conn:
        _order_scope(conn, actor)
        return db.get_contractors(conn, search=search, limit=CONTRACTOR_MATCHES)


def _lock_manageable_order(conn, actor, order_id):
    creator = _order_scope(conn, actor)
    order = db.lock_work_order(conn, order_id)
    # Someone else's order is reported like a missing one, revealing nothing about it.
    if order is None or (creator is not None and order["created_by"] != creator):
        raise NotFound("This work order does not exist or is not yours to manage.")
    if order["is_cancelled"]:
        raise ValueError("This work order was cancelled and can no longer be changed.")
    if order["completion_time"] is not None:
        raise ValueError("This work order is complete and can no longer be changed.")
    return order


@validate_call
def edit_work_order_service(
    actor, pool, order_id: PositiveInt, *,
    order_number: NonBlankText | UnsetType = UNSET,
    contractor_id: PositiveInt | UnsetType = UNSET,
    start_date: date | None | UnsetType = UNSET, due_date: date | None | UnsetType = UNSET,
    notes: str | None | UnsetType = UNSET,
) -> bool:
    """Change an open order's details; omitted fields keep their stored value.

    A duplicate order number raises UniqueViolation.
    """
    changes = {key: value for key, value in (
        ("order_number", order_number.strip() if isinstance(order_number, str) else order_number),
        ("contractor_id", contractor_id), ("start_date", start_date),
        ("due_date", due_date), ("notes", notes)) if value is not UNSET}
    if not changes:
        raise ValueError("No order changes supplied")
    with pool.connection() as conn, conn.transaction():
        order = _lock_manageable_order(conn, actor, order_id)
        # Dates are checked against the stored value of whichever one was not submitted.
        _check_dates(changes.get("start_date", order["start_date"]),
                     changes.get("due_date", order["due_date"]))
        if "contractor_id" in changes and db.get_contractor(
                conn, contractor_id, fields=("id",)) is None:
            raise ValueError("Selected contractor does not exist")
        return db.edit_work_order(conn, order_id, **changes)


@validate_call
def cancel_work_order_service(actor, pool, order_id: PositiveInt) -> bool:
    """Cancel an open order. Its pieces leave every queue, overview and statistic at once."""
    with pool.connection() as conn, conn.transaction():
        _lock_manageable_order(conn, actor, order_id)
        return db.edit_work_order(conn, order_id, is_cancelled=True)


MAX_REPLACEMENTS = 10000


@validate_call
def resolve_corrective_request_service(
    actor, pool, request_id: PositiveInt, *, action: str,
    quantity: PositiveInt | None = None, note: str | None = None,
) -> int:
    """Answer a scrap request: make replacement pieces, or close it without any.

    Replacements follow the order's own product and process version, start at the first
    step, and reopen a completed order. Returns the number of pieces added.
    """
    if action not in ("replace", "close"):
        raise ValueError("Choose to add replacement pieces or close the request")
    if action == "replace" and not quantity:
        raise ValueError("Enter how many replacement pieces to make")
    if quantity and quantity > MAX_REPLACEMENTS:
        raise ValueError("That is more replacement pieces than an order can take")
    note = (note or "").strip()[:1000] or None
    with pool.connection() as conn, conn.transaction():
        creator = _order_scope(conn, actor)
        request = db.lock_corrective_request(conn, request_id)
        order = request and db.get_work_order(conn, request["work_order_id"])
        if order is None or (creator is not None and order["created_by"] != creator):
            raise NotFound("This request does not exist or is not yours to answer.")
        if request["resolved_at"] is not None:
            raise ValueError("This request was already answered. Refresh the list.")
        if order["is_cancelled"]:
            raise ValueError("This work order was cancelled and can no longer be changed.")
        added = 0
        if action == "replace":
            product_type_id, process_def_id = db.get_order_route(conn, order["id"])
            db.add_product_instances(conn, order["id"], product_type_id, process_def_id, quantity)
            create_order_executions(conn, order["id"])
            reopen_order(conn, order["id"])
            sync_notifications(conn, None, order["id"])
            added = quantity
        db.resolve_corrective_request(conn, request_id, actor.employee_id,
                                      "replaced" if added else "closed", added or None, note)
        return added
