import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    stripe_customer_id = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=_now)

    orders = relationship("Order", back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=_uuid)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    stripe_charge_id = Column(String, nullable=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, default="usd")
    status = Column(
        Enum("paid", "refunded", "partially_refunded", name="order_status"),
        default="paid",
    )
    created_at = Column(DateTime, default=_now)

    customer = relationship("Customer", back_populates="orders")
    refund_logs = relationship("RefundLog", back_populates="order")


class RefundLog(Base):
    __tablename__ = "refund_log"

    id = Column(String, primary_key=True, default=_uuid)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    stripe_refund_id = Column(String, nullable=True)
    amount_cents = Column(Integer, nullable=False)
    reason = Column(String, default="")
    refunded_by = Column(String, default="ai-assistant")
    created_at = Column(DateTime, default=_now)

    order = relationship("Order", back_populates="refund_logs")
