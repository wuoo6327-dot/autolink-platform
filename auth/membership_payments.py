"""Membership billing. All provider switches default to closed.

Only a verified provider webhook can turn a pending order into membership access.
The existing buyer_memberships table remains the entitlement source of truth.
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
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from buyer_service import BuyerError, BuyerService


PLANS = {
    "monthly": (1, 199, 1990),
    "quarterly": (3, 999, 2999),
    "annual": (12, 3999, 9999),
}
METHODS = {
    "stripe_card": ("stripe", "STRIPE_CARD_ENABLED"),
    # Reserved API values. Airwallex cannot be enabled in this Stripe-first release.
    "airwallex_alipay": ("airwallex", None),
    "airwallex_wechat": ("airwallex", None),
}


def add_months(timestamp, months):
    value = datetime.fromtimestamp(timestamp, timezone.utc)
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    source_last = calendar.monthrange(value.year, value.month)[1]
    target_last = calendar.monthrange(year, month)[1]
    day = target_last if value.day == source_last else min(value.day, target_last)
    return int(value.replace(year=year, month=month, day=day).timestamp())


class GatewayError(Exception):
    pass


class PaymentGateway:
    """Server-only Stripe hosted checkout; Airwallex is a reserved later adapter."""

    def stripe(self, path, fields, order_id):
        secret = os.environ["STRIPE_SECRET_KEY"]
        data = urlencode(fields).encode()
        headers = {"Authorization": "Bearer " + secret,
                   "Content-Type": "application/x-www-form-urlencoded",
                   "Idempotency-Key": "autolink-" + order_id}
        try:
            with urlopen(Request("https://api.stripe.com/v1/" + path, data=data, headers=headers), timeout=12) as response:
                return json.load(response)
        except Exception as exc:
            raise GatewayError("Stripe checkout requires reconciliation.") from exc

    def stripe_get(self, path):
        secret = os.environ["STRIPE_SECRET_KEY"]
        try:
            with urlopen(Request("https://api.stripe.com/v1/" + path,
                                 headers={"Authorization": "Bearer " + secret}), timeout=12) as response:
                return json.load(response)
        except Exception as exc:
            raise GatewayError("Stripe status is unavailable; retain the order for review.") from exc

    def verify_account(self):
        configured = os.environ.get("STRIPE_ACCOUNT_ID", "")
        account = self.stripe_get("account")
        if not configured or not isinstance(account, dict) or account.get("id") != configured:
            raise GatewayError("Stripe account does not match the configured merchant.")

    def checkout(self, order, email):
        if order["provider"] != "stripe":
            raise GatewayError("This payment adapter is not available.")
        self.verify_account()
        amount = order["amount_minor"]
        order_id = order["id"]
        label = {"monthly": "Monthly", "quarterly": "Quarterly", "annual": "Annual"}[order["plan"]]
        fields = {
            "mode": "payment", "payment_method_types[0]": "card",
            "client_reference_id": order_id, "metadata[autolink_order_id]": order_id,
            "customer_email": email, "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][unit_amount]": str(amount),
            "line_items[0][price_data][product_data][name]": "AUTOLINK " + label + " membership",
            "success_url": "https://autolinkglobal.com/membership?checkout=return",
            "cancel_url": "https://autolinkglobal.com/membership?checkout=cancelled",
            "expires_at": str(order["expires_at"]),
        }
        result = self.stripe("checkout/sessions", fields, order_id)
        if not isinstance(result, dict):
            raise GatewayError("Stripe returned an invalid checkout response.")
        ref, url = result.get("id"), result.get("url")
        if result.get("livemode") is not (os.environ.get("PAYMENTS_ENV") == "live"):
            raise GatewayError("Stripe checkout environment does not match.")
        metadata = result.get("metadata")
        if (result.get("mode") != "payment" or result.get("client_reference_id") != order_id
                or not isinstance(metadata, dict) or metadata.get("autolink_order_id") != order_id
                or result.get("amount_total") != amount or result.get("currency") != "usd"):
            raise GatewayError("Stripe checkout does not match the membership order.")
        expected_prefix = "cs_live_" if os.environ.get("PAYMENTS_ENV") == "live" else "cs_test_"
        if (not isinstance(ref, str) or not ref.startswith(expected_prefix)
                or not isinstance(url, str) or urlparse(url).scheme != "https"
                or urlparse(url).hostname != "checkout.stripe.com"):
            raise GatewayError("Provider returned an invalid checkout URL.")
        return ref, url

    def retrieve_checkout(self, reference):
        if not isinstance(reference, str) or not re.fullmatch(r"cs_(?:test|live)_[A-Za-z0-9]+", reference):
            raise GatewayError("Invalid Stripe checkout reference.")
        self.verify_account()
        return self.stripe_get("checkout/sessions/" + quote(reference, safe=""))


class MembershipPaymentService:
    def __init__(self, auth, gateway=None):
        self.auth = auth
        self.gateway = gateway or PaymentGateway()
        with auth.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS membership_orders (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    plan TEXT NOT NULL, purchase_type TEXT NOT NULL,
                    amount_minor INTEGER NOT NULL, currency TEXT NOT NULL,
                    method TEXT NOT NULL, provider TEXT NOT NULL,
                    status TEXT NOT NULL, provider_ref TEXT UNIQUE,
                    checkout_url TEXT, checkout_email TEXT, provider_payment_id TEXT UNIQUE,
                    membership_id TEXT REFERENCES buyer_memberships(id),
                    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                    paid_at INTEGER, updated_at INTEGER NOT NULL,
                    auto_renew_authorized INTEGER NOT NULL DEFAULT 0,
                    agreement_version TEXT, agreement_at INTEGER,
                    next_charge_minor INTEGER, next_charge_at INTEGER,
                    refund_status TEXT, dispute_status TEXT
                );
                CREATE INDEX IF NOT EXISTS membership_orders_owner ON membership_orders(user_id,created_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS membership_orders_one_open
                    ON membership_orders(user_id) WHERE status IN ('CREATING','PENDING','UNKNOWN');
                CREATE TABLE IF NOT EXISTS membership_intro_uses (
                    user_id TEXT PRIMARY KEY REFERENCES users(id), order_id TEXT NOT NULL UNIQUE REFERENCES membership_orders(id),
                    used_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS membership_payment_events (
                    provider TEXT NOT NULL, event_id TEXT NOT NULL,
                    order_id TEXT, event_type TEXT NOT NULL, received_at INTEGER NOT NULL,
                    PRIMARY KEY(provider,event_id)
                );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(membership_orders)")}
            if "checkout_email" not in columns:
                db.execute("ALTER TABLE membership_orders ADD COLUMN checkout_email TEXT")

    @staticmethod
    def enabled(method):
        provider, flag = METHODS[method]
        if provider != "stripe":
            return False
        if os.environ.get("PAYMENTS_ENV") not in ("sandbox", "live"):
            return False
        if os.environ.get(flag, "false").lower() != "true":
            return False
        expected = ("sk_test_", "rk_test_") if os.environ["PAYMENTS_ENV"] == "sandbox" else ("sk_live_", "rk_live_")
        return bool(os.environ.get("STRIPE_SECRET_KEY", "").startswith(expected)
                    and os.environ.get("STRIPE_WEBHOOK_SECRET", "").startswith("whsec_")
                    and os.environ.get("STRIPE_ACCOUNT_ID", "").startswith("acct_"))

    @staticmethod
    def first_purchase(db, user_id):
        return not (db.execute("SELECT 1 FROM membership_intro_uses WHERE user_id=?", (user_id,)).fetchone()
                    or db.execute("SELECT 1 FROM buyer_memberships WHERE user_id=?", (user_id,)).fetchone()
                    or db.execute("SELECT 1 FROM buyer_membership_payments WHERE user_id=? AND status='PAID'", (user_id,)).fetchone())

    def pricing(self, user):
        with self.auth.connect() as db:
            first = self.first_purchase(db, user["id"])
        return {"currency": "USD", "firstPurchaseEligible": first,
                "plans": {name: {"months": months, "firstMinor": intro,
                                  "renewalMinor": normal, "dueMinor": intro if first else normal}
                          for name, (months, intro, normal) in PLANS.items()},
                "methods": {name: {"available": self.enabled(name), "autoRenewAvailable": False}
                            for name in METHODS},
                "defaultRenewal": "manual"}

    def orders(self, user):
        with self.auth.connect() as db:
            rows = db.execute("SELECT id,plan,purchase_type,amount_minor,currency,method,status,created_at,paid_at,"
                              "auto_renew_authorized,next_charge_minor,next_charge_at,refund_status,dispute_status "
                              "FROM membership_orders WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user["id"],)).fetchall()
        return [dict(row) for row in rows]

    def create_checkout(self, user, body):
        plan, method = body.get("plan"), body.get("method")
        if plan not in PLANS or method not in METHODS:
            raise BuyerError(400, "Choose a valid membership plan and payment method.")
        if body.get("autoRenew") is not False:
            raise BuyerError(409, "Automatic renewal is unavailable for this payment method. Choose manual renewal.")
        if not self.enabled(method):
            raise BuyerError(503, "This payment method is unavailable.")
        if user.get("is_test_workspace"):
            raise BuyerError(403, "Test workspace cannot purchase membership.")
        now, order_id = int(time.time()), str(uuid.uuid4())
        provider = METHODS[method][0]
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT id FROM membership_orders WHERE user_id=? AND status IN ('CREATING','PENDING','UNKNOWN')", (user["id"],)).fetchone():
                raise BuyerError(409, "An earlier checkout is still open. Contact support if it cannot be completed.")
            if db.execute("SELECT 1 FROM buyer_memberships WHERE user_id=? AND auto_renew=1 AND status='ACTIVE'", (user["id"],)).fetchone():
                raise BuyerError(409, "An automatic membership already exists; avoid a second subscription.")
            first = self.first_purchase(db, user["id"])
            amount = PLANS[plan][1 if first else 2]
            db.execute("INSERT INTO membership_orders(id,user_id,plan,purchase_type,amount_minor,currency,method,provider,"
                       "status,checkout_email,created_at,expires_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (order_id, user["id"], plan, "FIRST" if first else "RENEWAL", amount, "USD", method,
                        provider, "CREATING", user["email"], now, now + 3600, now))
        with self.auth.connect() as db:
            row = dict(db.execute("SELECT * FROM membership_orders WHERE id=?", (order_id,)).fetchone())
        try:
            ref, url = self.gateway.checkout(row, row["checkout_email"])
        except Exception:
            with self.auth.connect() as db:
                db.execute("UPDATE membership_orders SET status='UNKNOWN',updated_at=? WHERE id=?", (int(time.time()), order_id))
            raise BuyerError(503, "Checkout status is uncertain. Contact support before trying again.")
        with self.auth.connect() as db:
            db.execute("UPDATE membership_orders SET status='PENDING',provider_ref=?,checkout_url=?,updated_at=? WHERE id=?",
                       (ref, url, int(time.time()), order_id))
        return {"orderId": order_id, "amountMinor": amount, "currency": "USD", "checkoutUrl": url,
                "purchaseType": "FIRST" if first else "RENEWAL", "autoRenew": False}

    def _record_event(self, db, provider, event_id, order_id, event_type):
        return db.execute("INSERT OR IGNORE INTO membership_payment_events VALUES (?,?,?,?,?)",
                          (provider, event_id, order_id, event_type, int(time.time()))).rowcount == 1

    @staticmethod
    def _checkout_matches(order, session):
        return (isinstance(session, dict) and session.get("id") == order["provider_ref"]
                and session.get("client_reference_id") == order["id"]
                and isinstance(session.get("metadata"), dict)
                and session["metadata"].get("autolink_order_id") == order["id"]
                and session.get("mode") == "payment"
                and session.get("livemode") is (os.environ.get("PAYMENTS_ENV") == "live")
                and session.get("amount_total") == order["amount_minor"]
                and session.get("currency") == order["currency"].lower())

    def reconcile_order(self, order_id, recover_unknown=False):
        """Server-side repair only; never charges a card or trusts a browser return URL."""
        with self.auth.connect() as db:
            row = db.execute("SELECT * FROM membership_orders WHERE id=? AND provider='stripe'", (order_id,)).fetchone()
        if not row:
            raise BuyerError(404, "Stripe membership order was not found.")
        order = dict(row)
        if order["status"] == "PAID":
            return {"status": "PAID", "alreadyProcessed": True,
                    "manualReview": bool(order["refund_status"] or order["dispute_status"]),
                    "refundStatus": order["refund_status"], "disputeStatus": order["dispute_status"]}
        if order["status"] not in ("CREATING", "UNKNOWN", "PENDING", "EXPIRED"):
            return {"status": order["status"], "manualReview": True}
        if not order["provider_ref"]:
            if (order["status"] not in ("CREATING", "UNKNOWN") or not recover_unknown
                    or not order["checkout_email"] or int(time.time()) >= order["expires_at"]):
                return {"status": "UNKNOWN", "manualReview": True}
            try:
                ref, url = self.gateway.checkout(order, order["checkout_email"])
            except GatewayError:
                return {"status": "UNKNOWN", "manualReview": True}
            with self.auth.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT status,provider_ref FROM membership_orders WHERE id=?", (order_id,)).fetchone()
                if current["status"] == "PAID":
                    return {"status": "PAID", "alreadyProcessed": True}
                if current["provider_ref"] and current["provider_ref"] != ref:
                    raise BuyerError(409, "Checkout identity changed during reconciliation.")
                db.execute("UPDATE membership_orders SET status='PENDING',provider_ref=?,checkout_url=?,updated_at=? WHERE id=?",
                           (ref, url, int(time.time()), order_id))
            order["provider_ref"] = ref
        try:
            session = self.gateway.retrieve_checkout(order["provider_ref"])
        except GatewayError:
            return {"status": "UNKNOWN", "manualReview": True}
        if not self._checkout_matches(order, session):
            raise BuyerError(409, "Stripe checkout does not match the order; manual review required.")
        if session.get("status") == "complete" and session.get("payment_status") == "paid":
            payment_id = session.get("payment_intent")
            if not isinstance(payment_id, str) or not payment_id.startswith("pi_"):
                raise BuyerError(409, "Stripe payment identity requires manual review.")
            result = self._fulfill("stripe", "reconcile:" + order["provider_ref"], "checkout.session.reconciled",
                                   order_id, order["provider_ref"], payment_id,
                                   session["amount_total"], session["currency"])
            if result.get("review"):
                return {"status": "REVIEW", "manualReview": True}
            return {"status": "PAID", "reconciled": True}
        if session.get("status") == "expired" and session.get("payment_status") == "unpaid":
            with self.auth.connect() as db:
                db.execute("UPDATE membership_orders SET status='EXPIRED',updated_at=? WHERE id=? AND status IN ('CREATING','UNKNOWN','PENDING')",
                           (int(time.time()), order_id))
            return {"status": "EXPIRED"}
        return {"status": "PENDING", "manualReview": session.get("status") != "open"}

    def _fulfill(self, provider, event_id, event_type, order_id, provider_ref, payment_id, amount_minor, currency):
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM membership_orders WHERE id=?", (order_id,)).fetchone()
            if not row or row["provider"] != provider or row["provider_ref"] != provider_ref:
                raise BuyerError(409, "Provider order identity does not match.")
            if amount_minor != row["amount_minor"] or not isinstance(currency, str) or currency.upper() != row["currency"]:
                raise BuyerError(409, "Provider payment amount does not match the order.")
            if not self._record_event(db, provider, event_id, order_id, event_type):
                return {"duplicate": True}
            if row["status"] == "PAID":
                if row["provider_payment_id"] != payment_id:
                    raise BuyerError(409, "Payment identity does not match the paid order.")
                return {"duplicate": True}
            if row["status"] not in ("PENDING", "UNKNOWN", "CREATING", "EXPIRED"):
                raise BuyerError(409, "Order cannot be fulfilled in this state.")
            if row["purchase_type"] == "FIRST" and not self.first_purchase(db, row["user_id"]):
                db.execute("UPDATE membership_orders SET status='REVIEW',provider_payment_id=?,paid_at=?,updated_at=? WHERE id=?",
                           (payment_id, now, now, order_id))
                return {"review": "Introductory discount conflict; do not grant access."}
            previous = db.execute("SELECT max(end_at) FROM buyer_memberships WHERE user_id=? AND status='ACTIVE'", (row["user_id"],)).fetchone()[0]
            start = max(now, previous or now)
            end = add_months(start, PLANS[row["plan"]][0])
            member_id = str(uuid.uuid4())
            db.execute("INSERT INTO buyer_memberships(id,user_id,plan,status,start_at,end_at,auto_renew) VALUES (?,?,?,?,?,?,0)",
                       (member_id, row["user_id"], row["plan"], "ACTIVE", start, end))
            db.execute("INSERT INTO buyer_membership_payments(id,user_id,membership_id,amount_minor,currency,paid_at,status,transaction_id) "
                       "VALUES (?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), row["user_id"], member_id,
                       amount_minor, currency.upper(), now, "PAID", payment_id))
            if row["purchase_type"] == "FIRST":
                db.execute("INSERT INTO membership_intro_uses VALUES (?,?,?)", (row["user_id"], order_id, now))
            db.execute("UPDATE membership_orders SET status='PAID',provider_payment_id=?,membership_id=?,paid_at=?,updated_at=? WHERE id=?",
                       (payment_id, member_id, now, now, order_id))
        return {"paid": True, "membershipId": member_id}

    def _adjustment(self, provider, event_id, event_type, payment_id, refund_minor=None, dispute=None):
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            order = db.execute("SELECT * FROM membership_orders WHERE provider=? AND provider_payment_id=?",
                               (provider, payment_id)).fetchone()
            if not order:
                raise BuyerError(409, "Payment adjustment has no matching order.")
            if not self._record_event(db, provider, event_id, order["id"], event_type):
                return {"duplicate": True}
            if refund_minor is not None:
                if refund_minor < 0 or refund_minor > order["amount_minor"]:
                    raise BuyerError(409, "Stripe refund amount does not match the order.")
                state = "FULL" if order["refund_status"] == "FULL" or refund_minor == order["amount_minor"] else "PARTIAL_REVIEW"
                db.execute("UPDATE membership_orders SET refund_status=?,updated_at=? WHERE id=?",
                           (state, int(time.time()), order["id"]))
                if state == "FULL" and order["membership_id"]:
                    db.execute("UPDATE buyer_memberships SET status='REFUNDED' WHERE id=?", (order["membership_id"],))
                    db.execute("UPDATE buyer_membership_payments SET status='REFUNDED' WHERE membership_id=?", (order["membership_id"],))
            if dispute:
                db.execute("UPDATE membership_orders SET dispute_status=?,updated_at=? WHERE id=?",
                           (dispute, int(time.time()), order["id"]))
        return {"recorded": True}

    @staticmethod
    def _signed_stripe(raw, header):
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        parts = [part.strip() for part in header.split(",")]
        values = dict(part.split("=", 1) for part in parts if "=" in part)
        timestamp = values.get("t", "")
        if not secret or not timestamp.isdigit() or abs(int(time.time()) - int(timestamp)) > 300:
            raise BuyerError(400, "Invalid Stripe signature timestamp.")
        expected = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, part[3:]) for part in parts if part.startswith("v1=")):
            raise BuyerError(400, "Invalid Stripe signature.")

    def webhook(self, provider, raw, headers):
        if provider == "stripe":
            if os.environ.get("PAYMENTS_ENV") not in ("sandbox", "live") or not os.environ.get("STRIPE_ACCOUNT_ID", "").startswith("acct_"):
                raise BuyerError(503, "Stripe merchant configuration is unavailable.")
            self._signed_stripe(raw, headers.get("Stripe-Signature", ""))
        elif provider == "airwallex":
            raise BuyerError(503, "Airwallex integration is reserved and unavailable.")
        else:
            raise BuyerError(404, "Unknown payment provider.")
        try:
            event = json.loads(raw)
        except ValueError as exc:
            raise BuyerError(400, "Invalid provider event.") from exc
        if not isinstance(event, dict):
            raise BuyerError(400, "Invalid provider event.")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise BuyerError(400, "Missing provider event ID.")
        if provider == "stripe":
            if event.get("livemode") is not (os.environ.get("PAYMENTS_ENV") == "live"):
                raise BuyerError(409, "Stripe environment mismatch.")
            if event.get("account") and event["account"] != os.environ.get("STRIPE_ACCOUNT_ID"):
                raise BuyerError(409, "Stripe account mismatch.")
            event_type = event.get("type", "")
            data = event.get("data")
            obj = data.get("object") if isinstance(data, dict) else None
            if not isinstance(obj, dict):
                raise BuyerError(400, "Invalid Stripe event object.")
            if event_type == "charge.refunded":
                if (not obj.get("payment_intent") or not isinstance(obj.get("currency"), str)
                        or obj["currency"].upper() != "USD" or not isinstance(obj.get("amount_refunded"), int)):
                    raise BuyerError(409, "Stripe refund identity mismatch.")
                return self._adjustment(provider, event_id, event_type, obj["payment_intent"],
                                        refund_minor=obj.get("amount_refunded"))
            if event_type in ("charge.dispute.created", "charge.dispute.closed"):
                if not obj.get("payment_intent"):
                    raise BuyerError(409, "Stripe dispute identity mismatch.")
                return self._adjustment(provider, event_id, event_type, obj["payment_intent"],
                                        dispute="OPEN" if event_type.endswith("created") else str(obj.get("status", "CLOSED")).upper())
            if event_type == "checkout.session.expired":
                with self.auth.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if self._record_event(db, provider, event_id, obj.get("client_reference_id"), event_type):
                        db.execute("UPDATE membership_orders SET status='EXPIRED',updated_at=? WHERE id=? AND provider_ref=? AND status='PENDING'",
                                   (int(time.time()), obj.get("client_reference_id"), obj.get("id")))
                return {"expired": True}
            if event_type != "checkout.session.completed":
                with self.auth.connect() as db:
                    self._record_event(db, provider, event_id, None, event_type)
                return {"ignored": True}
            if obj.get("mode") != "payment" or obj.get("payment_status") != "paid" or not obj.get("payment_intent"):
                return {"pending": True}
            order_id = obj.get("client_reference_id")
            metadata = obj.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("autolink_order_id") != order_id:
                raise BuyerError(409, "Stripe metadata mismatch.")
            return self._fulfill(provider, event_id, event_type, order_id, obj.get("id"),
                                 obj["payment_intent"], obj.get("amount_total"), obj.get("currency", ""))
