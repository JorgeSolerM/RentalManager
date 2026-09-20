"""Local ISO alpha-2 catalogue, Spanish names from Unicode CLDR (see data licence)."""
import json
import unicodedata
from pathlib import Path

COUNTRIES = json.loads((Path(__file__).parent / 'data/countries_es.json').read_text(encoding='utf-8'))

def search_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))

COUNTRY_OPTIONS = sorted(COUNTRIES.items(), key=lambda item: search_key(item[1]))
_LABEL_CODES = {search_key(label): code for code, label in COUNTRIES.items()}

def normalize_nationality(value):
    value = (value or '').strip()
    if not value:
        return None
    if value.upper() in COUNTRIES:
        return value.upper()
    return _LABEL_CODES.get(search_key(value))

def nationality_label(value):
    code = normalize_nationality(value)
    return COUNTRIES[code] if code else (value or '—')

def nationality_options(person):
    raw = person.nationality if person else None
    selected = normalize_nationality(raw) or raw or ''
    options = list(COUNTRY_OPTIONS)
    if selected and selected not in COUNTRIES:
        options.insert(0, (selected, f'Dato anterior sin normalizar: {selected}'))
    return options, selected
