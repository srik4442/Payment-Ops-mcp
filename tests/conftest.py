import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

os.environ.setdefault("STRIPE_API_KEY", "rk_test_placeholder")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.models import Base, Customer, Order


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def mock_stripe(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.services.payment_service.sc", mock)
    return mock


@pytest.fixture()
def sample_customer(db):
    customer = Customer(
        email="sarah@example.com",
        name="Sarah Test",
        stripe_customer_id="cus_test123",
    )
    db.add(customer)
    db.flush()
    return customer


@pytest.fixture()
def sample_order(db, sample_customer):
    order = Order(
        customer_id=sample_customer.id,
        stripe_charge_id="pi_test_abc",
        amount_cents=4999,
        currency="usd",
        status="paid",
        created_at=datetime.now(timezone.utc),
    )
    db.add(order)
    db.flush()
    return order


@pytest.fixture()
def old_order(db, sample_customer):
    order = Order(
        customer_id=sample_customer.id,
        stripe_charge_id="pi_test_old",
        amount_cents=4999,
        currency="usd",
        status="paid",
        created_at=datetime.now(timezone.utc) - timedelta(days=100),
    )
    db.add(order)
    db.flush()
    return order
