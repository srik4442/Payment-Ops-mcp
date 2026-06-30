import sys
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.models.models import Customer, Order, RefundLog
from src.integrations import stripe_client as sc

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

REFUND_WINDOW_DAYS = 90


def _get_customer_by_email(db: Session, email: str) -> Customer | None:
    return db.query(Customer).filter_by(email=email).first()


def lookup_customer(db: Session, email: str) -> str:
    """Look up a customer by email, joining internal DB data with live Stripe status."""
    customer = _get_customer_by_email(db, email)
    if not customer:
        return f"No customer found with email '{email}' in the orders database."

    orders = db.query(Order).filter_by(customer_id=customer.id).order_by(Order.created_at.desc()).all()
    order_count = len(orders)
    total_cents = sum(o.amount_cents for o in orders if o.status == "paid")

    stripe_info = ""
    if customer.stripe_customer_id:
        try:
            sc_customer = sc.get_customer(customer.stripe_customer_id)
            stripe_info = f"\n**Stripe ID:** {sc_customer.id}\n**Stripe email:** {sc_customer.email}"
        except Exception as e:
            logger.error("Stripe lookup failed: %s", e)
            stripe_info = "\n**Stripe:** (lookup failed)"

    return (
        f"## Customer: {customer.name}\n"
        f"**Email:** {customer.email}\n"
        f"**Internal ID:** {customer.id}\n"
        f"**Orders:** {order_count} total | {sum(1 for o in orders if o.status == 'paid')} paid | "
        f"{sum(1 for o in orders if o.status == 'refunded')} refunded\n"
        f"**Lifetime value (paid):** ${total_cents / 100:.2f}"
        f"{stripe_info}"
    )


