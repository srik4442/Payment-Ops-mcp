"""
Seed script: creates 5 test customers in both the local DB and Stripe (test mode),
each with 2-3 succeeded test charges. Run once before demoing.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from src.db.database import SessionLocal, create_tables
from src.models.models import Customer, Order
from src.integrations import stripe_client

TEST_CUSTOMERS = [
    {"email": "sarah@example.com", "name": "Sarah Test", "charges": [4999, 4999, 2999]},
    {"email": "james@example.com", "name": "James Demo", "charges": [9999, 4999]},
    {"email": "alice@example.com", "name": "Alice Sample", "charges": [1999, 4999, 7999]},
    {"email": "bob@example.com", "name": "Bob Tester", "charges": [4999, 9999]},
    {"email": "carol@example.com", "name": "Carol Mock", "charges": [2999, 4999, 4999]},
]


def seed():
    create_tables()
    db = SessionLocal()
    try:
        for data in TEST_CUSTOMERS:
            existing = db.query(Customer).filter_by(email=data["email"]).first()
            if existing:
                print(f"Skipping {data['email']} — already exists in DB.")
                continue

            stripe_cust = stripe_client.create_customer(data["email"], data["name"])

            customer = Customer(
                email=data["email"],
                name=data["name"],
                stripe_customer_id=stripe_cust.id,
            )
            db.add(customer)
            db.flush()

            for amount in data["charges"]:
                intent = stripe_client.create_test_charge(stripe_cust.id, amount)
                order = Order(
                    customer_id=customer.id,
                    stripe_charge_id=intent.id,  # always store pi_xxx — used as payment_intent in refunds
                    amount_cents=amount,
                    currency="usd",
                    status="paid",
                )
                db.add(order)

            print(f"Created {data['name']} ({data['email']}) — Stripe ID: {stripe_cust.id}")

        db.commit()
        print("\nSeed complete. All customers and charges created.")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    seed()
