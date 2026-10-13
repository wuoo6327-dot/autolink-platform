"""Isolated membership payment tests: provider calls are never sent over network."""

import hashlib
import hmac
import io
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from app import AuthService, Handler
from buyer_service import BuyerError, BuyerService
from membership_payments import GatewayError, MembershipPaymentService, PaymentGateway, add_months
from reconcile_membership import main as reconcile_main


class FakeGateway:
    def __init__(self):
        self.sessions = {}
        self.fail_after_create = False

    def checkout(self, order, email):
        ref = "cs_" + order["id"]
        self.sessions.setdefault(ref, {"id": ref, "client_reference_id": order["id"],
            "metadata": {"autolink_order_id": order["id"]}, "mode": "payment", "livemode": False,
            "amount_total": order["amount_minor"], "currency": "usd", "status": "open",
            "payment_status": "unpaid", "payment_intent": None})
        if self.fail_after_create:
            self.fail_after_create = False
            raise GatewayError("Simulated response loss after Stripe created a session.")
        return ref, "https://checkout.stripe.com/test/" + ref

    def retrieve_checkout(self, reference):
        return self.sessions[reference]


class MembershipPaymentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"PAYMENTS_ENV": "sandbox", "STRIPE_CARD_ENABLED": "true",
            "STRIPE_ACCOUNT_ID": "acct_isolated", "STRIPE_SECRET_KEY": "sk_test_isolated",
            "STRIPE_WEBHOOK_SECRET": "whsec_isolated",
            "STRIPE_PAYMENT_METHOD_CONFIGURATION": "pmc_isolated"})
        env.start(); self.addCleanup(env.stop)
        self.auth = AuthService(Path(self.temp.name) / "auth.db", "test-client", verifier=lambda *_: {})
        BuyerService(self.auth)
        self.gateway = FakeGateway()
        self.payments = MembershipPaymentService(self.auth, self.gateway)
        with self.auth.connect() as db:
            db.execute("INSERT INTO users(id,email,display_name,company_name,role,created_at,email_verified_at) "
                       "VALUES ('buyer','buyer@example.test','Buyer','Test Buyer','BUYER',?,?)",
                       (int(time.time()), int(time.time())))
        self.user = {"id": "buyer", "email": "buyer@example.test", "role": "BUYER"}

    def stripe_event(self, checkout, *, amount=None, event_id="evt_1", event_type="checkout.session.completed"):
        order_id = checkout["orderId"]
        obj = {"id": "cs_" + order_id, "client_reference_id": order_id,
               "metadata": {"autolink_order_id": order_id}, "mode": "payment",
               "payment_status": "paid", "payment_intent": "pi_" + order_id,
               "amount_total": checkout["amountMinor"] if amount is None else amount, "currency": "usd"}
        event = {"id": event_id, "type": event_type, "livemode": False, "data": {"object": obj}}
        raw = json.dumps(event).encode()
        stamp = str(int(time.time()))
        signature = hmac.new(b"whsec_isolated", stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        return raw, {"Stripe-Signature": "t=" + stamp + ", v1=" + signature}

    def test_prices_first_purchase_once_across_plans(self):
        self.assertEqual({k:v["dueMinor"] for k,v in self.payments.pricing(self.user)["plans"].items()},
                         {"monthly":199,"quarterly":999,"annual":3999})
        order = self.payments.create_checkout(self.user, {"plan":"annual", "method":"stripe_card", "autoRenew":False})
        self.assertEqual((order["amountMinor"],order["purchaseType"]),(3999,"FIRST"))
        with self.assertRaises(BuyerError):
            self.payments.create_checkout(self.user, {"plan":"monthly", "method":"airwallex_alipay", "autoRenew":False})
        raw, headers = self.stripe_event(order)
        self.payments.webhook("stripe", raw, headers)
        self.assertEqual(self.payments.webhook("stripe", raw, headers), {"duplicate":True})
        self.assertEqual({k:v["dueMinor"] for k,v in self.payments.pricing(self.user)["plans"].items()},
                         {"monthly":1990,"quarterly":2999,"annual":9999})
        renewal = self.payments.create_checkout(self.user, {"plan":"monthly", "method":"stripe_card", "autoRenew":False})
        self.assertEqual((renewal["amountMinor"],renewal["purchaseType"]),(1990,"RENEWAL"))
        raw, headers = self.stripe_event(renewal, event_id="evt_renewal")
        self.payments.webhook("stripe", raw, headers)
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM buyer_memberships WHERE user_id='buyer'").fetchone()[0],2)
            self.assertEqual(db.execute("SELECT count(*) FROM membership_intro_uses WHERE user_id='buyer'").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM buyer_membership_payments WHERE user_id='buyer'").fetchone()[0],2)

    def test_stripe_webhook_signature_amount_and_account_fail_closed(self):
        order = self.payments.create_checkout(self.user, {"plan":"monthly", "method":"stripe_card", "autoRenew":False})
        raw, headers = self.stripe_event(order)
        with self.assertRaises(BuyerError):self.payments.webhook("stripe", raw, {"Stripe-Signature":"bad"})
        with self.assertRaises(BuyerError):self.payments.webhook("stripe", *self.stripe_event(order,amount=200))
        event=json.loads(raw);event["account"]="wrong"
        wrong=json.dumps(event).encode();stamp=str(int(time.time()))
        sig=hmac.new(b"whsec_isolated",stamp.encode()+b"."+wrong,hashlib.sha256).hexdigest()
        with self.assertRaises(BuyerError):self.payments.webhook("stripe",wrong,{"Stripe-Signature":"t="+stamp+",v1="+sig})
        for payload in ([], {"id":"evt_missing_mode", "type":"checkout.session.completed", "data":{"object":{}}}):
            invalid=json.dumps(payload).encode()
            sig=hmac.new(b"whsec_isolated",stamp.encode()+b"."+invalid,hashlib.sha256).hexdigest()
            with self.assertRaises(BuyerError):
                self.payments.webhook("stripe",invalid,{"Stripe-Signature":"t="+stamp+",v1="+sig})
        self.payments.webhook("stripe",raw,headers)
        with self.auth.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM buyer_memberships").fetchone()[0],1)

    def test_stripe_checkout_rejects_wrong_environment_and_host(self):
        order={"provider":"stripe", "amount_minor":199, "id":"order-test", "plan":"monthly", "expires_at":int(time.time())+3600}
        gateway=PaymentGateway()
        valid={"id":"cs_test_abc", "url":"https://checkout.stripe.com/test/cs_test_abc",
               "livemode":False,"mode":"payment","client_reference_id":"order-test",
               "metadata":{"autolink_order_id":"order-test"},"amount_total":199,"currency":"usd",
               "payment_method_configuration_details":{"id":"pmc_isolated"},
               "payment_method_types":["card"]}
        for response in (
            {**valid,"livemode":True},
            {**valid,"url":"https://checkout.evil.example/test/cs_test_abc"},
            {**valid,"amount_total":200},
            {**valid,"id":"cs_live_abc"},
            {**valid,"metadata":None},
            {**valid,"payment_method_configuration_details":{"id":"pmc_other"}},
            {**valid,"payment_method_types":["card","alipay"]},
        ):
            with patch.object(gateway,"verify_account"), patch.object(gateway,"stripe",return_value=response):
                with self.assertRaises(GatewayError):gateway.checkout(order,"buyer@example.test")
        with patch.object(gateway,"verify_account"), patch.object(gateway,"stripe",return_value=valid) as request:
            gateway.checkout(order,"buyer@example.test")
            self.assertEqual(request.call_args.args[1]["payment_method_configuration"], "pmc_isolated")
            self.assertNotIn("payment_method_types[0]", request.call_args.args[1])

    def test_stripe_account_preflight_blocks_wrong_merchant(self):
        gateway=PaymentGateway()
        with patch.object(gateway,"stripe_get",return_value={"id":"acct_other"}):
            with self.assertRaises(GatewayError):gateway.verify_account()
        with patch.object(gateway,"stripe_get",return_value={"id":"acct_isolated"}):
            gateway.verify_account()

    def test_restricted_test_key_can_be_used_without_accepting_live_key(self):
        with patch.dict(os.environ,{"STRIPE_SECRET_KEY":"rk_test_isolated"}):
            self.assertTrue(self.payments.enabled("stripe_card"))
        with patch.dict(os.environ,{"STRIPE_SECRET_KEY":"rk_live_isolated"}):
            self.assertFalse(self.payments.enabled("stripe_card"))

    def test_calendar_months_preserve_month_end_in_utc(self):
        stamp=lambda y,m,d:int(datetime(y,m,d,12,tzinfo=timezone.utc).timestamp())
        self.assertEqual(add_months(stamp(2024,1,31),1),stamp(2024,2,29))
        self.assertEqual(add_months(stamp(2024,2,29),1),stamp(2024,3,31))
        self.assertEqual(add_months(stamp(2023,1,31),1),stamp(2023,2,28))
        self.assertEqual(add_months(stamp(2023,12,31),12),stamp(2024,12,31))

    def test_reconcile_lost_webhook_and_idempotent_late_event(self):
        checkout=self.payments.create_checkout(self.user,{"plan":"quarterly","method":"stripe_card","autoRenew":False})
        ref="cs_"+checkout["orderId"]
        self.gateway.sessions[ref].update(status="complete",payment_status="paid",payment_intent="pi_"+checkout["orderId"])
        self.assertEqual(self.payments.reconcile_order(checkout["orderId"])["status"],"PAID")
        self.assertTrue(self.payments.reconcile_order(checkout["orderId"])["alreadyProcessed"])
        self.assertEqual(self.payments.webhook("stripe",*self.stripe_event(checkout)),{"duplicate":True})
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM buyer_memberships WHERE user_id='buyer'").fetchone()[0],1)

    def test_reconcile_rejects_provider_amount_mismatch(self):
        checkout=self.payments.create_checkout(self.user,{"plan":"monthly","method":"stripe_card","autoRenew":False})
        ref="cs_"+checkout["orderId"]
        self.gateway.sessions[ref].update(status="complete",payment_status="paid",
                                          payment_intent="pi_"+checkout["orderId"],amount_total=200)
        with self.assertRaises(BuyerError) as error:self.payments.reconcile_order(checkout["orderId"])
        self.assertEqual(error.exception.status,409)
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM buyer_memberships WHERE user_id='buyer'").fetchone()[0],0)

    def test_timeout_recovery_uses_same_order_and_expired_checkout_releases_slot(self):
        self.gateway.fail_after_create=True
        with self.assertRaises(BuyerError):
            self.payments.create_checkout(self.user,{"plan":"monthly","method":"stripe_card","autoRenew":False})
        with self.auth.connect() as db:
            order=db.execute("SELECT * FROM membership_orders WHERE user_id='buyer'").fetchone()
            self.assertEqual(order["status"],"UNKNOWN")
            order_id=order["id"]
        self.assertTrue(self.payments.reconcile_order(order_id)["manualReview"])
        self.assertEqual(self.payments.reconcile_order(order_id,recover_unknown=True)["status"],"PENDING")
        ref="cs_"+order_id
        self.gateway.sessions[ref].update(status="expired",payment_status="unpaid")
        self.assertEqual(self.payments.reconcile_order(order_id)["status"],"EXPIRED")
        another=self.payments.create_checkout(self.user,{"plan":"annual","method":"stripe_card","autoRenew":False})
        self.assertEqual((another["amountMinor"],another["purchaseType"]),(3999,"FIRST"))

    def test_operator_reconciliation_requires_explicit_matching_confirmation(self):
        checkout=self.payments.create_checkout(self.user,{"plan":"monthly","method":"stripe_card","autoRenew":False})
        env={"AUTH_DB_PATH":str(Path(self.temp.name)/"auth.db")}
        with patch.dict(os.environ,env), patch("sys.argv",["reconcile_membership.py","--order-id",checkout["orderId"]]):
            output=io.StringIO()
            with redirect_stdout(output):reconcile_main()
        self.assertEqual(json.loads(output.getvalue())["status"],"PENDING")
        with patch.dict(os.environ,env), patch("sys.argv",["reconcile_membership.py","--order-id",checkout["orderId"],
                "--apply","--environment","sandbox","--confirm-order","wrong"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:reconcile_main()
        self.assertEqual(error.exception.code,2)
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM membership_orders WHERE id=?",(checkout["orderId"],)).fetchone()[0],"PENDING")

    def test_early_renewal_and_refund_preserve_other_paid_period(self):
        first=self.payments.create_checkout(self.user,{"plan":"monthly","method":"stripe_card","autoRenew":False})
        self.payments.webhook("stripe",*self.stripe_event(first))
        renewal=self.payments.create_checkout(self.user,{"plan":"quarterly","method":"stripe_card","autoRenew":False})
        self.payments.webhook("stripe",*self.stripe_event(renewal,event_id="evt_renewal"))
        with self.auth.connect() as db:
            rows=db.execute("SELECT start_at,end_at FROM buyer_memberships WHERE user_id='buyer' ORDER BY start_at").fetchall()
            self.assertEqual(rows[1]["start_at"],rows[0]["end_at"])
            self.assertEqual(BuyerService.membership(db,"buyer")["endAt"],rows[1]["end_at"])
        refund={"id":"evt_refund_renewal","type":"charge.refunded","livemode":False,
                "data":{"object":{"payment_intent":"pi_"+renewal["orderId"],"currency":"usd","amount_refunded":2999}}}
        raw=json.dumps(refund).encode();stamp=str(int(time.time()))
        sig=hmac.new(b"whsec_isolated",stamp.encode()+b"."+raw,hashlib.sha256).hexdigest()
        self.payments.webhook("stripe",raw,{"Stripe-Signature":"t="+stamp+",v1="+sig})
        self.assertEqual(self.payments.reconcile_order(renewal["orderId"])["refundStatus"],"FULL")
        self.assertTrue(self.payments.reconcile_order(renewal["orderId"])["manualReview"])
        with self.auth.connect() as db:
            self.assertEqual(BuyerService.membership(db,"buyer")["status"],"ACTIVE")
            self.assertEqual(BuyerService.membership(db,"buyer")["endAt"],rows[0]["end_at"])

    def test_auto_renewal_and_disabled_provider_are_rejected(self):
        with self.assertRaises(BuyerError) as error:
            self.payments.create_checkout(self.user,{"plan":"monthly","method":"stripe_card","autoRenew":True})
        self.assertEqual(error.exception.status,409)
        with patch.dict(os.environ,{"STRIPE_CARD_ENABLED":"false"}):
            with self.assertRaises(BuyerError) as error:
                self.payments.create_checkout(self.user,{"plan":"monthly","method":"stripe_card","autoRenew":False})
            self.assertEqual(error.exception.status,503)
        with self.auth.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM membership_orders").fetchone()[0],0)

    def test_full_refund_revokes_its_entitlement_and_preserves_intro_history(self):
        checkout=self.payments.create_checkout(self.user,{"plan":"monthly","method":"stripe_card","autoRenew":False})
        self.payments.webhook("stripe",*self.stripe_event(checkout))
        obj={"payment_intent":"pi_"+checkout["orderId"],"currency":"usd","amount_refunded":199}
        event={"id":"evt_refund","type":"charge.refunded","livemode":False,"data":{"object":obj}}
        raw=json.dumps(event).encode();stamp=str(int(time.time()))
        sig=hmac.new(b"whsec_isolated",stamp.encode()+b"."+raw,hashlib.sha256).hexdigest()
        self.payments.webhook("stripe",raw,{"Stripe-Signature":"t="+stamp+",v1="+sig})
        event["id"]="evt_refund_delayed_partial"
        event["data"]["object"]["amount_refunded"]=100
        delayed=json.dumps(event).encode()
        delayed_sig=hmac.new(b"whsec_isolated",stamp.encode()+b"."+delayed,hashlib.sha256).hexdigest()
        self.payments.webhook("stripe",delayed,{"Stripe-Signature":"t="+stamp+",v1="+delayed_sig})
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM buyer_memberships WHERE user_id='buyer'").fetchone()[0],"REFUNDED")
            self.assertEqual(db.execute("SELECT status FROM buyer_membership_payments WHERE user_id='buyer'").fetchone()[0],"REFUNDED")
            self.assertEqual(db.execute("SELECT refund_status FROM membership_orders WHERE id=?",(checkout["orderId"],)).fetchone()[0],"FULL")
        self.assertFalse(self.payments.pricing(self.user)["firstPurchaseEligible"])

    def test_out_of_order_refund_waits_for_verified_payment_then_revokes_once(self):
        checkout=self.payments.create_checkout(self.user,{"plan":"monthly","method":"stripe_card","autoRenew":False})
        event={"id":"evt_refund_before_payment","type":"charge.refunded","livemode":False,
               "data":{"object":{"payment_intent":"pi_"+checkout["orderId"],"currency":"usd","amount_refunded":199}}}
        raw=json.dumps(event).encode();stamp=str(int(time.time()))
        sig=hmac.new(b"whsec_isolated",stamp.encode()+b"."+raw,hashlib.sha256).hexdigest()
        headers={"Stripe-Signature":"t="+stamp+",v1="+sig}
        with self.assertRaises(BuyerError):self.payments.webhook("stripe",raw,headers)
        self.payments.webhook("stripe",*self.stripe_event(checkout))
        self.assertEqual(self.payments.webhook("stripe",raw,headers),{"recorded":True})
        self.assertEqual(self.payments.webhook("stripe",raw,headers),{"duplicate":True})
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM buyer_memberships WHERE user_id='buyer'").fetchone()[0],"REFUNDED")

    def test_airwallex_extension_is_reserved_and_fail_closed(self):
        self.assertFalse(self.payments.pricing(self.user)["methods"]["airwallex_alipay"]["available"])
        self.assertFalse(self.payments.pricing(self.user)["methods"]["airwallex_wechat"]["available"])
        with patch.dict(os.environ, {"AIRWALLEX_ALIPAY_ENABLED":"true", "AIRWALLEX_CHECKOUT_APPROVED":"true"}):
            with self.assertRaises(BuyerError) as error:
                self.payments.create_checkout(self.user, {"plan":"monthly", "method":"airwallex_alipay", "autoRenew":False})
            self.assertEqual(error.exception.status, 503)
        with self.assertRaises(BuyerError) as error:
            self.payments.webhook("airwallex", b"{}", {})
        self.assertEqual(error.exception.status, 503)

    def test_http_auth_csrf_and_verified_webhook_only(self):
        class PaymentHandler(Handler):
            pass
        PaymentHandler.service=self.auth
        PaymentHandler.buyer=BuyerService(self.auth)
        PaymentHandler.payments=self.payments
        server=ThreadingHTTPServer(("127.0.0.1",0),PaymentHandler)
        Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base="http://127.0.0.1:"+str(server.server_port)
        token=self.auth.session_for_user("buyer")["access_token"]
        def call(path,method="GET",body=None,cookie=True,headers=None):
            values={"Cookie":"autolink_session="+token} if cookie else {}
            if body is not None:values["Content-Type"]="application/json"
            values.update(headers or {})
            request=Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                            headers=values,method=method)
            try: response=urlopen(request)
            except HTTPError as exc: response=exc
            with response:return response.status,json.loads(response.read())
        self.assertEqual(call("/autolink/buyer/membership",cookie=False)[0],401)
        status,result=call("/autolink/buyer/membership")
        self.assertEqual(status,200)
        self.assertEqual(result["data"]["pricing"]["plans"]["annual"]["dueMinor"],3999)
        self.assertEqual(call("/autolink/buyer/membership/checkout","POST",
                              {"plan":"annual","method":"stripe_card","autoRenew":False},cookie=False)[0],401)
        self.assertEqual(call("/autolink/buyer/membership/checkout","POST",
                              {"plan":"annual","method":"stripe_card","autoRenew":False},
                              headers={"Origin":"https://evil.example"})[0],403)
        status,result=call("/autolink/buyer/membership/checkout","POST",
                           {"plan":"annual","method":"stripe_card","autoRenew":False})
        self.assertEqual(status,200)
        order=result["data"]
        self.assertEqual(order["amountMinor"],3999)
        self.assertEqual(call("/autolink/buyer/membership")[1]["data"]["membership"]["status"],"FREE")
        raw,headers=self.stripe_event(order)
        request=Request(base+"/autolink/payments/webhooks/stripe",data=raw,headers={
            "Content-Type":"application/json","Stripe-Signature":"bad"},method="POST")
        with self.assertRaises(HTTPError) as failed:urlopen(request)
        self.assertEqual(failed.exception.code,400)
        request=Request(base+"/autolink/payments/webhooks/stripe",data=raw,headers={
            "Content-Type":"application/json",**headers},method="POST")
        with urlopen(request) as response:self.assertEqual(response.status,200)
        self.assertEqual(call("/autolink/buyer/membership")[1]["data"]["membership"]["status"],"ACTIVE")


if __name__ == "__main__":
    unittest.main()
