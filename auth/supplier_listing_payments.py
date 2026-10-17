"""Stripe Checkout for reviewed supplier listing-service orders.

This is independent of buyer membership billing. Both switches default off.
Payment records a service period; existing company, vehicle and publication
reviews remain authoritative.
"""

import calendar
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

from buyer_service import BuyerError
from membership_payments import GatewayError, PaymentGateway


PRICES_MINOR = (4000, 14000, 20000)
PLAN_VERSION = "supplier-launch-20261007-v1"


def quarter_end(timestamp):
    current = datetime.fromtimestamp(timestamp, timezone.utc)
    month_number = current.month + 3
    year = current.year + (month_number - 1) // 12
    month = (month_number - 1) % 12 + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return int(current.replace(year=year, month=month, day=day).timestamp())


class StripeListingGateway:
    """Use the same merchant account as membership, with a distinct order type."""

    def __init__(self, stripe=None):
        self.stripe = stripe or PaymentGateway()

    @staticmethod
    def _validate(session, order, *, paid=False, require_url=False):
        ref = session.get("id")
        url = session.get("url")
        metadata = session.get("metadata")
        config = os.environ.get("STRIPE_PAYMENT_METHOD_CONFIGURATION", "")
        methods = session.get("payment_method_types")
        details = session.get("payment_method_configuration_details")
        expected_prefix = "cs_live_" if os.environ.get("PAYMENTS_ENV") == "live" else "cs_test_"
        if (not isinstance(ref, str) or not ref.startswith(expected_prefix)
                or (require_url and (not isinstance(url, str) or urlparse(url).scheme != "https"
                                  or urlparse(url).hostname != "checkout.stripe.com"))
                or session.get("livemode") is not (os.environ.get("PAYMENTS_ENV") == "live")
                or session.get("mode") != "payment"
                or session.get("client_reference_id") != order["id"]
                or not isinstance(metadata, dict)
                or metadata.get("autolink_supplier_order") != order["id"]
                or metadata.get("plan_version") != PLAN_VERSION
                or metadata.get("purpose") != "supplier_listing"
                or session.get("amount_total") != order["amount_minor"]
                or session.get("currency") != "usd"
                or not isinstance(details, dict) or details.get("id") != config
                or not isinstance(methods, list) or "card" not in methods
                or not set(methods).issubset({"card", "cartes_bancaires", "link"})
                or (order.get("provider_ref") and ref != order["provider_ref"])
                or (paid and (session.get("payment_status") != "paid"
                              or not isinstance(session.get("payment_intent"), str)))):
            raise BuyerError(409, "Stripe session does not match the supplier order.")
        return ref, url

    def create_checkout(self, order, email):
        try:
            self.stripe.verify_account()
            listing = quote(order["listing_id"], safe="")
            fields = {
                "mode": "payment",
                "payment_method_configuration": os.environ["STRIPE_PAYMENT_METHOD_CONFIGURATION"],
                "client_reference_id": order["id"],
                "metadata[autolink_supplier_order]": order["id"],
                "metadata[plan_version]": PLAN_VERSION,
                "metadata[purpose]": "supplier_listing",
                "customer_email": email,
                "line_items[0][quantity]": "1",
                "line_items[0][price_data][currency]": "usd",
                "line_items[0][price_data][unit_amount]": str(order["amount_minor"]),
                "line_items[0][price_data][product_data][name]":
                    "AUTOLINK reviewed supplier listing service (one SKC / one quarter)",
                "success_url": f"https://autolinkglobal.com/supplier/vehicles/{listing}?checkout=return",
                "cancel_url": f"https://autolinkglobal.com/supplier/vehicles/{listing}?checkout=cancelled",
                "expires_at": str(order["expires_at"]),
            }
            session = self.stripe.stripe("checkout/sessions", fields, order["id"])
            if not isinstance(session, dict):
                raise BuyerError(503, "Stripe returned an invalid session.")
            return self._validate(session, order, require_url=True)
        except (GatewayError, KeyError) as exc:
            raise BuyerError(503, "Stripe checkout requires reconciliation.") from exc

    def retrieve_checkout(self, reference):
        if not isinstance(reference, str) or not re.fullmatch(r"cs_(?:test|live)_[A-Za-z0-9]+", reference):
            raise BuyerError(409, "Invalid Stripe session reference.")
        try:
            return self.stripe.retrieve_checkout(reference)
        except GatewayError as exc:
            raise BuyerError(503, "Stripe session requires reconciliation.") from exc

    validate_checkout = _validate