def list_payments(db: Session, email: str, limit: int = 5) -> str:
    """List recent Stripe payment intents for a customer, resolved by email via the DB."""
    customer = _get_customer_by_email(db, email)
    if not customer:
        return f"No customer found with email '{email}'."
    if not customer.stripe_customer_id:
        return f"Customer '{email}' has no linked Stripe account."

    try:
        intents = sc.list_charges_for_customer(customer.stripe_customer_id, limit=limit)
    except Exception as e:
        logger.error("Stripe list failed: %s", e)
        return f"Error fetching payments from Stripe: {e}"

    if not intents:
        return f"No payments found in Stripe for {email}."

    lines = [f"## Recent payments for {customer.name} ({email})\n"]
    for intent in intents:
        amount = intent.amount / 100
        created = datetime.fromtimestamp(intent.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        charge_id = intent.latest_charge if isinstance(intent.latest_charge, str) else (intent.latest_charge.id if intent.latest_charge else "N/A")
        lines.append(
            f"- **${amount:.2f} {intent.currency.upper()}** | {intent.status} | {created} | "
            f"Intent: `{intent.id}` | Charge: `{charge_id}`"
        )
    return "\n".join(lines)


def get_order_history(db: Session, email: str) -> str:
    """Return a customer's internal order history from the DB."""
    customer = _get_customer_by_email(db, email)
    if not customer:
        return f"No customer found with email '{email}'."

    orders = db.query(Order).filter_by(customer_id=customer.id).order_by(Order.created_at.desc()).all()
    if not orders:
        return f"No orders found in the database for {email}."

    lines = [f"## Order history for {customer.name} ({email})\n"]
    for o in orders:
        created = o.created_at.strftime("%Y-%m-%d %H:%M UTC") if o.created_at else "unknown"
        lines.append(
            f"- **${o.amount_cents / 100:.2f} {o.currency.upper()}** | {o.status} | {created} | "
            f"Order: `{o.id}` | Charge: `{o.stripe_charge_id or 'N/A'}`"
        )
    return "\n".join(lines)


def issue_refund(
    db: Session,
    email: str,
    charge_id: Optional[str] = None,
    amount_cents: Optional[int] = None,
    reason: str = "requested_by_customer",
    confirmed: bool = False,
) -> str:
    """
    Issue a refund for a customer.

    IMPORTANT: Always call this first with confirmed=False to show the user a preview,
    then ask the user to confirm before calling again with confirmed=True.
    Never set confirmed=True without explicit user approval.
    """
    customer = _get_customer_by_email(db, email)
    if not customer:
        return f"No customer found with email '{email}'."

    if charge_id:
        order = db.query(Order).filter_by(stripe_charge_id=charge_id, customer_id=customer.id).first()
        if not order:
            return f"No order found with charge ID `{charge_id}` for {email}."
    else:
        order = (
            db.query(Order)
            .filter_by(customer_id=customer.id, status="paid")
            .order_by(Order.created_at.desc())
            .first()
        )
        if not order:
            return f"No paid orders found for {email} to refund."

    age_days = (datetime.now(timezone.utc) - order.created_at.replace(tzinfo=timezone.utc)).days
    if age_days > REFUND_WINDOW_DAYS:
        return (
            f"Refund denied: charge `{order.stripe_charge_id}` is {age_days} days old. "
            f"Our policy only allows refunds within {REFUND_WINDOW_DAYS} days."
        )

    refund_amount = amount_cents or order.amount_cents
    refund_display = f"${refund_amount / 100:.2f} {order.currency.upper()}"

    if not confirmed:
        return (
            f"## Refund Preview — please confirm\n"
            f"**Customer:** {customer.name} ({email})\n"
            f"**Order:** `{order.id}`\n"
            f"**Charge:** `{order.stripe_charge_id}`\n"
            f"**Amount:** {refund_display}\n"
            f"**Reason:** {reason}\n"
            f"**Charge age:** {age_days} days\n\n"
            f"To proceed, reply 'yes' and I will call issue_refund with confirmed=True."
        )

    idempotency_key = f"refund-{order.id}-{reason[:20].replace(' ', '_')}"
    try:
        refund = sc.create_refund(
            payment_intent_id=order.stripe_charge_id,
            amount_cents=amount_cents,
            reason="requested_by_customer",
            idempotency_key=idempotency_key,
        )
    except Exception as e:
        logger.error("Stripe refund failed: %s", e)
        return f"Stripe refund failed: {e}"

    order.status = "refunded" if refund_amount >= order.amount_cents else "partially_refunded"
    log = RefundLog(
        order_id=order.id,
        stripe_refund_id=refund.id,
        amount_cents=refund_amount,
        reason=reason,
        refunded_by="ai-assistant",
    )
    db.add(log)
    db.commit()

    return (
        f"## Refund issued\n"
        f"**Customer:** {customer.name} ({email})\n"
        f"**Amount refunded:** {refund_display}\n"
        f"**Stripe Refund ID:** `{refund.id}`\n"
        f"**DB Log ID:** `{log.id}`\n"
        f"**Order status:** {order.status}\n"
        f"**Reason:** {reason}"
    )


def create_payment_link(amount_cents: int, description: str) -> str:
    """Generate a Stripe test-mode payment link for a given amount and description."""
    try:
        url = sc.create_payment_link(amount_cents, description)
        return f"Payment link created: {url}\nAmount: ${amount_cents / 100:.2f} | Description: {description}"
    except Exception as e:
        logger.error("Payment link creation failed: %s", e)
        return f"Failed to create payment link: {e}"


def revenue_summary(db: Session, start_date: str, end_date: str) -> str:
    """Summarize total revenue from paid orders between two dates (YYYY-MM-DD)."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    except ValueError:
        return "Invalid date format. Use YYYY-MM-DD."

    orders = (
        db.query(Order)
        .filter(Order.status == "paid", Order.created_at >= start, Order.created_at < end)
        .all()
    )

    if not orders:
        return f"No paid orders found between {start_date} and {end_date}."

    total = sum(o.amount_cents for o in orders)
    return (
        f"## Revenue summary: {start_date} to {end_date}\n"
        f"**Orders:** {len(orders)}\n"
        f"**Total revenue:** ${total / 100:.2f} USD"
    )


def flag_for_review(db: Session, charge_id: str, note: str) -> str:
    """Flag a charge for manual review by adding a note to the refund log."""
    order = db.query(Order).filter_by(stripe_charge_id=charge_id).first()
    if not order:
        return f"No order found with charge ID `{charge_id}`."

    log = RefundLog(
        order_id=order.id,
        stripe_refund_id=None,
        amount_cents=0,
        reason=f"[FLAGGED FOR REVIEW] {note}",
        refunded_by="ai-assistant",
    )
    db.add(log)
    db.commit()
    return f"Charge `{charge_id}` flagged for review. Note: {note}\nLog ID: `{log.id}`"
