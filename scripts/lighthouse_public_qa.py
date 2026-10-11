"""Three cold Lighthouse runs per priority page and viewport on loopback QA."""
import json,os,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parent.parent
out=Path(os.environ.get('LIGHTHOUSE_OUTPUT',root/'tests/results/lighthouse-candidate-20261012'))
out.mkdir(parents=True,exist_ok=True)
cli=Path(os.environ['LIGHTHOUSE_CLI'])
base=os.environ.get('LIGHTHOUSE_BASE','http://127.0.0.1:18081')
pages={'home':'/?lang=zh','model-detail':'/trade/models/zeekr-9x-2026?lang=zh'}
if os.environ.get('LIGHTHOUSE_PAGES'):
    selected=set(os.environ['LIGHTHOUSE_PAGES'].split(','))
    pages={key:value for key,value in pages.items() if key in selected}
summary=[]
for repeat in range(1,4):
    for label,path in pages.items():
        for device in ('mobile','desktop'):
            name=f'{label}-{device}-{repeat}';file=out/(name+'.json')
            cmd=['node',str(cli),base+path,'--only-categories=performance,seo,accessibility,best-practices',
                 '--output=json','--output-path='+str(file),'--chrome-flags=--headless --disable-gpu --no-first-run','--quiet']
            if device=='desktop':cmd.append('--preset=desktop')
            started=time.monotonic()
            try:
                run=subprocess.run(cmd,capture_output=True,text=True,timeout=160)
                (out/(name+'.log')).write_text(run.stderr[-4000:])
                data=json.loads(file.read_text()) if file.exists() else {}
                audit=data.get('audits',{});scores=data.get('categories',{})
                item={'page':label,'device':device,'repeat':repeat,'seconds':round(time.monotonic()-started,1),
                      'exit':run.returncode,'error':data.get('runtimeError'),
                      'performance':scores.get('performance',{}).get('score'),
                      'seo':scores.get('seo',{}).get('score'),
                      'lcpMs':audit.get('largest-contentful-paint',{}).get('numericValue'),
                      'cls':audit.get('cumulative-layout-shift',{}).get('numericValue'),
                      'tbtMs':audit.get('total-blocking-time',{}).get('numericValue')}
            except Exception as exc:item={'page':label,'device':device,'repeat':repeat,'error':str(exc)}
            summary.append(item);print(json.dumps(item),flush=True)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
