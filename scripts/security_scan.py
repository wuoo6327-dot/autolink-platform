#!/usr/bin/env python3
"""Run local official scanners and publish only whitelisted, redacted metadata.

Exit 0 = completed without blocking findings; 1 = blocking findings;
2 = missing/incompatible scanner, missing scan coverage, or incomplete scan.
Scanner stderr and source snippets are deliberately not copied to CI logs.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


BLOCKING = {'HIGH', 'CRITICAL'}


def safe_text(value):
    text = re.sub(r'[\x00-\x1f\x7f]', ' ', str(value or ''))
    text = re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', text)
    return re.sub(r'(?i)(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|re_[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})', '[REDACTED]', text)[:600]


def safe_path(value, root):
    value = safe_text(value)
    try:
        path = Path(value)
        if path.is_absolute():
            return str(path.resolve().relative_to(root))
    except (ValueError, OSError):
        return '[outside scan root]'
    return value


def redact_gitleaks(raw, root):
    return [{'scanner':'gitleaks', 'category':'secret', 'severity':'HIGH',
             'rule':safe_text(item.get('RuleID')), 'file':safe_path(item.get('File'),root),
             'start_line':item.get('StartLine'), 'end_line':item.get('EndLine'),
             'commit':safe_text(item.get('Commit')), 'secret':'[REDACTED]'}
            for item in raw if isinstance(item,dict)]


def redact_trivy(raw, root):
    findings, coverage = [], {'dependency_manifests':[], 'configuration_files':[]}
    for result in raw.get('Results', []):
        target = safe_path(result.get('Target'),root)
        if result.get('Class') == 'lang-pkgs': coverage['dependency_manifests'].append(target)
        if result.get('MisconfSummary') is not None or result.get('Misconfigurations') is not None:
            coverage['configuration_files'].append(target)
        for category, key in [('vulnerability','Vulnerabilities'),('misconfiguration','Misconfigurations'),('secret','Secrets')]:
            for item in result.get(key) or []:
                if category=='misconfiguration' and item.get('Status')!='FAIL': continue
                record={'scanner':'trivy','category':category,'file':target,
                        'severity':safe_text(item.get('Severity')).upper(),
                        'rule':safe_text(item.get('VulnerabilityID') or item.get('ID') or item.get('RuleID'))}
                if category=='vulnerability':
                    record.update(package=safe_text(item.get('PkgName')),
                                  installed_version=safe_text(item.get('InstalledVersion')),
                                  fixed_version=safe_text(item.get('FixedVersion')))
                elif category=='misconfiguration':
                    cause=item.get('CauseMetadata') or {}
                    record.update(start_line=cause.get('StartLine'),end_line=cause.get('EndLine'))
                else:
                    record.update(start_line=item.get('StartLine'),end_line=item.get('EndLine'),secret='[REDACTED]')
                # Match, Secret, code snippets, descriptions, author/email and raw
                # environment values are never copied out of a scanner payload.
                findings.append(record)
    return findings, coverage


def run(command, root, timeout=900):
    return subprocess.run(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,timeout=timeout,check=False)


def version(binary, name, expected, root):
    output=run([binary,'version' if name=='gitleaks' else '--version'],root,30)
    return output.returncode==0 and bool(re.search(r'(?<![0-9.])'+re.escape(expected)+r'(?![0-9.])',output.stdout))


def scan(name, root, manifest, history, temp):
    binary=shutil.which(name)
    if not binary:return {'tool':name,'state':'not_run','error':'TOOL_NOT_INSTALLED','findings':[]}
    if not version(binary,name,manifest[name]['version'],root):
        return {'tool':name,'state':'not_run','error':'TOOL_VERSION_MISMATCH','findings':[]}
    if name=='gitleaks':
        if history:
            git=run(['git','rev-parse','--show-toplevel'],root,30)
            if git.returncode or Path(git.stdout.strip()).resolve()!=root:
                return {'tool':name,'state':'not_run','error':'HISTORY_REQUIRES_REPOSITORY_ROOT','findings':[]}
        report=Path(temp)/'gitleaks-redacted.json'
        command=[binary,'git' if history else 'dir',str(root),'--config',str(root/'security/gitleaks.toml'),
                 '--redact=100','--no-banner','--no-color','--ignore-gitleaks-allow',
                 '--gitleaks-ignore-path',str(Path(temp)/'empty.ignore'),
                 '--report-format','json','--report-path',str(report),'--exit-code','1','--timeout','600']
        if history:command.extend(['--log-opts=--all'])
        output=run(command,root)
        if output.returncode not in (0,1) or not report.is_file():
            return {'tool':name,'state':'error','error':'SCANNER_FAILED','findings':[]}
        raw=json.loads(report.read_text())
        if not isinstance(raw,list):raise ValueError('Invalid Gitleaks result')
        findings=redact_gitleaks(raw,root)
        if output.returncode==1 and not findings:
            return {'tool':name,'state':'error','error':'INCOMPLETE_SCAN','findings':[]}
        return {'tool':name,'state':'completed','mode':'history' if history else 'directory','findings':findings}
    cache=root/'.security-cache'/'trivy'
    cache.mkdir(parents=True,exist_ok=True,mode=0o700)
    command=[binary,'fs','--config',str(root/'security/trivy.yaml'),'--cache-dir',str(cache),
             '--ignorefile',str(Path(temp)/'empty.ignore'),str(root)]
    output=run(command,root)
    if output.returncode not in (0,1):return {'tool':name,'state':'error','error':'SCANNER_FAILED','findings':[]}
    raw=json.loads(output.stdout)
    if not isinstance(raw,dict) or 'Results' not in raw:raise ValueError('Invalid Trivy result')
    findings,coverage=redact_trivy(raw,root)
    required_manifest=(root/'auth/requirements.txt').is_file()
    if required_manifest and 'auth/requirements.txt' not in coverage['dependency_manifests']:
        return {'tool':name,'state':'error','error':'NO_REQUIREMENTS_COVERAGE','findings':findings,'coverage':coverage}
    return {'tool':name,'state':'completed','mode':'filesystem','findings':findings,'coverage':coverage}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool',choices=['all','gitleaks','trivy'],default='all')
    parser.add_argument('--history',action='store_true',help='Gitleaks all local Git refs; requires this checkout to be the Git root')
    parser.add_argument('--output',default='security-reports')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent
    destination=(root/args.output).resolve()
    if destination==root or root not in destination.parents:
        parser.error('The sanitized output must be a subdirectory of this isolated checkout.')
    destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    manifest=json.loads((root/'security/tool-versions.json').read_text())
    tools=['gitleaks','trivy'] if args.tool=='all' else [args.tool]
    results=[]
    with tempfile.TemporaryDirectory(prefix='autolink-scan-private-') as temp:
        ignore=Path(temp)/'empty.ignore';ignore.write_text('');os.chmod(ignore,0o600)
        for name in tools:
            try:result=scan(name,root,manifest,args.history,temp)
            except (OSError,ValueError,subprocess.TimeoutExpired):
                result={'tool':name,'state':'error','error':'INCOMPLETE_SCAN','findings':[]}
            result['version_expected']=manifest[name]['version'];results.append(result)
            print(name+': '+result['state']+'; findings='+str(len(result['findings']))+(' ; '+result['error'] if 'error' in result else ''))
    blocked=[finding for result in results for finding in result['findings']
             if finding['category']=='secret' or finding['severity'] in BLOCKING]
    incomplete=any(result['state']!='completed' for result in results)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'source_scan_only':True,'production_accessed':False,
            'state':'incomplete' if incomplete else 'blocked' if blocked else 'passed',
            'blocking_findings':len(blocked),'results':results}
    file=destination/(args.tool+('-history' if args.history else '')+'-sanitized.json')
    file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');os.chmod(file,0o600)
    print('Sanitized report: '+str(file.relative_to(root)))
    return 2 if incomplete else 1 if blocked else 0


if __name__=='__main__':
    raise SystemExit(main())
