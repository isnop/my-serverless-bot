import json
import logging
import re
import os
from http.server import BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
# ==========================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# State disimpan di memori (cocok untuk bot sederhana, tapi akan hilang saat cold start)
last_user = {}

# ---------- Handler Functions (Sama seperti sebelumnya) ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello, I'm your support assistant.\n\n"
        "Just send me a message directly. Text, images, voice messages, and files are all supported. "
        "I'll reply as soon as possible."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "You can contact us by sending a message directly. "
        "Text, images, voice messages, and files are all supported.\n"
        "Please wait patiently for a reply 🙂"
    )

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    if user.id == ADMIN_ID:
        return
    last_user[ADMIN_ID] = user.id
    info = (
        f"📩 New Message\n"
        f"From: {user.first_name} (@{user.username})\n"
        f"User ID: {user.id}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=info)
    await context.bot.forward_message(
        chat_id=ADMIN_ID, from_chat_id=msg.chat_id, message_id=msg.message_id
    )
    await msg.reply_text(
        "✅ Your message has been received. Please wait for a reply from our team."
    )

def extract_user_id(replied) -> int | None:
    if getattr(replied, "forward_from", None):
        return replied.forward_from.id
    text_to_parse = replied.text or replied.caption
    if text_to_parse:
        m = re.search(r"User ID:\s*(\d+)", text_to_parse)
        if m:
            return int(m.group(1))
    return None

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.from_user.id != ADMIN_ID:
        return
    target_id = None
    if msg.reply_to_message:
        target_id = extract_user_id(msg.reply_to_message)
    if not target_id:
        target_id = last_user.get(ADMIN_ID)
    if not target_id:
        await msg.reply_text("⚠️ No user to reply to yet. Wait for a user to send a message first.")
        return
    try:
        await context.bot.copy_message(
            chat_id=target_id, from_chat_id=msg.chat_id, message_id=msg.message_id
        )
        await msg.reply_text(f"✅ Reply sent to user {target_id}.")
    except Exception as e:
        await msg.reply_text(f"❌ Failed to send reply: {e}")

# ---------- Entry Point Serverless (Vercel) ----------
async def process_update(update_data: dict):
    """Membangun application, memproses update, lalu shutdown."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(~filters.COMMAND & ~filters.User(ADMIN_ID), forward_to_admin))
    application.add_handler(MessageHandler(filters.User(ADMIN_ID) & ~filters.COMMAND, admin_reply))

    update = Update.de_json(data=update_data, bot=application.bot)
    
    await application.initialize()
    await application.process_update(update)
    await application.shutdown()

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        try:
            update_data = json.loads(body)
            # Jalankan proses async
            import asyncio
            asyncio.run(process_update(update_data))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            self.send_response(500)
            self.end_headers()

    def do_GET(self):
        # Endpoint untuk health check
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running')
