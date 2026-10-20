import base64
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet, InvalidToken

from laily.bot import Bot
from laily.config import Settings
from laily.demo import SAMPLE
from laily.integrations import Status, platform_status
from laily.listings import extract, generate, review_reasons, validate_edits
from laily.packages import manual_package
from laily.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "private", Fernet.generate_key())


def test_forwarded_listing_to_distinct_bilingual_drafts(store):
    r, _ = store.ingest(SAMPLE, {"source_url": "https://t.me/example/12"}, b"photo", "file1", event_id=1)
    fb, mudah = generate(r, "facebook"), generate(r, "mudah")
    assert fb["description_bm"] != mudah["description_bm"]
    assert fb["description_en"] != mudah["description_en"]
    assert "RM 450,000" in fb["description_en"]
    assert "Availability is unconfirmed" in fb["description_en"]
    assert r["fields"]["bathrooms"] == "2"
    assert review_reasons(r)
    assert store.get(r["id"])["sources"][0]["source_url"].endswith("/12")


def test_missing_and_conflicting_information_never_invented():
    f = extract("Nice house in KL!\nPrice: RM 900\nPrice: RM 1,000")
    assert f["location"] is None
    assert f["price"] is None
    assert f["availability"] is None
    assert f["availability_confirmed"] is False


def test_duplicate_text_property_and_photo_flagged_without_data_loss(store):
    first, _ = store.ingest(SAMPLE, {"message": 1}, b"image", "same")
    second, _ = store.ingest(SAMPLE, {"message": 2}, b"new image", "different")
    third, _ = store.ingest("", {"message": 3}, b"image", "same")
    fourth, _ = store.ingest(SAMPLE.replace("450,000", "460,000"), {"message": 4})
    assert first["id"] in second["duplicate_candidates"]
    assert first["id"] in third["duplicate_candidates"]
    assert first["id"] in fourth["duplicate_candidates"]
    assert len(store.all()) == 4
    assert base64.b64decode(second["photos"][0]["data"]) == b"new image"


def test_album_and_replayed_updates_are_durable(store):
    a, _ = store.ingest(SAMPLE, {"id": 1}, b"a", "a", "album", 101)
    a["reuse_confirmed"] = True
    store.put(a)
    b, _ = store.ingest("", {"id": 2}, b"b", "b", "album", 102)
    assert a["id"] == b["id"]
    assert len(b["photos"]) == 2
    assert not b["reuse_confirmed"]
    assert store.ingest("", {}, b"b", "b", "album", 102) == (None, "replayed")
    key = base64.urlsafe_b64encode(store.cipher._signing_key + store.cipher._encryption_key)
    reopened = Store(store.directory, key)
    assert len(reopened.get(a["id"])["photos"]) == 2


def test_encrypted_listing_photos_and_audit_on_disk(store):
    r, _ = store.ingest("Location: SECRET_LOCATION", {"source": "SECRET_SOURCE"}, b"SECRET_PHOTO", "photo")
    store.audit("test", r["id"], {"note": "SECRET_AUDIT"})
    raw = store.path.read_bytes()
    for secret in (b"SECRET_LOCATION", b"SECRET_SOURCE", b"SECRET_PHOTO", b"SECRET_AUDIT"):
        assert secret not in raw
    with pytest.raises(InvalidToken):
        Store(store.directory, Fernet.generate_key())


def test_export_requires_permission_and_never_claims_account_save(store):
    r, _ = store.ingest(SAMPLE, {"kind": "sample"}, b"image", "photo")
    with pytest.raises(PermissionError):
        manual_package(r, "facebook")
    r["reuse_confirmed"] = True
    for platform in ("facebook", "mudah"):
        with zipfile.ZipFile(manual_package(r, platform)) as archive:
            draft = json.loads(archive.read("draft.json"))
            assert draft["integration"]["status"] == "INTEGRATION_UNAVAILABLE"
            assert draft["integration"]["verified_draft_url"] is None
            assert archive.read("photos/01.jpg") == b"image"
            assert json.loads(archive.read("original-and-source.json"))["originals"] == [SAMPLE]
    assert platform_status("facebook")["status"] != Status.PLATFORM_DRAFT_SAVED
    with pytest.raises(ValueError):
        platform_status("page")


