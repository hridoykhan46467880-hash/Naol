import logging
import random
import string
import asyncio
import aiohttp
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Config  (set via environment variables)
# ─────────────────────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DEVELOPER   = "@muintop1"
BOT_NAME    = "AC Temp Mail"

# ─────────────────────────────────────────────
#  Temp‑mail domains (public free domains)
# ─────────────────────────────────────────────
DOMAINS = [
    "1secmail.com",
    "1secmail.net",
    "1secmail.org",
    "wwjmp.com",
    "esiix.com",
]

# In‑memory store  {user_id: {"email": str, "login": str, "domain": str}}
user_sessions: dict[int, dict] = {}


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def random_username(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_email() -> tuple[str, str, str]:
    """Return (full_email, login, domain)."""
    login  = random_username()
    domain = random.choice(DOMAINS)
    return f"{login}@{domain}", login, domain


def main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("📬 GET MAIL",  callback_data="get_mail"),
            InlineKeyboardButton("📥 INBOX",     callback_data="inbox"),
        ],
        [
            InlineKeyboardButton("👤 PROFILE",   callback_data="profile"),
            InlineKeyboardButton("👨‍💻 DEVELOPER", callback_data="developer"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 Back to Home", callback_data="home")]]
    )


# ─────────────────────────────────────────────
#  1secmail API
# ─────────────────────────────────────────────
API_BASE = "https://www.1secmail.com/api/v1/"


async def fetch_inbox(login: str, domain: str) -> list[dict]:
    url = f"{API_BASE}?action=getMessages&login={login}&domain={domain}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.error("Inbox fetch error: %s", e)
    return []


async def fetch_message(login: str, domain: str, msg_id: int) -> dict | None:
    url = f"{API_BASE}?action=readMessage&login={login}&domain={domain}&id={msg_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.error("Message fetch error: %s", e)
    return None


# ─────────────────────────────────────────────
#  /start  command
# ─────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome = (
        f"╔══════════════════════════╗\n"
        f"║  🌟  {BOT_NAME}  🌟  ║\n"
        f"╚══════════════════════════╝\n\n"
        f"👋 হ্যালো, <b>{user.first_name}</b>! স্বাগতম!\n\n"
        f"📧 আমি তোমাকে যেকোনো সাইটে রেজিস্ট্রেশনের জন্য\n"
        f"   <b>ফ্রি টেম্পোরারি ইমেইল</b> দিতে পারব!\n\n"
        f"✨ <b>কি কি করতে পারবে?</b>\n"
        f"   📬 GET MAIL  → নতুন ইমেইল তৈরি করো\n"
        f"   📥 INBOX     → মেইল ও কোড দেখো\n"
        f"   👤 PROFILE   → তোমার বর্তমান মেইল দেখো\n"
        f"   👨‍💻 DEVELOPER → ডেভেলপারের সাথে যোগাযোগ করো\n\n"
        f"⚡ নিচের বাটন থেকে শুরু করো!"
    )
    await update.message.reply_html(welcome, reply_markup=main_keyboard())


