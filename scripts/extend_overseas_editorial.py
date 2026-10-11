"""Apply a manually reviewed, source-bound English SEO editorial batch.

This is deliberately an explicit release operation. A catalog or reference edit
invalidates approval in PublicSEOService; this tool never runs at server startup.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'auth'))
from seo_service import PublicSEOService  # noqa: E402


# Each entry was written against the selected China-market reference trim. Trim
# labels are editorial English renderings; the linked source retains the exact
# Chinese trim. No inventory, export authorization, price or compliance claim.
MODELS = {
    'geely-catalog-3': (
        '2025 1.5L manual Chao Neng',
        'Coolray is the international name used for Geely Binyue. This China-market 2025 manual configuration records a 2600 mm wheelbase, 5 seats and 93 kW maximum power. The smaller SUV format is a useful starting point for comparing approved listings, while overseas equipment can differ.',
        'Ask whether an offered Coolray matches the Binyue configuration, including transmission, steering side and production year.'),
    'geely-catalog-4': (
        '2026 1.5L manual four-million commemorative Chaoyue',
        'Geely Emgrand is represented by a 2026 China-market manual sedan rather than a generic export specification. The selected record gives a 4638 mm length, 2650 mm wheelbase and 5 seats. Confirm the exact sedan trim and market-specific equipment before comparing supplier quotations.',
        'Request the offered Emgrand trim sheet and vehicle identification details; a catalogue configuration does not establish stock.'),
    'geely-catalog-5': (
        '2026 1.5TD DCT Huanle five-seat',
        'The Haoyue L reference covers a five-seat 2026 SUV configuration in China. Its source lists a 4865 mm body length and 2825 mm wheelbase, giving buyers concrete dimensions to compare with other Geely SUVs. Supply, steering configuration and shipment timing require a separate seller confirmation.',
        'Check that a seller quote specifies the five-seat version, transmission and actual production batch.'),
    'galaxy-catalog-2': (
        '2025 575 km Qihang Zhijia',
        'Galaxy E8 is a battery-electric sedan in this 2025 China-market reference. The selected configuration lists a 62 kWh battery, 575 km CLTC electric range and 2925 mm wheelbase. The CLTC figure is a test-cycle result for this trim, so buyers should request destination-market documentation separately.',
        'For an E8 inquiry, identify battery variant, charging standard and documented range cycle in the actual offer.'),
    'galaxy-catalog-3': (
        '2025 EM-i 60 km Qihang',
        'This Galaxy L6 reference focuses on a 2025 EM-i plug-in hybrid sedan. The selected source configuration records an 8.5 kWh battery and 60 km CLTC electric range, alongside a 2752 mm wheelbase. These figures should be matched to a specific offered vehicle rather than treated as universal L6 specifications.',
        'Confirm battery and hybrid variant, charging interface and the test cycle shown on any supplier documents.'),
    'galaxy-catalog-5': (
        '2026 130 km Qihang',
        'Starship 7 EM-i is represented here by a 2026 China-market plug-in hybrid SUV. The source records a 19.09 kWh battery, 130 km CLTC electric range and 2755 mm wheelbase for the selected configuration. Export availability and destination approval remain separate questions for an actual supplier.',
        'Ask the seller to identify the exact Starship 7 EM-i version and provide current vehicle and shipping documents.'),
    'geely-xingyuan-2026': (
        '2026 310 km Xiangwang',
        'The Xingyuan entry describes a 2026 China-market battery-electric model, not an overseas homologation. Its selected trim has a 30.12 kWh battery, 310 km CLTC electric range and 2650 mm wheelbase in the reference. Buyers comparing compact EVs should check the offered battery and charging specification.',
        'Request the battery label and charging connector for the offered Xingyuan before arranging a purchase inquiry.'),
    'zeekr-catalog-4': (
        '2026 seven-seat Ultra',
        'Zeekr 009 is an electric MPV, and this 2026 China-market reference selects the seven-seat Ultra configuration. It records a 108 kWh battery, 740 km CLTC electric range and 3205 mm wheelbase. Passenger layout and battery specification should be checked on any real supplier listing.',
        'Verify the seven-seat layout, battery version and documentation for the destination before discussing a Zeekr 009 shipment.'),
    'zeekr-catalog-5': (
        '2025 Zhijia',
        'The Zeekr MIX reference selects a 2025 battery-electric configuration with 5 seats. The source lists a 76 kWh battery, 550 km CLTC electric range and 3008 mm wheelbase. Its cabin-oriented body shape makes seating and door configuration important details to confirm on a particular vehicle.',
        'Ask a supplier for the exact seat and door layout, charging standard and production date of the offered MIX.'),
    'byd-catalog-1': (
        '2026 DM-i 128 km Jinqu',
        'BYD Qin PLUS appears here as a 2026 China-market DM-i plug-in hybrid sedan. The selected reference gives a 15.87 kWh battery, 128 km CLTC electric range and 2718 mm wheelbase. Buyers should distinguish this configuration from other Qin PLUS years and powertrains before requesting a quote.',
        'Specify Qin PLUS DM-i, the requested battery/range version and destination market in the inquiry.'),
    'byd-catalog-2': (
        '2026 DM-i 128 km Jinqu',
        'Qin L is a separate BYD sedan reference from Qin PLUS, despite the similar DM-i trim label. This 2026 China-market configuration records a 2790 mm wheelbase, 15.87 kWh battery and 128 km CLTC electric range. Use the precise model name and body dimensions when comparing offers.',
        'Ask for the Qin L model code and trim sheet so it is not confused with a Qin PLUS listing.'),
    'byd-catalog-3': (
        '2026 DM-i Chao Xiang 128 km Luxury',
        'The BYD Seal 06 record concerns a 2026 China-market DM-i plug-in hybrid configuration. It lists a 4830 mm length, 15.87 kWh battery and 128 km CLTC electric range for the selected sedan. The Seal 06 name spans distinct powertrains, so the exact suffix and trim matter in procurement.',
        'Confirm that an offered Seal 06 is the DM-i version and obtain its complete model and battery identifiers.'),
    'denza-catalog-3': (
        '2026 battery-electric Flash Charge Premium',
        'Denza N8L is shown as a six-seat battery-electric configuration in this 2026 China-market source. The selected record lists a 130.15 kWh battery, 960 km CLTC electric range and 3075 mm wheelbase. Those figures belong to this trim and cannot establish an overseas specification or available stock.',
        'Request documentary confirmation of the N8L battery, charging equipment and seating configuration for the specific vehicle.'),
    'denza-catalog-5': (
        '2026 Flash Charge Premium',
        'This Denza Z9GT reference selects a 2026 battery-electric shooting-brake configuration. Its source records a 102.3 kWh battery, 880 km CLTC electric range and 3125 mm wheelbase. Buyers should compare the offered drivetrain and charging version with the China-market reference before negotiating supply.',
        'Check whether an offered Z9GT is battery-electric or plug-in hybrid and identify its exact charging specification.'),
    'changan-catalog-3': (
        '2026 1.5T Blue Core hybrid Zhiyue',
        'Changan UNI-V is represented by a 2026 hybrid sedan configuration in this source. The selected record lists a 2750 mm wheelbase, 5 seats and 110 kW maximum power. It should not be conflated with other UNI-V gasoline variants or with a supplier inventory listing.',
        'Ask whether the quoted UNI-V is the selected hybrid powertrain and obtain its current trim and emissions documents.'),
    'changan-catalog-5': (
        '2026 PLUS 1.4T Changxing',
        'The Eado reference covers a 2026 China-market PLUS gasoline sedan. A 4730 mm length, 2700 mm wheelbase and 5-seat layout are recorded for the selected configuration. Because Eado naming varies by version, buyers should compare the actual offer against this specific trim.',
        'State the Eado PLUS version and production year clearly when requesting stock or a supplier quotation.'),
    'deepal-catalog-4': (
        '2026 rear-wheel-drive Ultra long-range',
        'Deepal S09 is represented by a 2026 range-extended electric SUV configuration with 6 seats. The source records a 53.49 kWh battery, 310 km CLTC electric range and 3105 mm wheelbase. A range-extender vehicle has a different fuel and charging profile from a battery-only SUV.',
        'Verify the range-extender system, battery, seating and charging interface on the specific S09 offer.'),
    'deepal-catalog-5': (
        '2026 240 Max Huawei Qiankun ADS SE',
        'The Deepal L07 reference selects a 2026 range-extended electric sedan, identified by its 240 Max China-market trim. It lists a 28.39 kWh battery, 240 km CLTC electric range and 2900 mm wheelbase. Software and driver-assistance availability should be checked for the destination vehicle.',
        'Request exact powertrain and software equipment details for an offered L07; destination features may differ.'),
    'trumpchi-catalog-1': (
        '2026 Yingsu 270T Jinqu',
        'Trumpchi GS3 is shown here in a 2026 China-market gasoline SUV configuration. The selected reference records a 4410 mm body length, 2650 mm wheelbase and 5 seats. Buyers comparing compact SUVs can use those dimensions while treating availability and export terms as supplier-specific.',
        'Confirm the GS3 trim, transmission and steering side with any seller before requesting shipping terms.'),
    'trumpchi-catalog-2': (
        '2026 fifth-generation 1.5T standard',
        'This Trumpchi GS4 reference concerns a fifth-generation 2026 gasoline SUV, not every model year sold under the GS4 badge. Its selected configuration lists a 4680 mm length, 2770 mm wheelbase and 5 seats. A current supplier offer should identify the generation and exact equipment.',
        'Ask for the fifth-generation GS4 trim sheet and actual production year before comparing quotations.'),
    'trumpchi-catalog-4': (
        '2026 M6 MAX 1.5T DCT Elite',
        'The Trumpchi M6 entry focuses on a 2026 seven-seat MPV configuration. The source gives a 2810 mm wheelbase, 4793 mm length and 130 kW maximum power. Seat arrangement and luggage space can differ across M6 versions, so an inquiry should identify the precise vehicle.',
        'Check the seven-seat arrangement and full equipment sheet of any offered M6 MAX.'),
    'trumpchi-m8-2026': (
        '2026 Xiangwang M8 PHEV L Pro',
        'The Xiangwang M8 PHEV L reference selects a 2026 plug-in hybrid MPV with 7 seats. It records a 44.57 kWh battery, 248 km CLTC electric range and 3070 mm wheelbase. The figures describe the China-market source trim, while local import eligibility requires separate verification.',
        'Ask for the exact Xiangwang M8 PHEV L variant, battery and seating documents before discussing supply.'),
    'saic-volkswagen-catalog-1': (
        '2026 Lavida Xinrui 1.5L Chuzhong Xinyi',
        'SAIC Volkswagen Lavida is represented by a 2026 China-market gasoline sedan configuration. Its selected source lists a 4561 mm length, 2651 mm wheelbase and 5 seats. Lavida trim names differ from other Volkswagen sedans, making model identity and equipment evidence important in trade inquiries.',
        'Check the SAIC Volkswagen vehicle identity, Lavida trim and destination-market documentation separately.'),
    'saic-volkswagen-catalog-4': (
        '2026 Teramont Pro 380TSI front-wheel-drive Yuejing',
        'This SAIC Volkswagen Teramont reference selects a 2026 seven-seat gasoline SUV configuration. The source records a 5158 mm body length, 2980 mm wheelbase and 157 kW maximum power. Buyers should identify whether a proposed vehicle is Teramont Pro and verify its drivetrain before comparing offers.',
        'Ask the supplier to confirm Teramont Pro identity, seating, drivetrain and the actual production year.'),
    'faw-volkswagen-catalog-1': (
        '2026 Sagitar S 1.5L Fashion',
        'FAW Volkswagen Sagitar is represented by a 2026 China-market gasoline sedan. The selected configuration records a 4702 mm length, 2688 mm wheelbase and 5 seats. The Sagitar badge and equipment are market-specific, so importers should compare documentation for the exact vehicle rather than rely on a familiar name.',
        'Request the FAW Volkswagen model and trim identifiers, plus documents for the specific Sagitar offered.'),
    'faw-volkswagen-catalog-2': (
        '2026 30-million-vehicle edition 280TSI DSG Comfort',
        'The FAW Volkswagen Magotan reference describes a 2026 China-market gasoline sedan configuration. Its source lists a 4866 mm length, 2871 mm wheelbase and 110 kW maximum power. The special-edition trim label should be matched to actual supplier documents before discussing shipment.',
        'Ask whether a proposed Magotan is this special edition or another 280TSI trim, and verify its production date.'),
    'faw-volkswagen-catalog-4': (
        '2026 30-million-vehicle edition 300TSI',
        'FAW Volkswagen Tayron is shown as a 2026 China-market gasoline SUV configuration. The selected source records a 4593 mm body length, 2731 mm wheelbase and 118 kW maximum power. It should be compared with an actual Tayron offer by year, engine and variant before export terms are discussed.',
        'Request the Tayron trim sheet, drivetrain and documented production year from the proposed supplier.'),
    'faw-volkswagen-catalog-5': (
        '2026 450TSI all-wheel-drive Supreme six-seat',
        'This FAW Volkswagen Talagon reference selects a six-seat 2026 gasoline SUV configuration. Its source lists a 5143 mm length, 2980 mm wheelbase and 200 kW maximum power. The seating and all-wheel-drive specification must be confirmed for any actual supplier vehicle.',
        'Identify the six-seat layout, 450TSI drivetrain and actual VIN-linked equipment before requesting a quote.'),
}


# Manufacturer-owned primary sources support the company or sub-brand context.
# Model inventory and catalogue composition remain database facts, not OEM claims.
BRANDS = {
    'geely': ('https://global.geely.com/en/brand',
        'Geely Auto is a China-based automotive manufacturer whose public range includes passenger cars and SUVs. This AUTOLINK directory follows China-market Geely model references, including Emgrand, Coolray/Binyue, Boyue L, Haoyue L and Monjaro/Xingyue L. The listed configurations are research material; manufacturer affiliation, stock and export permission are not implied.'),
    'galaxy': ('https://global.geely.com/en/news/2026/geely-full-domain-ai-auto-china-2026',
        'Geely Galaxy is the new-energy nameplate in Geely Auto’s portfolio. The AUTOLINK China-market directory spans electric models such as E5, E8 and Xingyuan as well as plug-in hybrid L-series and Starship 7 references. Powertrain and test-cycle figures belong to individual source trims, not every Galaxy vehicle or export market.'),
    'zeekr': ('https://www.zeekrgroup.com/en/about-zeekr',
        'Zeekr is a luxury electric mobility brand in the Zeekr Group. This directory covers China-market references across electric passenger cars, SUVs and MPVs, including 001, 007, 7X, 009 and MIX. The brand information helps compare models; actual stock and supplier identity must be checked through separate approved listings.'),
    'byd': ('https://www.byd.com/en/about-byd',
        'BYD is a Chinese manufacturer known for battery-electric and plug-in hybrid vehicles. AUTOLINK lists China-market references such as Han, Qin L, Qin PLUS, Seal 06 and Yuan PLUS/ATTO 3. Similar names can represent different powertrains and market specifications, so the exact offered trim must be confirmed with a supplier.'),
    'denza': ('https://media.byd.com/section/company/brands/denza/?lang=eng',
        'Denza is a premium new-energy vehicle brand within the BYD Group. The AUTOLINK directory presents China-market references for its MPVs, SUVs and Z-series passenger vehicles, including D9, N7, N8L and Z9GT. A model’s presence here does not establish manufacturer authorization, current inventory or delivery eligibility.'),
    'changan': ('https://www.globalchangan.com/aboutus.html/',
        'Changan Automobile is a Chinese automotive group with CHANGAN and DEEPAL among its passenger-vehicle brands. This CHANGAN directory focuses on China-market CS-series SUVs, Eado and UNI-series references. The body, powertrain and model year shown on an individual page describe a selected configuration rather than a guaranteed export offer.'),
    'deepal': ('https://www.globalchangan.com/deepal.html',
        'Deepal is Changan’s electric vehicle brand, with official model families including S05, S07, S09, L07 and G318. AUTOLINK keeps China-market battery-electric and range-extended configurations separate, because batteries and range-cycle figures differ by trim. Buyers should verify a particular vehicle and its destination requirements with an approved seller.'),
    'trumpchi': ('https://www.gacmotor.com/about',
        'Trumpchi is the passenger-vehicle brand presented by GAC Motor in China. This AUTOLINK directory includes GS-series SUVs and M-series MPVs, with gasoline and plug-in hybrid configurations represented where source data exists. The brand page supports model research and supplier discovery without claiming that AUTOLINK is a GAC-authorized dealer.'),
    'saic-volkswagen': ('https://www.volkswagen-newsroom.com/en/volkswagen-group-china-4068',
        'SAIC Volkswagen is Volkswagen Group’s China joint venture established in Shanghai. The China-market references on AUTOLINK include Lavida, Passat, Tiguan L and Teramont. These are local model and trim records; overseas homologation, Volkswagen authorization and available supplier stock must be verified independently.'),
    'faw-volkswagen': ('https://www.volkswagen-newsroom.com/en/volkswagen-group-china-4068',
        'FAW Volkswagen is a Volkswagen Group joint venture in China. This AUTOLINK directory separates its China-market references, including Sagitar, Magotan, Golf, Tayron and Talagon, from SAIC Volkswagen vehicles. Model badges can cross markets while specifications vary; buyers should review the actual trim, documentation and seller listing.'),
}


def build():
    seo = PublicSEOService(None, ROOT / 'site')
    models = {item['id']: item for item in json.loads((ROOT / 'auth/catalog.json').read_text())}
    brands = {item['id']: item for item in json.loads((ROOT / 'tests/fixtures/production-public-catalog-20261012.json').read_text())['brands']}
    existing = json.loads((ROOT / 'site/locales/seo-model-en-reviewed.json').read_text())
    existing_approved = sum(entry.get('status') == 'approved' for entry in existing.values())
    if len(MODELS) != 28:
        raise ValueError('Expected 28 distinct model reviews')
    if len(BRANDS) != 10:
        raise ValueError('Expected ten priority brand reviews')
    reviewer = 'Codex source-to-English content QA, 2026-10-12'
    for ident, (trim, intro, buyer_note) in MODELS.items():
        model = models[ident]
        reference = seo.reference(model)
        if not seo.reference_complete({**model, 'active': True, 'brandActive': True}, reference):
            raise ValueError(f'{ident}: incomplete reference')
        facts = seo.english_specifications(reference)
        if len(facts) < 5 or len(intro.split()) < 35 or len(buyer_note.split()) < 12:
            raise ValueError(f'{ident}: short editorial or facts')
        if re.search(r'[\u3400-\u9fff]', trim + intro + buyer_note):
            raise ValueError(f'{ident}: untranslated editorial')
        allowed_numbers = {str(reference['variants'][0]['year'])}
        for value in list(facts.values()) + re.findall(r'\d+(?:\.\d+)?', trim + ' ' + model['model']):
            allowed_numbers.add(str(value))
        mentioned = set(re.findall(r'\d+(?:\.\d+)?', intro))
        if mentioned - allowed_numbers:
            raise ValueError(f'{ident}: unsupported numeric claims {mentioned - allowed_numbers}')
        source = ROOT / 'site/model-reference' / (ident + '.json')
        existing[ident] = {
            'status': 'approved', 'brandName': model['brand'], 'modelName': model['model'],
            'sourceTrim': reference['variants'][0]['name'], 'trim': trim,
            'intro': intro, 'buyerNote': buyer_note,
            'chinaName': reference.get('modelZh', ''),
            'referenceSHA256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'catalogSHA256': seo.catalog_digest({**model, 'active': True, 'brandActive': True}), 'reviewedBy': reviewer,
            'evidence': f"source:{reference['sourceUrl']}; checked against current production reference and selected trim; no supply, price or market approval claimed",
        }
    by_brand = {}
    for model in models.values():
        by_brand.setdefault(model['brandId'], []).append(model)
    brand_file = ROOT / 'site/locales/seo-brand-en-reviewed.json'
    brand_entries = json.loads(brand_file.read_text()) if brand_file.is_file() else {}
    for ident, (source_url, intro) in BRANDS.items():
        brand = {**brands[ident], 'models': [
            {**item, 'active': True, 'brandActive': True} for item in by_brand[ident]]}
        parsed = urlsplit(source_url)
        if parsed.scheme != 'https' or not parsed.hostname or len(intro.split()) < 35:
            raise ValueError(f'{ident}: unreviewed brand source or thin editorial')
        brand_entries[ident] = {
            'status': 'approved', 'brandName': brand['name'], 'intro': intro,
            'sourceUrl': source_url, 'catalogSHA256': seo.brand_digest(brand),
            'reviewedBy': reviewer,
            'evidence': 'source:' + source_url + '; company context checked against manufacturer-owned publication; catalog lineup from current AUTOLINK records',
        }
    return existing, brand_entries, existing_approved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true', help='write reviewed JSON after validation')
    args = parser.parse_args()
    models, brands, previous_approved = build()
    if args.write:
        for name, data in [('seo-model-en-reviewed.json', models), ('seo-brand-en-reviewed.json', brands)]:
            (ROOT / 'site/locales' / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'previousApprovedModels': previous_approved, 'reviewedModelBatch': len(MODELS),
                      'totalEnglishModels': sum(v.get('status') == 'approved' for v in models.values()),
                      'reviewedBrandBatch': len(BRANDS), 'totalEnglishBrands': sum(v.get('status') == 'approved' for v in brands.values()),
                      'wroteFiles': args.write}))


if __name__ == '__main__':
    main()
