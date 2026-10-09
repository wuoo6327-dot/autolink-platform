"""Delivery uses fake senders only; checks the real transaction and identity boundaries."""
import io
import json
import threading
import time
import unittest
from datetime import date
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer
import urllib.request
import urllib.error

import test_trade
from app import Handler
from business_mail import BusinessMailer, TEMPLATES, render
from mail_service import MailUnavailable, send_message, send_verification
from platform_service import PlatformService
from mail_templates import RESOURCES, SUPPORTED_LANGUAGES, verification_message

class BusinessMailTests(unittest.TestCase):
    setUp=test_trade.TradeFlowTests.setUp
    approved_vehicle=test_trade.TradeFlowTests.approved_vehicle

    def jobs(self):
        with self.auth.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM business_mail_jobs ORDER BY created_at,id')]

    def welcome(self, user='buyer-a', key='welcome-qa'):
        with self.auth.connect() as db:return BusinessMailer.enqueue(db,user,'WELCOME',user,'/buyer',key)

    def test_recipient_language_is_used_and_retry_payload_remains_immutable(self):
        with self.auth.connect() as db:db.execute("UPDATE users SET preferred_language='ar' WHERE id='buyer-a'")
        self.welcome()
        sender=Mock(side_effect=MailUnavailable('mock failure'))
        mailer=BusinessMailer(self.auth,sender=sender)
        self.assertEqual(mailer.process_once(),0)
        first=sender.call_args
        self.assertIn('dir="rtl"', first.args[3])
        self.assertEqual(first.args[1], 'AUTOLINK · '+RESOURCES['ar']['events']['WELCOME'][0])
        with self.auth.connect() as db:
            db.execute("UPDATE users SET preferred_language='fr' WHERE id='buyer-a'")
            db.execute('UPDATE business_mail_jobs SET next_attempt_at=0')
        sender.side_effect=None;sender.return_value='qa-accepted'
        self.assertEqual(mailer.process_once(),1)
        self.assertEqual(sender.call_args,first)
        self.welcome(key='next-language')
        self.assertEqual(mailer.process_once(),1)
        self.assertEqual(sender.call_args.args[1], 'AUTOLINK · '+RESOURCES['fr']['events']['WELCOME'][0])
        self.assertNotIn('buyer-b@example.com',str(sender.call_args_list))

    def test_nine_language_templates_are_complete_and_security_codes_are_ascii(self):
        self.assertEqual(set(RESOURCES),set(SUPPORTED_LANGUAGES))
        for language in SUPPORTED_LANGUAGES:
            labels=RESOURCES[language]
            self.assertEqual(set(labels['events']),set(TEMPLATES))
            for event in TEMPLATES:
                title,text=labels['events'][event]
                self.assertTrue(title and text)
                subject,plain,content=render(event,'/buyer/notifications',language)
                self.assertEqual(subject,'AUTOLINK · '+title)
                self.assertIn(text,plain);self.assertIn(labels['footer'],plain)
                self.assertIn('dir="'+('rtl' if language=='ar' else 'ltr')+'"',content)
                if language!='en':self.assertNotEqual(title,TEMPLATES[event][0])
            for purpose in ('login','reset_password'):
                subject,plain,content=verification_message('012345',purpose,language)
                self.assertIn('012345',plain);self.assertIn(labels['expires'],plain)
                self.assertIn(labels['ignore'],plain);self.assertIn('dir="ltr"',content);self.assertIn('charset="utf-8"',content)
                self.assertIn(labels['verification' if purpose=='login' else 'reset'],subject)
        self.assertEqual(render('WELCOME','/buyer','bad'),render('WELCOME','/buyer','en'))
        self.assertEqual(render('WELCOME','/buyer','zh-CN'),render('WELCOME','/buyer','zh'))
        for code,purpose in [('１２３４５６','login'),('12345','login'),('<img>','login'),('123456','change_email')]:
            with self.assertRaises(ValueError):verification_message(code,purpose,'en')

    def trade_quote(self):
        listing=self.approved_vehicle()
        inquiry=self.trade.create_inquiry(self.users['buyer-a'],{'listingId':listing,'quantity':2,'destinationCountry':'Saudi Arabia'})
        quote=self.trade.create_quote(self.users['supplier-a'],inquiry['id'],{'unitPriceMinor':1850000,'quantity':2,'validUntil':str(date.today().replace(year=date.today().year+1)),'send':True})
        return inquiry,quote

    def test_real_inquiry_quote_review_and_welcome_are_queued_and_delivered_to_owners(self):
        inquiry,quote=self.trade_quote();self.welcome()
        sender=Mock(return_value='qa-provider-accepted')
        mailer=BusinessMailer(self.auth,sender=sender)
        self.assertEqual(mailer.process_once(limit=20),5)
        self.assertEqual({j['event'] for j in self.jobs()},{'SUPPLIER_APPROVED','VEHICLE_APPROVED','NEW_INQUIRY','NEW_QUOTE','WELCOME'})
        self.assertTrue(all(j['status']=='SENT' and j['payload'] is None for j in self.jobs()))
        destinations=[c.args[0] for c in sender.call_args_list]
        self.assertEqual(destinations.count('supplier-a@example.com'),3)
        self.assertEqual(destinations.count('buyer-a@example.com'),2)
        self.assertNotIn('buyer-b@example.com',destinations)
        for call in sender.call_args_list:
            self.assertTrue(call.kwargs['idempotency_key'].startswith('business/MAIL-'))
            self.assertNotIn('1850000',call.args[2])
            self.assertNotIn('Saudi Arabia',call.args[2])
        self.assertEqual(mailer.process_once(),0)
        self.assertEqual(self.trade.buyer_inquiry(self.users['buyer-a'],inquiry['id'])['status'],'QUOTED')
        self.assertEqual(self.trade.quote_rows(self.users['buyer-a'])[0]['id'],quote['id'])

    def test_rollback_and_deduplication_do_not_emit_extra_mail(self):
        with self.assertRaises(RuntimeError):
            with self.auth.connect() as db:
                PlatformService.notify(db,'buyer-a','WELCOME','buyer-a','/buyer')
                raise RuntimeError('Rollback QA only')
        self.assertEqual(self.jobs(),[])
        self.welcome();self.welcome()
        self.assertEqual(len(self.jobs()),1)
        self.assertIsNone(self.auth.mailer.thread)

    def test_failed_sender_retries_same_payload_and_key_without_losing_inquiry(self):
        inquiry,quote=self.trade_quote()
        sender=Mock(side_effect=MailUnavailable('PRIVATE_TEST_VALUE'))
        mailer=BusinessMailer(self.auth,sender=sender)
        mailer.process_once(limit=20)
        self.assertTrue(all(j['status']=='PENDING' and j['last_error']=='DELIVERY_UNAVAILABLE' for j in self.jobs()))
        self.assertNotIn('PRIVATE_TEST_VALUE',json.dumps(self.jobs()))
        self.assertEqual(self.trade.quote_rows(self.users['buyer-a'])[0]['id'],quote['id'])
        first={call.kwargs['idempotency_key']:call.args for call in sender.call_args_list}
        with self.auth.connect() as db:db.execute('UPDATE business_mail_jobs SET next_attempt_at=0')
        sender.side_effect=None;sender.return_value='qa-accepted'
        self.assertEqual(mailer.process_once(limit=20),4)
        for call in sender.call_args_list[4:]:self.assertEqual(call.args,first[call.kwargs['idempotency_key']])
        self.assertTrue(all(j['attempt_count']==2 for j in self.jobs()))
        self.assertEqual(self.trade.buyer_inquiry(self.users['buyer-a'],inquiry['id'])['status'],'QUOTED')

    def test_foreign_quote_suspended_recipient_and_changed_email_cancel_delivery(self):
        _,quote=self.trade_quote()
        with self.auth.connect() as db:
            BusinessMailer.enqueue(db,'buyer-b','NEW_QUOTE',quote['id'],'/buyer/quotes/'+quote['id'],'foreign-quote')
            db.execute("UPDATE users SET status='SUSPENDED' WHERE id='supplier-a'")
        sender=Mock(return_value='qa-accepted');mailer=BusinessMailer(self.auth,sender=sender)
        self.assertEqual(mailer.process_once(limit=20),1)
        self.assertEqual([c.args[0] for c in sender.call_args_list],['buyer-a@example.com'])
        self.assertEqual(next(j for j in self.jobs() if j['dedupe_key']=='foreign-quote')['status'],'CANCELLED')
        self.welcome('buyer-b','changed-email')
        failed=BusinessMailer(self.auth,sender=Mock(side_effect=MailUnavailable('QA failure')));failed.process_once()
        with self.auth.connect() as db:
            db.execute("UPDATE users SET email='changed@example.com' WHERE id='buyer-b'")
            db.execute("UPDATE business_mail_jobs SET next_attempt_at=0 WHERE dedupe_key='changed-email'")
        mailer.process_once()
        self.assertEqual(next(j for j in self.jobs() if j['dedupe_key']=='changed-email')['last_error'],'RECIPIENT_CHANGED')

    def test_claim_leases_retry_window_and_attempt_limit(self):
        self.welcome();mailer=BusinessMailer(self.auth,sender=Mock(return_value='qa-accepted'))
        claim=mailer.claim();self.assertEqual(claim['attempt_count'],1)
        self.assertIsNone(mailer.claim())
        with self.auth.connect() as db:db.execute('UPDATE business_mail_jobs SET lease_until=0')
        recovered=mailer.claim();self.assertEqual(recovered['id'],claim['id']);self.assertEqual(recovered['payload'],claim['payload'])
        with self.auth.connect() as db:db.execute('UPDATE business_mail_jobs SET lease_until=0,attempt_count=5')
        self.assertIsNone(mailer.claim());self.assertEqual(self.jobs()[0]['last_error'],'ATTEMPT_LIMIT')
        self.welcome(key='window-expired')
        with self.auth.connect() as db:db.execute("UPDATE business_mail_jobs SET first_attempt_at=? WHERE dedupe_key='window-expired'",(int(time.time())-24*3600,))
        self.assertIsNone(mailer.claim());self.assertEqual(next(j for j in self.jobs() if j['dedupe_key']=='window-expired')['last_error'],'RETRY_WINDOW_EXPIRED')

    def test_per_recipient_hourly_limit_and_unconfigured_sender_preserves_queue(self):
        for i in range(21):self.welcome(key='rate-'+str(i))
        sender=Mock(return_value='qa-accepted');mailer=BusinessMailer(self.auth,sender=sender)
        self.assertEqual(mailer.process_once(limit=20),20)
        self.assertEqual(mailer.process_once(),0)
        self.assertEqual(sender.call_count,20)
        pending=next(j for j in self.jobs() if j['status']=='PENDING')
        self.assertGreater(pending['next_attempt_at'],int(time.time()))
        with patch.dict('os.environ',{},clear=True):self.assertEqual(self.auth.mailer.process_once(),0)
        self.assertEqual(next(j for j in self.jobs() if j['status']=='PENDING')['attempt_count'],0)

    def test_membership_expiry_is_single_notification_and_preserves_account(self):
        now=int(time.time())
        with self.auth.connect() as db:db.execute("INSERT INTO buyer_memberships VALUES ('qa-membership','buyer-a','monthly','ACTIVE',?,?,0)",(now-4000000,now-10))
        mailer=BusinessMailer(self.auth,sender=Mock(return_value='qa-accepted'))
        mailer.queue_membership_expiry();mailer.queue_membership_expiry()
        self.assertEqual(len(self.jobs()),1);self.assertEqual(mailer.process_once(),1)
        self.assertIn('does not automatically charge',mailer.sender.call_args.args[2])
        with self.auth.connect() as db:self.assertEqual(db.execute("SELECT status FROM users WHERE id='buyer-a'").fetchone()[0],'ACTIVE')

    def test_team_invitation_and_revoked_sales_notifications_are_scoped(self):
        self.approved_vehicle();owner=self.users['supplier-a'];recipient=self.users['buyer-b']
        invite=self.trade.team.invite(owner,{'email':recipient['email']})
        sender=Mock(return_value='qa-accepted');mailer=BusinessMailer(self.auth,sender=sender)
        self.assertEqual(mailer.process_once(limit=20),3)
        self.assertTrue(any(c.args[0]=='buyer-b@example.com' and 'invitation' in c.args[1] for c in sender.call_args_list))
        self.trade.team.accept(recipient,invite['id'])
        self.assertEqual(mailer.process_once(limit=20),1)
        with self.auth.connect() as db:
            BusinessMailer.enqueue(db,'buyer-b','BUYER_ASSIGNED','buyer-a','/supplier/buyers/buyer-a','revoked-sales')
        self.trade.team.remove(owner,'buyer-b')
        self.assertEqual(mailer.process_once(limit=20),0)
        self.assertEqual(next(j for j in self.jobs() if j['dedupe_key']=='revoked-sales')['status'],'CANCELLED')

    def test_templates_are_safe_and_admin_status_exposes_no_recipient_or_payload(self):
        required={'WELCOME','NEW_INQUIRY','NEW_QUOTE','SUPPLIER_APPROVED','SUPPLIER_REJECTED','VEHICLE_APPROVED','VEHICLE_REJECTED','MEMBERSHIP_EXPIRY'}
        self.assertTrue(required<=set(TEMPLATES))
        for event in TEMPLATES:
            subject,plain,content=render(event,'/buyer/notifications')
            self.assertIn('AUTOLINK',subject);self.assertIn('https://autolinkglobal.com',plain);self.assertNotIn('<script>',content)
        for path in ['//attacker.example','/buyer/../../private','/buyer\\evil','/supplier-terms']:
            with self.assertRaises(ValueError):render('WELCOME',path)
        self.welcome();mailer=BusinessMailer(self.auth,sender=Mock(return_value='qa-accepted'));mailer.process_once()
        data=mailer.status();self.assertEqual(data['counts']['SENT'],1)
        self.assertNotIn('buyer-a@example.com',json.dumps(data));self.assertNotIn('payload',json.dumps(data))
        class TestHandler(Handler):pass
        TestHandler.service=self.auth;TestHandler.trade=self.trade;TestHandler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler);threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        for account,expected in [('buyer-a',403),('supplier-a',403),('admin',200)]:
            token=self.auth.session_for_user(account)['access_token'];request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/autolink/admin/email',headers={'Cookie':'autolink_session='+token})
            try:response=urllib.request.urlopen(request)
            except urllib.error.HTTPError as error:response=error
            with response:self.assertEqual(response.status,expected)

