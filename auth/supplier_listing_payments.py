"""Isolated Airwallex payment-link orders for reviewed supplier SKCs.

This service is separate from buyer membership billing. Both checkout and
webhook handling are closed unless the supplier payment switch is enabled.
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
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from buyer_service import BuyerError


PRICES_MINOR = (4000, 14000, 20000)
PLAN_VERSION = "supplier-launch-20261007-v1"


def quarter_end(timestamp):
    current = datetime.fromtimestamp(timestamp, timezone.utc)
    month_number = current.month + 3
    year = current.year + (month_number - 1) // 12
    month = (month_number - 1) % 12 + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return int(current.replace(year=year, month=month, day=day).timestamp())


def minor_units(amount):
    try:
        cents = Decimal(str(amount)) * 100
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BuyerError(409, "Payment amount is invalid.") from exc
    if not cents.is_finite() or cents != cents.to_integral_value():
        raise BuyerError(409, "Payment amount is invalid.")
    return int(cents)


class AirwallexListingGateway:
    """Server-only Airwallex API access; credentials never reach a browser."""

    def __init__(self):
        self._token = None
        self._token_until = 0

    @staticmethod
    def base():
        return ("https://api.sandbox.airwallex.com" if os.environ.get("PAYMENTS_ENV") == "sandbox"
                else "https://api.airwallex.com")

    def request(self, path, payload=None, *, authenticate=True):
        headers = {"Content-Type": "application/json"}
        if os.environ.get("AIRWALLEX_API_VERSION"):
            headers["x-api-version"] = os.environ["AIRWALLEX_API_VERSION"]
        if authenticate:
            headers["Authorization"] = "Bearer " + self.token()
        else:
            headers["x-client-id"] = os.environ["AIRWALLEX_CLIENT_ID"]
            headers["x-api-key"] = os.environ["AIRWALLEX_API_KEY"]
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        try:
            with urlopen(Request(self.base() + path, data=body, headers=headers), timeout=12) as response:
                result = json.load(response)
        except Exception as exc:
            raise BuyerError(503, "Airwallex request requires reconciliation.") from exc
        if not isinstance(result, dict):
            raise BuyerError(503, "Airwallex returned an invalid response.")
        return result

    def token(self):
        if self._token and self._token_until > time.time() + 60:
            return self._token
        result = self.request("/api/v1/authentication/login", {}, authenticate=False)
        token, expiry = result.get("token"), result.get("expires_at")
        if not isinstance(token, str) or not token or not isinstance(expiry, str):
            raise BuyerError(503, "Airwallex authentication response is invalid.")
        try:
            until = datetime.fromisoformat(expiry.replace("Z", "+00:00")).timestamp()
        except ValueError as exc:
            raise BuyerError(503, "Airwallex token expiry is invalid.") from exc
        self._token, self._token_until = token, until
        return token

    def create_link(self, order):
        amount = order["amount_minor"] / 100
        result = self.request("/api/v1/pa/payment_links/create", {
            "reusable": False, "title": "AUTOLINK reviewed supplier listing service",
            "description": "One SKC / one quarter. Manual renewal.",
            "amount": amount, "currency": "USD", "reference": order["id"],
            "metadata": {"autolink_supplier_order": order["id"], "plan_version": PLAN_VERSION},
            "expires_at": datetime.fromtimestamp(order["expires_at"], timezone.utc).isoformat(),
        })
        self.validate_link(result, order, paid=False)
        return result["id"], result["url"]

    def retrieve_link(self, link_id):
        if not isinstance(link_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", link_id):
            raise BuyerError(409, "Invalid Airwallex link reference.")
        return self.request("/api/v1/pa/payment_links/" + quote(link_id, safe=""))

    @staticmethod
    def validate_link(link, order, *, paid):
        metadata = link.get("metadata")
        url = link.get("url")
        host = urlparse(url).hostname if isinstance(url, str) else None
        if ((order.get("provider_ref") is not None and link.get("id") != order["provider_ref"])
                or not isinstance(link.get("id"), str) or not link["id"]
                or link.get("reference") != order["id"]
                or not isinstance(metadata, dict)
                or metadata.get("autolink_supplier_order") != order["id"]
                or metadata.get("plan_version") != PLAN_VERSION
                or link.get("reusable") is not False
                or link.get("currency") != "USD"
                or minor_units(link.get("amount")) != order["amount_minor"]
                or host not in {"www.airwallex.com", "checkout.airwallex.com"}
                or urlparse(url).scheme != "https"
                or link.get("status") != ("PAID" if paid else "UNPAID")):
            raise BuyerError(409, "Airwallex payment link does not match the supplier order.")
        if paid and (link.get("successful_payment_intent_count") != 1
                     or not isinstance(link.get("latest_successful_payment_intent_id"), str)):
            raise BuyerError(409, "Airwallex payment link is not uniquely paid.")


class SupplierListingPayments:
    def __init__(self, trade, gateway=None):
        self.trade = trade
        self.auth = trade.auth
        self.gateway = gateway or AirwallexListingGateway()
        with self.auth.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS supplier_listing_orders (
                    id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL REFERENCES users(id),
                    listing_id TEXT NOT NULL REFERENCES supplier_vehicles(id),
                    model_id TEXT NOT NULL, model_year INTEGER NOT NULL,
                    quarter_number INTEGER NOT NULL, amount_minor INTEGER NOT NULL,
                    currency TEXT NOT NULL CHECK(currency='USD'),
                    plan_version TEXT NOT NULL, provider TEXT NOT NULL CHECK(provider='airwallex'),
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

    @staticmethod
    def enabled():
        # The merchant application is under review. A production switch is not
        # exposed until live method approval, terms, and reconciliation are verified.
        return (os.environ.get("SUPPLIER_LISTING_PAYMENTS_ENABLED", "false").lower() == "true"
                and os.environ.get("PAYMENTS_ENV") == "sandbox"
                and all(os.environ.get(key) for key in
                        ("AIRWALLEX_CLIENT_ID", "AIRWALLEX_API_KEY", "AIRWALLEX_ACCOUNT_ID",
                         "AIRWALLEX_LISTING_WEBHOOK_SECRET")))

    def quote(self, supplier, listing_id):
        with self.auth.connect() as db:
            self.trade.active_company_owner(db, supplier)
            row = db.execute("SELECT * FROM supplier_vehicles WHERE id=? AND supplier_id=? AND archived_at IS NULL",
                             (listing_id, supplier["id"])).fetchone()
            if not row:
                raise BuyerError(404, "Supplier listing not found.")
            if row["status"] != "APPROVED":
                raise BuyerError(409, "Listing review must be completed before payment.")
            paid = db.execute("SELECT count(*),max(service_until) FROM supplier_listing_orders "
                              "WHERE supplier_id=? AND model_id=? AND model_year=? AND status='PAID'",
                              (supplier["id"], row["model_id"], row["model_year"])).fetchone()
        quarter = paid[0] + 1
        return {"listingId": listing_id, "modelId": row["model_id"], "modelYear": row["model_year"],
                "quarterNumber": quarter, "amountMinor": PRICES_MINOR[min(paid[0], 2)],
                "currency": "USD", "planVersion": PLAN_VERSION,
                "currentServiceUntil": paid[1], "available": self.enabled(), "renewal": "manual"}

    def create_checkout(self, supplier, listing_id):
        if not self.enabled():
            raise BuyerError(503, "Supplier listing payment is not yet available.")
        if supplier.get("is_test_workspace"):
            raise BuyerError(403, "Test workspace cannot purchase listing service.")
        quote_data = self.quote(supplier, listing_id)
        now, order_id = int(time.time()), "SLO-" + uuid.uuid4().hex.upper()
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.trade.active_company_owner(db, supplier)
            row = db.execute("SELECT model_id,model_year,status FROM supplier_vehicles WHERE id=? AND supplier_id=? AND archived_at IS NULL",
                             (listing_id, supplier["id"])).fetchone()
            if not row or row["status"] != "APPROVED" or row["model_id"] != quote_data["modelId"] or row["model_year"] != quote_data["modelYear"]:
                raise BuyerError(409, "Listing changed during checkout; review the quote again.")
            paid_count = db.execute("SELECT count(*) FROM supplier_listing_orders WHERE supplier_id=? AND model_id=? AND model_year=? AND status='PAID'",
                                    (supplier["id"], row["model_id"], row["model_year"])).fetchone()[0]
            if paid_count + 1 != quote_data["quarterNumber"]:
                raise BuyerError(409, "Listing price changed; review the quote again.")
            if db.execute("SELECT 1 FROM supplier_listing_orders WHERE supplier_id=? AND model_id=? AND model_year=? "
                          "AND status IN ('CREATING','PENDING','UNKNOWN')",
                          (supplier["id"],row["model_id"],row["model_year"])).fetchone():
                raise BuyerError(409, "A listing checkout is already open; reconcile it before retrying.")
            db.execute("INSERT INTO supplier_listing_orders(id,supplier_id,listing_id,model_id,model_year,quarter_number,"
                       "amount_minor,currency,plan_version,provider,status,created_at,expires_at,updated_at) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (order_id,supplier["id"],listing_id,row["model_id"],row["model_year"],paid_count+1,
                        quote_data["amountMinor"],"USD",PLAN_VERSION,"airwallex","CREATING",now,now+3600,now))
            order = dict(db.execute("SELECT * FROM supplier_listing_orders WHERE id=?", (order_id,)).fetchone())
        try:
            reference, url = self.gateway.create_link(order)
        except Exception as exc:
            with self.auth.connect() as db:
                db.execute("UPDATE supplier_listing_orders SET status='UNKNOWN',updated_at=? WHERE id=?",
                           (int(time.time()), order_id))
            raise BuyerError(503, "Checkout outcome is uncertain. Contact support before retrying.") from exc
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_listing_orders SET status='PENDING',provider_ref=?,checkout_url=?,updated_at=? WHERE id=?",
                       (reference,url,int(time.time()),order_id))
        return {"orderId":order_id,"amountMinor":order["amount_minor"],"currency":"USD",
                "checkoutUrl":url,"renewal":"manual"}

    def webhook(self, raw, headers):
        if not self.enabled():
            raise BuyerError(503, "Supplier listing payment is not available.")
        timestamp = headers.get("x-timestamp", "")
        signature = headers.get("x-signature", "")
        secret = os.environ["AIRWALLEX_LISTING_WEBHOOK_SECRET"]
        if not re.fullmatch(r"\d{13}", timestamp) or abs(int(time.time()*1000)-int(timestamp)) > 300000:
            raise BuyerError(400, "Invalid Airwallex webhook timestamp.")
        expected = hmac.new(secret.encode(), timestamp.encode()+raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise BuyerError(400, "Invalid Airwallex webhook signature.")
        try:
            event = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise BuyerError(400, "Invalid Airwallex event.") from exc
        if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"]:
            raise BuyerError(400, "Invalid Airwallex event.")
        if event.get("account_id", event.get("accountId")) != os.environ["AIRWALLEX_ACCOUNT_ID"]:
            raise BuyerError(409, "Airwallex merchant account mismatch.")
        name = event.get("name")
        obj = event.get("data", {}).get("object") if isinstance(event.get("data"), dict) else None
        if name != "payment_link.paid":
            return {"ignored": True}
        if not isinstance(obj, dict):
            raise BuyerError(400, "Invalid Airwallex payment link event.")
        with self.auth.connect() as db:
            if db.execute("SELECT 1 FROM supplier_listing_payment_events WHERE event_id=?", (event["id"],)).fetchone():
                return {"duplicate": True}
            row = db.execute("SELECT * FROM supplier_listing_orders WHERE provider_ref=?", (obj.get("id"),)).fetchone()
        if not row:
            raise BuyerError(409, "Airwallex payment link is not yet recognized.")
        order = dict(row)
        confirmed = self.gateway.retrieve_link(order["provider_ref"])
        self.gateway.validate_link(confirmed, order, paid=True)
        payment_id = confirmed["latest_successful_payment_intent_id"]
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM supplier_listing_payment_events WHERE event_id=?", (event["id"],)).fetchone():
                return {"duplicate": True}
            current = db.execute("SELECT status FROM supplier_listing_orders WHERE id=?", (order["id"],)).fetchone()
            if not current or current["status"] not in ("PENDING", "PAID"):
                raise BuyerError(409, "Supplier order is not payable.")
            if current["status"] == "PAID":
                db.execute("INSERT INTO supplier_listing_payment_events VALUES(?,?,?,?)",
                           (event["id"],name,order["id"],now))
                return {"duplicate": True}
            prior = db.execute("SELECT max(service_until) FROM supplier_listing_orders WHERE supplier_id=? AND model_id=? "
                               "AND model_year=? AND status='PAID'",
                               (order["supplier_id"],order["model_id"],order["model_year"])).fetchone()[0]
            until = quarter_end(max(now, prior or now))
            db.execute("UPDATE supplier_listing_orders SET status='PAID',provider_payment_id=?,paid_at=?,service_until=?,updated_at=? WHERE id=? AND status='PENDING'",
                       (payment_id,now,until,now,order["id"]))
            db.execute("INSERT INTO supplier_listing_payment_events VALUES(?,?,?,?)",
                       (event["id"],name,order["id"],now))
            # Existing review controls remain authoritative. A paid order alone
            # does not bypass publication, image, stock, or catalogue checks.
        return {"paid": True, "serviceUntil": until, "publication": "awaiting_verified_activation"}