# ─────────────────────────────────────────────
#  Callback query handler
# ─────────────────────────────────────────────
async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query  = update.callback_query
    await query.answer()
    data   = query.data
    uid    = update.effective_user.id
    uname  = update.effective_user.first_name

    # ── HOME ──────────────────────────────────
    if data == "home":
        text = (
            f"🏠 <b>প্রধান মেনুতে ফিরে এলে!</b>\n\n"
            f"নিচের বাটন থেকে যা চাও সেটা বেছে নাও 👇"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard())

    # ── GET MAIL ──────────────────────────────
    elif data == "get_mail":
        email, login, domain = generate_email()
        user_sessions[uid] = {
            "email":      email,
            "login":      login,
            "domain":     domain,
            "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        }
        text = (
            f"╔══════════════════════════╗\n"
            f"║  📬  নতুন ইমেইল তৈরি হয়েছে!  ║\n"
            f"╚══════════════════════════╝\n\n"
            f"✅ <b>তোমার টেম্প মেইল:</b>\n"
            f"<code>{email}</code>\n\n"
            f"📋 উপরের মেইলটা কপি করে যেকোনো সাইটে ব্যবহার করো!\n\n"
            f"⏳ মেইলে কোড আসলে <b>📥 INBOX</b> বাটনে চাপো\n"
            f"🔄 নতুন মেইল চাইলে আবার <b>GET MAIL</b> চাপো\n\n"
            f"⚠️ <i>নোট: টেম্প মেইল সাময়িক, গুরুত্বপূর্ণ কাজে ব্যবহার করো না।</i>"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard())

    # ── INBOX ─────────────────────────────────
    elif data == "inbox":
        session = user_sessions.get(uid)
        if not session:
            text = (
                f"⚠️ <b>কোনো ইমেইল পাওয়া গেল না!</b>\n\n"
                f"আগে <b>📬 GET MAIL</b> বাটনে চেপে একটি ইমেইল তৈরি করো,\n"
                f"তারপর ইনবক্স চেক করো।"
            )
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard())
            return

        await query.edit_message_text(
            "⏳ <b>ইনবক্স লোড হচ্ছে... একটু অপেক্ষা করো!</b>",
            parse_mode="HTML",
        )

        messages = await fetch_inbox(session["login"], session["domain"])

        if not messages:
            text = (
                f"📭 <b>ইনবক্স এখন খালি!</b>\n\n"
                f"📧 তোমার মেইল: <code>{session['email']}</code>\n\n"
                f"⏳ মেইল আসতে ৩০–৬০ সেকেন্ড লাগতে পারে।\n"
                f"🔄 আবার চেক করতে <b>INBOX</b> বাটন চাপো।"
            )
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard())
            return

        # show latest 5 messages
        lines = [
            f"📥 <b>ইনবক্স — {session['email']}</b>\n",
            f"📨 মোট <b>{len(messages)}</b> টি মেইল পাওয়া গেছে!\n",
        ]
        for i, msg in enumerate(messages[:5], 1):
            lines.append(
                f"\n━━━━━━━━━━━━━━━━━━━━\n"
                f"✉️ <b>মেইল #{i}</b>\n"
                f"👤 From : <code>{msg.get('from','Unknown')}</code>\n"
                f"📌 Subject : {msg.get('subject','(কোনো বিষয় নেই)')}\n"
                f"📅 Date : {msg.get('date','')}"
            )

        # fetch body of the latest mail
        latest_id = messages[0]["id"]
        detail    = await fetch_message(session["login"], session["domain"], latest_id)
        if detail:
            body = detail.get("textBody") or detail.get("htmlBody") or ""
            # strip html tags simply
            import re
            body = re.sub(r"<[^>]+>", " ", body).strip()
            body = " ".join(body.split())[:600]  # limit chars
            lines.append(
                f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
                f"📄 <b>সর্বশেষ মেইলের বিষয়বস্তু:</b>\n\n"
                f"<code>{body if body else '(কোনো টেক্সট নেই)'}</code>"
            )

        lines.append("\n\n🔄 আপডেট করতে INBOX আবার চাপো।")
        await query.edit_message_text(
            "".join(lines), parse_mode="HTML", reply_markup=main_keyboard()
        )

    # ── PROFILE ───────────────────────────────
    elif data == "profile":
        session = user_sessions.get(uid)
        if not session:
            text = (
                f"👤 <b>তোমার প্রোফাইল</b>\n\n"
                f"❌ এখনো কোনো ইমেইল তৈরি করোনি!\n\n"
                f"📬 <b>GET MAIL</b> বাটনে চেপে প্রথম মেইল নাও।"
            )
        else:
            text = (
                f"╔══════════════════════════╗\n"
                f"║  👤  তোমার প্রোফাইল  ║\n"
                f"╚══════════════════════════╝\n\n"
                f"🙋 নাম    : <b>{uname}</b>\n"
                f"🆔 User ID : <code>{uid}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📧 <b>বর্তমান ইমেইল:</b>\n"
                f"<code>{session['email']}</code>\n\n"
                f"🌐 ডোমেইন  : <code>{session['domain']}</code>\n"
                f"⏰ তৈরির সময় : {session['created_at']}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔄 নতুন মেইল চাইলে GET MAIL চাপো!"
            )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard())

    # ── DEVELOPER ─────────────────────────────
    elif data == "developer":
        text = (
            f"╔══════════════════════════╗\n"
            f"║  👨‍💻  Developer Info  ║\n"
            f"╚══════════════════════════╝\n\n"
            f"🚀 <b>{BOT_NAME}</b> বটটি তৈরি করেছেন:\n\n"
            f"👤 <b>Developer:</b> {DEVELOPER}\n"
            f"💬 <b>Telegram:</b> <a href='https://t.me/muintop1'>{DEVELOPER}</a>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>যোগাযোগের কারণ:</b>\n"
            f"   🐛 বাগ রিপোর্ট করতে\n"
            f"   💎 ফিচার রিকোয়েস্ট করতে\n"
            f"   🤝 কোলাবোরেশনের জন্য\n"
            f"   ❓ যেকোনো প্রশ্নের জন্য\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"❤️ <i>ধন্যবাদ {BOT_NAME} ব্যবহার করার জন্য!</i>"
        )
        await query.edit_message_text(
            text, parse_mode="HTML",
            reply_markup=back_keyboard(),
            disable_web_page_preview=True,
        )


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("✅ %s bot is running...", BOT_NAME)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
