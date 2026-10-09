"""Synthetic scanner payloads only; no credential or production fixture."""
import importlib.util
import json
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('autolink_security_scan',Path(__file__).resolve().parents[1]/'security_scan.py')
scan=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(scan)

class RedactionTests(unittest.TestCase):
    def test_gitleaks_discards_match_secret_and_author(self):
        marker='SYNTHETIC_PRIVATE_VALUE_DO_NOT_PUBLISH'
        raw=[{'RuleID':'test-rule','File':'auth/example.py','StartLine':12,'Secret':marker,'Match':'key='+marker,'Author':marker,'Email':marker,'Commit':'abc123'}]
        result=scan.redact_gitleaks(raw,Path('/isolated'))
        self.assertNotIn(marker,json.dumps(result))
        self.assertEqual(result[0]['start_line'],12)
        self.assertEqual(result[0]['secret'],'[REDACTED]')
    def test_trivy_discards_source_snippets_and_raw_secret(self):
        marker='SYNTHETIC_PRIVATE_VALUE_DO_NOT_PUBLISH'
        raw={'Results':[{'Target':'auth/Dockerfile','Class':'config','MisconfSummary':{'Failures':1},'Misconfigurations':[{'ID':'DS-TEST','Severity':'HIGH','Status':'FAIL','Description':marker,'CauseMetadata':{'StartLine':5,'EndLine':5,'Code':{'Lines':[{'Content':marker}]}}}],'Secrets':[{'RuleID':'test-rule','Severity':'MEDIUM','Match':marker,'StartLine':9}]}]}
        findings,coverage=scan.redact_trivy(raw,Path('/isolated'))
        self.assertNotIn(marker,json.dumps([findings,coverage]))
        self.assertEqual(findings[0]['start_line'],5)
        self.assertEqual(findings[1]['secret'],'[REDACTED]')
        self.assertEqual(coverage['configuration_files'],['auth/Dockerfile'])
    def test_dependency_versions_remain_without_descriptions(self):
        raw={'Results':[{'Target':'auth/requirements.txt','Class':'lang-pkgs','Vulnerabilities':[{'VulnerabilityID':'CVE-SYNTHETIC','Severity':'CRITICAL','PkgName':'example','InstalledVersion':'1.0','FixedVersion':'1.1','Description':'SYNTHETIC_PRIVATE_VALUE_DO_NOT_PUBLISH'}]}]}
        findings,coverage=scan.redact_trivy(raw,Path('/isolated'))
        self.assertEqual(findings[0]['fixed_version'],'1.1')
        self.assertEqual(coverage['dependency_manifests'],['auth/requirements.txt'])
        self.assertNotIn('Description',findings[0])
    def test_outside_paths_and_url_credentials_are_hidden(self):
        self.assertEqual(scan.safe_path('/private/file',Path('/isolated')),'[outside scan root]')
        self.assertEqual(scan.safe_text('https://user:synthetic@host/path'),'https://[REDACTED]@host/path')

if __name__=='__main__':unittest.main()
