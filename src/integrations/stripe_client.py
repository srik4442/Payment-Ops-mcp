import sys
import logging
import stripe
from src.core.config import settings

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_api_key


def create_customer(email: str, name: str) -> stripe.Customer:
    customer = stripe.Customer.create(email=email, name=name)
    logger.info("Created Stripe customer %s for %s", customer.id, email)
    return customer


def create_test_charge(
    stripe_customer_id: str, amount_cents: int, currency: str = "usd"
) -> stripe.PaymentIntent:
    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency=currency,
        customer=stripe_customer_id,
        payment_method="pm_card_visa",
        confirm=True,
        automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
    )
    logger.info("Created test charge %s for customer %s", intent.id, stripe_customer_id)
    return intent


def list_charges_for_customer(stripe_customer_id: str, limit: int = 10) -> list:
    intents = stripe.PaymentIntent.list(customer=stripe_customer_id, limit=limit)
    return intents.data


def get_customer(stripe_customer_id: str) -> stripe.Customer:
    return stripe.Customer.retrieve(stripe_customer_id)


def create_refund(
    charge_or_intent_id: str,
    amount_cents: int | None = None,
    reason: str = "requested_by_customer",
    idempotency_key: str | None = None,
) -> stripe.Refund:
    # Always use payment_intent parameter — we store pi_xxx IDs in the DB
    params: dict = {"payment_intent": charge_or_intent_id, "reason": reason}
    if amount_cents is not None:
        params["amount"] = amount_cents
    kwargs = {}
    if idempotency_key:
        kwargs["idempotency_key"] = idempotency_key
    refund = stripe.Refund.create(**params, **kwargs)
    logger.info("Created refund %s for %s", refund.id, charge_or_intent_id)
    return refund


def create_payment_link(amount_cents: int, description: str) -> str:
    price = stripe.Price.create(
        unit_amount=amount_cents,
        currency="usd",
        product_data={"name": description},
    )
    link = stripe.PaymentLink.create(line_items=[{"price": price.id, "quantity": 1}])
    logger.info("Created payment link %s", link.url)
    return link.url