def test_edit_validation():
    assert validate_edits({"availability_confirmed": True})
    with pytest.raises(ValueError):
        validate_edits({"availability_confirmed": "yes"})
    with pytest.raises(ValueError):
        validate_edits({"publish": True})


@pytest.fixture
def bot(tmp_path):
    return Bot(Settings("123:unused", 123, Fernet.generate_key(), tmp_path / "bot"))


def update_for(user_id=123, chat_type="private", **kwargs):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id),
                           effective_chat=SimpleNamespace(id=123, type=chat_type), **kwargs)


@pytest.mark.asyncio
async def test_unauthorized_commands_messages_and_callbacks_rejected(bot):
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), user_data={})
    for update in (update_for(999), update_for(123, "group")):
        await bot.command(update, context)
        await bot.received(update, context)
        await bot.callback(update, context)
    context.bot.send_message.assert_not_awaited()
    assert bot.store.all() == []


@pytest.mark.asyncio
async def test_authorized_forwarded_message_local_draft_and_preview(bot):
    message = SimpleNamespace(text=SAMPLE, caption=None, photo=[], media_group_id=None,
                              message_id=10, chat_id=123,
                              forward_origin=SimpleNamespace(type="channel", date=__import__('datetime').datetime.now(),
                                  chat=SimpleNamespace(title="Example", username="example"), message_id=88))
    update = update_for(effective_message=message, update_id=1)
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), user_data={})
    await bot.received(update, context)
    r = bot.store.all()[0]
    assert r["sources"][0]["source_url"] == "https://t.me/example/88"
    assert not r["reuse_confirmed"]
    sent = context.bot.send_message.call_args.kwargs
    assert "LOCAL_DRAFT" in sent["text"]
    assert "Preview Facebook" in str(sent["reply_markup"])


@pytest.mark.asyncio
async def test_save_confirmation_then_export_and_audit(bot):
    r, _ = bot.store.ingest(SAMPLE, {"kind": "sample"})
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock(), send_document=AsyncMock()))
    async def click(data):
        q = SimpleNamespace(data=data, answer=AsyncMock())
        await bot.callback(update_for(callback_query=q), context)
    await click(f"save:local:{r['id']}")
    assert not bot.store.get(r["id"])["reuse_confirmed"]
    await click(f"export:facebook:{r['id']}")
    context.bot.send_document.assert_not_awaited()
    await click(f"confirm:local:{r['id']}")
    await click(f"export:facebook:{r['id']}")
    context.bot.send_document.assert_awaited_once()
    with bot.store.db() as db:
        assert db.execute("SELECT count(*) FROM audit WHERE event='manual_export_sent'").fetchone()[0] == 1


def test_config_fails_closed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("AUTHORIZED_TELEGRAM_USER_ID", "")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "")
    with pytest.raises(ValueError):
        Settings.load()


@pytest.mark.asyncio
async def test_real_transport_photo_album_accumulation_and_shutdown(bot):
    remote = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(b"jpeg content")))
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), user_data={})
    for n in range(2):
        photo = SimpleNamespace(file_size=12, file_unique_id=f"photo{n}", get_file=AsyncMock(return_value=remote))
        message = SimpleNamespace(text=None, caption=SAMPLE if n == 0 else None,
                                  photo=[photo], media_group_id="group1", message_id=10+n,
                                  chat_id=123, forward_origin=None)
        await bot.received(update_for(effective_message=message, update_id=100+n), context)
    records = bot.store.all()
    assert len(records) == 1
    assert len(records[0]["photos"]) == 2
    assert records[0]["fields"]["location"] == "Kajang"
    import asyncio
    await asyncio.sleep(2.1)
    context.bot.send_message.assert_awaited_once()
    await bot.shutdown(None)
    assert not bot.album_tasks


def test_application_registers_commands_and_callbacks_without_network(bot):
    app = bot.application()
    commands = app.handlers[0][0].commands
    assert {"start", "drafts", "facebook", "mudah", "status", "help", "profile"} == set(commands)
    assert len(app.handlers[0]) == 3
