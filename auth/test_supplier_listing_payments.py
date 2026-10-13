"""Airwallex listing-fee isolation tests. No provider network calls are made."""

import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import AuthService, Handler
from buyer_service import BuyerError, BuyerService
from supplier_listing_payments import AirwallexListingGateway, SupplierListingPayments
from trade_service import TradeService


class FakeGateway:
    def __init__(self):
        self.links = {}

    def create_link(self, order):
        link_id = "link_" + order["id"]
        url = "https://www.airwallex.com/pay/hk/link/" + link_id
        self.links[link_id] = {"id": link_id, "url": url, "reference": order["id"],
            "metadata": {"autolink_supplier_order": order["id"],
                         "plan_version": "supplier-launch-20261007-v1"}, "reusable": False,
            "amount": order["amount_minor"] / 100, "currency": "USD", "status": "UNPAID",
            "successful_payment_intent_count": 0}
        return link_id, url

    def retrieve_link(self, link_id):
        return self.links[link_id]

    validate_link = staticmethod(AirwallexListingGateway.validate_link)


class SupplierListingPaymentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"PAYMENTS_ENV": "sandbox", "SUPPLIER_LISTING_PAYMENTS_ENABLED": "true",
            "AIRWALLEX_CLIENT_ID": "test-client", "AIRWALLEX_API_KEY": "test-key",
            "AIRWALLEX_ACCOUNT_ID": "acct_sandbox", "AIRWALLEX_LISTING_WEBHOOK_SECRET": "test-webhook"})
        env.start(); self.addCleanup(env.stop)
        self.auth = AuthService(Path(temp.name)/"auth.db", "test-client", verifier=lambda *_: {})
        BuyerService(self.auth)
        self.trade = TradeService(self.auth)
        self.gateway = FakeGateway()
        self.payments = SupplierListingPayments(self.trade, self.gateway)
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute("INSERT INTO users(id,email,display_name,company_name,role,created_at,email_verified_at) "
                       "VALUES('supplier','supplier@example.test','Supplier','Supplier Co','SUPPLIER',?,?)", (now, now))
            db.execute("INSERT INTO supplier_profiles(user_id,updated_at) VALUES('supplier',?)", (now,))
            db.execute("INSERT INTO supplier_applications(supplier_id,status,updated_at) VALUES('supplier','APPROVED',?)", (now,))
            db.execute("INSERT INTO supplier_vehicles(id,supplier_id,model_id,model_year,price_minor,moq,stock,origin_port,valid_until,status,created_at,updated_at) "
                       "VALUES('listing','supplier','model',2026,100000,1,1,'Shanghai','2099-01-01','APPROVED',?,?)", (now,now))
        self.user = {"id":"supplier", "email":"supplier@example.test", "supplier_role":"OWNER"}

    @staticmethod
    def signed_event(link_id, event_id, account="acct_sandbox"):
        raw = json.dumps({"id":event_id, "name":"payment_link.paid", "account_id":account,
            "data":{"object":{"id":link_id}}}, separators=(",", ":")).encode()
        stamp = str(int(time.time()*1000))
        sig = hmac.new(b"test-webhook", stamp.encode()+raw, hashlib.sha256).hexdigest()
        return raw, {"x-timestamp":stamp, "x-signature":sig}

    def pay(self, order, event_id):
        link = self.gateway.links["link_" + order["orderId"]]
        link.update(status="PAID", successful_payment_intent_count=1,
                    latest_successful_payment_intent_id="int_" + event_id)
        return self.payments.webhook(*self.signed_event(link["id"],event_id))

    def test_closed_by_default_even_with_credentials(self):
        with patch.dict(os.environ, {"SUPPLIER_LISTING_PAYMENTS_ENABLED":"false"}):
            self.assertFalse(self.payments.enabled())
            with self.assertRaises(BuyerError) as error:
                self.payments.create_checkout(self.user, "listing")
            self.assertEqual(error.exception.status, 503)
        with patch.dict(os.environ, {"PAYMENTS_ENV":"live"}):
            self.assertFalse(self.payments.enabled())

    def test_review_owner_and_price_are_server_controlled(self):
        self.assertEqual(self.payments.quote(self.user,"listing")["amountMinor"],4000)
        with self.assertRaises(BuyerError):
            self.payments.quote({**self.user,"supplier_role":"SALES"},"listing")
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_vehicles SET status='PENDING_REVIEW' WHERE id='listing'")
        with self.assertRaises(BuyerError):
            self.payments.create_checkout(self.user,"listing")

    def test_paid_quarters_signature_and_idempotence(self):
        for quarter, amount in ((1,4000),(2,14000),(3,20000)):
            quote = self.payments.quote(self.user,"listing")
            self.assertEqual((quote["quarterNumber"],quote["amountMinor"]),(quarter,amount))
            order = self.payments.create_checkout(self.user,"listing")
            self.assertEqual(order["amountMinor"],amount)
            with self.assertRaises(BuyerError):
                self.payments.create_checkout(self.user,"listing")
            event_id = "evt_" + str(quarter)
            self.assertTrue(self.pay(order,event_id)["paid"])
            link_id = "link_" + order["orderId"]
            self.assertEqual(self.payments.webhook(*self.signed_event(link_id,event_id)),{"duplicate":True})
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM supplier_listing_orders WHERE status='PAID'").fetchone()[0],3)
            self.assertEqual(db.execute("SELECT status FROM supplier_vehicles WHERE id='listing'").fetchone()[0],"APPROVED")

    def test_wrong_signature_merchant_amount_and_link_remain_unpaid(self):
        order = self.payments.create_checkout(self.user,"listing")
        link_id = "link_" + order["orderId"]
        link = self.gateway.links[link_id]
        link.update(status="PAID",successful_payment_intent_count=1,
                    latest_successful_payment_intent_id="int_valid")
        raw, headers = self.signed_event(link_id,"evt_bad")
        with self.assertRaises(BuyerError):
            self.payments.webhook(raw,{**headers,"x-signature":"bad"})
        with self.assertRaises(BuyerError):
            self.payments.webhook(*self.signed_event(link_id,"evt_wrong",account="other"))
        link["amount"] = 1
        with self.assertRaises(BuyerError):
            self.payments.webhook(raw,headers)
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM supplier_listing_orders WHERE id=?",(order["orderId"],)).fetchone()[0],"PENDING")
        link["amount"] = 40
        self.assertTrue(self.payments.webhook(raw,headers)["paid"])

    def test_provider_link_rejects_wrong_url_and_reuse(self):
        order = {"id":"SLO-test","provider_ref":"link_12345678","amount_minor":4000}
        link = {"id":"link_12345678","reference":"SLO-test","url":"https://www.airwallex.com/pay/hk/link/abc",
            "metadata":{"autolink_supplier_order":"SLO-test",
                        "plan_version":"supplier-launch-20261007-v1"},"reusable":False,
            "amount":40,"currency":"USD","status":"UNPAID"}
        AirwallexListingGateway.validate_link(link,order,paid=False)
        for invalid in ({**link,"url":"https://www.airwallex.com.evil.test/pay"},
                        {**link,"reusable":True},{**link,"amount":40.01}):
            with self.assertRaises(BuyerError):
                AirwallexListingGateway.validate_link(invalid,order,paid=False)

    def test_http_routes_require_owner_session_and_origin(self):
        class PaymentHandler(Handler):
            pass
        PaymentHandler.service = self.auth
        PaymentHandler.trade = self.trade
        PaymentHandler.supplier_payments = self.payments
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaymentHandler)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(server.server_port)
        token = self.auth.session_for_user("supplier")["access_token"]

        def call(path, method="GET", body=None, authenticated=True, origin=None):
            headers = {"Cookie":"autolink_session="+token} if authenticated else {}
            if body is not None:
                headers["Content-Type"] = "application/json"
            if origin:
                headers["Origin"] = origin
            request = Request(base+path, data=json.dumps(body).encode() if body is not None else None,
                              headers=headers, method=method)
            try:
                response = urlopen(request)
            except HTTPError as exc:
                response = exc
            with response:
                return response.status, json.loads(response.read())

        quote_path = "/autolink/supplier/vehicles/listing/listing-quote"
        checkout_path = "/autolink/supplier/vehicles/listing/listing-checkout"
        self.assertEqual(call(quote_path, authenticated=False)[0], 401)
        self.assertEqual(call(quote_path)[1]["data"]["amountMinor"], 4000)
        self.assertEqual(call(checkout_path, "POST", {}, authenticated=False)[0], 401)
        self.assertEqual(call(checkout_path, "POST", {}, origin="https://evil.test")[0], 403)
        self.assertEqual(call(checkout_path, "POST", {})[1]["data"]["amountMinor"], 4000)
        self.assertEqual(call("/autolink/supplier/listing-payments")[1]["data"][0]["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
