"""Stripe supplier listing checkout tests; no provider network or real charge."""

import hashlib
import hmac
import io
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
from PIL import Image

import image_service
from app import AuthService, Handler
from buyer_service import BuyerError, BuyerService
from membership_payments import GatewayError
from supplier_listing_payments import CONSENT_VERSION, StripeListingGateway, SupplierListingPayments
from trade_service import TradeService


class FakeGateway:
    def __init__(self):
        self.sessions = {}
        self.fail_after_create = False

    def create_checkout(self, order, email):
        ref = "cs_test_" + order["id"].replace("-", "")
        session = {"id": ref, "url": "https://checkout.stripe.com/c/pay/" + ref,
                   "livemode": False, "mode": "payment", "client_reference_id": order["id"],
                   "metadata": {"autolink_supplier_order": order["id"],
                                "plan_version": "supplier-launch-20261007-v1",
                                "purpose": "supplier_listing"},
                   "amount_total": order["amount_minor"], "currency": "usd",
                   "payment_method_configuration_details": {"id": "pmc_cards"},
                   "payment_method_types": ["card"], "status": "open", "payment_status": "unpaid",
                   "payment_intent": None}
        self.sessions.setdefault(ref, session)
        if self.fail_after_create:
            self.fail_after_create = False
            raise GatewayError("Simulated lost response after Stripe created a session.")
        return StripeListingGateway.validate_checkout(session, order, require_url=True)

    def retrieve_checkout(self, reference):
        return self.sessions[reference]

    validate_checkout = staticmethod(StripeListingGateway.validate_checkout)


class SupplierStripeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {
            "PAYMENTS_ENV": "sandbox", "STRIPE_SUPPLIER_LISTING_ENABLED": "true",
            "STRIPE_SECRET_KEY": "rk_test_isolated", "STRIPE_ACCOUNT_ID": "acct_isolated",
            "STRIPE_PAYMENT_METHOD_CONFIGURATION": "pmc_cards",
            "STRIPE_SUPPLIER_WEBHOOK_SECRET": "whsec_supplier_isolated",
        })
        env.start()
        self.addCleanup(env.stop)
        self.auth = AuthService(Path(temp.name) / "auth.db", "test-client", verifier=lambda *_: {})
        original_image_root = image_service.ROOT
        image_service.ROOT = Path(temp.name) / "images"
        self.addCleanup(lambda: setattr(image_service, "ROOT", original_image_root))
        BuyerService(self.auth)
        self.trade = TradeService(self.auth)
        self.gateway = FakeGateway()
        self.payments = SupplierListingPayments(self.trade, self.gateway)
        now = int(time.time())
        image_service.ROOT.mkdir()
        photo = io.BytesIO()
        Image.new("RGB", (240, 240), "gray").save(photo, "JPEG")
        stock_name = "a" * 32 + ".jpg"
        (image_service.ROOT / stock_name).write_bytes(photo.getvalue())
        with self.auth.connect() as db:
            db.execute(
                "INSERT INTO users(id,email,display_name,company_name,role,created_at,email_verified_at) "
                "VALUES('supplier','supplier@example.test','Supplier','Supplier Co','SUPPLIER',?,?)",
                (now, now)
            )
            db.execute("INSERT INTO supplier_profiles(user_id,published,updated_at) VALUES('supplier',1,?)", (now,))
            db.execute(
                "INSERT INTO users(id,email,display_name,company_name,role,created_at,email_verified_at) "
                "VALUES('reviewer','reviewer@example.test','Reviewer','AUTOLINK','PLATFORM_ADMIN',?,?)",
                (now, now)
            )
            db.execute(
                "INSERT INTO supplier_applications(supplier_id,status,updated_at) "
                "VALUES('supplier','APPROVED',?)", (now,)
            )
            db.execute(
                "INSERT INTO supplier_vehicles(id,supplier_id,model_id,model_year,price_minor,"
                "moq,stock,origin_port,valid_until,status,reviewed_by,reviewed_at,created_at,updated_at) "
                "VALUES('listing','supplier','zeekr-9x-2026',2026,100000,1,1,'Shanghai',"
                "'2099-01-01','APPROVED','reviewer',?,?,?)", (now, now, now)
            )
            db.execute("INSERT INTO vehicle_images(id,listing_id,supplier_id,filename,stored_name,"
                "bytes,width,height,created_at,stock_photo,attested_by,attested_at) "
                "VALUES('photo','listing','supplier','stock.jpg',?,?,?,?,?,1,'supplier',?)",
                (stock_name, len(photo.getvalue()), 240, 240, now, now))
        self.user = {"id": "supplier", "email": "supplier@example.test",
                     "supplier_role": "OWNER"}

    @staticmethod
    def event(session, event_id, kind="checkout.session.completed", account="acct_isolated"):
        obj = dict(session)
        raw = json.dumps({"id": event_id, "type": kind, "livemode": False,
                          "account": account, "data": {"object": obj}},
                         separators=(",", ":")).encode()
        stamp = str(int(time.time()))
        sig = hmac.new(b"whsec_supplier_isolated", stamp.encode() + b"." + raw,
                       hashlib.sha256).hexdigest()
        return raw, {"Stripe-Signature": "t=" + stamp + ",v1=" + sig}

    def pay(self, order, event_id):
        session = self.gateway.sessions["cs_test_" + order["orderId"].replace("-", "")]
        session.update(status="complete", payment_status="paid", payment_intent="pi_" + event_id)
        return self.payments.webhook(*self.event(session, event_id))

    def checkout(self, supplier, listing_id):
        return self.payments.create_checkout(supplier, listing_id, {
            "serviceConsent": True, "serviceTermsVersion": CONSENT_VERSION})

    def test_closed_by_default_and_environment_checks(self):
        with patch.dict(os.environ, {"STRIPE_SUPPLIER_LISTING_ENABLED": "false"}):
            self.assertFalse(self.payments.enabled())
            with self.assertRaises(BuyerError) as error:
                self.checkout(self.user, "listing")
            self.assertEqual(error.exception.status, 503)
        with patch.dict(os.environ, {"PAYMENTS_ENV": "live", "STRIPE_SECRET_KEY": "rk_live_isolated",
                                  "STRIPE_LIVE_RELEASE_READY": "false"}):
            self.assertFalse(self.payments.enabled())

    def test_review_owner_and_price_are_server_controlled(self):
        self.assertEqual(self.payments.quote(self.user, "listing")["amountMinor"], 4000)
        with self.assertRaises(BuyerError):
            self.payments.quote({**self.user, "supplier_role": "SALES"}, "listing")
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_vehicles SET status='PENDING_REVIEW' WHERE id='listing'")
        with self.assertRaises(BuyerError):
            self.checkout(self.user, "listing")

    def test_paid_quarters_replay_and_reviewed_publication(self):
        with self.assertRaises(BuyerError) as unpaid:
            self.trade.transition_vehicle(self.user, 'listing', 'online')
        self.assertEqual(unpaid.exception.status, 409)
        for quarter, amount in ((1, 4000), (2, 14000), (3, 20000)):
            self.assertEqual(self.payments.quote(self.user, "listing")["amountMinor"], amount)
            order = self.checkout(self.user, "listing")
            self.assertEqual(order["amountMinor"], amount)
            with self.assertRaises(BuyerError):
                self.checkout(self.user, "listing")
            event_id = "evt_" + str(quarter)
            settled = self.pay(order, event_id)
            self.assertTrue(settled["paid"])
            self.assertEqual(settled["publication"], "online")
            session = self.gateway.sessions["cs_test_" + order["orderId"].replace("-", "")]
            self.assertEqual(self.payments.webhook(*self.event(session, event_id)),
                             {"duplicate": True})
        with self.auth.connect() as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM supplier_listing_orders WHERE status='PAID'"
            ).fetchone()[0], 3)
            self.assertEqual(db.execute(
                "SELECT status FROM supplier_vehicles WHERE id='listing'"
            ).fetchone()[0], "ONLINE")
        self.assertEqual(self.trade.vehicle('listing', public=True)['id'], 'listing')

    def test_one_paid_skc_covers_another_reviewed_trim_and_expiry_hides_both(self):
        with self.auth.connect() as db:
            db.execute("INSERT INTO supplier_vehicles(id,supplier_id,model_id,model_year,price_minor,"
                "moq,stock,origin_port,valid_until,status,reviewed_by,reviewed_at,created_at,updated_at) "
                "SELECT 'second',supplier_id,model_id,model_year,price_minor,moq,stock,origin_port,"
                "valid_until,status,reviewed_by,reviewed_at,created_at,updated_at "
                "FROM supplier_vehicles WHERE id='listing'")
        order = self.checkout(self.user, 'listing')
        self.pay(order, 'evt_skc')
        self.trade.transition_vehicle(self.user, 'second', 'online')
        self.assertEqual(self.trade.vehicle('second', public=True)['id'], 'second')
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_listing_orders SET service_until=? WHERE id=?",
                       (int(time.time()) - 1, order['orderId']))
        for listing in ('listing', 'second'):
            with self.assertRaises(BuyerError) as expired:
                self.trade.vehicle(listing, public=True)
            self.assertEqual(expired.exception.status, 404)
            self.assertIn('LISTING_SERVICE_EXPIRED',
                          self.trade.vehicle(listing, supplier_id='supplier')['publication']['reasons'])

    def test_paid_order_does_not_publish_changed_or_unavailable_listing(self):
        order = self.checkout(self.user, 'listing')
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_vehicles SET status='DRAFT' WHERE id='listing'")
        result = self.pay(order, 'evt_changed')
        self.assertEqual(result['publication'], 'manual_review')
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM supplier_listing_orders WHERE id=?",
                (order['orderId'],)).fetchone()[0], 'PAID')
        with self.assertRaises(BuyerError):
            self.trade.vehicle('listing', public=True)

    def test_signature_merchant_amount_and_url_rejections(self):
        order = self.checkout(self.user, "listing")
        session = self.gateway.sessions["cs_test_" + order["orderId"].replace("-", "")]
        session.update(status="complete", payment_status="paid", payment_intent="pi_valid")
        raw, headers = self.event(session, "evt_bad")
        with self.assertRaises(BuyerError):
            self.payments.webhook(raw, {"Stripe-Signature": "bad"})
        with self.assertRaises(BuyerError):
            self.payments.webhook(*self.event(session, "evt_wrong", account="acct_other"))
        session["amount_total"] = 1
        with self.assertRaises(BuyerError):
            self.payments.webhook(raw, headers)
        with self.auth.connect() as db:
            self.assertEqual(db.execute(
                "SELECT status FROM supplier_listing_orders WHERE id=?", (order["orderId"],)
            ).fetchone()[0], "PENDING")
        session["amount_total"] = 4000
        self.assertTrue(self.payments.webhook(raw, headers)["paid"])
        for changed in ({"url": "https://checkout.stripe.com.evil.test/pay"},
                        {"amount_total": 4001}, {"mode": "subscription"}):
            with self.assertRaises(BuyerError):
                StripeListingGateway.validate_checkout(
                    {**session, **changed}, {"id": order["orderId"], "amount_minor": 4000},
                    paid=False, require_url=True
                )

    def test_refund_and_expiry_records(self):
        order = self.checkout(self.user, "listing")
        session = self.gateway.sessions["cs_test_" + order["orderId"].replace("-", "")]
        session.update(status="complete", payment_status="paid", payment_intent="pi_paid")
        self.payments.webhook(*self.event(session, "evt_paid"))
        refund = {"payment_intent": "pi_paid", "currency": "usd", "amount_refunded": 4000}
        raw, headers = self.event(refund, "evt_refund", "charge.refunded")
        self.assertTrue(self.payments.webhook(raw, headers)["recorded"])
        self.assertTrue(self.payments.webhook(*self.event(
            refund, "evt_refund_repeat", "charge.refunded"))["recorded"])
        with self.auth.connect() as db:
            self.assertEqual(db.execute(
                "SELECT refund_status FROM supplier_listing_orders WHERE id=?",
                (order["orderId"],)
            ).fetchone()[0], "FULL")
            self.assertEqual(db.execute("SELECT status FROM supplier_vehicles WHERE id='listing'")
                             .fetchone()[0], 'OFFLINE')
            self.assertEqual(db.execute("SELECT count(*) FROM account_notifications "
                "WHERE user_id='supplier' AND event='LISTING_SERVICE_REFUNDED'").fetchone()[0], 1)
        with self.assertRaises(BuyerError) as hidden:
            self.trade.vehicle('listing', public=True)
        self.assertEqual(hidden.exception.status, 404)
        with self.assertRaises(BuyerError):
            self.trade.transition_vehicle(self.user, 'listing', 'online')
        renewal = self.checkout(self.user, 'listing')
        self.assertEqual(renewal['amountMinor'], 14000)
        self.assertEqual(self.pay(renewal, 'evt_after_refund')['publication'], 'online')
        self.assertEqual(self.trade.vehicle('listing', public=True)['id'], 'listing')

    def test_partial_refund_and_dispute_remain_for_manual_review(self):
        order = self.checkout(self.user, 'listing')
        self.pay(order, 'evt_partial_paid')
        partial = {'payment_intent': 'pi_evt_partial_paid', 'currency': 'usd',
                   'amount_refunded': 1000}
        self.assertTrue(self.payments.webhook(*self.event(
            partial, 'evt_partial_refund', 'charge.refunded'))['recorded'])
        dispute = {'payment_intent': 'pi_evt_partial_paid', 'status': 'needs_response'}
        self.assertTrue(self.payments.webhook(*self.event(
            dispute, 'evt_dispute', 'charge.dispute.created'))['recorded'])
        self.assertEqual(self.trade.vehicle('listing', public=True)['id'], 'listing')
        with self.auth.connect() as db:
            self.assertEqual(tuple(db.execute(
                'SELECT refund_status,dispute_status FROM supplier_listing_orders WHERE id=?',
                (order['orderId'],)).fetchone()), ('PARTIAL', 'OPEN'))

    def test_lost_checkout_response_reconciles_without_a_second_order(self):
        self.gateway.fail_after_create = True
        with self.assertRaises(BuyerError):
            self.checkout(self.user, "listing")
        with self.auth.connect() as db:
            row = db.execute("SELECT id,status,provider_ref FROM supplier_listing_orders").fetchone()
            self.assertEqual((row["status"], row["provider_ref"]), ("UNKNOWN", None))
            order_id = row["id"]
        self.assertEqual(self.payments.reconcile_order(order_id)["status"], "UNKNOWN")
        self.assertEqual(self.payments.reconcile_order(order_id, recover_unknown=True)["status"], "PENDING")
        session = self.gateway.sessions["cs_test_" + order_id.replace("-", "")]
        session.update(status="complete", url=None, payment_status="paid", payment_intent="pi_recovered")
        self.assertTrue(self.payments.reconcile_order(order_id)["paid"])
        self.assertTrue(self.payments.reconcile_order(order_id)["alreadyProcessed"])
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM supplier_listing_orders").fetchone()[0], 1)

    def test_expired_stripe_session_without_checkout_url_releases_order(self):
        checkout = self.checkout(self.user, "listing")
        session = self.gateway.sessions["cs_test_" + checkout["orderId"].replace("-", "")]
        session.update(status="expired", url=None)
        self.assertTrue(self.payments.webhook(*self.event(
            session, "evt_expired", "checkout.session.expired"))["expired"])
        self.assertEqual(self.payments.reconcile_order(checkout["orderId"])["status"], "EXPIRED")
        self.assertEqual(self.payments.quote(self.user, "listing")["amountMinor"], 4000)

    def test_http_routes_require_owner_session_and_origin(self):
        class PaymentHandler(Handler):
            pass
        PaymentHandler.service = self.auth
        PaymentHandler.trade = self.trade
        PaymentHandler.supplier_payments = self.payments
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaymentHandler)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(server.server_port)
        token = self.auth.session_for_user("supplier")["access_token"]

        def call(path, method="GET", body=None, authenticated=True, origin=None):
            headers = {"Cookie": "autolink_session=" + token} if authenticated else {}
            if body is not None:
                headers["Content-Type"] = "application/json"
            if origin:
                headers["Origin"] = origin
            request = Request(base + path,
                              data=json.dumps(body).encode() if body is not None else None,
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
        self.assertEqual(call(checkout_path, "POST", {})[0], 400)
        self.assertEqual(call(checkout_path, "POST", {"serviceConsent": True,
            "serviceTermsVersion": CONSENT_VERSION})[1]["data"]["amountMinor"], 4000)
        self.assertEqual(call("/autolink/supplier/listing-payments")[1]["data"][0]["status"],
                         "PENDING")


if __name__ == "__main__":
    unittest.main()
