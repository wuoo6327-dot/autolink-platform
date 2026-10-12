"""Remove a measured O(dictionary-size) lookup from the frozen UI bundle.

The repository contains a compiled Vite asset, not its React source. Exact
signatures make this narrow patch fail if the upstream artifact changes.
"""
from pathlib import Path

bundle = Path(__file__).resolve().parent.parent / "site/assets/index-autolink-membership-apply-pricing.js"
source = bundle.read_text()
old_dictionary = ('const d={...b,...v};autolinkTranslationMemo.set(i,'
                  '{business:b,membership:v,dictionary:d});return d}')
new_dictionary = ('const d={...b,...v},lowercase=new Map;'
                  'for(const [key,value] of Object.entries(d)){'
                  'const folded=key.toLowerCase();if(!lowercase.has(folded))lowercase.set(folded,value)}'
                  'autolinkTranslationMemo.set(i,{business:b,membership:v,dictionary:d,lowercase});return d}')
old_scan = ('const w=Object.keys(s).find(f=>f.toLowerCase()===y[1].toLowerCase());'
            'return`${s[x]||x} ${w?s[w]:y[1]}${x==="Show"?" "+(s["stock listings"]||"listings"):""}`')
new_scan = ('const w=autolinkTranslationMemo.get(i).lowercase.get(y[1].toLowerCase());'
            'return`${s[x]||x} ${w===void 0?y[1]:w}${x==="Show"?" "+(s["stock listings"]||"listings"):""}`')
for old in (old_dictionary, old_scan):
    if source.count(old) != 1:
        raise SystemExit("Unexpected translator signature; inspect before editing")
bundle.write_text(source.replace(old_dictionary, new_dictionary, 1).replace(old_scan, new_scan, 1))
