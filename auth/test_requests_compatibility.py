"""Actual Requests/Google-auth interop on loopback; no real Google login."""
import json
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt, jwt
from google.auth.transport.requests import Request
from google.oauth2 import id_token


class RequestsCompatibilityTests(unittest.TestCase):
    def test_real_transport_verifies_synthetic_signature_and_rejects_wrong_audience(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Synthetic QA only')])
        now = datetime.now(timezone.utc)
        certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(minutes=10))
            .sign(key, hashes.SHA256()))
        certs = json.dumps({'synthetic-key': certificate.public_bytes(serialization.Encoding.PEM).decode()}).encode()
        hits = []
        class LocalCertificates(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.end_headers(); self.wfile.write(certs)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), LocalCertificates)
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        token = jwt.encode(crypt.RSASigner.from_string(pem, 'synthetic-key'), {
            'iss':'https://accounts.google.com', 'aud':'synthetic-qa-client',
            'sub':'synthetic-qa-user', 'iat':int(time.time()), 'exp':int(time.time())+300})
        with requests.Session() as session:
            session.trust_env = False
            transport = Request(session=session)
            with patch.object(id_token, '_GOOGLE_OAUTH2_CERTS_URL', 'http://127.0.0.1:'+str(server.server_port)+'/certs'):
                claims = id_token.verify_oauth2_token(token, transport, audience='synthetic-qa-client')
                self.assertEqual(claims['sub'], 'synthetic-qa-user')
                with self.assertRaises(ValueError):
                    id_token.verify_oauth2_token(token, transport, audience='wrong-synthetic-client')
        self.assertEqual(hits, ['/certs', '/certs'])


if __name__ == '__main__':
    unittest.main()