class MailTransportTests(unittest.TestCase):
    settings={'MAIL_PROVIDER':'resend','RESEND_API_KEY':'qa-not-a-real-key','MAIL_FROM':'AUTOLINK <no-reply@autolinkglobal.com>'}

    def test_resend_http_uses_idempotency_header_without_external_request(self):
        with patch.dict('os.environ',self.settings,clear=True),patch('mail_service.urlopen',return_value=io.StringIO('{"id":"qa-provider-id"}')) as mocked:
            self.assertEqual(send_message('qa@example.com','QA subject','QA body','<p>QA body</p>',idempotency_key='business/qa-id'),'qa-provider-id')
            request=mocked.call_args.args[0]
            self.assertEqual({k.lower():v for k,v in request.header_items()}['idempotency-key'],'business/qa-id')
            self.assertEqual(json.loads(request.data)['to'],['qa@example.com'])

    def test_resend_smtp_uses_idempotency_header_and_security_templates_share_transport(self):
        settings={**self.settings,'MAIL_PROVIDER':'resend_smtp'}
        with patch.dict('os.environ',settings,clear=True),patch('mail_service.smtplib.SMTP_SSL') as mocked:
            client=mocked.return_value.__enter__.return_value
            self.assertEqual(send_message('qa@example.com','QA','body','<p>body</p>',idempotency_key='business/qa-id'),'smtp-accepted')
            self.assertEqual(client.send_message.call_args.args[0]['Resend-Idempotency-Key'],'business/qa-id')
        with patch.dict('os.environ',self.settings,clear=True),patch('mail_service.send_message',return_value='qa-accepted') as mocked:
            send_verification('qa@example.com','123456','login');self.assertIn('123456',mocked.call_args.args[2])
            send_verification('qa@example.com','654321','reset_password');self.assertIn('Password Reset',mocked.call_args.args[2])

if __name__=='__main__':unittest.main()
