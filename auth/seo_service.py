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

    @staticmethod
    def catalog_digest(model):
        fields = ('id','brand','model','year','bodyType','energy','image','description',
                  'specifications','active','brandActive')
        payload = {key:model.get(key) for key in fields}
        return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,
            separators=(',',':')).encode()).hexdigest()

    def english_editorial(self, model, reference=None):
        """Return a reviewed English entry only while its exact source still matches.

        A new or edited reference automatically withdraws the English approval;
        catalogue publication and supplier approval remain independent gates.
        """
        reference = reference if reference is not None else self.reference(model)
        file = self.site_root/'locales/seo-model-en-reviewed.json'
        source = self.site_root/'model-reference'/(str(model.get('id'))+'.json')
        if not file.is_file() or not source.is_file() or not self.reference_complete(model, reference):
            return None
        try:
            entry = asset_json(str(file),asset_version(file)).get(model['id'])
            if not isinstance(entry,dict) or entry.get('status') != 'approved': return None
            if entry.get('referenceSHA256') != asset_hash(str(source),asset_version(source)): return None
            if entry.get('catalogSHA256') != self.catalog_digest(model): return None
            if entry.get('modelName') != model['model'] or entry.get('brandName') != model['brand']: return None
            first = reference['variants'][0]
            if entry.get('sourceTrim') != first['name'] or first['year'] not in reference['availableYears']: return None
            prose = [entry.get(key,'') for key in ('intro','trim','reviewedBy','evidence')]
            if any(not isinstance(value,str) or not value.strip() for value in prose): return None
            if re.search(r'[\u3400-\u9fff]', ' '.join(prose[:2])): return None
            if len(entry['intro'].split()) < 18 or not entry['evidence'].startswith('source:'): return None
            if len(self.english_specifications(reference)) < 5: return None
            return entry
        except (ValueError, OSError, KeyError, TypeError):
            return None

    @staticmethod
    def english_specifications(reference):
        """Exact numeric facts and a controlled powertrain term from one trim."""
        labels = {
            '长度(mm)':'Length (mm)', '宽度(mm)':'Width (mm)',
            '高度(mm)':'Height (mm)', '轴距(mm)':'Wheelbase (mm)',
            '座位数(个)':'Seats', '最大功率(kW)':'Maximum power (kW)',
            'CLTC纯电续航里程(km)':'CLTC electric range (km)',
            'WLTC纯电续航里程(km)':'WLTC electric range (km)',
            '电池能量(kWh)':'Battery capacity (kWh)',
            'WLTC综合油耗(L/100km)':'WLTC fuel consumption (L/100 km)',
        }
        variant = reference.get('variants',[{}])[0]
        facts = {}
        for group in reference.get('groups',[]):
            for row in group.get('rows',[]):
                label = labels.get(row.get('label'))
                if not label or label in facts: continue
                value = str(variant.get('values',{}).get(row.get('key')) or '').strip().lstrip('● ').strip()
                if re.fullmatch(r'\d+(?:\.\d+)?',value): facts[label] = value
        powertrains={'汽油':'Gasoline','纯电动':'Battery electric',
                     '插电式混合动力':'Plug-in hybrid','油电混合':'Hybrid'}
        for group in reference.get('groups',[]):
            for row in group.get('rows',[]):
                if row.get('label') == '能源类型':
                    value=variant.get('values',{}).get(row.get('key'))
                    if isinstance(value,str) and value in powertrains:facts['Powertrain']=powertrains[value]
                    return facts
        return facts

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
            editorial = self.english_editorial(record,reference) if kind == 'model' and language == 'en' and complete else None
            if complete and ((kind == 'model' and language == 'zh') or editorial or reviewed):
                if language == 'zh' or editorial or not self.untranslated_reference(record,reference,language):
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
            return '<article class="trade-card"><img loading="lazy" decoding="async" src="' + e(self.safe_image(model.get('image'))) + '" alt="' + e(model['model'] if model['model'].casefold().startswith(model['brand'].casefold()+' ') else model['brand'] + ' ' + model['model']) + '"><div class="trade-card-body"><span class="eyebrow">' + e(model['brand']) + '</span><h2>' + e(model['model']) + '</h2><p>' + e(model.get('year') or tr('Year unspecified')) + ' · ' + e(tr(model.get('energy', ''))) + ' · ' + e(tr(model.get('bodyType', ''))) + '</p>' + anchor(target, tr('View model reference')) + '</div></article>'

        def vehicle_card(vehicle):
            return '<article class="trade-card"><img loading="lazy" decoding="async" src="' + e(self.safe_image(vehicle.get('image'))) + '" alt="' + e(vehicle['brand'] + ' ' + vehicle['model']) + '"><div class="trade-card-body"><span class="eyebrow">' + e(vehicle['supplier_name']) + '</span><h2>' + e(vehicle['brand'] + ' ' + vehicle['model']) + '</h2><p>' + e(vehicle.get('model_year') or '') + ' · ' + e(vehicle.get('trim') or tr(vehicle.get('energy_type', ''))) + '</p><p>' + e(tr('Supplier quote pending')) + '</p>' + anchor('/trade/vehicles/' + quote(vehicle['id'], safe=''), tr('View trade details')) + '</div></article>'

        try:
            if not match or collection == 'compare' and ident:
                raise BuyerError(404, 'Page not found.')
            if ident and collection == 'models':
                model = self.trade.catalog.get(ident)
                if not model or not model['active'] or not model['brandActive']:
                    raise BuyerError(404, 'Model not found.')
                reference = self.reference(model)
                editorial = self.english_editorial(model,reference) if language == 'en' else None
                index_languages = self.index_policy('model',model)['indexLanguages']
                indexable = indexable and language in index_languages
                model_name = model['model'] if model['model'].casefold().startswith(model['brand'].casefold()+' ') else model['brand']+' '+model['model']
                name = ' '.join(str(value) for value in (model_name,model.get('year')) if value)
                title = (name + ' Specifications & China Export Inquiry | AUTOLINK') if editorial else tr('{model} Model Reference | AUTOLINK').replace('{model}', name)
                description = (editorial['intro'] if editorial else name + ' · ' + tr('Model reference · not a supplier inventory offer.') + ' ' + description)
                image = self.safe_image(model.get('image'))
                years = ', '.join(map(str,reference.get('availableYears',[]))) or tr('Year unspecified')
                introduction = editorial['intro'] if editorial else tr('This catalogue entry describes a model only. Confirm the exact trim, steering, specification, stock and price with an approved supplier. No supplier inventory or quote is implied.')
                facts = [('Brand',model['brand']),('Model',model['model']),('Year',years),('Body type',tr(model['bodyType']))]
                if not editorial: facts += [('Energy',tr(model['energy'])),*model.get('specifications',{}).items()]
                safe_description = model.get('description') and not editorial and (language!='en' or not re.search(r'[\u3400-\u9fff]',model['description']))
                mobile_image = self.mobile_hero(model, image)
                hero = ('<picture>' + ('<source media="(max-width:700px)" srcset="' + e(mobile_image) + '">' if mobile_image else '') + '<img class="trade-hero-image" width="1200" height="750" fetchpriority="high" src="' + e(image) + '" alt="' + e(name) + '"></picture>')
                content = '<div class="trade-intro"><div><span class="eyebrow">' + e(tr('MODEL REFERENCE · NOT A STOCK OFFER')) + '</span><h1>' + e(model_name) + '</h1><p>' + e(introduction) + '</p></div></div><div class="trade-detail"><div>' + hero + '</div><div>' + fields(facts) + ('<p>' + e(model['description']) + '</p>' if safe_description else '') + anchor('/trade/vehicles?' + urlencode({'brand':model['brand'],'model':model['model']}), tr('Find approved supplier offers')) + '</div></div>'
                content += self.reference_parameters(model, language, tr)
                content += anchor(canonical_path+'?interactive=1',tr('Compare all configurations'),True)
                related = [item for item in self.trade.catalog.models(brand=model['brandId']) if item['id'] != ident][:4]
                content += '<section class="related-models"><h2>' + e(tr('Related models')) + '</h2><div class="trade-grid">' + ''.join(model_card(item) for item in related) + '</div></section>'
                content += '<p class="trade-note">' + e(tr('No public supplier vehicles are currently shown for this model unless they appear in the approved listing directory.')) + '</p>'
                graph.append({'@type':'ProductModel','name':name,'url':localized_url(canonical_path,language),'brand':{'@type':'Brand','name':model['brand']},'description':description})
            elif ident and collection == 'brands':
                brand = self.trade.catalog.brand(ident)
                index_languages = self.index_policy('brand',brand)['indexLanguages']
                indexable = indexable and language in index_languages
                title = tr('{brand} Vehicles for Export from China | AUTOLINK').replace('{brand}',brand['name'])
                description = brand['name'] + ' · ' + description
                body_types = sorted({item['bodyType'] for item in brand['models'] if item.get('bodyType')})
                energies = sorted({item['energy'] for item in brand['models'] if item.get('energy')})
                overview = brand.get('overview') or (brand['name'] + ' has ' + str(len(brand['models'])) + ' public model references on AUTOLINK. The catalogue lists ' + ', '.join(body_types) + ' body types and ' + ', '.join(energies) + ' energy labels where provided. These are model references, not confirmed inventory or manufacturer authorization.')
                content = '<div class="trade-intro"><div><h1>' + e(brand['name']) + '</h1><p>' + e(overview) + '</p></div></div><div class="trade-grid">' + ''.join(model_card(model) for model in brand['models']) + '</div>' + anchor('/trade/vehicles?brand='+quote(brand['name'],safe=''),tr('Find approved supplier offers'))
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
        language_links=''.join('<a href="'+e(canonical_path+('' if code=='en' else '?lang='+code))+'" lang="'+LANGUAGE_TAGS[code]+'">'+e(code.upper())+'</a>' for code in LANGUAGES)
        body='<header class="trade-head"><div class="trade-head-inner"><a class="brand" href="/">AUTOLINK</a><nav class="trade-nav">'+navigation+'</nav></div></header><nav class="trade-language-links" aria-label="Languages">'+language_links+'</nav><main class="trade-main" id="main">'+content+'</main>'
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

    def mobile_hero(self, model, image):
        """Serve a verified derivative only while its original is unchanged."""
        if not image.startswith('/images/') or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',str(model['id'])):
            return None
        manifest_file = self.site_root/'images/seo-heroes/manifest.json'
        source_file = self.site_root/image.lstrip('/')
        try:
            entry = asset_json(str(manifest_file),asset_version(manifest_file)).get(model['id'],{})
            mobile = entry.get('mobile','')
            derivative = self.site_root/mobile.lstrip('/')
            if (entry.get('source') == image and mobile == '/images/seo-heroes/'+model['id']+'-640.webp'
                    and source_file.is_file() and derivative.is_file()
                    and entry.get('sourceSHA256') == asset_hash(str(source_file),asset_version(source_file))):
                return mobile
        except (ValueError, OSError, TypeError):
            pass
        return None

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
        if language == 'en':
            variants=data.get('variants',[])
            if not variants:return ''
            editorial=self.english_editorial(model,data)
            trim=editorial['trim'] if editorial else 'China-market reference configuration (English trim review pending)'
            facts=self.english_specifications(data)
            if not facts:return ''
            rows=''.join('<tr><th>'+html.escape(label)+'</th><td>'+html.escape(value)+'</td></tr>' for label,value in facts.items())
            source=urlsplit(str(data.get('sourceUrl','')))
            source_link=('<a href="'+html.escape(data['sourceUrl'],quote=True)+'" rel="noopener noreferrer">Source configuration</a>'
                if source.scheme=='https' and source.hostname and not source.username and not source.password else '')
            return '<section class="model-reference" data-ssr-reference><h2>Specifications</h2><p class="trade-note">China-market reference; values apply to the selected configuration and are not an inventory offer.</p><h3>'+html.escape(trim if re.match(r'^\s*'+re.escape(str(variants[0].get('year') or ''))+r'\b', trim) else str(variants[0].get('year') or '')+' '+trim)+'</h3><div class="reference-table-scroll"><table class="reference-table"><tbody>'+rows+'</tbody></table></div><p class="reference-provenance">'+source_link+'</p></section>'
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
