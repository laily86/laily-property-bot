import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from laily.bot import Bot
from laily.config import Settings
from laily.listings import generate
from laily.packages import manual_package
from laily.profile import ContactProfile
from laily.storage import Store


@pytest.mark.parametrize('platform', ['facebook', 'mudah'])
def test_profile_overrides_original_contact_in_both_languages_and_export(tmp_path, platform):
    store = Store(tmp_path, Fernet.generate_key())
    text = 'Lokasi: Kajang\nEjen: Ejen Asal, REN 98765, Agensi Asal, https://wa.me/60111111111'
    record, _ = store.ingest(text, {'source_url': 'https://t.me/example/123'})
    profile = ContactProfile.parse('Nama Contoh | +60 12-345 6789')
    store.set_contact_profile(profile)
    original_fields = dict(record['fields'])
    draft = generate(record, platform, store.contact_profile())
    for language in ('bm', 'en'):
        description = draft[f'description_{language}']
        assert 'Nama Contoh' in description
        assert 'https://wa.me/60123456789' in description
        assert 'Ejen Asal' not in description
        assert 'REN 98765' not in description
        assert 'Agensi Asal' not in description
        assert '60111111111' not in description
    assert record['fields'] == original_fields
    assert store.get(record['id'])['originals'] == [text]
    with pytest.raises(PermissionError):
        manual_package(record, platform, profile)
    record['reuse_confirmed'] = True
    with zipfile.ZipFile(manual_package(record, platform, profile)) as archive:
        exported = json.loads(archive.read('draft.json'))
        assert exported['description_bm'] == draft['description_bm']
        assert exported['integration']['status'] == 'INTEGRATION_UNAVAILABLE'
        assert exported['integration']['verified_draft_url'] is None
        assert json.loads(archive.read('original-and-source.json'))['originals'] == [text]


def test_profile_survives_restart_encrypted_and_updates_existing_drafts(tmp_path):
    key = Fernet.generate_key()
    store = Store(tmp_path, key)
    record, _ = store.ingest('Lokasi: Johor\nEjen: Original', {})
    store.set_contact_profile(ContactProfile.parse('First Agent | 60123456789 | REN 12345 | Example Agency'))
    reopened = Store(tmp_path, key)
    assert reopened.contact_profile().agency == 'Example Agency'
    assert b'First Agent' not in reopened.path.read_bytes()
    assert b'60123456789' not in reopened.path.read_bytes()
    reopened.set_contact_profile(ContactProfile.parse('Second Agent | 60198765432'))
    rendered = generate(reopened.get(record['id']), 'facebook', reopened.contact_profile())
    assert 'Second Agent' in rendered['description_en']
    assert 'First Agent' not in rendered['description_en']
    assert 'REN 12345' not in rendered['description_en']


@pytest.mark.parametrize('value', ['', 'Name', 'Name | 0123456789', 'Name | wrong',
                                    'Name | 60123456789 | Other persons REN',
                                    'Name\nInjected | 60123456789'])
def test_invalid_profile_rejected(value):
    with pytest.raises(ValueError):
        ContactProfile.parse(value)


@pytest.mark.asyncio
async def test_profile_command_authorized_only_and_preview_export_use_it(tmp_path):
    bot = Bot(Settings('123:unused', 123, Fernet.generate_key(), tmp_path))
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock(), send_document=AsyncMock()))
    def update(user_id, text):
        return SimpleNamespace(effective_user=SimpleNamespace(id=user_id),
            effective_chat=SimpleNamespace(id=123, type='private'),
            effective_message=SimpleNamespace(text=text))
    await bot.command(update(999, '/profile Intruder | 60123456789'), context)
    assert bot.store.contact_profile() is None
    await bot.command(update(123, '/profile Owner | 60123456789'), context)
    assert bot.store.contact_profile().name == 'Owner'
    await bot.command(update(123, '/profile Bad | 0123456789'), context)
    assert bot.store.contact_profile().name == 'Owner'
    record, _ = bot.store.ingest('Lokasi: Kajang\nEjen: Source Agent', {})
    await bot.preview(context.bot, 123, record, 'facebook')
    assert 'Owner' in context.bot.send_message.call_args.kwargs['text']
    assert 'Source Agent' not in context.bot.send_message.call_args.kwargs['text']
    record['reuse_confirmed'] = True
    bot.store.put(record)
    query = SimpleNamespace(data=f'export:mudah:{record["id"]}', answer=AsyncMock())
    u = update(123, '')
    u.callback_query = query
    await bot.callback(u, context)
    document = context.bot.send_document.call_args.args[1]
    import io
    with zipfile.ZipFile(io.BytesIO(document.input_file_content)) as archive:
        exported = json.loads(archive.read('draft.json'))
        assert 'Owner' in exported['description_bm']
        assert 'Source Agent' not in exported['description_bm']