class SupplierListingPayments:
    def __init__(self, trade, gateway=None):
        self.trade = trade
        self.auth = trade.auth
        self.gateway = gateway or StripeListingGateway()
        with self.auth.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS supplier_listing_orders (
                    id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL REFERENCES users(id),
                    listing_id TEXT NOT NULL REFERENCES supplier_vehicles(id),
                    model_id TEXT NOT NULL, model_year INTEGER NOT NULL,
                    quarter_number INTEGER NOT NULL, amount_minor INTEGER NOT NULL,
                    currency TEXT NOT NULL CHECK(currency='USD'),
                    plan_version TEXT NOT NULL, provider TEXT NOT NULL CHECK(provider='stripe'),
                    status TEXT NOT NULL, provider_ref TEXT UNIQUE, checkout_url TEXT,
                    provider_payment_id TEXT UNIQUE, created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL, paid_at INTEGER, service_until INTEGER,
                    updated_at INTEGER NOT NULL, refund_status TEXT, dispute_status TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS supplier_listing_one_open
                    ON supplier_listing_orders(supplier_id,model_id,model_year)
                    WHERE status IN ('CREATING','PENDING','UNKNOWN');
                CREATE TABLE IF NOT EXISTS supplier_listing_payment_events (
                    event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
                    order_id TEXT, received_at INTEGER NOT NULL
                );
            """)
            schema = db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='supplier_listing_orders'"
            ).fetchone()[0].lower()
            if "provider='airwallex'" in schema:
                raise RuntimeError("Old Airwallex supplier orders need an explicit migration before Stripe use.")

    @staticmethod
    def enabled():
        env = os.environ.get("PAYMENTS_ENV")
        key = os.environ.get("STRIPE_SECRET_KEY", "")
        expected = ("sk_test_", "rk_test_") if env == "sandbox" else ("sk_live_", "rk_live_")
        return (env in ("sandbox", "live")
                and (env != "live" or os.environ.get("STRIPE_LIVE_RELEASE_READY", "false").lower() == "true")
                and os.environ.get("STRIPE_SUPPLIER_LISTING_ENABLED", "false").lower() == "true"
                and key.startswith(expected)
                and os.environ.get("STRIPE_ACCOUNT_ID", "").startswith("acct_")
                and os.environ.get("STRIPE_SUPPLIER_WEBHOOK_SECRET", "").startswith("whsec_")
                and re.fullmatch(r"pmc_[A-Za-z0-9]+",
                                 os.environ.get("STRIPE_PAYMENT_METHOD_CONFIGURATION", "")) is not None)

    def quote(self, supplier, listing_id):
        with self.auth.connect() as db:
            self.trade.active_company_owner(db, supplier)
            row = db.execute(
                "SELECT * FROM supplier_vehicles WHERE id=? AND supplier_id=? AND archived_at IS NULL",
                (listing_id, supplier["id"])
            ).fetchone()
            if not row:
                raise BuyerError(404, "Supplier listing not found.")
            if row["status"] != "APPROVED":
                raise BuyerError(409, "Listing review must be completed before payment.")
            paid = db.execute(
                "SELECT count(*),max(service_until) FROM supplier_listing_orders "
                "WHERE supplier_id=? AND model_id=? AND model_year=? AND status='PAID'",
                (supplier["id"], row["model_id"], row["model_year"])
            ).fetchone()
        return {"listingId": listing_id, "modelId": row["model_id"],
                "modelYear": row["model_year"], "quarterNumber": paid[0] + 1,
                "amountMinor": PRICES_MINOR[min(paid[0], 2)], "currency": "USD",
                "planVersion": PLAN_VERSION, "currentServiceUntil": paid[1],
                "available": self.enabled(), "renewal": "manual", "provider": "stripe"}

    def create_checkout(self, supplier, listing_id):
        if not self.enabled():
            raise BuyerError(503, "Supplier listing payment is not yet available.")
        if supplier.get("is_test_workspace"):
            raise BuyerError(403, "Test workspace cannot purchase listing service.")
        quoted = self.quote(supplier, listing_id)
        now, order_id = int(time.time()), "SLO-" + uuid.uuid4().hex.upper()
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.trade.active_company_owner(db, supplier)
            row = db.execute(
                "SELECT model_id,model_year,status FROM supplier_vehicles "
                "WHERE id=? AND supplier_id=? AND archived_at IS NULL",
                (listing_id, supplier["id"])
            ).fetchone()
            if (not row or row["status"] != "APPROVED"
                    or row["model_id"] != quoted["modelId"]
                    or row["model_year"] != quoted["modelYear"]):
                raise BuyerError(409, "Listing changed during checkout; review the quote again.")
            paid_count = db.execute(
                "SELECT count(*) FROM supplier_listing_orders WHERE supplier_id=? AND model_id=? "
                "AND model_year=? AND status='PAID'",
                (supplier["id"], row["model_id"], row["model_year"])
            ).fetchone()[0]
            if paid_count + 1 != quoted["quarterNumber"]:
                raise BuyerError(409, "Listing price changed; review the quote again.")
            if db.execute(
                "SELECT 1 FROM supplier_listing_orders WHERE supplier_id=? AND model_id=? AND model_year=? "
                "AND status IN ('CREATING','PENDING','UNKNOWN')",
                (supplier["id"], row["model_id"], row["model_year"])
            ).fetchone():
                raise BuyerError(409, "A listing checkout is already open; reconcile it before retrying.")
            db.execute(
                "INSERT INTO supplier_listing_orders(id,supplier_id,listing_id,model_id,model_year,"
                "quarter_number,amount_minor,currency,plan_version,provider,status,created_at,"
                "expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (order_id, supplier["id"], listing_id, row["model_id"], row["model_year"],
                 paid_count + 1, quoted["amountMinor"], "USD", PLAN_VERSION, "stripe",
                 "CREATING", now, now + 3600, now)
            )
            order = dict(db.execute(
                "SELECT * FROM supplier_listing_orders WHERE id=?", (order_id,)
            ).fetchone())
        try:
            reference, url = self.gateway.create_checkout(order, supplier["email"])
        except Exception as exc:
            with self.auth.connect() as db:
                db.execute("UPDATE supplier_listing_orders SET status='UNKNOWN',updated_at=? WHERE id=?",
                           (int(time.time()), order_id))
            raise BuyerError(503, "Checkout outcome is uncertain. Contact support before retrying.") from exc
        with self.auth.connect() as db:
            db.execute(
                "UPDATE supplier_listing_orders SET status='PENDING',provider_ref=?,checkout_url=?,"
                "updated_at=? WHERE id=? AND status='CREATING'",
                (reference, url, int(time.time()), order_id)
            )
        return {"orderId": order_id, "amountMinor": order["amount_minor"],
                "currency": "USD", "checkoutUrl": url, "renewal": "manual",
                "provider": "stripe"}

    @staticmethod
    def _verify_signature(raw, header):
        secret = os.environ.get("STRIPE_SUPPLIER_WEBHOOK_SECRET", "")
        parts = [part.strip() for part in header.split(",")]
        values = dict(part.split("=", 1) for part in parts if "=" in part)
        timestamp = values.get("t", "")
        if not secret or not timestamp.isdigit() or abs(int(time.time()) - int(timestamp)) > 300:
            raise BuyerError(400, "Invalid Stripe webhook signature.")
        expected = hmac.new(secret.encode(), timestamp.encode() + b"." + raw,
                            hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, part[3:]) for part in parts if part.startswith("v1=")):
            raise BuyerError(400, "Invalid Stripe webhook signature.")

    def _settle_session(self, order, session, event_id, event_type):
        paid = event_type in ("checkout.session.completed", "checkout.session.reconciled")
        if paid:
            if (session.get("status") != "complete" or session.get("payment_status") != "paid"
                    or not isinstance(session.get("payment_intent"), str)
                    or not session["payment_intent"].startswith("pi_")):
                raise BuyerError(409, "Stripe payment is not confirmed.")
        elif session.get("status") != "expired" or session.get("payment_status") != "unpaid":
            raise BuyerError(409, "Stripe checkout is not confirmed expired.")
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM supplier_listing_payment_events WHERE event_id=?", (event_id,)
            ).fetchone():
                return {"duplicate": True}
            current = db.execute(
                "SELECT status,provider_payment_id FROM supplier_listing_orders WHERE id=?",
                (order["id"],)
            ).fetchone()
            if not current or current["status"] not in ("PENDING", "PAID", "EXPIRED"):
                raise BuyerError(409, "Supplier order is not payable.")
            if not paid:
                if current["status"] == "PAID":
                    result = {"alreadyPaid": True}
                else:
                    db.execute(
                        "UPDATE supplier_listing_orders SET status='EXPIRED',updated_at=? "
                        "WHERE id=? AND status='PENDING'", (now, order["id"])
                    )
                    result = {"expired": True}
            elif current["status"] == "PAID":
                if current["provider_payment_id"] != session["payment_intent"]:
                    raise BuyerError(409, "Stripe payment identity changed.")
                result = {"duplicate": True}
            else:
                prior = db.execute(
                    "SELECT max(service_until) FROM supplier_listing_orders WHERE supplier_id=? "
                    "AND model_id=? AND model_year=? AND status='PAID'",
                    (order["supplier_id"], order["model_id"], order["model_year"])
                ).fetchone()[0]
                until = quarter_end(max(now, prior or now))
                db.execute(
                    "UPDATE supplier_listing_orders SET status='PAID',provider_payment_id=?,paid_at=?,"
                    "service_until=?,updated_at=? WHERE id=? AND status IN ('PENDING','EXPIRED')",
                    (session["payment_intent"], now, until, now, order["id"])
                )
                result = {"paid": True, "serviceUntil": until,
                          "publication": "awaiting_verified_activation"}
            db.execute("INSERT INTO supplier_listing_payment_events VALUES(?,?,?,?)",
                       (event_id, event_type, order["id"], now))
        return result

    def reconcile_order(self, order_id, recover_unknown=False):
        """Operator-only status repair through the same idempotent Stripe Checkout key."""
        with self.auth.connect() as db:
            row = db.execute(
                "SELECT o.*,u.email FROM supplier_listing_orders o JOIN users u ON u.id=o.supplier_id "
                "WHERE o.id=? AND o.provider='stripe'", (order_id,)
            ).fetchone()
        if not row:
            raise BuyerError(404, "Stripe supplier order was not found.")
        order = dict(row)
        if order["status"] == "PAID":
            return {"status": "PAID", "alreadyProcessed": True,
                    "manualReview": bool(order["refund_status"] or order["dispute_status"])}
        if order["status"] not in ("CREATING", "UNKNOWN", "PENDING", "EXPIRED"):
            return {"status": order["status"], "manualReview": True}
        if not order["provider_ref"]:
            if (not recover_unknown or order["status"] not in ("CREATING", "UNKNOWN")
                    or int(time.time()) >= order["expires_at"]):
                return {"status": "UNKNOWN", "manualReview": True}
            with self.auth.connect() as db:
                self.trade.active_company_owner(db, {"id": order["supplier_id"]})
                listing = db.execute(
                    "SELECT status,model_id,model_year FROM supplier_vehicles "
                    "WHERE id=? AND supplier_id=? AND archived_at IS NULL",
                    (order["listing_id"], order["supplier_id"])
                ).fetchone()
                if (not listing or listing["status"] != "APPROVED"
                        or listing["model_id"] != order["model_id"]
                        or listing["model_year"] != order["model_year"]):
                    return {"status": "UNKNOWN", "manualReview": True}
            try:
                reference, url = self.gateway.create_checkout(order, order["email"])
            except (GatewayError, BuyerError):
                return {"status": "UNKNOWN", "manualReview": True}
            with self.auth.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT status,provider_ref FROM supplier_listing_orders WHERE id=?", (order_id,)
                ).fetchone()
                if current["status"] == "PAID":
                    return {"status": "PAID", "alreadyProcessed": True}
                if current["provider_ref"] and current["provider_ref"] != reference:
                    raise BuyerError(409, "Stripe checkout identity changed during reconciliation.")
                db.execute(
                    "UPDATE supplier_listing_orders SET status='PENDING',provider_ref=?,checkout_url=?,"
                    "updated_at=? WHERE id=? AND status IN ('CREATING','UNKNOWN','PENDING')",
                    (reference, url, int(time.time()), order_id)
                )
            order["provider_ref"] = reference
        try:
            session = self.gateway.retrieve_checkout(order["provider_ref"])
        except (GatewayError, BuyerError):
            return {"status": "UNKNOWN", "manualReview": True}
        paid = session.get("status") == "complete" and session.get("payment_status") == "paid"
        self.gateway.validate_checkout(session, order, paid=paid)
        if paid:
            result = self._settle_session(order, session, "reconcile:" + order["provider_ref"],
                                          "checkout.session.reconciled")
            return {"status": "PAID", **result}
        if session.get("status") == "expired" and session.get("payment_status") == "unpaid":
            result = self._settle_session(order, session, "reconcile-expired:" + order["provider_ref"],
                                          "checkout.session.expired")
            return {"status": "PAID" if result.get("alreadyPaid") else "EXPIRED", **result}
        return {"status": "PENDING", "manualReview": session.get("status") != "open"}

    def webhook(self, raw, headers):
        if not self.enabled():
            raise BuyerError(503, "Supplier listing payment is not available.")
        self._verify_signature(raw, headers.get("Stripe-Signature", ""))
        try:
            event = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise BuyerError(400, "Invalid Stripe event.") from exc
        if not isinstance(event, dict) or not isinstance(event.get("id"), str):
            raise BuyerError(400, "Invalid Stripe event.")
        if event.get("livemode") is not (os.environ.get("PAYMENTS_ENV") == "live"):
            raise BuyerError(409, "Stripe environment mismatch.")
        if event.get("account") and event["account"] != os.environ["STRIPE_ACCOUNT_ID"]:
            raise BuyerError(409, "Stripe account mismatch.")
        name = event.get("type")
        data = event.get("data")
        obj = data.get("object") if isinstance(data, dict) else None
        if not isinstance(obj, dict):
            raise BuyerError(400, "Invalid Stripe event object.")
        if name not in ("checkout.session.completed", "checkout.session.expired",
                        "charge.refunded", "charge.dispute.created", "charge.dispute.closed"):
            return {"ignored": True}
        with self.auth.connect() as db:
            if db.execute(
                "SELECT 1 FROM supplier_listing_payment_events WHERE event_id=?",
                (event["id"],)
            ).fetchone():
                return {"duplicate": True}
            if name.startswith("charge."):
                payment_id = obj.get("payment_intent")
                row = db.execute(
                    "SELECT * FROM supplier_listing_orders WHERE provider_payment_id=?",
                    (payment_id,)
                ).fetchone()
                if not row:
                    return {"ignored": True}
                if name == "charge.refunded":
                    if obj.get("currency") != "usd" or not isinstance(obj.get("amount_refunded"), int):
                        raise BuyerError(409, "Stripe refund identity mismatch.")
                    if obj["amount_refunded"] > row["amount_minor"]:
                        raise BuyerError(409, "Stripe refund exceeds the supplier order.")
                    status = "FULL" if obj["amount_refunded"] == row["amount_minor"] else "PARTIAL"
                    db.execute("UPDATE supplier_listing_orders SET refund_status=?,updated_at=? WHERE id=?",
                               (status, int(time.time()), row["id"]))
                else:
                    status = "OPEN" if name.endswith("created") else str(obj.get("status", "CLOSED")).upper()
                    db.execute("UPDATE supplier_listing_orders SET dispute_status=?,updated_at=? WHERE id=?",
                               (status, int(time.time()), row["id"]))
                db.execute("INSERT INTO supplier_listing_payment_events VALUES(?,?,?,?)",
                           (event["id"], name, row["id"], int(time.time())))
                return {"recorded": True}
            order_id = obj.get("client_reference_id")
            metadata = obj.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("autolink_supplier_order") != order_id:
                raise BuyerError(409, "Supplier order metadata mismatch.")
            row = db.execute(
                "SELECT * FROM supplier_listing_orders WHERE id=? AND provider_ref=?",
                (order_id, obj.get("id"))
            ).fetchone()
        if not row:
            raise BuyerError(409, "Supplier Stripe session is not yet recognized.")
        order = dict(row)
        if name == "checkout.session.completed":
            if obj.get("mode") != "payment" or obj.get("payment_status") != "paid":
                return {"pending": True}
        confirmed = self.gateway.retrieve_checkout(order["provider_ref"])
        self.gateway.validate_checkout(confirmed, order, paid=name == "checkout.session.completed")
        if name == "checkout.session.completed":
            if (obj.get("id") != confirmed.get("id")
                    or obj.get("payment_intent") != confirmed.get("payment_intent")
                    or obj.get("amount_total") != order["amount_minor"]
                    or obj.get("currency") != "usd"):
                raise BuyerError(409, "Stripe event and session disagree.")
        return self._settle_session(order, confirmed, event["id"], name)
