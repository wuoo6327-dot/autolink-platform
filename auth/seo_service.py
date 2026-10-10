"""Public HTML rendered from the same catalog and publication gates as the API.

No account session is read here. In particular, member prices, direct contacts,
private documents, inquiries and quotes never become part of crawler HTML.
The existing trade application replaces the initial content when it is ready.
"""
from __future__ import annotations

import html
import hashlib
import json
import os
import re
from functools import lru_cache
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from buyer_service import BuyerError

ORIGIN = 'https://autolinkglobal.com'
LANGUAGES = ('en', 'zh', 'ar', 'ru', 'kk', 'uz', 'ko', 'fr', 'sw')
LANGUAGE_TAGS = {language: 'zh-CN' if language == 'zh' else language for language in LANGUAGES}


def asset_version(path):
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=512)
def asset_hash(path, version):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=512)
def asset_json(path, version):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def localized_url(path, language='en'):
    """English and x-default use the existing URL; other languages are explicit."""
    return ORIGIN + path + ('' if language == 'en' else '?lang=' + language)


def sitemap_alternates(node, path, element_tree, languages=LANGUAGES):
    for language in languages:
        element_tree.SubElement(node, '{http://www.w3.org/1999/xhtml}link',
            rel='alternate', hreflang=LANGUAGE_TAGS[language], href=localized_url(path, language))
    element_tree.SubElement(node, '{http://www.w3.org/1999/xhtml}link',
        rel='alternate', hreflang='x-default', href=localized_url(path, 'en' if 'en' in languages else languages[0]))


@lru_cache(maxsize=48)
def read_dictionary(site_root, language, specifications=False):
    root = Path(site_root)
    if specifications:
        if language == 'zh':
            return {}
        file = root / 'locales' / ('specs-' + language + '.json')
        return json.loads(file.read_text(encoding='utf-8')) if file.is_file() else {}
    loader = root / 'assets' / 'business-language-loader.mjs'
    manifest = re.search(r'export const languageFiles\s*=\s*(\{[^\n]+\})\s*;', loader.read_text(encoding='utf-8')) if loader.is_file() else None
    relative = json.loads(manifest[1]).get(language, '') if manifest else ''
    file = root / relative.lstrip('/')
    if not relative or not file.is_file() or not file.resolve().is_relative_to(root.resolve()):
        return {}
    source = file.read_text(encoding='utf-8')
    match = re.search(r'Object\.assign\(window\.AUTOLINK_BUSINESS_RESOURCES\|\|\{\},(\{.*\})\);?\s*$', source, re.S)
    return json.loads(match[1]).get(language, {}).get('translation', {}) if match else {}


