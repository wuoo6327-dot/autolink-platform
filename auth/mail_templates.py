"""Shared, localised security/business copy; transport and user data stay separate."""
import html
import json
import re
from pathlib import Path

SUPPORTED_LANGUAGES = ('en', 'zh', 'ar', 'ru', 'kk', 'uz', 'ko', 'fr', 'sw')
RESOURCES = json.loads(Path(__file__).with_name('mail_translations.json').read_text(encoding='utf-8'))


def language_code(value):
    if value == 'zh-CN':
        return 'zh'
    if not isinstance(value, str) or value not in SUPPORTED_LANGUAGES:
        raise ValueError('Unsupported language.')
    return value


def copy_for(value='en'):
    # Corrupt/legacy stored preferences fall back safely. API input is validated separately.
    try:
        language = language_code(value)
    except ValueError:
        language = 'en'
    return language, RESOURCES[language]


def verification_message(code, purpose, language='en'):
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code) or purpose not in ('login', 'reset_password'):
        raise ValueError('Invalid verification template input.')
    language, labels = copy_for(language)
    title = labels['verification' if purpose == 'login' else 'reset']
    plain = '\n\n'.join(('AUTOLINK', title, code, labels['expires'], labels['ignore']))
    direction = 'rtl' if language == 'ar' else 'ltr'
    lang = 'zh-CN' if language == 'zh' else language
    content = f'''<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f7f9f7;font-family:Arial,sans-serif;color:#233b2d"><main style="max-width:520px;margin:30px auto;padding:32px;background:white;border:1px solid #e0e9e1;border-radius:12px"><strong dir="ltr" style="font-size:22px;letter-spacing:.08em">AUTOLINK</strong><h1 style="font-size:21px;margin-top:34px">{html.escape(title)}</h1><p dir="ltr" style="font-size:34px;letter-spacing:.22em;font-weight:bold;color:#224734">{code}</p><p>{html.escape(labels['expires'])}</p><p style="color:#667a6b">{html.escape(labels['ignore'])}</p></main></body></html>'''
    return 'AUTOLINK · ' + title, plain, content
