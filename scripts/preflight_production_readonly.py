"""Read production metadata and save PRIVATE backups under the QA directory.

No production container restart, configuration write, SQL update or HTTP login.
The real database copy is never served by staging and never put in Git.
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--root',required=True);args=p.parse_args()
root=Path(args.root).resolve()
assert os.geteuid()==0 and 'autolink-round3-stage-native' in str(root)
assert os.environ.get('AUTOLINK_STAGE_ACK')=='ISOLATED_ROUND3'
private=root/'private-production-backup';private.mkdir(mode=0o700,exist_ok=True)
proof=root/'evidence';proof.mkdir(mode=0o700,exist_ok=True)
def command(cmd):
    return subprocess.check_output(cmd,text=True)
prod=json.loads(command(['docker','inspect','autolink-demo-auth-1','autolink-demo-web-1']))
metadata={'uname':os.uname().release,'machine':os.uname().machine,
          'dockerServer':json.loads(command(['docker','version','--format','{{json .Server}}'])),
          'containers':[{'id':x['Id'],'image':x['Image'],'startedAt':x['State']['StartedAt'],'user':x['Config']['User'],
                         'privileged':x['HostConfig']['Privileged'],'capAdd':x['HostConfig'].get('CapAdd'),
                         'mounts':[{k:m.get(k) for k in ['Type','Name','Source','Destination','RW']} for m in x['Mounts']]} for x in prod]}
(proof/'production-readonly.json').write_text(json.dumps(metadata,indent=2))
assert metadata['machine']=='x86_64' and metadata['dockerServer']['Arch']=='amd64'
auth_mount=next(m for m in prod[0]['Mounts'] if m['Destination']=='/data')
db_path=Path(auth_mount['Source'])/'autolink-auth.sqlite3'
assert db_path.is_file()
snapshot=private/'auth-snapshot.sqlite3'
assert not snapshot.exists(), 'Never overwrite an earlier private backup'
with sqlite3.connect('file:'+str(db_path)+'?mode=ro',uri=True) as source:
    with sqlite3.connect(snapshot) as target:source.backup(target)
snapshot.chmod(0o600)
with sqlite3.connect('file:'+str(snapshot)+'?mode=ro',uri=True) as db:
    assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
restore=private/'restored-snapshot.sqlite3';shutil.copy2(snapshot,restore)
assert hashlib.sha256(snapshot.read_bytes()).digest()==hashlib.sha256(restore.read_bytes()).digest()
with sqlite3.connect('file:'+str(restore)+'?mode=ro',uri=True) as db:
    assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
archives=[('production-source.tar.gz',Path('/opt/autolink-demo')),
          ('uploads.tar.gz',Path(auth_mount['Source']))]
archives += [(name+'.tar.gz',Path(m['Source'])) for name,m in [('caddy-data',next(m for m in prod[1]['Mounts'] if m['Destination']=='/data')),('caddy-config',next(m for m in prod[1]['Mounts'] if m['Destination']=='/config'))]]
counts={}
for filename, source_path in archives:
    archive_path=private/filename
    assert not archive_path.exists()
    with tarfile.open(archive_path,'w:gz') as archive:
        for f in source_path.rglob('*'):
            if not f.is_file() or f.is_symlink():continue
            if filename=='uploads.tar.gz' and ('.sqlite' in f.name or f.name.endswith(('-wal','-shm','-journal'))):continue
            archive.add(f,arcname=str(f.relative_to(source_path)),recursive=False)
    archive_path.chmod(0o600)
    restored=private/(filename+'.restore');restored.mkdir(mode=0o700)
    with tarfile.open(archive_path) as archive:
        archive.extractall(restored,filter='data')
        n=0
        for member in archive:
            if member.isfile():
                assert hashlib.sha256(archive.extractfile(member).read()).digest()==hashlib.sha256((restored/member.name).read_bytes()).digest()
                n+=1
        counts[filename]=n
# Save the actual old images into this private isolation directory, never run them.
for name, container in [('prod-auth-image.tar',prod[0]),('prod-caddy-image.tar',prod[1])]:
    subprocess.run(['docker','image','save','-o',str(private/name),container['Image']],check=True)
    (private/name).chmod(0o600)
files={x.name:{'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in private.iterdir() if x.is_file()}
(proof/'production-backup-proof.json').write_text(json.dumps({'files':files,'restoredArchiveFiles':counts,'sqliteQuickCheck':'ok','productionDataOverwritten':False,'realRecordsServedInQA':False},indent=2))
# Compare old database rows before/after initializer only, inside a disconnected
# disposable container. No web server or mailer thread is started.
compat=private/'compatibility';compat.mkdir(mode=0o700);os.chown(compat,10001,10001)
clone=compat/'copy.sqlite3';shutil.copy2(snapshot,clone);os.chown(clone,10001,10001)
image=json.loads((root/'images.json').read_text())['auth']['reference']
code="""import hashlib,json,sqlite3
from pathlib import Path
from app import AuthService
from buyer_service import BuyerService
from email_auth import EmailAuthService
from trade_service import TradeService
path=Path('/qa/copy.sqlite3')
def rows():
 d=sqlite3.connect(path);names=[r[0] for r in d.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'\")];out={}
 for t in names:
  values=sorted(repr(r) for r in d.execute('SELECT * FROM '+t));out[t]=(len(values),hashlib.sha256(('\\n'.join(values)).encode()).hexdigest())
 d.close();return out
before=rows();a=AuthService(path,'offline-qa-client');EmailAuthService(a,sender=lambda *_:None);BuyerService(a);TradeService(a);after=rows()
assert all(after[t]==value for t,value in before.items()),'Existing rows changed during initialization'
d=sqlite3.connect(path);assert d.execute('PRAGMA quick_check').fetchone()[0]=='ok';d.close()
print(json.dumps({'existingTableCount':len(before),'allExistingTableRowsUnchanged':True,'sqliteQuickCheck':'ok','webServerStarted':False,'mailerThreadStarted':False}))
"""
done=subprocess.run(['docker','run','--rm','--network','none','--cpus','0.5','--memory','512m',
    '--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only','--tmpfs','/tmp:size=32m,mode=1777',
    '-e','MAIL_PROVIDER=','-e','RESEND_API_KEY=','-v',str(compat)+':/qa',image,'python','-c',code],capture_output=True,text=True)
(proof/'production-copy-compatibility.log').write_text(done.stdout+done.stderr)
assert done.returncode==0, 'See private-copy compatibility log'
for label, url in [('https','https://autolinkglobal.com/'),('http','http://autolinkglobal.com/')]:
    done=subprocess.run(['curl','--silent','--show-error','--max-time','15','--http2','-I',url],capture_output=True,text=True,check=True)
    (proof/('external-'+label+'.log')).write_text(done.stdout+done.stderr)
print('READONLY_PRODUCTION_BACKUP_AND_OFFLINE_COPY_VERIFIED; no production deployment')
