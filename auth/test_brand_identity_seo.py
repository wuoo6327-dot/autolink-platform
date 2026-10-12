"""Public brand identity stays consistent with the site's actual platform role."""
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path


SITE = Path(__file__).resolve().parent.parent / 'site'


class Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.links = []
        self.jsonld = []
        self._script = None
        self._text = []
        self._title = False
        self.title = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta[attrs.get('name') or attrs.get('property')] = attrs.get('content')
        elif tag == 'link':
            self.links.append(attrs)
        elif tag == 'script' and attrs.get('type') == 'application/ld+json':
            self._script = attrs.get('id')
            self._text = []
        elif tag == 'title':
            self._title = True

    def handle_endtag(self, tag):
        if tag == 'script' and self._script is not None:
            self.jsonld.append((self._script, json.loads(''.join(self._text))))
            self._script = None
        elif tag == 'title':
            self._title = False

    def handle_data(self, text):
        if self._script is not None:
            self._text.append(text)
        if self._title:
            self.title += text


class BrandIdentityTests(unittest.TestCase):
    def test_home_identity_is_in_initial_html_once(self):
        source = (SITE / 'index.html').read_text()
        head = Head()
        head.feed(source)
        self.assertEqual(head.title, 'AUTOLINK | Chinese Vehicle Sourcing & B2B Supplier Platform')
        self.assertIn('international vehicle buyers', head.meta['description'])
        self.assertEqual(head.meta['og:site_name'], 'AUTOLINK')
        self.assertEqual(head.meta['robots'], 'index, follow')
        self.assertEqual([item['href'] for item in head.links if item.get('rel') == 'canonical'],
                         ['https://autolinkglobal.com/'])
        self.assertEqual(len(head.jsonld), 1)
        self.assertEqual(head.jsonld[0][0], 'autolink-public-jsonld')
        graph = {item['@type']: item for item in head.jsonld[0][1]['@graph']}
        self.assertEqual(set(graph), {'Organization', 'WebSite'})
        org, website = graph['Organization'], graph['WebSite']
        self.assertEqual(org['@id'], 'https://autolinkglobal.com/#organization')
        self.assertEqual(website['@id'], 'https://autolinkglobal.com/#website')
        self.assertEqual(website['publisher'], {'@id': org['@id']})
        self.assertEqual(org['logo'], 'https://autolinkglobal.com/favicon.svg')
        self.assertEqual(org['contactPoint']['url'], 'https://autolinkglobal.com/support')
        self.assertTrue((SITE / 'favicon.svg').is_file())
        for unsupported in ('legalName', 'sameAs', 'hasShippingService', 'Offer'):
            self.assertNotIn(unsupported, source)
        self.assertIn('<a href="/about">About AUTOLINK</a>', source)

    def test_about_has_public_english_explanation_without_fake_translation(self):
        source = (SITE / 'about.html').read_text()
        head = Head()
        head.feed(source)
        self.assertIn('<html lang="en">', source)
        self.assertIn('<h1>About AUTOLINK</h1>', source)
        self.assertEqual([item['href'] for item in head.links if item.get('rel') == 'canonical'],
                         ['https://autolinkglobal.com/about'])
        self.assertEqual(head.meta['robots'], 'index, follow')
        self.assertFalse(any(item.get('hreflang') for item in head.links))
        self.assertIn('does not directly provide vehicle shipping', source)
        self.assertIn('A model reference is not a stock offer.', source)
        self.assertNotIn('FAQPage', source)


if __name__ == '__main__':
    unittest.main()
