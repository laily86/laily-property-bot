"""Telegram transport. All callbacks and commands pass the same access guard."""
import asyncio
import json
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from .config import Settings
from .integrations import platform_status
from .listings import FIELDS, generate, review_reasons, validate_edits
from .packages import manual_package
from .profile import ContactProfile
from .storage import MAX_PHOTO_BYTES, Store

HELP = ("Laily Property Draft Automation — DRAF SAHAJA\n"
        "Forward teks/gambar/album dalam chat peribadi. Medan berlabel seperti Lokasi: dan Harga: lebih tepat.\n"
        "/drafts — senarai draf\n/facebook ID — pratonton Facebook\n/mudah ID — pratonton Mudah\n"
        "/status — status integrasi\n/profile — profil nama dan WhatsApp untuk semua draf\n/help — bantuan\n"
        "Save Draft menyimpan draf tempatan dan menghantar ZIP manual selepas pengesahan hak guna. "
        "Tiada iklan diterbitkan atau disimpan dalam akaun platform.")


class Bot:
    def __init__(self, settings):
        self.settings = settings
        self.store = Store(settings.data_dir, settings.key)
        self.album_tasks = {}

    def allowed(self, update):
        user, chat = update.effective_user, update.effective_chat
        permitted = bool(user and chat and user.id == self.settings.user_id and chat.type == "private")
        if not permitted:
            self.store.audit("access_denied")
        return permitted

    def buttons(self, record_id):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Preview Facebook", callback_data=f"preview:facebook:{record_id}"),
             InlineKeyboardButton("Preview Mudah", callback_data=f"preview:mudah:{record_id}")],
            [InlineKeyboardButton("Edit", callback_data=f"edit:local:{record_id}"),
             InlineKeyboardButton("Save Draft", callback_data=f"save:local:{record_id}")],
            [InlineKeyboardButton("Draft Status", callback_data=f"status:local:{record_id}")]])

    async def send(self, bot, chat_id, text, **kwargs):
        # Never parse listing content as HTML/Markdown; forwarded text is untrusted data.
        chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)] or [""]
        for i, chunk in enumerate(chunks):
            await bot.send_message(chat_id=chat_id, text=chunk,
                                   **(kwargs if i == len(chunks)-1 else {}))

    async def command(self, update, context):
        if not self.allowed(update):
            return
        cmd = update.effective_message.text.split()[0].split("@")[0]
        self.store.audit("command", detail={"command": cmd})
        chat_id = update.effective_chat.id
        if cmd in ("/start", "/help"):
            await self.send(context.bot, chat_id, HELP)
        elif cmd == "/profile":
            raw = update.effective_message.text.split(maxsplit=1)
            if len(raw) == 1:
                profile = self.store.contact_profile()
                await self.send(context.bot, chat_id,
                    ("Profil semasa:\n" + profile.contact_text() if profile else "Profil belum ditetapkan.") +
                    "\n\nTetapkan dengan satu mesej:\n/profile Nama anda | Nombor WhatsApp kod negara"
                    "\nContoh rekaan: /profile Ejen Contoh | 60123456789"
                    "\nREN dan agensi sendiri adalah pilihan: /profile Nama | WhatsApp | REN 12345 | Agensi"
                    "\nSemua pratonton dan pakej baharu (termasuk rekod lama) akan menggunakan profil ini. "
                    "Pakej yang sudah dimuat turun tidak berubah. Sumber asal kekal disimpan. "
                    "Gunakan listing hanya dengan kebenaran pemilik/ejen dan hak guna gambar.")
                return
            try:
                profile = ContactProfile.parse(raw[1])
            except ValueError as exc:
                self.store.audit("contact_profile_rejected")
                await self.send(context.bot, chat_id, str(exc))
                return
            self.store.set_contact_profile(profile)
            await self.send(context.bot, chat_id,
                "Profil disimpan secara tersulit. Semua pratonton dan eksport draf seterusnya akan menggunakan:\n" +
                profile.contact_text() +
                "\nNama, REN dan agensi ejen asal tidak digunakan sebagai identiti anda. "
                "Teks asal dan sumber tetap disimpan. Tiada iklan diterbitkan.")
        elif cmd == "/status":
            await self.send(context.bot, chat_id, "\n".join(
                f"{p}: {platform_status(p)['status']} — {platform_status(p)['reason']}" for p in ("facebook", "mudah")))
        elif cmd == "/drafts":
            records = self.store.all()
            if not records:
                await self.send(context.bot, chat_id, "Belum ada draf. Forward satu listing dahulu.")
            for r in records[:20]:
                await self.send(context.bot, chat_id,
                                f"{r['id']} | {r['fields'].get('location') or 'Lokasi belum diketahui'} | LOCAL_DRAFT",
                                reply_markup=self.buttons(r["id"]))
        else:
            records = self.store.all()
            listing_id = context.args[0] if context.args else (records[0]["id"] if records else None)
            if listing_id is None:
                await self.send(context.bot, chat_id, "Forward listing dahulu.")
                return
            try:
                await self.preview(context.bot, chat_id, self.store.get(listing_id), cmd[1:])
            except KeyError:
                await self.send(context.bot, chat_id, "ID draf tidak ditemui.")

    async def preview(self, bot, chat_id, record, platform):
        draft = generate(record, platform, self.store.contact_profile())
        self.store.audit("preview", record["id"], {"platform": platform})
        text = (f"{record['id']} | {platform.upper()} | LOCAL_DRAFT\n"
                f"BM: {draft['title_bm']}\n{draft['description_bm']}\n\n"
                f"EN: {draft['title_en']}\n{draft['description_en']}\n\n"
                "SEMAKAN:\n" + "\n".join(draft["review_reasons"]) +
                f"\nGambar: {len(record['photos'])}\nPendua berpotensi: {', '.join(record['duplicate_candidates']) or 'Tiada dikesan'}")
        await self.send(bot, chat_id, text, reply_markup=self.buttons(record["id"]))

    async def callback(self, update, context):
        if not self.allowed(update):
            return
        query = update.callback_query
        await query.answer()
        try:
            action, platform, listing_id = query.data.split(":")
            if action not in {"preview", "edit", "save", "status", "confirm", "export"}:
                raise ValueError("Tindakan tidak sah")
            record = self.store.get(listing_id)
            self.store.audit("button", listing_id, {"action": action})
            chat_id = update.effective_chat.id
            if action == "preview":
                await self.preview(context.bot, chat_id, record, platform)
            elif action == "edit":
                context.user_data["editing"] = listing_id
                await self.send(context.bot, chat_id,
                    "Hantar satu objek JSON untuk medan yang hendak dibetulkan. Medan: " + ", ".join(FIELDS) +
                    ', availability_confirmed. Contoh:\n{"location":"Kajang", "price":"RM 450,000", '
                    '"availability":"Tersedia", "availability_confirmed":true}\n'
                    "Gunakan fakta yang anda sahkan sahaja. Jika /profile ditetapkan, maklumat ejen dalam draf "
                    "menggunakan profil anda; Edit tidak menggantikan profil. /help untuk batal.")
            elif action == "status":
                await self.send(context.bot, chat_id, "LOCAL_DRAFT\n" +
                    ("NEEDS_REVIEW\n" if review_reasons(record) else "") +
                    "\n".join(f"{p}: {platform_status(p)['status']}" for p in ("facebook", "mudah")) +
                    "\nTiada pautan draf akaun yang disahkan.")
            elif action in ("save", "confirm"):
                if action == "confirm":
                    record["reuse_confirmed"] = True
                    self.store.put(record, "reuse_permission_confirmed")
                if not record["reuse_confirmed"]:
                    await self.send(context.bot, chat_id,
                        "Adakah anda mempunyai kebenaran menggunakan listing DAN semua gambar? "
                        "Sahkan hanya jika benar. Tiada tindakan akaun platform akan dibuat.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                            "Saya sahkan hak guna listing dan gambar", callback_data=f"confirm:local:{listing_id}")]]))
                    return
                self.store.put(record, "local_draft_saved")
                await self.send(context.bot, chat_id, "LOCAL_DRAFT disimpan. Integrasi: INTEGRATION_UNAVAILABLE. "
                    "Pilih pakej manual (teks dan gambar tidak disulitkan semasa dieksport).",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Pakej Facebook", callback_data=f"export:facebook:{listing_id}"),
                                                        InlineKeyboardButton("Pakej Mudah", callback_data=f"export:mudah:{listing_id}")]]))
            elif action == "export":
                package = manual_package(record, platform, self.store.contact_profile())
                self.store.audit("manual_export_requested", listing_id, {"platform": platform})
                await context.bot.send_document(chat_id, InputFile(package, filename=f"{platform}-{listing_id}.zip"),
                    caption="Pakej manual sahaja. Tiada draf disimpan dalam akaun platform. Semak fakta sebelum penggunaan.")
                self.store.audit("manual_export_sent", listing_id, {"platform": platform})
        except (KeyError, ValueError, PermissionError) as exc:
            self.store.audit("callback_rejected")
            await self.send(context.bot, update.effective_chat.id, str(exc))

    def source(self, message):
        origin = message.forward_origin
        result = {"received_message_id": message.message_id,
                  "forwarded": origin is not None}
        if origin:
            result["origin_type"] = str(origin.type)
            result["origin_date"] = origin.date.isoformat()
            channel = getattr(origin, "chat", None)
            if channel:
                result["chat_title"] = channel.title
                result["channel_id"] = channel.id
                if channel.username:
                    result["channel_username"] = channel.username
                original_id = getattr(origin, "message_id", None)
                result["original_message_id"] = original_id
                if channel.username and original_id:
                    result["source_url"] = f"https://t.me/{channel.username}/{original_id}"
            sender_chat = getattr(origin, "sender_chat", None)
            if sender_chat:
                result["sender_chat_id"] = sender_chat.id
                result["sender_chat_title"] = sender_chat.title
            name = getattr(origin, "sender_user_name", None)
            if name:
                result["hidden_sender_name"] = name
            sender = getattr(origin, "sender_user", None)
            if sender:
                result["sender_id"] = sender.id
        return result

    async def received(self, update, context):
        if not self.allowed(update):
            return
        message = update.effective_message
        text = message.text or message.caption or ""
        editing = context.user_data.get("editing")
        if editing and not message.forward_origin and not message.photo:
            try:
                edits = validate_edits(json.loads(text))
                record = self.store.get(editing)
                record["fields"].update(edits)
                if "availability" in edits and "availability_confirmed" not in edits:
                    record["fields"]["availability_confirmed"] = False
                record["reuse_confirmed"] = False
                self.store.put(record, "edited")
                del context.user_data["editing"]
                await self.preview(context.bot, message.chat_id, record, "facebook")
            except (ValueError, KeyError):
                await self.send(context.bot, message.chat_id, "JSON tidak sah atau ID tiada. Cuba lagi; /help untuk batal.")
            return
        photo_bytes, photo_id = None, None
        if message.photo:
            photo = message.photo[-1]
            if photo.file_size and photo.file_size > MAX_PHOTO_BYTES:
                self.store.audit("photo_rejected")
                await self.send(context.bot, message.chat_id, "Had gambar 10 MB. Hantar versi lebih kecil.")
                return
            remote = await photo.get_file()
            photo_bytes = bytes(await remote.download_as_bytearray())
            photo_id = photo.file_unique_id
        album_id = f"{message.chat_id}:{message.media_group_id}" if message.media_group_id else None
        record, outcome = self.store.ingest(text, self.source(message), photo_bytes, photo_id,
                                             album_id, update.update_id)
        if outcome == "replayed":
            return
        if album_id:
            old = self.album_tasks.get(album_id)
            if old:
                old.cancel()
            async def delayed():
                try:
                    await asyncio.sleep(2)
                    await self.preview(context.bot, message.chat_id, self.store.get(record["id"]), "facebook")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.store.audit("album_preview_error", record["id"], {"class": type(exc).__name__})
                finally:
                    if self.album_tasks.get(album_id) is asyncio.current_task():
                        self.album_tasks.pop(album_id, None)
            self.album_tasks[album_id] = asyncio.create_task(delayed())
        else:
            await self.preview(context.bot, message.chat_id, record, "facebook")

    async def on_command(self, update, context):
        if self.allowed(update):
            context.user_data.pop("editing", None)
        await self.command(update, context)

    async def error(self, update, context):
        # Never log exceptions/URLs: Telegram URLs can embed the bot token.
        self.store.audit("error", detail={"class": type(context.error).__name__})
        if update is not None and self.allowed(update):
            try:
                await self.send(context.bot, update.effective_chat.id,
                                "ERROR: Tindakan gagal. Draf yang sudah disimpan kekal tersulit. Cuba /drafts.")
            except Exception:
                self.store.audit("error_notification_failed")

    async def shutdown(self, application):
        tasks = list(self.album_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def application(self):
        app = Application.builder().token(self.settings.token).post_shutdown(self.shutdown).build()
        app.add_handler(CommandHandler(["start", "help", "drafts", "facebook", "mudah", "status", "profile"], self.on_command))
        app.add_handler(CallbackQueryHandler(self.callback))
        app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, self.received))
        app.add_error_handler(self.error)
        return app


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("telegram").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    try:
        bot = Bot(Settings.load())
        bot.application().run_polling(allowed_updates=["message", "callback_query"], drop_pending_updates=False)
    except Exception:
        raise SystemExit("Permulaan gagal. Semak .env, rangkaian dan audit; butiran sensitif tidak dicetak.") from None


if __name__ == "__main__":
    main()
