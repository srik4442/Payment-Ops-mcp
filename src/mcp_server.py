"""
Payment Ops MCP Server
Orchestrates between Stripe (payments) and an internal orders DB.
All logging goes to stderr — never stdout (stdout carries the JSON-RPC stream).
"""
import sys
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

from mcp.server.fastmcp import FastMCP
from src.db.database import SessionLocal, create_tables
from src.services import payment_service as svc

create_tables()

mcp = FastMCP("payment-ops")


# ---------------------------------------------------------------------------
# Tools — read
# ---------------------------------------------------------------------------

@mcp.tool()
def lookup_customer(email: str) -> str:
    """
    Look up a customer by email address.
    Returns merged view: internal DB info (orders, lifetime value) + live Stripe status.
    Use this first when handling any customer support request.
    """
    db = SessionLocal()
    try:
        return svc.lookup_customer(db, email)
    finally:
        db.close()


@mcp.tool()
def list_payments(email: str, limit: int = 5) -> str:
    """
    List the most recent Stripe payment intents for a customer (by email).
    Returns amount, status, date, and charge/intent IDs.
    Use to review a customer's payment history before taking any action.
    """
    db = SessionLocal()
    try:
        return svc.list_payments(db, email, limit)
    finally:
        db.close()


@mcp.tool()
def get_order_history(email: str) -> str:
    """
    Return the customer's full order history from the internal orders database.
    Shows order IDs, amounts, statuses, and linked Stripe charge IDs.
    """
    db = SessionLocal()
    try:
        return svc.get_order_history(db, email)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tools — write
# ---------------------------------------------------------------------------

@mcp.tool()
def issue_refund(
    email: str,
    charge_id: Optional[str] = None,
    amount_cents: Optional[int] = None,
    reason: str = "requested_by_customer",
    confirmed: bool = False,
) -> str:
    """
    Issue a refund for a customer.

    SAFETY PROTOCOL — ALWAYS follow this two-step process:
    1. Call with confirmed=False first. This returns a preview (no money moves).
    2. Show the preview to the user and ask: "Shall I proceed with this refund?"
    3. Only call with confirmed=True after the user explicitly says yes.

    Business rule: refunds older than 90 days are automatically rejected by the server.
    The charge_id and amount_cents are optional — omitting charge_id refunds the most
    recent paid order; omitting amount_cents issues a full refund.
    """
    db = SessionLocal()
    try:
        return svc.issue_refund(db, email, charge_id, amount_cents, reason, confirmed)
    finally:
        db.close()


@mcp.tool()
def create_payment_link(amount_cents: int, description: str) -> str:
    """
    Generate a Stripe test-mode payment link for a given amount (in cents) and description.
    Example: amount_cents=4999 → $49.99.
    """
    return svc.create_payment_link(amount_cents, description)


@mcp.tool()
def revenue_summary(start_date: str, end_date: str) -> str:
    """
    Summarize total revenue from paid orders between two dates.
    Dates must be in YYYY-MM-DD format (e.g. '2025-01-01').
    """
    db = SessionLocal()
    try:
        return svc.revenue_summary(db, start_date, end_date)
    finally:
        db.close()


@mcp.tool()
def flag_for_review(charge_id: str, note: str) -> str:
    """
    Flag a specific charge for manual review by adding a note to the audit log.
    Use when a charge looks suspicious or needs human follow-up.
    """
    db = SessionLocal()
    try:
        return svc.flag_for_review(db, charge_id, note)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("customer://{email}")
def customer_resource(email: str) -> str:
    """Fetch full customer profile (DB + Stripe) by email URI."""
    db = SessionLocal()
    try:
        return svc.lookup_customer(db, email)
    finally:
        db.close()


@mcp.resource("payment://{charge_id}")
def payment_resource(charge_id: str) -> str:
    """Fetch order details by Stripe charge ID."""
    db = SessionLocal()
    try:
        from src.models.models import Order
        order = db.query(Order).filter_by(stripe_charge_id=charge_id).first()
        if not order:
            return f"No order found with charge ID `{charge_id}`."
        return (
            f"## Order `{order.id}`\n"
            f"**Charge:** `{charge_id}`\n"
            f"**Amount:** ${order.amount_cents / 100:.2f} {order.currency.upper()}\n"
            f"**Status:** {order.status}\n"
            f"**Created:** {order.created_at}"
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt()
def daily_revenue_report() -> str:
    """Generate a prompt for producing today's revenue report."""
    from datetime import date
    today = date.today().isoformat()
    return (
        f"Please generate a daily revenue report for {today}. "
        f"Use the revenue_summary tool with start_date='{today}' and end_date='{today}'. "
        f"Then list the top customers by value using get_order_history."
    )


@mcp.prompt()
def find_refund_candidates() -> str:
    """Generate a prompt for finding orders that may need refunds."""
    return (
        "Review recent orders and identify potential refund candidates. "
        "Look for: duplicate charges (same customer, same amount within 5 minutes), "
        "charges marked as disputed, or any anomalies. "
        "Use list_payments and get_order_history to investigate. "
        "Do NOT issue any refunds without explicit user confirmation."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
