"""End-to-end service checks for the real buyer → supplier → buyer loop."""

import tempfile
import time
import unittest
import base64
import io
import hashlib
from PIL import Image
import image_service
import json
import threading
from unittest.mock import patch
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from app import Handler
from datetime import date
from pathlib import Path

from app import AuthService
from buyer_service import BuyerError, BuyerService
from email_auth import EmailAuthService
from trade_service import TradeService
from business_mail import BusinessMailer
import trade_service
from xml.etree import ElementTree
from supplier_agreement_service import SupplierAgreementService


def synthetic_final_document():
    """Never promote or rewrite the actual packaged legal draft."""
    body = 'SYNTHETIC QA AGREEMENT ONLY. Temporary automated-test company agreement; never for public acceptance.'
    return {'version':'synthetic-final-v1-isolated-tests', 'status':'FINAL',
        'acceptanceEnabled':True, 'pendingFields':[], 'language':'en', 'body':body,
        'bodySha256':hashlib.sha256(body.encode()).hexdigest(),
        'sourceSha256':hashlib.sha256(b'synthetic-isolated-qa-source').hexdigest(),
        'legalDetails':{'operatorLegalName':'Synthetic QA Operator Ltd',
            'operatorRegistrationNumber':'SYNTHETIC-QA-001',
            'operatorRegisteredAddress':'1 Synthetic Test Street, QA City',
            'operatorContactAddress':'2 Synthetic Test Street, QA City',
            'supportEmail':'synthetic-support@example.com', 'governingLaw':'Synthetic QA jurisdiction',
            'disputeJurisdiction':'Synthetic QA court', 'effectiveDate':'2020-01-01'}}


class TradeFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agreement_path = Path(self.temp.name) / 'synthetic-final-agreement.json'
        self.agreement_path.write_text(json.dumps(synthetic_final_document()))
        agreement_factory = patch('trade_service.SupplierAgreementService',
            side_effect=lambda auth: SupplierAgreementService(auth, self.agreement_path))
        agreement_factory.start()
        self.addCleanup(agreement_factory.stop)
        self.auth = AuthService(Path(self.temp.name) / "auth.sqlite3", "test-client", verifier=lambda *_: {})
        trade_service.DOCUMENT_ROOT = Path(self.temp.name) / "documents"
        image_service.ROOT = Path(self.temp.name) / "images"
        EmailAuthService(self.auth, sender=lambda *_: None)
        BuyerService(self.auth)
        self.trade = TradeService(self.auth)
        # The startup migration must be safe to repeat against populated accounts.
        TradeService(self.auth)
        now = int(time.time())
        with self.auth.connect() as db:
            for account, role in (("buyer-a", "BUYER"), ("buyer-b", "BUYER"),
                                  ("supplier-a", "MERCHANT"), ("supplier-b", "MERCHANT"),
                                  ("admin", "PLATFORM_ADMIN")):
                db.execute("INSERT INTO users(id,email,display_name,company_name,role,created_at,email_verified_at) "
                           "VALUES (?,?,?,?,?,?,?)", (account, account + "@example.com", account,
                           account + " company", role, now, now))
        self.users = {account: self.auth.user_for_token(self.auth.session_for_user(account)["access_token"])
                      for account in ("buyer-a", "buyer-b", "supplier-a", "supplier-b", "admin")}

    def add_application_evidence(self, owner):
        output = io.BytesIO()
        Image.new('RGB', (240, 240), 'grey').save(output, 'PNG')
        for kind in ('PREMISES_PHOTO', 'INVENTORY_PHOTO'):
            self.trade.add_document(owner, {'kind': kind, 'filename': kind+'.png',
                'contentType': 'image/png', 'base64': base64.b64encode(output.getvalue()).decode()})

    def sign_company(self, owner):
        doc=self.trade.agreement.document
        return self.trade.agreement.confirm(owner, {'version':doc['version'],'bodySha256':doc['bodySha256'],
            'consent':True,'privacyAcknowledged':True,'authorized':True})

    def record_price(self, listing):
        v=self.trade.vehicle(listing)
        return self.trade.price_reviews.record(self.users['admin'],listing,{
            'referencePriceMinor':round(v['price_minor']/0.925),'currency':v['currency'],'incoterm':v['incoterm'],
            'sourceName':'Isolated QA comparable quote','sourceUrl':'','observedOn':date.today().isoformat(),
            'referenceSpec':'Synthetic matching configuration for automated tests only','comparableConfirmed':True})['id']

    def approved_vehicle(self, supplier="supplier-a"):
        owner = self.users[supplier]
        form = {
            "companyName": "China Export Co", "registrationNo": "REG123", "address": "Shanghai",
            "country": "China", "contactName": "Sales", "contactPhone": "+8613800000000",
        }
        form.update({'premisesAddress':'QA warehouse, Shanghai','inventoryCount':12,'inventoryBasis':'OWNED','inventoryAsOf':date.today().isoformat()})
        self.trade.save_application(owner, form)
        self.trade.add_document(owner, {"kind":"BUSINESS_LICENSE","filename":"licence.pdf",
            "contentType":"application/pdf","base64":base64.b64encode(b"%PDF-1.4\n1 0 obj << >> endobj\n%%EOF").decode()})
        TradeFlowTests.add_application_evidence(self, owner)
        TradeFlowTests.sign_company(self, owner)
        self.trade.save_application(owner, {**form,"submit":True})
        self.trade.review_supplier(self.users["admin"], supplier, {"decision": "APPROVED"})
        item = self.trade.save_vehicle(owner, {
            "modelId": "zeekr-9x-2026", "modelYear": 2026,
            "priceMinor": 1890000, "moq": 2, "stock": 12,
            "originPort": "Shanghai", "validUntil": str(date.today().replace(year=date.today().year + 1)),
        })
        self.trade.images.add(owner,item["id"],TradeFlowTests.image_body(self))
        self.trade.transition_vehicle(owner, item["id"], "submit")
        self.trade.review_vehicle(self.users["admin"], item["id"], {"decision": "APPROVED", "priceReviewId":TradeFlowTests.record_price(self, item["id"])})
        self.trade.transition_vehicle(owner, item["id"], "online")
        return item["id"]

    def image_body(self):
        image=Image.new("RGB",(400,300),"gray");output=io.BytesIO();image.save(output,"JPEG")
        return {"filename":"stock.jpg","contentType":"image/jpeg","stockPhoto":True,"base64":base64.b64encode(output.getvalue()).decode()}

    def test_sending_old_draft_beyond_list_window_returns_committed_quote(self):
        listing = self.approved_vehicle()
        owner, buyer = self.users['supplier-a'], self.users['buyer-a']
        inquiry = self.trade.create_inquiry(buyer, {
            'listingId': listing, 'quantity': 2, 'destinationCountry': 'Kenya'})
        draft = self.trade.create_quote(owner, inquiry['id'], {
            'unitPriceMinor': 1890000, 'validUntil': str(date.today())})
        with self.auth.connect() as db:
            db.execute('UPDATE trade_quotes SET created_at=? WHERE id=?',
                       (int(time.time())-600, draft['id']))
            original = dict(db.execute('SELECT * FROM trade_quotes WHERE id=?', (draft['id'],)).fetchone())
            columns = ','.join(original)
            for n in range(205):
                newer = {**original, 'id': 'QUO-WINDOW-'+str(n), 'created_at': int(time.time())}
                db.execute(f'INSERT INTO trade_quotes ({columns}) VALUES ({",".join("?" for _ in newer)})', tuple(newer.values()))
        self.assertNotIn(draft['id'], {q['id'] for q in self.trade.quote_rows(owner, True)})
        with self.assertRaises(BuyerError):
            self.trade.send_quote(self.users['supplier-b'], draft['id'])
        sent = self.trade.send_quote(owner, draft['id'])
        self.assertEqual(sent['id'], draft['id'])
        self.assertEqual(sent['status'], 'SENT')
        with self.auth.connect() as db:
            self.assertEqual(sent['supplier_name'], db.execute('SELECT company_name FROM users WHERE id=?', (owner['id'],)).fetchone()[0])
        self.assertEqual(sent['total_price_minor'], 3780000)
        self.assertEqual(self.trade.buyer_quote(buyer, draft['id'])['status'], 'SENT')
        self.assertEqual(self.trade.mark_quote_viewed(buyer, draft['id'])['status'], 'VIEWED')
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM account_notifications WHERE user_id=? AND event='NEW_QUOTE' AND entity_id=?", (buyer['id'], draft['id'])).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM trade_audit WHERE action='QUOTE_SENT' AND entity_id=?", (draft['id'],)).fetchone()[0], 1)
        with self.assertRaises(BuyerError):
            self.trade.send_quote(owner, draft['id'])

    def sitemap_locations(self, filename):
        root=ElementTree.fromstring(self.trade.sitemap_xml(filename))
        return [node.text for node in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]

    def test_sitemap_contains_only_public_inventory_and_no_private_records(self):
        listing=self.approved_vehicle()
        draft=self.trade.copy_vehicle(self.users['supplier-a'],listing)['id']
        inquiry=self.trade.create_inquiry(self.users['buyer-a'],{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        locations=self.sitemap_locations('vehicles-1.xml')
        from seo_service import LANGUAGES, localized_url
        self.assertEqual(locations,[localized_url('/trade/vehicles/'+listing,language) for language in LANGUAGES])
        xml=self.trade.sitemap_xml('vehicles-1.xml').decode()
        for value in (draft,inquiry['id'],'buyer-a','supplier-a@example.com','stored_name','review_reason','password'):
            self.assertNotIn(value,xml)
        self.trade.transition_vehicle(self.users['supplier-a'],listing,'offline')
        self.assertEqual(self.sitemap_locations('vehicles-1.xml'),[])
        self.assertEqual(self.trade.vehicle_rows(public=True),[])

    def test_sitemap_hides_unpublished_suspended_and_unapproved_suppliers(self):
        listing=self.approved_vehicle()
        for statement,restore in (
            ("UPDATE supplier_profiles SET published=0 WHERE user_id='supplier-a'", "UPDATE supplier_profiles SET published=1 WHERE user_id='supplier-a'"),
            ("UPDATE supplier_applications SET status='SUSPENDED' WHERE supplier_id='supplier-a'", "UPDATE supplier_applications SET status='APPROVED' WHERE supplier_id='supplier-a'"),
            ("UPDATE users SET status='SUSPENDED' WHERE id='supplier-a'", "UPDATE users SET status='ACTIVE' WHERE id='supplier-a'"),
            ("UPDATE users SET deleted_at=1 WHERE id='supplier-a'", "UPDATE users SET deleted_at=NULL WHERE id='supplier-a'"),
            ("UPDATE users SET email_verified_at=NULL WHERE id='supplier-a'", "UPDATE users SET email_verified_at=1 WHERE id='supplier-a'"),
            ("UPDATE users SET role='PLATFORM_ADMIN' WHERE id='supplier-a'", "UPDATE users SET role='MERCHANT' WHERE id='supplier-a'"),
        ):
            with self.subTest(statement=statement):
                with self.auth.connect() as db:db.execute(statement)
                self.assertEqual(self.sitemap_locations('suppliers-1.xml'),[])
                self.assertEqual(self.sitemap_locations('vehicles-1.xml'),[])
                self.assertEqual(self.trade.supplier_list(),[])
                self.assertEqual(self.trade.vehicle_rows(public=True),[])
                with self.assertRaises(BuyerError):self.trade.vehicle(listing,public=True)
                with self.auth.connect() as db:db.execute(restore)
        self.assertEqual(len(self.sitemap_locations('vehicles-1.xml')),9)

    def test_sitemap_hides_inactive_catalogue_and_archived_inventory(self):
        listing=self.approved_vehicle()
        for statement,restore in (
            ("UPDATE catalog_models SET active=0 WHERE id='zeekr-9x-2026'", "UPDATE catalog_models SET active=1 WHERE id='zeekr-9x-2026'"),
            ("UPDATE catalog_brands SET active=0 WHERE id='zeekr'", "UPDATE catalog_brands SET active=1 WHERE id='zeekr'"),
            ("UPDATE supplier_vehicles SET archived_at=1 WHERE id=?", "UPDATE supplier_vehicles SET archived_at=NULL WHERE id=?"),
        ):
            with self.subTest(statement=statement):
                args=(listing,) if '?' in statement else ()
                with self.auth.connect() as db:db.execute(statement,args)
                self.assertEqual(self.sitemap_locations('vehicles-1.xml'),[])
                if 'catalog' in statement:
                    self.assertNotIn('https://autolinkglobal.com/trade/models/zeekr-9x-2026',self.sitemap_locations('models-1.xml'))
                with self.auth.connect() as db:db.execute(restore,args)

    def test_sitemap_uses_real_lastmod_and_static_pages_have_no_fake_timestamp(self):
        listing=self.approved_vehicle()
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_vehicles SET updated_at=1700000000 WHERE id=?",(listing,))
            db.execute("UPDATE supplier_profiles SET updated_at=1600000000 WHERE user_id='supplier-a'")
            db.execute("UPDATE supplier_applications SET updated_at=1600000000 WHERE supplier_id='supplier-a'")
        xml=self.trade.sitemap_xml('vehicles-1.xml').decode()
        self.assertIn('<lastmod>2023-11-14T22:13:20+00:00</lastmod>',xml)
        static=self.trade.sitemap_xml('static-1.xml').decode()
        self.assertNotIn('<lastmod>',static)
        self.assertNotIn('/buyer',static)
        self.assertNotIn('/admin',static)
        for missing in ('/about','/help','/faq','/refund'):
            self.assertNotIn('https://autolinkglobal.com'+missing,static)

    def test_sitemap_shards_cover_catalogue_once_with_bounded_results(self):
        with patch.object(trade_service,'SITEMAP_PAGE_SIZE',18):
            index=self.sitemap_locations('sitemap.xml')
            children=[url.rsplit('/',1)[1] for url in index if '/models-' in url]
            found=[]
            for child in children:
                locations=self.sitemap_locations(child)
                self.assertLessEqual(len(locations),18)
                found.extend(locations)
            self.assertEqual(len(found),len(set(found)))
            self.assertEqual(len(found),len(self.trade.catalog.models())*9)
            for filename in ('models-0.xml','models-01.xml','models-99999.xml','users-1.xml','../static-1.xml'):
                with self.assertRaises(BuyerError):self.trade.sitemap_xml(filename)

    def test_public_image_disappears_when_supplier_verification_is_revoked(self):
        listing=self.photographed_listing()
        image=self.trade.images.list(listing)[0]
        self.assertTrue(self.trade.images.bytes(image['id']))
        with self.auth.connect() as db:db.execute("UPDATE users SET email_verified_at=NULL WHERE id='supplier-a'")
        with self.assertRaises(BuyerError):self.trade.images.bytes(image['id'])
        # Existing owner access remains private and authenticated.
        self.assertTrue(self.trade.images.bytes(image['id'],self.users['supplier-a']))

    def test_http_sitemap_is_xml_host_independent_and_rejects_invalid_shards(self):
        Handler.service=self.auth;Handler.trade=self.trade
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        with urllib.request.urlopen(urllib.request.Request(base+'/autolink/public/sitemap.xml',headers={'Host':'attacker.example'})) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(response.headers['Content-Type'],'application/xml; charset=utf-8')
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            body=response.read()
            ElementTree.fromstring(body)
            self.assertNotIn(b'attacker.example',body)
        for path,method in (('/autolink/public/sitemaps/users-1.xml','GET'),('/autolink/public/sitemap.xml','POST')):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(urllib.request.Request(base+path,method=method))
            self.assertEqual(caught.exception.code,404 if method=='GET' else 405)

    def test_image_decoding_and_private_draft_access(self):
        listing_id=self.approved_vehicle()
        owner=self.users["supplier-a"]
        self.trade.transition_vehicle(owner,listing_id,"offline")
        existing=self.trade.vehicle(listing_id,supplier_id=owner["id"])
        self.trade.save_vehicle(owner,{"modelId":existing["model_id"],"modelYear":2026,"priceMinor":1890000,
              "moq":2,"stock":12,"originPort":"Shanghai","validUntil":str(date.today())},listing_id)
        image=self.trade.images.add(owner,listing_id,self.image_body())
        self.assertNotIn("stored_name",image)
        for user in (None,self.users["supplier-b"],self.users["buyer-a"]):
            with self.assertRaises(BuyerError): self.trade.images.bytes(image["id"],user)
        data=self.trade.images.bytes(image["id"],owner)
        with Image.open(io.BytesIO(data)) as loaded:
            self.assertEqual(loaded.format,"JPEG")
            self.assertEqual(loaded.size,(400,300))
            self.assertFalse(loaded.getexif())
        with self.assertRaises(BuyerError):
            self.trade.images.add(owner,listing_id,{**self.image_body(),"base64":base64.b64encode(b"<script>not an image</script>").decode()})
        with self.assertRaises(BuyerError):
            self.trade.images.add(self.users["supplier-b"],listing_id,self.image_body())

    def test_real_inquiry_quote_and_buyer_response(self):
        listing_id = self.approved_vehicle()
        buyer, supplier = self.users["buyer-a"], self.users["supplier-a"]
        self.assertEqual(len(self.trade.vehicle_rows(public=True)), 1)
        inquiry = self.trade.create_inquiry(buyer, {
            "listingId": listing_id, "quantity": 2, "destinationCountry": "Saudi Arabia",
            "destinationPort": "Jeddah", "incoterm": "FOB", "message": "Need two units",
        })
        self.assertEqual(inquiry["supplier_id"], supplier["id"])
        inbox = self.trade.supplier_inquiries(supplier, inquiry["id"])
        self.assertEqual(inbox[0]["status"], "SUBMITTED")
        self.trade.update_inquiry(supplier,inquiry['id'],{'status':'VIEWED'})
        self.assertEqual(self.trade.supplier_inquiries(supplier,inquiry['id'])[0]['status'],'VIEWED')
        quote = self.trade.create_quote(supplier, inquiry["id"], {
            "unitPriceMinor": 1850000, "quantity": 2, "validUntil": str(date.today().replace(year=date.today().year + 1)),
            "send": True,
        })
        self.assertEqual(quote["total_price_minor"], 3700000)
        self.assertEqual(len(self.trade.quote_rows(buyer)), 1)
        self.assertEqual(self.trade.buyer_quote(buyer, quote["id"], "ACCEPTED")["status"], "ACCEPTED")
        self.assertEqual(self.trade.buyer_inquiry(buyer, inquiry["id"])["status"], "QUOTED")

    def test_cross_supplier_and_cross_buyer_access_is_denied(self):
        listing_id = self.approved_vehicle()
        buyer, other_buyer = self.users["buyer-a"], self.users["buyer-b"]
        supplier, other_supplier = self.users["supplier-a"], self.users["supplier-b"]
        inquiry = self.trade.create_inquiry(buyer, {"listingId": listing_id, "quantity": 2,
                                                    "destinationCountry": "Kenya"})
        for operation in (
            lambda: self.trade.vehicle(listing_id, supplier_id=other_supplier["id"]),
            lambda: self.trade.buyer_inquiry(other_buyer, inquiry["id"]),
            lambda: self.trade.update_inquiry(other_supplier, inquiry["id"], {"status": "CONTACTED"}),
            lambda: self.trade.create_quote(other_supplier, inquiry["id"], {"unitPriceMinor": 1,
                        "validUntil": str(date.today().replace(year=date.today().year + 1))}),
            lambda: self.trade.update_crm(other_supplier, buyer["id"], {"status": "FOLLOW_UP"}),
        ):
            with self.assertRaises(BuyerError) as raised:
                operation()
            self.assertEqual(raised.exception.status, 404)
        self.assertEqual(self.trade.supplier_inquiries(other_supplier), [])
        self.assertEqual(self.trade.crm(other_supplier), [])
        with self.assertRaises(BuyerError) as raised:
            self.trade.require_admin(self.auth.session_for_user("supplier-a")["access_token"])
        self.assertEqual(raised.exception.status, 403)
        self.assertEqual(supplier["id"], inquiry["supplier_id"])

    def test_unreviewed_listing_is_not_public_and_duplicate_inquiry_is_blocked(self):
        supplier = self.users["supplier-a"]
        form={"companyName": "China Export Co", "registrationNo": "REG123",
            "address": "Shanghai", "country": "China", "contactName": "Sales", "contactPhone": "+8613800000000",
            }
        form.update({'premisesAddress':'QA warehouse, Shanghai','inventoryCount':12,'inventoryBasis':'OWNED','inventoryAsOf':date.today().isoformat()})
        self.trade.save_application(supplier, form)
        self.trade.add_document(supplier, {"kind":"BUSINESS_LICENSE","filename":"licence.pdf",
            "contentType":"application/pdf","base64":base64.b64encode(b"%PDF-1.4\n1 0 obj << >> endobj\n%%EOF").decode()})
        TradeFlowTests.add_application_evidence(self, supplier)
        TradeFlowTests.sign_company(self, supplier)
        self.trade.save_application(supplier, {**form,"submit":True})
        self.trade.review_supplier(self.users["admin"], supplier["id"], {"decision": "APPROVED"})
        draft = self.trade.save_vehicle(supplier, {"modelId": "zeekr-9x-2026", "modelYear": 2026,
            "priceMinor": 1890000, "moq": 2, "stock": 12, "originPort": "Shanghai",
            "validUntil": str(date.today().replace(year=date.today().year + 1))})
        self.assertEqual(self.trade.vehicle_rows(public=True), [])
        with self.assertRaises(BuyerError):
            self.trade.create_inquiry(self.users["buyer-a"], {"listingId": draft["id"], "quantity": 2,
                                                        "destinationCountry": "Kenya"})
        self.trade.images.add(supplier,draft["id"],TradeFlowTests.image_body(self))
        self.trade.transition_vehicle(supplier, draft["id"], "submit")
        self.trade.review_vehicle(self.users["admin"], draft["id"], {"decision": "APPROVED", "priceReviewId":TradeFlowTests.record_price(self, draft["id"])})
        self.trade.transition_vehicle(supplier, draft["id"], "online")
        body = {"listingId": draft["id"], "quantity": 2, "destinationCountry": "Kenya"}
        self.trade.create_inquiry(self.users["buyer-a"], body)
        with self.assertRaises(BuyerError) as raised:
            self.trade.create_inquiry(self.users["buyer-a"], body)
        self.assertEqual(raised.exception.status, 409)

    def test_document_content_and_owner_isolation(self):
        owner = self.users["supplier-a"]
        self.trade.save_application(owner, {"companyName":"China Export", "registrationNo":"REG", "address":"China", "country":"China", "contactName":"Sales", "contactPhone":"123"})
        body = {"kind":"BUSINESS_LICENSE", "filename":"licence.pdf", "contentType":"application/pdf", "base64":base64.b64encode(b"%PDF-1.4\n1 0 obj << >> endobj\n%%EOF").decode()}
        document = self.trade.add_document(owner, body)
        self.assertNotIn("stored_name", document)
        self.assertTrue(self.trade.document_bytes(document["id"], owner)["data"].startswith(b"%PDF"))
        for account in ("supplier-b", "buyer-a"):
            with self.assertRaises(BuyerError) as error:
                self.trade.document_bytes(document["id"], self.users[account])
            self.assertEqual(error.exception.status, 404)
        with self.assertRaises(BuyerError):
            self.trade.add_document(owner, {**body,"base64":base64.b64encode(b"<script>alert(1)</script>").decode()})
        with self.assertRaises(BuyerError):
            self.trade.add_document(owner, {**body,"filename":"../licence.pdf"})
        self.assertTrue(self.trade.document_bytes(document["id"], self.users["admin"])["data"])

    def test_crm_notes_quote_visibility_and_public_redaction(self):
        listing = self.approved_vehicle()
        supplier, buyer = self.users["supplier-a"], self.users["buyer-a"]
        item = self.trade.vehicle(listing, public=True)
        for key in ("review_reason", "reviewed_by", "reviewed_at"):
            self.assertNotIn(key, item)
            self.assertNotIn(key, self.trade.vehicle_rows(public=True)[0])
        inquiry = self.trade.create_inquiry(buyer, {"listingId":listing,"quantity":2,"destinationCountry":"Kenya"})
        self.trade.update_crm(supplier, buyer["id"], {"status":"HIGH_INTENT", "note":"Follow up next week", "tag":"SUV"})
        detail = self.trade.crm_detail(supplier, buyer["id"])
        self.assertEqual(detail["notes"][0]["note"], "Follow up next week")
        quote = self.trade.create_quote(supplier, inquiry["id"], {"unitPriceMinor":10000,"validUntil":str(date.today()),"send":False})
        self.assertEqual(self.trade.quote_rows(buyer), [])
        self.trade.send_quote(supplier, quote["id"])
        with self.assertRaises(BuyerError):
            self.trade.buyer_quote(self.users["buyer-b"], quote["id"])
        self.trade.cancel_quote(supplier, quote["id"])
        self.assertEqual(self.trade.buyer_quote(buyer, quote["id"])["status"], "CANCELLED")
        with self.assertRaises(BuyerError):
            self.trade.buyer_quote(buyer, quote["id"], "ACCEPTED")
        self.assertTrue(self.trade.audit_rows())

    def test_http_rbac_csrf_and_suspended_session(self):
        Handler.service = self.auth
        Handler.email_auth = EmailAuthService(self.auth, sender=lambda *_: None)
        Handler.buyer = BuyerService(self.auth)
        Handler.trade = self.trade
        Handler.platform = self.trade.platform
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        token = self.auth.session_for_user("buyer-a")["access_token"]
        base = "http://127.0.0.1:"+str(server.server_port)
        def call(path, method="GET", body=None, origin=None):
            headers = {"Cookie":"autolink_session="+token,"Content-Type":"application/json"}
            if origin: headers["Origin"] = origin
            request = urllib.request.Request(base+path, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
            try:
                with urllib.request.urlopen(request) as response:
                    return response.status,json.load(response)
            except urllib.error.HTTPError as error:
                return error.code,json.load(error)
        self.assertEqual(call("/autolink/admin/overview")[0],403)
        self.assertEqual(call("/autolink/supplier/vehicles")[0],403)
        self.assertEqual(call("/autolink/buyer/inquiries","POST",{"vehicleId":"zeekr-9x-2026"})[0],400)
        self.assertEqual(call("/autolink/buyer/history","POST",{},"https://attacker.example")[0],403)
        self.trade.user_status(self.users["admin"], "buyer-a", {"status":"SUSPENDED","reason":"test"})
        self.assertEqual(call("/autolink/me")[0],401)

    def photographed_listing(self):
        owner=self.users['supplier-a']
        listing=self.approved_vehicle()
        self.trade.transition_vehicle(owner,listing,'offline')
        self.trade.save_vehicle(owner,{'modelId':'zeekr-9x-2026','modelYear':2026,'priceMinor':1890000,
            'moq':2,'stock':12,'originPort':'Shanghai','validUntil':str(date.today().replace(year=date.today().year+1))},listing)
        self.trade.images.add(owner,listing,self.image_body())
        self.trade.transition_vehicle(owner,listing,'submit')
        self.trade.review_vehicle(self.users['admin'],listing,{'decision':'APPROVED','priceReviewId':TradeFlowTests.record_price(self,listing)})
        self.trade.transition_vehicle(owner,listing,'online')
        return listing

    def test_copy_is_an_independent_private_draft_with_private_images(self):
        owner=self.users['supplier-a'];listing=self.photographed_listing()
        copied=self.trade.copy_vehicle(owner,listing)
        self.assertNotEqual(copied['id'],listing)
        self.assertEqual(copied['status'],'DRAFT')
        self.assertIsNone(copied['reviewed_at']);self.assertIsNone(copied['reviewed_by'])
        self.assertIsNone(copied['archived_at']);self.assertEqual(copied['review_reason'],'')
        source_photo=self.trade.images.list(listing)[0]['id'];photo=self.trade.images.list(copied['id'])[0]['id']
        self.assertNotEqual(source_photo,photo)
        self.assertEqual(self.trade.images.bytes(source_photo,owner),self.trade.images.bytes(photo,owner))
        for identity in (None,self.users['supplier-b'],self.users['buyer-a']):
            with self.assertRaises(BuyerError):self.trade.images.bytes(photo,identity)
        self.assertEqual([v['id'] for v in self.trade.vehicle_rows(public=True)],[listing])
        with self.assertRaises(BuyerError):self.trade.transition_vehicle(owner,copied['id'],'online')
        self.approved_vehicle('supplier-b')
        with self.assertRaises(BuyerError) as error:self.trade.copy_vehicle(self.users['supplier-b'],listing)
        self.assertEqual(error.exception.status,404)
        with self.assertRaises(BuyerError) as error:
            self.trade.copy_vehicle({**owner,'supplier_role':'SALES'},listing)
        self.assertEqual(error.exception.status,403)
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM trade_audit WHERE action='VEHICLE_COPIED' AND entity_id=?",(copied['id'],)).fetchone()[0],1)
            db.execute("UPDATE users SET status='SUSPENDED' WHERE id=?",(owner['id'],))
        with self.assertRaises(BuyerError):self.trade.copy_vehicle(owner,listing)

    def test_copy_rolls_back_new_rows_and_files_when_transaction_fails(self):
        owner=self.users['supplier-a'];listing=self.photographed_listing()
        files=set(image_service.ROOT.iterdir())
        with self.auth.connect() as db:
            before=db.execute('SELECT count(*) FROM supplier_vehicles').fetchone()[0]
            before_images=db.execute('SELECT count(*) FROM vehicle_images').fetchone()[0]
        with patch.object(self.trade,'audit',side_effect=RuntimeError('test audit failure')):
            with self.assertRaises(RuntimeError):self.trade.copy_vehicle(owner,listing)
        self.assertEqual(set(image_service.ROOT.iterdir()),files)
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM supplier_vehicles').fetchone()[0],before)
            self.assertEqual(db.execute('SELECT count(*) FROM vehicle_images').fetchone()[0],before_images)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_archive_restore_preserves_inquiry_quote_and_requires_fresh_review(self):
        owner,buyer=self.users['supplier-a'],self.users['buyer-a'];listing=self.approved_vehicle()
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        quote=self.trade.create_quote(owner,inquiry['id'],{'unitPriceMinor':1850000,'send':True,
            'validUntil':str(date.today().replace(year=date.today().year+1))})
        self.trade.transition_vehicle(owner,listing,'offline');self.trade.transition_vehicle(owner,listing,'archive')
        with self.assertRaises(BuyerError):self.trade.vehicle(listing,public=True,include_archived=True)
        self.assertEqual(self.trade.vehicle_rows(supplier_id=owner['id']),[])
        self.assertEqual(self.trade.vehicle_rows(supplier_id=owner['id'],status='ARCHIVED')[0]['id'],listing)
        self.assertEqual(self.trade.vehicle(listing,supplier_id=owner['id'],include_archived=True)['status'],'ARCHIVED')
        self.assertEqual(self.trade.buyer_inquiry(buyer,inquiry['id'])['listing_id'],listing)
        self.assertEqual(self.trade.buyer_quote(buyer,quote['id'])['id'],quote['id'])
        with self.assertRaises(BuyerError):self.trade.transition_vehicle(self.users['supplier-b'],listing,'restore')
        restored=self.trade.transition_vehicle(owner,listing,'restore')
        self.assertEqual(restored['status'],'DRAFT');self.assertIsNone(restored['reviewed_at'])
        self.assertEqual(self.trade.vehicle_rows(public=True),[])
        with self.assertRaises(BuyerError):self.trade.transition_vehicle(owner,listing,'online')
        self.trade.transition_vehicle(owner,listing,'submit')
        self.trade.review_vehicle(self.users['admin'],listing,{'decision':'APPROVED','priceReviewId':TradeFlowTests.record_price(self,listing)})
        self.trade.transition_vehicle(owner,listing,'online')
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM trade_quotes WHERE inquiry_id=?',(inquiry['id'],)).fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_cancelled_unsent_draft_is_never_visible_to_buyer(self):
        owner,buyer=self.users['supplier-a'],self.users['buyer-a'];listing=self.approved_vehicle()
        buyer_service=BuyerService(self.auth)
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        body={'unitPriceMinor':1850000,'validUntil':str(date.today().replace(year=date.today().year+1))}
        draft=self.trade.create_quote(owner,inquiry['id'],body)
        self.trade.cancel_quote(owner,draft['id'])
        self.assertEqual(self.trade.quote_rows(buyer),[])
        self.assertEqual(buyer_service.overview(buyer)['counts']['quotes'],0)
        with self.assertRaises(BuyerError) as error:self.trade.buyer_quote(buyer,draft['id'])
        self.assertEqual(error.exception.status,404)
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM account_notifications WHERE entity_id=?',(draft['id'],)).fetchone()[0],0)
        sent=self.trade.create_quote(owner,inquiry['id'],{**body,'send':True})
        self.trade.buyer_quote(buyer,sent['id']);self.trade.cancel_quote(owner,sent['id'])
        self.assertEqual(self.trade.buyer_quote(buyer,sent['id'])['status'],'CANCELLED')
        self.assertEqual(buyer_service.overview(buyer)['counts']['quotes'],1)
        self.assertEqual(buyer_service.overview(self.users['buyer-b'])['counts']['quotes'],0)
        with self.assertRaises(BuyerError):self.trade.buyer_quote(buyer,sent['id'],'ACCEPTED')
        with self.auth.connect() as db:
            job=db.execute("SELECT * FROM business_mail_jobs WHERE entity_id=? AND event='QUOTE_CANCELLED'",(sent['id'],)).fetchone()
            self.assertEqual(job['user_id'],buyer['id']);self.assertTrue(BusinessMailer.eligible(db,job))
            self.assertFalse(BusinessMailer.eligible(db,{**dict(job),'user_id':'buyer-b'}))

    def test_quote_shipping_and_total_are_validated_as_integer_minor_units(self):
        owner,buyer=self.users['supplier-a'],self.users['buyer-a'];listing=self.approved_vehicle()
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        body={'unitPriceMinor':1850000,'validUntil':str(date.today().replace(year=date.today().year+1))}
        quote=self.trade.create_quote(owner,inquiry['id'],{**body,'shippingCostMinor':12500})
        self.assertEqual(quote['total_price_minor'],3712500)
        self.assertEqual(self.trade.create_quote(owner,inquiry['id'],{**body,'shippingCostMinor':0})['shipping_cost_minor'],0)
        for extra in ({'shippingCostMinor':-1},{'shippingCostMinor':True},{'shippingCostMinor':1.2},
                      {'unitPriceMinor':0},{'unitPriceMinor':10**12,'quantity':100000}):
            with self.assertRaises(BuyerError):self.trade.create_quote(owner,inquiry['id'],{**body,**extra})

    def test_supplier_quote_detail_is_scoped_to_assigned_active_sales(self):
        owner,buyer=self.users['supplier-a'],self.users['buyer-a'];listing=self.approved_vehicle()
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        quote=self.trade.create_quote(owner,inquiry['id'],{'unitPriceMinor':1850000,
            'validUntil':str(date.today().replace(year=date.today().year+1))})
        invitation=self.trade.team.invite(owner,{'email':'buyer-b@example.com'})
        self.trade.team.accept(self.users['buyer-b'],invitation['id'])
        sales=self.trade.team.principal(self.users['buyer-b'],'supplier-a',True)
        with self.assertRaises(BuyerError):self.trade.supplier_quote(sales,quote['id'])
        self.trade.team.assign(owner,buyer['id'],{'userId':'buyer-b'})
        self.assertEqual(self.trade.supplier_quote(sales,quote['id'])['buyer_company'],buyer['company_name'])
        with self.assertRaises(BuyerError):self.trade.supplier_quote(self.users['supplier-b'],quote['id'])
        self.trade.team.remove(owner,'buyer-b')
        with self.assertRaises(BuyerError):self.trade.supplier_quote(sales,quote['id'])

    def test_lifecycle_http_routes_enforce_owner_assignment_and_csrf(self):
        owner,buyer=self.users['supplier-a'],self.users['buyer-a'];listing=self.approved_vehicle()
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        quote=self.trade.create_quote(owner,inquiry['id'],{'unitPriceMinor':1850000,
            'validUntil':str(date.today().replace(year=date.today().year+1))})
        invitation=self.trade.team.invite(owner,{'email':'buyer-b@example.com'})
        self.trade.team.accept(self.users['buyer-b'],invitation['id'])
        self.trade.team.assign(owner,buyer['id'],{'userId':'buyer-b'})
        class TestHandler(Handler):pass
        TestHandler.service=self.auth;TestHandler.trade=self.trade;TestHandler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        tokens={key:self.auth.session_for_user(key)['access_token'] for key in ('supplier-a','supplier-b','buyer-a','buyer-b')}
        def call(user,tail,method='GET',company='supplier-a',origin=None):
            headers={'Cookie':'autolink_session='+tokens[user],'X-Autolink-Supplier':company,'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/autolink/supplier/'+tail,
                data=b'{}' if method=='POST' else None,headers=headers,method=method)
            try:response=urllib.request.urlopen(request)
            except urllib.error.HTTPError as error:response=error
            with response:return response.status,json.loads(response.read())
        self.assertEqual(call('buyer-b','quotes/'+quote['id'])[0],200)
        self.assertEqual(call('buyer-b','vehicles/'+listing+'/copy','POST')[0],403)
        self.assertEqual(call('buyer-b','vehicles/'+listing+'/restore','POST')[0],403)
        self.assertEqual(call('supplier-b','quotes/'+quote['id'],company='supplier-b')[0],403)
        self.assertEqual(call('supplier-a','vehicles/'+listing+'/copy','POST',origin='https://other.example')[0],403)
        status,result=call('supplier-a','vehicles/'+listing+'/copy','POST')
        self.assertEqual(status,200);copied=result['data']['id']
        self.assertEqual(call('supplier-a','vehicles/'+copied+'/archive','POST')[0],200)
        self.assertEqual(call('supplier-a','vehicles?status=ARCHIVED')[1]['data'][0]['id'],copied)
        self.assertEqual(call('supplier-a','vehicles/'+copied)[1]['data']['status'],'ARCHIVED')
        self.assertEqual(call('supplier-a','vehicles/'+copied+'/restore','POST')[1]['data']['status'],'DRAFT')
        self.assertEqual(call('supplier-a','vehicles?status=BAD')[0],400)
        self.trade.team.remove(owner,'buyer-b')
        self.assertEqual(call('buyer-b','quotes/'+quote['id'])[0],404)


if __name__ == "__main__":
    unittest.main()
