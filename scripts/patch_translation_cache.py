"""Apply the measured home-render translation fix to the checked-in web bundle.

The original translator copied both language dictionaries for every string and
attribute. Keep the same lookup precedence while rebuilding only when a loaded
dictionary object changes. The exact signature makes a changed upstream bundle
fail closed instead of silently patching the wrong code.
"""
from pathlib import Path

bundle = Path(__file__).resolve().parent.parent / "site/assets/index-autolink-membership-apply-pricing.js"
source = bundle.read_text()
old = 'function ba(a,i){if(i==="en"||!a.trim())return a;const c=a.replace(/\\s+/g," ").trim(),s={...(window.AUTOLINK_BUSINESS_RESOURCES?.[i]?.translation||{}),...(vb[i]||{})},m=s[c]||s[c.toLowerCase()];'
new = ('const autolinkTranslationMemo=new Map;'
       'function autolinkTranslationDictionary(i){'
       'const b=window.AUTOLINK_BUSINESS_RESOURCES?.[i]?.translation||{},'
       'v=vb[i]||{},p=autolinkTranslationMemo.get(i);'
       'if(p&&p.business===b&&p.membership===v)return p.dictionary;'
       'const d={...b,...v};'
       'autolinkTranslationMemo.set(i,{business:b,membership:v,dictionary:d});'
       'return d}'
       'function ba(a,i){if(i==="en"||!a.trim())return a;'
       'const c=a.replace(/\\s+/g," ").trim(),s=autolinkTranslationDictionary(i),m=s[c]||s[c.toLowerCase()];')
if old not in source or source.count(old) != 1:
    raise SystemExit("Expected translator signature exactly once; inspect the bundle before patching")
bundle.write_text(source.replace(old, new, 1))
