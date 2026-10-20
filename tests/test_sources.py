import json
import zipfile
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from laily.bot import Bot
from laily.config import Settings
from laily.listings import generate, review_reasons
from laily.packages import manual_package
from laily.profile import ContactProfile
from laily.sources import CHANNEL_TAGS, source_hashtags, source_tag
from laily.storage import Store


@pytest.mark.parametrize('username,expected', [
    ('umairpropertylisting', '#xum'), ('EjenHartanah_Sufi', '#xsfi'),
    ('brotherkhaiproperty', '#xkhi'), ('AsrizadBakriListing', '#xas'),
    ('Blacky_Listing_Property', '#nrhfdz')])
@pytest.mark.parametrize('platform', ['facebook', 'mudah'])
def test_custom_channel_mapping_preview_and_export(tmp_path, username, expected, platform):
    store = Store(tmp_path, Fernet.generate_key())
    original = 'Lokasi: Kajang\nEjen: Original Agent'
    r, _ = store.ingest(original, {'source_url': f'https://t.me/{username}/123', 'chat_title': 'Channel Title'})
    profile = ContactProfile.parse('Example Owner | 60123456789')
    generated = generate(r, platform, profile)
    assert generated['source_hashtags'] == [expected]
    for language in ('bm', 'en'):
        assert generated[f'description_{language}'].endswith(expected)
        assert 'Example Owner' in generated[f'description_{language}']
        assert 'Original Agent' not in generated[f'description_{language}']
    assert not r['reuse_confirmed']
    with pytest.raises(PermissionError):
        manual_package(r, platform, profile)
    r['reuse_confirmed'] = True
    with zipfile.ZipFile(manual_package(r, platform, profile)) as archive:
        assert json.loads(archive.read('draft.json'))['source_hashtags'] == [expected]
        assert json.loads(archive.read('original-and-source.json'))['originals'] == [original]
    assert store.get(r['id'])['originals'] == [original]


def test_other_channel_name_is_sanitized_without_guessing_known_code():
    assert source_tag({'channel_username': 'otherchannel', 'chat_title': 'Rumah Johor 🏡 2026!'}) == '#Rumah_Johor_2026'
    assert source_tag({'channel_username': 'OTHERCHANNEL'}) == '#otherchannel'
    assert source_tag({'chat_title': 'Asrizad Bakri'}) == '#Asrizad_Bakri'
    assert source_tag({'chat_title': '🏡🏡'}) is None
    assert source_tag({'source_url': 'https://t.me/AsrizadBakriListing/1', 'chat_title': 'Nama Baharu'}) == '#xas'


def test_hidden_or_copied_source_is_not_guessed_from_text():
    record = {'fields': {}, 'originals': ['From Asrizad https://t.me/AsrizadBakriListing/1'],
              'sources': [{'hidden_sender_name': 'Asrizad Bakri', 'origin_type': 'hidden_user'}]}
    assert source_hashtags(record) == []
    assert any('Sumber channel' in reason for reason in review_reasons(record))
    assert source_tag({'source_url': 'https://t.me.evil.test/AsrizadBakriListing/1'}) is None
    assert source_tag({'source_url': 'https://t.me/c/123/456'}) is None
    assert source_tag({'source_url': 'https://t.me/AsrizadBakriListing/1'}) == '#xas'


def test_album_deduplicates_tags_and_keeps_distinct_sources():
    record = {'sources': [{'channel_username': 'AsrizadBakriListing'},
                          {'source_url': 'https://t.me/AsrizadBakriListing/2'},
                          {'channel_username': 'umairpropertylisting'}]}
    assert source_hashtags(record) == ['#xas', '#xum']


def test_forward_metadata_captures_username_for_renamed_channel(tmp_path):
    from datetime import datetime, timezone
    bot = Bot(Settings('123:unused', 1, Fernet.generate_key(), tmp_path))
    message = SimpleNamespace(message_id=10, forward_origin=SimpleNamespace(
        type='channel', date=datetime.now(timezone.utc), message_id=20,
        chat=SimpleNamespace(id=-100123, title='Renamed Channel', username='ASRIZADBAKRILISTING')))
    source = bot.source(message)
    assert source['channel_id'] == -100123
    assert source['channel_username'] == 'ASRIZADBAKRILISTING'
    assert source_tag(source) == '#xas'


@pytest.mark.parametrize('platform', ['facebook', 'mudah'])
def test_original_promotional_hashtags_removed_from_draft_but_retained_in_source(tmp_path, platform):
    store = Store(tmp_path, Fernet.generate_key())
    original = ('Jenis: Apartment #ForRent\nLokasi: Kajang #JohorProperty\n'
                'Harga: RM 1,500 / bulan #Promo\nKemudahan: Pool #IQIRealty #RealtyiCan\n'
                'Ejen: Original Agent #OldAgent')
    r, _ = store.ingest(original, {'channel_username': 'AsrizadBakriListing'})
    before = dict(r['fields'])
    draft = generate(r, platform)
    for key in ('title_bm', 'title_en', 'price', 'description_bm', 'description_en'):
        for tag in ('#ForRent', '#JohorProperty', '#Promo', '#IQIRealty', '#RealtyiCan', '#OldAgent'):
            assert tag not in draft[key]
    assert draft['source_hashtags'] == ['#xas']
    assert draft['description_bm'].count('#xas') == 1
    assert draft['description_en'].count('#xas') == 1
    assert r['fields'] == before
    r['reuse_confirmed'] = True
    with zipfile.ZipFile(manual_package(r, platform)) as archive:
        exported = json.loads(archive.read('draft.json'))
        assert exported['description_bm'] == draft['description_bm']
        assert exported['description_en'] == draft['description_en']
        assert exported['source_hashtags'] == ['#xas']
        assert json.loads(archive.read('original-and-source.json'))['originals'] == [original]
    assert store.get(r['id'])['originals'] == [original]


def test_hashtag_cleaning_preserves_unit_numbers_and_url_fragments():
    from laily.sources import remove_listing_hashtags
    assert remove_listing_hashtags('Unit #A12, floor #12-03 #ForRent') == 'Unit #A12, floor #12-03'
    assert remove_listing_hashtags('Info https://example.com/property#details #Promo') == 'Info https://example.com/property#details'
    assert remove_listing_hashtags('#Tag1 #Tag2\nPool #Kolam') == 'Pool'