class PublicSEOService:
    def __init__(self, trade, site_root=None):
        self.trade = trade
        default = Path(__file__).resolve().parent.parent / 'site'
        self.site_root = Path(site_root or os.environ.get('SEO_SITE_ROOT') or (default if default.is_dir() else '/srv'))

    def index_policy(self, kind, record):
        """Publication quality is checked again, never stored in business tables.

        Source-language references can recover after validated real data arrives.
        Foreign text needs an explicit review bound to the exact public content;
        a dictionary/template alone is not evidence of complete localization.
        """
        reference = self.reference(record) if kind == 'model' else {}
        keys = ('id','brand','model','year','bodyType','energy','description','specifications') if kind == 'model' else ('id','name','country','overview')
        source = {key: record.get(key) for key in keys}
        reference_file = self.site_root/'model-reference'/(str(record.get('id'))+'.json')
        source['modelIds'] = sorted(str(item.get('id')) for item in record.get('models',[])) if kind=='brand' else []
        source['referenceSHA256'] = asset_hash(str(reference_file),asset_version(reference_file)) if kind=='model' and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',str(record.get('id'))) and reference_file.is_file() else None
        # A terminology/dictionary change invalidates the previous content review.
        source['localizationSHA256'] = {
            str(p.relative_to(self.site_root)): asset_hash(str(p),asset_version(p))
            for p in sorted((self.site_root/'locales').glob('specs-*.json'))
        }
        terms = self.site_root/'locales/seo-verified-terms.json'
        source['verifiedTermsSHA256'] = asset_hash(str(terms),asset_version(terms)) if terms.is_file() else None
        fingerprint = hashlib.sha256(json.dumps(source,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        complete = self.reference_complete(record, reference) if kind == 'model' else bool(str(record.get('overview') or '').strip() and record.get('models'))
        review_file = self.site_root/'locales/seo-index-reviews.json'
        try:
            reviews = asset_json(str(review_file),asset_version(review_file)) if review_file.is_file() else {}
        except (ValueError, OSError):
            reviews = {}  # Invalid review material must fail closed.
        if not isinstance(reviews,dict): reviews = {}
        allowed = []
        for language in LANGUAGES:
            kind_reviews = reviews.get(kind,{})
            record_reviews = kind_reviews.get(str(record.get('id')),{}) if isinstance(kind_reviews,dict) else {}
            review = record_reviews.get(language,{}) if isinstance(record_reviews,dict) else {}
            if not isinstance(review,dict): review = {}
            reviewed = (review.get('sourceFingerprint') == fingerprint and
                        bool(str(review.get('reviewedBy') or '').strip()) and
                        bool(str(review.get('evidence') or '').strip()))
            if complete and ((kind == 'model' and language == 'zh') or reviewed):
                if language == 'zh' or not self.untranslated_reference(record,reference,language):
                    allowed.append(language)
        return {'contentComplete':complete,'indexLanguages':allowed,'sourceFingerprint':fingerprint,
                'reason':'content_incomplete' if not complete else 'localization_review_required' if allowed==['zh'] or not allowed else 'reviewed'}

    @staticmethod
    def reference_complete(model, reference):
        if (not model.get('active',True) or not model.get('brandActive',True) or
                reference.get('modelId') != model.get('id') or reference.get('status') != 'available' or
                not reference.get('provider') or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(reference.get('checkedAt','')))):
            return False
        source = urlsplit(str(reference.get('sourceUrl','')))
        if source.scheme != 'https' or not source.hostname or source.username or source.password:
            return False
        try:
            date.fromisoformat(reference['checkedAt'])
        except ValueError:
            return False
        variants = reference.get('variants',reference.get('configurations',[]))
        groups = reference.get('groups',[])
        years = reference.get('availableYears',[])
        if not isinstance(variants,list) or not variants or not isinstance(groups,list) or not groups or not years:
            return False
        if any(type(year) is not int or not 1900 <= year <= 2100 for year in years):
            return False
        selected = variants[:2]
        if any(not isinstance(v,dict) or not v.get('name') or v.get('year') not in years or not isinstance(v.get('values'),dict) for v in selected):
            return False
        rows = [row for group in groups[:3] if isinstance(group,dict) for row in group.get('rows',[])[:12]
                if isinstance(row,dict) and row.get('key') and row.get('label') and not any(term in str(row['label']) for term in ('价格','指导价','报价'))]
        # Structural publication guard, not a claim about Google's word-count rules.
        return len(rows)>=8 and all(sum(v['values'].get(row['key']) is not None and str(v['values'].get(row['key'])).strip() not in ('','—','-') for row in rows)>=8 for v in selected)

    def translated_value(self, value, language):
        value = str(value if value is not None else '—')
        if language == 'zh': return value
        dictionary = read_dictionary(str(self.site_root),language,True)
        file = self.site_root/'locales/seo-verified-terms.json'
        terms = asset_json(str(file),asset_version(file)).get('translations',{}).get(language,{}) if file.is_file() else {}
        # Exact reviewed terms take precedence; never replace arbitrary fragments
        # of trim names or convert numbers/units through a substring translator.
        return terms.get(value,dictionary.get(value,value))

    def untranslated_reference(self, model, reference, language):
        values = [model.get('description') or '',*model.get('specifications',{}).keys(),*model.get('specifications',{}).values()]
        for variant in reference.get('variants',[])[:2]:
            values.append(' '.join(str(x) for x in (variant.get('year'),variant.get('name')) if x))
            values.extend(variant.get('values',{}).values())
        values.extend(group.get('name','') for group in reference.get('groups',[]))
        values.extend(row.get('label','') for group in reference.get('groups',[]) for row in group.get('rows',[]))
        return any(re.search(r'[\u3400-\u9fff]',self.translated_value(value,language)) for value in values)

    def render(self, request_url):
        parsed = urlsplit(request_url)
        path = parsed.path.rstrip('/') or '/'
        query = parse_qs(parsed.query)
        requested = query.get('lang', ['en'])[0]
        language = 'zh' if requested == 'zh-CN' else requested if requested in LANGUAGES else 'en'
        dictionary = read_dictionary(str(self.site_root), language)
        tr = lambda value: str(dictionary.get(value, value))
        e = lambda value: html.escape(str(value if value is not None else ''), quote=True)
        match = re.fullmatch(r'/trade(?:/(models|brands|vehicles|suppliers|compare)(?:/([A-Za-z0-9_-]{1,100}))?)?', path)
        status, graph, image = 200, [], None
        canonical_path = '/trade/vehicles' if path == '/trade' else path
        collection, ident = match.groups() if match else (None, None)
        collection = collection or 'vehicles'
        filtered = any(key != 'lang' for key in query)
        indexable = bool(match) and collection != 'compare' and not filtered
        index_languages = LANGUAGES
        title_key = {'models':'Chinese Vehicle Model References | AUTOLINK',
                     'brands':'Vehicle Brands | AUTOLINK',
                     'vehicles':'Approved Supplier Vehicle Listings | AUTOLINK',
                     'suppliers':'Chinese Vehicle Suppliers | AUTOLINK',
                     'compare':'Compare Vehicles | AUTOLINK'}[collection]
        title = tr(title_key)
        description = tr('AUTOLINK · Connecting Chinese vehicle suppliers and global buyers.')

        def anchor(target, label, secondary=False):
            # Explicit language links remain discoverable without localStorage.
            parts = urlsplit(target)
            params = parse_qs(parts.query)
            if language != 'en':
                params['lang'] = [language]
            suffix = '?' + urlencode(params, doseq=True) if params else ''
            return '<a class="button-link' + (' secondary' if secondary else '') + '" href="' + e(parts.path + suffix) + '">' + e(label) + '</a>'

        def fields(values):
            return '<div class="trade-fields">' + ''.join('<div class="trade-field"><span>' + e(tr(key)) + '</span><strong>' + e(value) + '</strong></div>' for key, value in values if value not in (None, '')) + '</div>'

        def model_card(model):
            target = '/trade/models/' + quote(model['id'], safe='')
            return '<article class="trade-card"><img loading="lazy" decoding="async" src="' + e(self.safe_image(model.get('image'))) + '" alt="' + e(model['brand'] + ' ' + model['model']) + '"><div class="trade-card-body"><span class="eyebrow">' + e(model['brand']) + '</span><h2>' + e(model['model']) + '</h2><p>' + e(model.get('year') or tr('Year unspecified')) + ' · ' + e(tr(model.get('energy', ''))) + ' · ' + e(tr(model.get('bodyType', ''))) + '</p>' + anchor(target, tr('View model reference')) + '</div></article>'

        def vehicle_card(vehicle):
            return '<article class="trade-card"><img loading="lazy" decoding="async" src="' + e(self.safe_image(vehicle.get('image'))) + '" alt="' + e(vehicle['brand'] + ' ' + vehicle['model']) + '"><div class="trade-card-body"><span class="eyebrow">' + e(vehicle['supplier_name']) + '</span><h2>' + e(vehicle['brand'] + ' ' + vehicle['model']) + '</h2><p>' + e(vehicle.get('model_year') or '') + ' · ' + e(vehicle.get('trim') or tr(vehicle.get('energy_type', ''))) + '</p><p>' + e(tr('Supplier quote pending')) + '</p>' + anchor('/trade/vehicles/' + quote(vehicle['id'], safe=''), tr('View trade details')) + '</div></article>'

        try:
            if not match or collection == 'compare' and ident:
                raise BuyerError(404, 'Page not found.')
            if ident and collection == 'models':
                model = self.trade.catalog.get(ident)
                if not model or not model['active'] or not model['brandActive']:
                    raise BuyerError(404, 'Model not found.')
                index_languages = self.index_policy('model',model)['indexLanguages']
                indexable = indexable and language in index_languages
                name = ' '.join(str(value) for value in (model['brand'], model['model'], model.get('year')) if value)
                title = tr('{model} Model Reference | AUTOLINK').replace('{model}', name)
                description = name + ' · ' + tr('Model reference · not a supplier inventory offer.') + ' ' + description
                image = self.safe_image(model.get('image'))
                content = '<div class="trade-intro"><div><span class="eyebrow">' + e(tr('MODEL REFERENCE · NOT A STOCK OFFER')) + '</span><h1>' + e(model['brand'] + ' ' + model['model']) + '</h1><p>' + e(tr('This catalogue entry describes a model only. Confirm the exact trim, steering, specification, stock and price with an approved supplier. No supplier inventory or quote is implied.')) + '</p></div></div><div class="trade-detail"><div><img class="trade-hero-image" src="' + e(image) + '" alt="' + e(name) + '"></div><div>' + fields([('Brand',model['brand']),('Model',model['model']),('Year',model.get('year') or ', '.join(map(str,self.reference(model).get('availableYears',[]))) or tr('Year unspecified')),('Energy',tr(model['energy'])),('Body type',tr(model['bodyType'])),*model.get('specifications',{}).items()]) + ('<p>' + e(model['description']) + '</p>' if model.get('description') else '') + anchor('/trade/vehicles?' + urlencode({'brand':model['brand'],'model':model['model']}), tr('Find approved supplier offers')) + '</div></div>'
                content += self.reference_parameters(model, language, tr)
                graph.append({'@type':'ProductModel','name':name,'url':localized_url(canonical_path,language),'brand':{'@type':'Brand','name':model['brand']},'description':tr('Model reference · not a supplier inventory offer.')})
            elif ident and collection == 'brands':
                brand = self.trade.catalog.brand(ident)
                index_languages = self.index_policy('brand',brand)['indexLanguages']
                indexable = indexable and language in index_languages
                title = tr('{brand} Vehicles for Export from China | AUTOLINK').replace('{brand}',brand['name'])
                description = brand['name'] + ' · ' + description
                content = '<div class="trade-intro"><div><h1>' + e(brand['name']) + '</h1><p>' + e(brand.get('overview') or tr('Browse model references and reviewed supplier offers.')) + '</p></div></div><div class="trade-grid">' + ''.join(model_card(model) for model in brand['models']) + '</div>'
            elif ident and collection == 'vehicles':
                vehicle = self.trade.vehicle(ident,public=True)
                # Whitelisted fields only: no serialized row or member price.
                name = ' '.join(str(value) for value in (vehicle['brand'],vehicle['model'],vehicle.get('model_year')) if value)
                title = tr('{vehicle} for Export from China | AUTOLINK').replace('{vehicle}',name)
                description = name + ' · ' + description
                image = self.safe_image(vehicle.get('image'))
                content = '<div class="trade-detail"><div><img class="trade-hero-image" src="' + e(image) + '" alt="' + e(name) + '"></div><div><h1>' + e(name) + '</h1>' + fields([('Trim',vehicle.get('trim')),('MOQ',vehicle.get('moq')),('Stock',vehicle.get('stock')),('Steering',vehicle.get('steering')),('Incoterm',vehicle.get('incoterm')),('Export port',vehicle.get('origin_port')),('Lead time',vehicle.get('lead_time'))]) + '<p>' + e(tr('Supplier quote pending')) + '</p><p>' + e(vehicle.get('description') or tr('Final vehicle specification and availability must be confirmed directly with the supplier.')) + '</p>' + anchor('/trade/suppliers/' + quote(vehicle['supplier_id'],safe=''),tr('View Supplier')) + '</div></div>'
                graph.append({'@type':'Vehicle','name':name,'url':localized_url(canonical_path,language),'brand':{'@type':'Brand','name':vehicle['brand']},'model':vehicle['model']})
            elif ident and collection == 'suppliers':
                supplier = self.trade.public_supplier(ident)
                if not supplier:
                    raise BuyerError(404,'Supplier not found.')
                title = tr('{supplier} | Chinese Vehicle Supplier | AUTOLINK').replace('{supplier}',supplier['company_name'])
                description = supplier['company_name'] + ' · ' + description
                content = '<div class="trade-intro"><div><h1>' + e(supplier['company_name']) + '</h1><p>' + e(supplier.get('description') or tr('No overview available.')) + '</p></div></div>' + fields([('Location',', '.join(value for value in (supplier.get('city'),supplier.get('country')) if value)),('Main brands',supplier.get('main_brands')),('Main markets',supplier.get('main_markets'))]) + anchor('/trade/vehicles?' + urlencode({'supplierId':ident}),tr('View this supplier’s vehicles'))
                graph.append({'@type':'Organization','name':supplier['company_name'],'url':localized_url(canonical_path,language)})
            elif collection == 'models':
                models = self.trade.catalog.models()
                keyword = query.get('keyword',[''])[0].strip().casefold()
                brand, body = query.get('brand',[''])[0],query.get('bodyType',[''])[0]
                models = [model for model in models if (not brand or model['brand']==brand) and (not body or model['bodyType']==body) and keyword in (model['brand']+' '+model['model']).casefold()]
                try: page=max(1,int(query.get('page',['1'])[0]))
                except ValueError: page=1
                pages=max(1,(len(models)+23)//24);page=min(page,pages)
                rows=models[(page-1)*24:page*24]
                content = '<div class="trade-intro"><div><h1>' + e(tr('Explore Chinese vehicle models.')) + '</h1><p>' + e(tr('Model references help you research vehicles. They are not supplier inventory, availability or an offer to sell.')) + '</p></div></div><p class="trade-results">' + str(len(models)) + ' ' + e(tr('Model references')) + '</p><div class="trade-grid">' + ''.join(model_card(model) for model in rows) + '</div>'
                content += '<nav class="model-directory-page">' + ''.join(anchor('/trade/models?'+urlencode({**{key:values[0] for key,values in query.items()},'page':number}),str(number),True) for number in range(1,pages+1)) + '</nav>'
            elif collection == 'brands':
                content = '<h1>' + e(tr('Explore vehicle brands.')) + '</h1><div class="trade-grid">' + ''.join('<article class="trade-card"><div class="trade-card-body"><h2>' + e(brand['name']) + '</h2><p>' + str(brand['model_count']) + ' ' + e(tr('Model references')) + '</p>' + anchor('/trade/brands/'+quote(brand['id'],safe=''),tr('Explore brand')) + '</div></article>' for brand in self.trade.catalog.brands()) + '</div>'
            elif collection == 'suppliers':
                suppliers = self.trade.supplier_list(public=True)
                content = '<h1>' + e(tr('Chinese vehicle suppliers.')) + '</h1>' + ''.join('<section class="panel"><h2>' + e(supplier['company_name']) + '</h2><p>' + e(supplier.get('description') or '') + '</p>' + anchor('/trade/suppliers/'+quote(supplier['id'],safe=''),tr('View supplier')) + '</section>' for supplier in suppliers)
                if not suppliers: content += '<p class="empty">' + e(tr('Suppliers appear here when approved stock is published.')) + '</p>'
            elif collection == 'compare':
                content='<h1>' + e(tr('Compare Vehicles')) + '</h1><p>' + e(tr('Select vehicles to compare.')) + '</p>'
            else:
                allowed=('keyword','brand','model','vehicleType','energyType','condition','steering','incoterm','year','minStock')
                filters={key:query[key][0] for key in allowed if key in query}
                supplier_id=query.get('supplierId',[None])[0]
                vehicles=self.trade.vehicle_rows(public=True,limit=25,supplier_id=supplier_id,filters=filters)
                content='<h1>' + e(tr('Supplier vehicles for global trade.')) + '</h1><div class="trade-grid">' + ''.join(vehicle_card(vehicle) for vehicle in vehicles) + '</div>'
                if not vehicles: content += '<p class="empty">' + e(tr('No matching supplier vehicles.')) + '</p>'
        except BuyerError as error:
            status=error.status if error.status in (400,403,404) else 500
            indexable=False;graph=[];image=None
            title=tr('Page Not Found | AUTOLINK') if status==404 else tr('Unable to Load Page | AUTOLINK')
            content='<h1>' + e(tr('404 · Page not found') if status==404 else tr('Unable to load. Please reload.')) + '</h1>' + anchor('/trade/models',tr('Model references'))
        shell=(self.site_root/'trade'/'index.html').read_text(encoding='utf-8')
        canonical=localized_url(canonical_path,language)
        shell=re.sub(r'<html\s+lang="[^"]*"', '<html lang="'+LANGUAGE_TAGS[language]+'" dir="'+('rtl' if language=='ar' else 'ltr')+'"',shell,count=1)
        shell=re.sub(r'<title>.*?</title>', lambda _: '<title>'+e(title)+'</title>',shell,count=1,flags=re.S)
        shell=re.sub(r'<meta name="description" content="[^"]*">',lambda _: '<meta name="description" content="'+e(description[:320])+'">',shell,count=1)
        metadata='<link rel="canonical" href="'+e(canonical)+'"><meta name="robots" content="'+('index, follow' if indexable else 'noindex, follow')+'"><meta property="og:title" content="'+e(title)+'"><meta property="og:description" content="'+e(description[:320])+'"><meta property="og:url" content="'+e(canonical)+'">'
        if indexable:
            metadata+=''.join('<link rel="alternate" hreflang="'+LANGUAGE_TAGS[code]+'" href="'+e(localized_url(canonical_path,code))+'">' for code in index_languages)+'<link rel="alternate" hreflang="x-default" href="'+e(localized_url(canonical_path,'en' if 'en' in index_languages else index_languages[0]))+'">'
        if image and indexable:metadata+='<meta property="og:image" content="'+e(ORIGIN+image if image.startswith('/') else image)+'">'
        if graph and indexable:metadata+='<script id="autolink-public-jsonld" type="application/ld+json">'+json.dumps({'@context':'https://schema.org','@graph':graph},ensure_ascii=False).replace('<','\\u003c')+'</script>'
        shell=shell.replace('</head>',metadata+'</head>',1)
        navigation=''.join(anchor(target,tr(label),True) for target,label in [('/','Home'),('/trade/models','Model references'),('/trade/brands','Brands'),('/trade/vehicles','Supplier Vehicles'),('/trade/suppliers','Suppliers')])
        body='<header class="trade-head"><div class="trade-head-inner"><a class="brand" href="/">AUTOLINK</a><nav class="trade-nav">'+navigation+'</nav></div></header><main class="trade-main" id="main">'+content+'</main>'
        shell=re.sub(r'<div id="app">.*?</div></div>',lambda _: '<div id="app" data-ssr="true">'+body+'</div>',shell,count=1,flags=re.S)
        return status,shell.encode('utf-8')

    @staticmethod
    def safe_image(value):
        value=str(value or '/favicon.svg')
        parsed=urlsplit(value)
        if value.startswith('/') and not value.startswith('//') and '\\' not in value and '..' not in parsed.path.split('/'):
            return value
        if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password:
            return value
        return '/favicon.svg'

    def reference(self, model):
        # Stored catalog IDs must never become filesystem traversal.
        ident = str(model['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', ident): return {}
        file = self.site_root / 'model-reference' / (ident + '.json')
        if not file.is_file(): return {}
        try:
            data = asset_json(str(file),asset_version(file))
        except (ValueError,OSError):
            return {}
        if not isinstance(data,dict): return {}
        return data if data.get('modelId') == ident else {}

    def reference_parameters(self,model,language,tr):
        """Visible, bounded manufacturer reference parameters; never import prices."""
        data=self.reference(model)
        dictionary=read_dictionary(str(self.site_root),language,True)
        def source(value):
            value=str(value if value is not None and value!='' else '—')
            value=self.translated_value(value,language)
            return html.escape(re.sub(r'\d+(?:\.\d+)?\s*(?:万元|元)',tr('Supplier quote pending'),value),quote=True)
        configs=data.get('variants',data.get('configurations',[]))
        configs=[config for config in configs if isinstance(config,dict)][:2]
        if not configs:return ''
        heading={'en':'Specifications','zh':'配置参数','ar':'المواصفات','ru':'Характеристики','kk':'Сипаттамалар','uz':'Xususiyatlar','ko':'제원','fr':'Caractéristiques','sw':'Vipimo'}[language]
        tables=[]
        for group in data.get('groups',[])[:3]:
            rows=[row for row in group.get('rows',[])[:12] if not any(term in str(row.get('label','')) for term in ('价格','指导价','报价'))]
            tables.append('<section class="reference-group"><h3>'+source(group.get('name'))+'</h3><div class="reference-table-scroll"><table class="reference-table"><thead><tr><th>'+html.escape(heading)+'</th>'+''.join('<th>'+source(' '.join(str(value) for value in (config.get('year'),config.get('name')) if value))+'</th>' for config in configs)+'</tr></thead><tbody>'+''.join('<tr><th>'+source(row.get('label'))+'</th>'+''.join('<td>'+source(config.get('values',{}).get(row.get('key')) )+'</td>' for config in configs)+'</tr>' for row in rows)+'</tbody></table></div></section>')
        return '<section class="model-reference" data-ssr-reference><h2>'+html.escape(heading)+'</h2><p class="trade-note">'+html.escape(tr('Model reference · not a supplier inventory offer.'))+'</p>'+''.join(tables)+'</section>'
