"""Isolated membership payment tests: provider calls are never sent over network."""

import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from app import AuthService, Handler
from buyer_service import BuyerError, BuyerService
from membership_payments import MembershipPaymentService


class FakeGateway:
    def __init__(self):
        self.sessions = {}

    def checkout(self, order, email):
        provider = order["provider"]
        ref = ("cs_" if provider == "stripe" else "bco_") + order["id"]
        host = "checkout.stripe.com" if provider == "stripe" else "checkout.airwallex.com"
        self.sessions[ref] = order
        return ref, "https://" + host + "/test/" + ref

    def airwallex_checkout(self, path, payload=None):
        ref = path.rsplit("/", 1)[1]
        order = self.sessions[ref]
        method = "alipaycn" if order["method"] == "airwallex_alipay" else "wechatpay"
        return {"id": ref, "account_id": "acct_test", "status": "COMPLETED", "mode": "PAYMENT",
                "payment_intent_id": "int_" + order["id"], "metadata": {"autolink_order_id": order["id"]},
                "payment_options": {"payment_method_types": [method]}, "currency": "USD"}


class MembershipPaymentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"PAYMENTS_ENV": "sandbox", "STRIPE_CARD_ENABLED": "true",
            "STRIPE_SECRET_KEY": "sk_test_isolated", "STRIPE_WEBHOOK_SECRET": "whsec_isolated",
            "AIRWALLEX_CHECKOUT_APPROVED": "true", "AIRWALLEX_ALIPAY_ENABLED": "true",
            "AIRWALLEX_WECHAT_ENABLED": "true", "AIRWALLEX_CLIENT_ID": "isolated",
            "AIRWALLEX_API_KEY": "isolated", "AIRWALLEX_WEBHOOK_SECRET": "airwallex-isolated",
            "AIRWALLEX_ACCOUNT_ID": "acct_test"})
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

    def airwallex_event(self, checkout, *, amount=None, method="alipaycn", event_id="aw_evt_1"):
        order_id = checkout["orderId"]
        event = {"id": event_id, "name": "payment_intent.succeeded", "accountId": "acct_test",
                 "data": {"object": {"id": "int_" + order_id, "merchant_order_id": order_id,
                     "amount": str(checkout["amountMinor"] / 100) if amount is None else amount,
                     "currency": "USD", "status": "SUCCEEDED", "payment_method": {"type": method}}}}
        raw = json.dumps(event).encode()
        stamp = str(int(time.time() * 1000))
        signature = hmac.new(b"airwallex-isolated", stamp.encode() + raw, hashlib.sha256).hexdigest()
        return raw, {"x-timestamp": stamp, "x-signature": signature}

    def test_prices_first_purchase_once_across_plan_and_provider(self):
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
        renewal = self.payments.create_checkout(self.user, {"plan":"monthly", "method":"airwallex_alipay", "autoRenew":False})
        self.assertEqual((renewal["amountMinor"],renewal["purchaseType"]),(1990,"RENEWAL"))
        raw, headers = self.airwallex_event(renewal)
        self.payments.webhook("airwallex", raw, headers)
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM buyer_memberships WHERE user_id='buyer'").fetchone()[0],2)
            self.assertEqual(db.execute("SELECT count(*) FROM membership_intro_uses WHERE user_id='buyer'").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM buyer_membership_payments WHERE user_id='buyer'").fetchone()[0],2)

    def test_webhook_signature_amount_method_and_account_fail_closed(self):
        order = self.payments.create_checkout(self.user, {"plan":"monthly", "method":"airwallex_wechat", "autoRenew":False})
        raw, headers = self.airwallex_event(order, method="wechatpay")
        with self.assertRaises(BuyerError):self.payments.webhook("airwallex", raw, {**headers,"x-signature":"bad"})
        with self.assertRaises(BuyerError):self.payments.webhook("airwallex", *self.airwallex_event(order,amount="2.00",method="wechatpay"))
        with self.assertRaises(BuyerError):self.payments.webhook("airwallex", *self.airwallex_event(order,method="alipaycn"))
        event=json.loads(raw);event["accountId"]="wrong"
        wrong=json.dumps(event).encode();stamp=headers["x-timestamp"]
        sig=hmac.new(b"airwallex-isolated",stamp.encode()+wrong,hashlib.sha256).hexdigest()
        with self.assertRaises(BuyerError):self.payments.webhook("airwallex",wrong,{"x-timestamp":stamp,"x-signature":sig})
        self.payments.webhook("airwallex",raw,headers)
        with self.auth.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM buyer_memberships").fetchone()[0],1)

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
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM buyer_memberships WHERE user_id='buyer'").fetchone()[0],"REFUNDED")
            self.assertEqual(db.execute("SELECT status FROM buyer_membership_payments WHERE user_id='buyer'").fetchone()[0],"REFUNDED")
        self.assertFalse(self.payments.pricing(self.user)["firstPurchaseEligible"])

    def test_airwallex_refund_acceptance_does_not_revoke_until_settled(self):
        checkout = self.payments.create_checkout(self.user, {"plan": "monthly", "method": "airwallex_alipay", "autoRenew": False})
        self.payments.webhook("airwallex", *self.airwallex_event(checkout))
        for event_id, name in (("refund_accepted", "refund.accepted"), ("refund_settled", "refund.settled")):
            event = {"id": event_id, "name": name, "accountId": "acct_test",
                     "data": {"object": {"payment_intent_id": "int_" + checkout["orderId"],
                                         "amount": "1.99", "currency": "USD"}}}
            raw = json.dumps(event).encode()
            stamp = str(int(time.time() * 1000))
            signature = hmac.new(b"airwallex-isolated", stamp.encode() + raw, hashlib.sha256).hexdigest()
            self.payments.webhook("airwallex", raw, {"x-timestamp": stamp, "x-signature": signature})
            with self.auth.connect() as db:
                status = db.execute("SELECT status FROM buyer_memberships WHERE user_id='buyer'").fetchone()[0]
                expected = "ACTIVE" if name == "refund.accepted" else "REFUNDED"
                self.assertEqual(status, expected)

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
