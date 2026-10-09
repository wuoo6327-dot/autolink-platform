"""Real HTTPS/HTTP2 requests to loopback staging with explicit CA validation."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--ca', required=True)
p.add_argument('--fixtures', required=True)
p.add_argument('--port', default='19443')
p.add_argument('--output', required=True)
args = p.parse_args()
fixtures = json.loads(Path(args.fixtures).read_text())
assert fixtures['syntheticOnly'] is True
results = []
base = 'https://autolinkglobal.com:'+args.port

def request(path, method='GET', account=None, body=None, headers=None, http='--http2', cookie=None):
    with tempfile.TemporaryDirectory() as d:
        hf, bf = Path(d)/'headers', Path(d)/'body'
        cmd = ['curl','--silent','--show-error','--noproxy','*','--max-time','10',http,
            '--cacert',args.ca,'--resolve','autolinkglobal.com:'+args.port+':127.0.0.1',
            '-D',str(hf),'-o',str(bf),'-w','%{http_code} %{http_version}', '-X',method,base+path]
        if account:
            cmd += ['-H','Cookie: autolink_session='+fixtures['tokens'][account]]
        if cookie:
            cmd += ['-H','Cookie: '+cookie]
        for key, value in (headers or {}).items():
            cmd += ['-H',key+': '+value]
        if body is not None:
            cmd += ['-H','Content-Type: application/json','--data-binary',json.dumps(body)]
        done = subprocess.run(cmd, capture_output=True, text=True, check=True)
        status, version = done.stdout.split()
        return int(status), version, hf.read_text(), bf.read_bytes()

def check(label, condition):
    results.append({'check':label,'passed':bool(condition)})
    if not condition:
        raise AssertionError(label)

def data(response):
    return json.loads(response[3])['data']

r = request('/healthz')
check('HTTPS certificate validated, HTTP/2 ALPN, backend JSON health',r[0]==200 and r[1]=='2' and data(r).get('status')=='ok')
for protocol in ['--http1.1','--http2']:
    r = request('/autolink/me',account='owner',http=protocol)
    check(protocol+' proxy/Cookie owner protection',r[0]==200 and data(r)['accountDeletionAllowed'] is False)
for role in ['owner','other-admin']:
    r = request('/autolink/me', 'DELETE', role, {}, {'Origin':'https://autolinkglobal.com'})
    expected = 403 if role=='owner' else 200
    check(role+' account closure boundary',r[0]==expected)
r = request('/autolink/me',account='owner')
check('last active admin remains protected',r[0]==200 and data(r)['accountDeletionAllowed'] is False)
check('anonymous login boundary',request('/autolink/me')[0]==401)
check('buyer admin API boundary',request('/autolink/admin/email',account='buyer')[0]==403)
check('wrong password rejected',request('/autolink/auth/password/login','POST',body={'email':'qa-buyer@example.invalid','password':'wrong','role':'BUYER'})[0]==401)
check('suspended password login rejected',request('/autolink/auth/password/login','POST',body={'email':'qa-suspended@example.invalid','password':fixtures['password'],'role':'BUYER'})[0] in (401,403))
r = request('/autolink/auth/password/login','POST',body={'email':'qa-buyer@example.invalid','password':fixtures['password'],'role':'BUYER'})
check('actual password login over TLS sets secure Cookie',r[0]==200 and all(x in r[2] for x in ['HttpOnly','Secure','SameSite=Lax','autolink_session=']))
cookie = next(line.split(':',1)[1].strip().split(';')[0] for line in r[2].splitlines() if line.lower().startswith('set-cookie:'))
check('Cookie-only session works through reverse proxy',request('/autolink/me',cookie=cookie)[0]==200)
image='/autolink/public/vehicle-images/qa-private'
for account in [None,'outsider','buyer','merchant','owner']:
    r=request(image,account=account)
    allowed=account in ('merchant','owner')
    check('private JPEG authorization '+str(account),r[0]==(200 if allowed else 404) and (not allowed or ('no-store' in r[2] and r[3][:2]==b'\xff\xd8')))
for headers in [{'Origin':'https://foreign.example'},{'Sec-Fetch-Site':'cross-site'},{'Origin':'null'}]:
    check('cross-site account closure refused '+str(headers),request('/autolink/me','DELETE','merchant',{},headers)[0]==403)
check('denied closure leaves session active',request('/autolink/me',account='merchant')[0]==200)
r=request('/autolink/me','DELETE','merchant',{}, {'Origin':'https://autolinkglobal.com'})
check('Cookie business account close clears Cookie',r[0]==200 and 'Max-Age=0' in r[2])
check('closed business session revoked',request('/autolink/me',account='merchant')[0]==401)
check('closed business private JPEG immediately denied',request(image,account='merchant')[0]==404)
check('other owner still sees preserved private image',request(image,account='owner')[0]==200)
r=request('/autolink/auth/logout-all','POST','buyer',{}, {'Origin':'https://autolinkglobal.com'})
check('logout-all succeeds',r[0]==200)
check('logout-all revokes original session',request('/autolink/me',account='buyer')[0]==401)
check('logout-all revokes new password Cookie',request('/autolink/me',cookie=cookie)[0]==401)
for route in ['/','/buyer/login','/supplier/login','/admin','/trade','/privacy','/cookies','/account-deletion']:
    r=request(route)
    check('existing page '+route,r[0]==200 and 'text/html' in r[2])
for lang in ['en','zh','ar','ru','kk','uz','ko','fr','sw']:
    check('existing language route '+lang,request('/buyer/login?lang='+lang)[0]==200)
Path(args.output).write_text(json.dumps({'syntheticOnly':True,'certificateValidation':True,'results':results,'passed':len(results)},indent=2))
print(json.dumps({'checks':len(results),'failed':0,'TLS':'validated','HTTP2':'negotiated'}))
