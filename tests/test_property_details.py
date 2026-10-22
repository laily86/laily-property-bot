import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from laily.bot import Bot
from laily.config import Settings
from laily.listings import extract, generate, review_reasons
from laily.packages import manual_package
from laily.storage import Store


@pytest.mark.parametrize('text,kind,location', [
    ('APARTMENT JENTAYU TAMPOI\n3 bedrooms 2 bathrooms', 'Apartment', 'JENTAYU TAMPOI'),
    ('FOR SALE: Condominium at Setia Sky 88, Johor Bahru', 'Condominium', 'Setia Sky 88, Johor Bahru'),
    ('UNTUK DIJUAL\nTANAH LOT DI KULAI\nLand area: 5,000 sqft', 'TANAH LOT', 'KULAI'),
    ('Double storey terrace Taman Universiti', '2 Storey Terrace', 'Taman Universiti'),
    ('Apartment\nProject: Jentayu Tampoi', 'Apartment', 'Jentayu Tampoi'),
])
def test_headline_details_are_taken_from_text(text, kind, location):
    result = extract(text)
    assert result['property_type'] == kind
    assert result['location'] == location


def test_amenities_conflicts_and_vague_text_do_not_create_facts():
    for text in ('Nearby: Apartment Jentayu Tampoi', 'Kemudahan: Condominium di Kulai',
                 'Land area: 5,000 sqft', 'Great investment, call me',
                 'Apartment / Condo Jentayu Tampoi'):
        assert extract(text)['property_type'] is None
        assert extract(text)['location'] is None
    assert extract('Location: Kajang\nLocation: Kulai\nApartment at Tampoi')['location'] is None
    assert extract('Jenis: Apartment\nJenis: Tanah\nApartment Jentayu')['property_type'] is None
    assert extract('Apartment with pool')['location'] is None
    assert extract('3 bedrooms 2 bathrooms')['bathrooms'] == '2'
    assert extract('3 bedrooms 2 bathrooms\n4 bathrooms')['bathrooms'] is None


@pytest.mark.parametrize('kind', ['Tanah', 'TANAH LOT', 'Agricultural land', 'Residential Land'])
def test_land_does_not_require_bedrooms_bathrooms_or_tenure(kind):
    record = {'fields': {'property_type': kind, 'location': 'Kulai', 'price': 'RM 480,000',
                         'floor_area': '5,000 sqft'}, 'sources': []}
    reasons = review_reasons(record)
    assert not any(reason in reasons for reason in ('Belum diketahui: bedrooms',
        'Belum diketahui: bathrooms', 'Belum diketahui: tenure'))
    for platform in ('facebook', 'mudah'):
        draft = generate(record, platform)
        assert 'Bathrooms:' not in draft['description_en']
        assert 'Land area: 5,000 sqft' in draft['description_en']
        assert 'availability' not in record['fields']
        assert 'Ketersediaan perlu pengesahan manual.' in draft['review_reasons']


def test_built_property_still_requires_bathrooms_but_tenure_is_optional():
    record = {'fields': {'property_type': 'Apartment', 'tenure': 'Leasehold'}, 'sources': []}
    assert 'Belum diketahui: bathrooms' in review_reasons(record)
    assert 'Belum diketahui: tenure' not in review_reasons(record)
    # Existing supplied tenure remains factual and can be shown, but is not mandatory.
    assert 'Tenure: Leasehold' in generate(record, 'facebook')['description_en']


def test_existing_saved_draft_is_enriched_without_reforwarding_or_overwriting_manual_edit(tmp_path):
    store = Store(tmp_path, Fernet.generate_key())
    original = 'APARTMENT JENTAYU TAMPOI\n3 bedrooms 2 bathrooms'
    r, _ = store.ingest(original, {})
    r['fields']['property_type'] = r['fields']['location'] = r['fields']['bathrooms'] = None
    store.put(r)
    old_record = store.get(r['id'])
    draft = generate(old_record, 'facebook')
    assert draft['title_bm'] == 'Apartment — JENTAYU TAMPOI'
    assert 'Bathrooms: 2' in draft['description_en']
    assert old_record['fields']['location'] is None
    old_record['fields']['location'] = 'Manually Confirmed Address'
    assert 'Manually Confirmed Address' in generate(old_record, 'mudah')['title_en']
    old_record['fields']['location'] = None
    old_record['manual_fields'] = ['location']
    assert 'Belum diketahui: location' in generate(old_record, 'facebook')['review_reasons']


@pytest.mark.asyncio
async def test_telegram_preview_and_export_share_enrichment(tmp_path):
    bot = Bot(Settings('123:unused', 123, Fernet.generate_key(), tmp_path))
    r, _ = bot.store.ingest('TANAH DI KULAI\nHarga: RM 480,000\nLand area: 5,000 sqft', {})
    api = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=123)))
    await bot.preview(api, 123, r, 'facebook')
    preview = api.send_message.call_args.kwargs['text']
    assert 'KULAI' in preview
    assert 'Belum diketahui: bathrooms' not in preview
    assert 'Belum diketahui: tenure' not in preview
    r['reuse_confirmed'] = True
    with zipfile.ZipFile(manual_package(r, 'mudah')) as archive:
        draft = json.loads(archive.read('draft.json'))
        assert 'KULAI' in draft['title_en']
        assert 'Belum diketahui: bathrooms' not in draft['review_reasons']
        assert draft['integration']['status'] == 'INTEGRATION_UNAVAILABLE'
