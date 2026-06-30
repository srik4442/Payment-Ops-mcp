import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

from src.models.models import RefundLog, Order
from src.services import payment_service as svc


class TestLookupCustomer:
    def test_lookup_customer_merges_db_and_stripe(self, db, sample_customer, mock_stripe):
        stripe_cust = MagicMock()
        stripe_cust.id = "cus_test123"
        stripe_cust.email = "sarah@example.com"
        mock_stripe.get_customer.return_value = stripe_cust

        result = svc.lookup_customer(db, "sarah@example.com")

        assert "Sarah Test" in result
        assert "sarah@example.com" in result
        assert "cus_test123" in result
        mock_stripe.get_customer.assert_called_once_with("cus_test123")

    def test_lookup_customer_not_found(self, db):
        result = svc.lookup_customer(db, "nobody@example.com")
        assert "No customer found" in result


class TestListPayments:
    def test_list_payments_resolves_email_to_stripe_id(self, db, sample_customer, mock_stripe):
        intent = MagicMock()
        intent.id = "pi_test_abc"
        intent.amount = 4999
        intent.currency = "usd"
        intent.status = "succeeded"
        intent.created = 1700000000
        intent.latest_charge = "ch_test_abc"
        mock_stripe.list_charges_for_customer.return_value = [intent]

        result = svc.list_payments(db, "sarah@example.com")

        assert "Sarah Test" in result
        assert "$49.99" in result
        mock_stripe.list_charges_for_customer.assert_called_once_with("cus_test123", limit=5)

    def test_list_payments_customer_not_found(self, db):
        result = svc.list_payments(db, "nobody@example.com")
        assert "No customer found" in result


class TestIssueRefund:
    def test_issue_refund_preview_when_not_confirmed(self, db, sample_customer, sample_order, mock_stripe):
        result = svc.issue_refund(db, "sarah@example.com", confirmed=False)

        assert "Refund Preview" in result
        assert "$49.99" in result
        assert "pi_test_abc" in result
        mock_stripe.create_refund.assert_not_called()

        log_count = db.query(RefundLog).count()
        assert log_count == 0

    def test_issue_refund_writes_refund_log_when_confirmed(self, db, sample_customer, sample_order, mock_stripe):
        refund = MagicMock()
        refund.id = "re_test_xyz"
        mock_stripe.create_refund.return_value = refund

        result = svc.issue_refund(db, "sarah@example.com", confirmed=True)

        assert "Refund issued" in result
        assert "re_test_xyz" in result

        log = db.query(RefundLog).first()
        assert log is not None
        assert log.stripe_refund_id == "re_test_xyz"
        assert log.refunded_by == "ai-assistant"
        assert log.amount_cents == 4999

        order = db.query(Order).filter_by(id=sample_order.id).first()
        assert order.status == "refunded"

    def test_issue_refund_rejected_for_charge_older_than_90_days(
        self, db, sample_customer, old_order, mock_stripe
    ):
        result = svc.issue_refund(db, "sarah@example.com", confirmed=True)

        assert "Refund denied" in result
        assert "90" in result
        mock_stripe.create_refund.assert_not_called()

        log_count = db.query(RefundLog).count()
        assert log_count == 0


class TestRevenueSummary:
    def test_revenue_summary_sums_paid_orders(self, db, sample_customer):
        for amount in [4999, 9999, 2999]:
            db.add(Order(
                customer_id=sample_customer.id,
                stripe_charge_id=f"pi_{amount}",
                amount_cents=amount,
                currency="usd",
                status="paid",
                created_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            ))
        db.flush()

        result = svc.revenue_summary(db, "2025-06-01", "2025-06-30")

        assert "Revenue summary" in result
        assert "$179.97" in result
        assert "3" in result

    def test_revenue_summary_no_orders(self, db):
        result = svc.revenue_summary(db, "2020-01-01", "2020-01-31")
        assert "No paid orders" in result

    def test_revenue_summary_invalid_date(self, db):
        result = svc.revenue_summary(db, "not-a-date", "2025-01-31")
        assert "Invalid date" in result


class TestGetOrderHistory:
    def test_get_order_history_returns_orders(self, db, sample_customer, sample_order):
        result = svc.get_order_history(db, "sarah@example.com")
        assert "Sarah Test" in result
        assert "$49.99" in result
        assert "pi_test_abc" in result

    def test_get_order_history_no_orders(self, db, sample_customer):
        result = svc.get_order_history(db, "sarah@example.com")
        assert "No orders found" in result

    def test_get_order_history_customer_not_found(self, db):
        result = svc.get_order_history(db, "nobody@example.com")
        assert "No customer found" in result


class TestCreatePaymentLink:
    def test_create_payment_link_success(self, mock_stripe):
        mock_stripe.create_payment_link.return_value = "https://buy.stripe.com/test_abc"
        result = svc.create_payment_link(4999, "Test Product")
        assert "https://buy.stripe.com/test_abc" in result
        assert "$49.99" in result

    def test_create_payment_link_stripe_error(self, mock_stripe):
        mock_stripe.create_payment_link.side_effect = Exception("Stripe error")
        result = svc.create_payment_link(4999, "Test Product")
        assert "Failed to create payment link" in result


class TestFlagForReview:
    def test_flag_for_review_success(self, db, sample_customer, sample_order):
        result = svc.flag_for_review(db, "pi_test_abc", "Suspicious duplicate")
        assert "flagged for review" in result
        assert "Suspicious duplicate" in result

        from src.models.models import RefundLog
        log = db.query(RefundLog).first()
        assert "FLAGGED FOR REVIEW" in log.reason

    def test_flag_for_review_charge_not_found(self, db):
        result = svc.flag_for_review(db, "pi_nonexistent", "test note")
        assert "No order found" in result


class TestIssueRefundEdgeCases:
    def test_refund_by_specific_charge_id(self, db, sample_customer, sample_order, mock_stripe):
        refund = MagicMock()
        refund.id = "re_specific"
        mock_stripe.create_refund.return_value = refund

        result = svc.issue_refund(db, "sarah@example.com", charge_id="pi_test_abc", confirmed=True)
        assert "re_specific" in result

    def test_refund_charge_not_found_by_id(self, db, sample_customer, mock_stripe):
        result = svc.issue_refund(db, "sarah@example.com", charge_id="pi_wrong", confirmed=True)
        assert "No order found" in result

    def test_refund_no_paid_orders(self, db, sample_customer, mock_stripe):
        result = svc.issue_refund(db, "sarah@example.com", confirmed=True)
        assert "No paid orders found" in result

    def test_refund_stripe_failure(self, db, sample_customer, sample_order, mock_stripe):
        mock_stripe.create_refund.side_effect = Exception("card_error")
        result = svc.issue_refund(db, "sarah@example.com", confirmed=True)
        assert "Stripe refund failed" in result

    def test_lookup_customer_stripe_failure(self, db, sample_customer, mock_stripe):
        mock_stripe.get_customer.side_effect = Exception("network error")
        result = svc.lookup_customer(db, "sarah@example.com")
        assert "Sarah Test" in result
        assert "lookup failed" in result

    def test_list_payments_stripe_error(self, db, sample_customer, mock_stripe):
        mock_stripe.list_charges_for_customer.side_effect = Exception("timeout")
        result = svc.list_payments(db, "sarah@example.com")
        assert "Error fetching payments" in result

    def test_list_payments_empty(self, db, sample_customer, mock_stripe):
        mock_stripe.list_charges_for_customer.return_value = []
        result = svc.list_payments(db, "sarah@example.com")
        assert "No payments found" in result
