"""Prove the candidate bundle is a narrow transform of the live JS asset.

The checked-in bundle has no source map or original React source. The three
reviewed transformations are evaluated from their literal patch definitions;
the patch modules themselves are never imported, since importing edits files.
"""

import argparse
import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha(data):
    return hashlib.sha256(data.encode()).hexdigest()


def literals(path):
    result = {}
    for statement in ast.parse(path.read_text()).body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                try:
                    result[target.id] = ast.literal_eval(statement.value)
                except (ValueError, TypeError):
                    pass
    return result


def replace_once(source, old, new, label):
    if source.count(old) != 1:
        raise RuntimeError(f'Unexpected {label} signature: {source.count(old)} matches')
    return source.replace(old, new, 1)


def verify(production_bundle, candidate):
    original = Path(production_bundle).read_text()
    cache = literals(ROOT / 'scripts/patch_translation_cache.py')
    hotpath = literals(ROOT / 'scripts/patch_round12_translation_hotpath.py')
    transformed = replace_once(original, 'import "/i18n/business-resources.js";\n', '',
                               'full nine-language dictionary import')
    transformed = replace_once(transformed, cache['old'], cache['new'], 'translation memo')
    transformed = replace_once(transformed, hotpath['old_dictionary'],
                               hotpath['new_dictionary'], 'case-folded lookup map')
    transformed = replace_once(transformed, hotpath['old_scan'], hotpath['new_scan'],
                               'translation hot path')
    transformed = replace_once(transformed, 'zl={hero:"/images/zeekr9x-villa.jpg",film:',
                               'zl={hero:"/images/zeekr9x-villa.webp",film:', 'desktop hero')
    candidate_text = Path(candidate).read_text()
    if transformed != candidate_text:
        raise RuntimeError('Candidate JS contains unreviewed changes beyond the narrow transforms')
    return {'productionSHA256': sha(original), 'candidateSHA256': sha(candidate_text),
            'productionBytes': len(original.encode()), 'candidateBytes': len(candidate_text.encode()),
            'verifiedTransforms': ['remove nine-language import', 'memoize active dictionary',
                                   'precompute case-folded lookup', 'reuse active lookup map',
                                   'use smaller full-resolution desktop hero']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--production-bundle', required=True)
    parser.add_argument('--candidate', default=str(ROOT / 'site/assets/index-autolink-membership-apply-pricing.js'))
    args = parser.parse_args()
    import json
    print(json.dumps(verify(args.production_bundle, args.candidate), indent=2))
