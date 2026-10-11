"""Loopback-only QA app with the dated public catalogue and synthetic accounts."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import os
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'auth'))
from app import Handler
from buyer_service import BuyerService
from test_current_catalog_seo import CurrentCatalogSEOTests

fixture=CurrentCatalogSEOTests()
fixture.setUp()
Handler.service=fixture.auth
Handler.trade=fixture.trade
Handler.buyer=BuyerService(fixture.auth)
Handler.platform=fixture.trade.platform
Handler.seo=fixture.seo
port=int(os.environ.get('QA_PORT','18080'))
server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
print(f'AUTOLINK_PUBLIC_SNAPSHOT_QA_READY 127.0.0.1:{port} 244_models 53_brands',flush=True)
try:server.serve_forever()
finally:
    server.server_close()
    fixture.doCleanups()
