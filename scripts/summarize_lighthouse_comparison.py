"""Print medians for the two fixed three-run Lighthouse result sets."""
import json
from pathlib import Path
from statistics import median

root = Path(__file__).resolve().parent.parent / 'tests/results'
sets = {
    name: json.loads((root / f'lighthouse-five-{name}-20261012/summary.json').read_text())
    for name in ('baseline', 'final')
}
pages = ('home', 'model-detail', 'brand-directory', 'model-directory', 'buyer-login')
rows = []
for page in pages:
    for device in ('mobile', 'desktop'):
        row = {'page': page, 'device': device}
        for stage, records in sets.items():
            selected = [r for r in records if r['page'] == page and r['device'] == device]
            assert len(selected) == 3 and all(r['exit'] == 0 and not r['error'] for r in selected)
            row[stage] = {key: median(r[key] for r in selected) for key in ('performance', 'lcpMs', 'tbtMs', 'cls')}
        rows.append(row)
print(json.dumps(rows, ensure_ascii=False, indent=2))
