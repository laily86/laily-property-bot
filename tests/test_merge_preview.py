import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from telegram.error import BadRequest

from laily.bot import Bot
from laily.config import Settings
from laily.listings import extract, generate, review_reasons
from laily.packages import manual_package
from laily.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path, Fernet.generate_key())


def test_inline_bedrooms_and_bathrooms_and_old_records():
    f = extract('Bedrooms: 3 Bathrooms: 2\nFloor area: 950 sqft\nPrice: RM480,000')
    assert f['bedrooms'] == '3'
    assert f['bathrooms'] == '2'
    assert f['floor_area'] == '950 sqft'
    f['bedrooms'], f['bathrooms'] = '3 Bathrooms: 2', None
    record = {'fields': f, 'sources': []}
    result = generate(record, 'facebook')
    assert 'Bedrooms: 3\nBathrooms: 2' in result['description_en']
    assert 'Belum diketahui: bathrooms' not in review_reasons(record)
    assert record['fields']['bedrooms'] == '3 Bathrooms: 2'
    assert extract('Bilik tidur: 3 Bilik air: 2')['bathrooms'] == '2'
    assert extract('Bedrooms: 3 Bathrooms: 2\nBathrooms: 4')['bathrooms'] is None


def test_explicit_merge_preserves_originals_resets_permission_and_routes_late_album(store):
    text, _ = store.ingest('Location: Kajang\nBedrooms: 3 Bathrooms: 2', {'channel_username': 'umairpropertylisting'})
    album, _ = store.ingest('', {'message': 2}, b'first image', 'p1', 'album', 2)
    text['reuse_confirmed'] = True
    text['fields']['availability_confirmed'] = True
    store.put(text)
    merged = store.merge_photos(text['id'], album['id'])
    assert len(store.all()) == 1
    assert len(store.all(include_merged=True)) == 2
    assert merged['id'] == text['id']
    assert merged['fields']['bedrooms'] == '3'
    assert merged['fields']['bathrooms'] == '2'
    assert len(merged['photos']) == 1
    assert not merged['reuse_confirmed']
    assert not merged['fields']['availability_confirmed']
    assert store.get(album['id'])['id'] == text['id']
    assert store.merge_photos(text['id'], album['id'])['id'] == text['id']
    with pytest.raises(PermissionError):
        manual_package(merged, 'facebook')
    late, _ = store.ingest('', {'message': 3}, b'second image', 'p2', 'album', 3)
    assert late['id'] == text['id']
    assert len(late['photos']) == 2
    late['reuse_confirmed'] = True
    with zipfile.ZipFile(manual_package(late, 'mudah')) as archive:
        assert archive.read('photos/01.jpg') == b'first image'
        assert archive.read('photos/02.jpg') == b'second image'
        assert json.loads(archive.read('original-and-source.json'))['originals'] == text['originals']
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM audit WHERE event='photos_merged_by_user'").fetchone()[0] == 1


def test_merge_rejects_conflicts_and_preserves_both_records(store):
    text, _ = store.ingest('Location: Kajang', {})
    album, _ = store.ingest('Location: Tampoi', {}, b'photo', 'p')
    with pytest.raises(ValueError, match='location'):
        store.merge_photos(text['id'], album['id'])
    assert len(store.all()) == 2
    assert len(store.get(text['id'])['photos']) == 0
    with pytest.raises(ValueError):
        store.merge_photos(text['id'], text['id'])


@pytest.fixture
def bot(tmp_path):
    return Bot(Settings('123:unused', 123, Fernet.generate_key(), tmp_path))


def transport():
    return SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=100)),
                           edit_message_text=AsyncMock(), delete_message=AsyncMock())


@pytest.mark.asyncio
async def test_repeated_preview_updates_existing_message_even_after_restart(bot):
    r, _ = bot.store.ingest('Location: Kajang', {})
    api = transport()
    await bot.preview(api, 123, r, 'facebook')
    await bot.preview(api, 123, r, 'facebook')
    api.send_message.assert_awaited_once()
    api.edit_message_text.assert_awaited_once()
    assert api.edit_message_text.call_args.kwargs['message_id'] == 100
    restarted = Bot(bot.settings)
    await restarted.preview(api, 123, r, 'facebook')
    assert api.send_message.await_count == 1
    assert api.edit_message_text.await_count == 2
    await bot.preview(api, 123, r, 'mudah')
    assert api.send_message.await_count == 2  # Platforms have separate previews.


@pytest.mark.asyncio
async def test_unchanged_preview_is_not_resent_and_deleted_preview_is_replaced(bot):
    r, _ = bot.store.ingest('Location: Kajang', {})
    api = transport()
    await bot.preview(api, 123, r, 'facebook')
    api.edit_message_text.side_effect = BadRequest('Message is not modified')
    await bot.preview(api, 123, r, 'facebook')
    assert api.send_message.await_count == 1
    api.edit_message_text.side_effect = BadRequest('Message to edit not found')
    await bot.preview(api, 123, r, 'facebook')
    assert api.send_message.await_count == 2


@pytest.mark.asyncio
async def test_merge_buttons_require_user_selection_and_confirmation(bot):
    text, _ = bot.store.ingest('Location: Kajang', {})
    album, _ = bot.store.ingest('', {}, b'image', 'p')
    context = SimpleNamespace(bot=transport())
    async def click(data, uid=123):
        await bot.callback(SimpleNamespace(effective_user=SimpleNamespace(id=uid),
            effective_chat=SimpleNamespace(id=123, type='private'),
            callback_query=SimpleNamespace(data=data, answer=AsyncMock())), context)
    await click(f'choose:local:{album["id"]}')
    assert 'Pilih draf teks' in context.bot.send_message.call_args.kwargs['text']
    assert len(bot.store.all()) == 2
    await click(f'checkmerge:{text["id"]}:{album["id"]}')
    assert 'Sahkan hanya' in context.bot.send_message.call_args.kwargs['text']
    assert len(bot.store.all()) == 2
    await click(f'merge:{text["id"]}:{album["id"]}', uid=999)
    assert len(bot.store.all()) == 2
    await click(f'merge:{text["id"]}:{album["id"]}')
    assert len(bot.store.all()) == 1
    assert len(bot.store.get(text['id'])['photos']) == 1


@pytest.mark.asyncio
async def test_long_preview_edits_all_parts_and_cleans_only_its_surplus(bot):
    r, _ = bot.store.ingest('Location: Kajang', {})
    r['fields']['facilities'] = 'A' * 3000
    bot.store.put(r)
    api = transport()
    api.send_message.side_effect = [SimpleNamespace(message_id=i) for i in (101, 102, 103)]
    await bot.preview(api, 123, r, 'facebook')
    ids = bot.store.preview_ids(r['id'], 'facebook', 123)
    assert len(ids) >= 2
    r['fields']['facilities'] = 'Pool'
    bot.store.put(r)
    await bot.preview(api, 123, r, 'facebook')
    assert bot.store.preview_ids(r['id'], 'facebook', 123) == [101]
    assert api.delete_message.await_count == len(ids) - 1
