import logging
import random
import string
import asyncio
import aiohttp
import os
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
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
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))   # ← তোমার Telegram User ID দাও
DEVELOPER = "@muintop1"
BOT_NAME  = "⚡ AC Temp Mail"

# ─────────────────────────────────────────────
#  Temp‑mail domains
# ─────────────────────────────────────────────
DOMAINS = [
    "1secmail.com",
    "1secmail.net",
    "1secmail.org",
    "wwjmp.com",
    "esiix.com",
]

# ─────────────────────────────────────────────
#  In‑memory store
# ─────────────────────────────────────────────
user_sessions: dict[int, dict] = {}
all_users:     set[int]        = set()   # /start করা সব ইউজার
awaiting_cast: dict[int, bool] = {}      # broadcast mode


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def random_username(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_email() -> tuple[str, str, str]:
    login  = random_username()
    domain = random.choice(DOMAINS)
    return f"{login}@{domain}", login, domain


def extract_otp(raw_body: str) -> str | None:
    """
    Email body থেকে OTP/Verification code বের করে।
    HTML সহ raw body ব্যবহার করে better detection এর জন্য।
    """
    # HTML ট্যাগ সরাও
    clean = re.sub(r"<[^>]+>", " ", raw_body)
    clean = re.sub(r"&nbsp;|&#160;", " ", clean)
    clean = re.sub(r"&amp;", "&", clean)
    clean = " ".join(clean.split())

    # ১. Keyword এর কাছে থাকা কোড খোঁজো
    keyword_patterns = [
        r'(?:code|otp|pin|passcode|verify|verification|token|kode|номер)[^\d]{0,20}(\d{4,8})',
        r'(\d{4,8})\s*(?:is your|as your|ist dein)',
        r'(?:use|enter|input)[^\d]{0,15}(\d{4,8})',
    ]
    for pat in keyword_patterns:
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            return m.group(1)

    # ২. সাধারণ digit patterns (সবচেয়ে সাধারণ OTP সাইজ থেকে শুরু)
    digit_patterns = [
        r'\b([0-9]{6})\b',
        r'\b([0-9]{4})\b',
        r'\b([0-9]{8})\b',
        r'\b([0-9]{5})\b',
        r'\b([0-9]{7})\b',
    ]
    for pat in digit_patterns:
        matches = re.findall(pat, clean)
        if matches:
            # Year ও phone number filter করো
            for code in matches:
                if not (1900 <= int(code) <= 2100):  # year না
                    return code

    return None


def clean_body(body: str, limit: int = 600) -> str:
    """HTML ট্যাগ সরিয়ে বডি পরিষ্কার করে।"""
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"&nbsp;|&#160;", " ", body)
    body = re.sub(r"&amp;", "&", body)
    body = re.sub(r"&lt;", "<", body)
    body = re.sub(r"&gt;", ">", body)
    body = " ".join(body.split())
    return body[:limit]


# ─────────────────────────────────────────────
#  Keyboards  (সব বাটন নিচে সুন্দর করে সাজানো)
# ─────────────────────────────────────────────
def main_keyboard() -> InlineKeyboardMarkup:
    """হোম স্ক্রিনের কীবোর্ড।"""
    buttons = [
        [InlineKeyboardButton("📬  GET MAIL",   callback_data="get_mail")],
        [InlineKeyboardButton("🔑  GET CODE",   callback_data="get_code")],
        [InlineKeyboardButton("👤  PROFILE",    callback_data="profile")],
        [InlineKeyboardButton("👨‍💻  DEVELOPER",  callback_data="developer")],
    ]
    return InlineKeyboardMarkup(buttons)


def mail_keyboard() -> InlineKeyboardMarkup:
    """GET MAIL করার পরে দেখানো কীবোর্ড।"""
    buttons = [
        [InlineKeyboardButton("🔑  GET CODE",   callback_data="get_code")],
        [InlineKeyboardButton("🔄  নতুন মেইল",  callback_data="get_mail")],
        [InlineKeyboardButton("🏠  HOME",        callback_data="home")],
    ]
    return InlineKeyboardMarkup(buttons)


def code_keyboard() -> InlineKeyboardMarkup:
    """GET CODE করার পরে দেখানো কীবোর্ড।"""
    buttons = [
        [InlineKeyboardButton("🔄  কোড রিফ্রেশ", callback_data="get_code")],
        [InlineKeyboardButton("📬  নতুন মেইল",   callback_data="get_mail")],
        [InlineKeyboardButton("🏠  HOME",         callback_data="home")],
    ]
    return InlineKeyboardMarkup(buttons)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠  Back to Home", callback_data="home")]]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📢  Broadcast",   callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊  Statistics",  callback_data="admin_stats")],
        [InlineKeyboardButton("🏠  HOME",         callback_data="home")],
    ]
    return InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────
#  1secmail API
# ─────────────────────────────────────────────
API_BASE = "https://www.1secmail.com/api/v1/"


async def fetch_inbox(login: str, domain: str) -> list[dict]:
    url = f"{API_BASE}?action=getMessages&login={login}&domain={domain}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.error("Inbox fetch error: %s", e)
    return []


async def fetch_message(login: str, domain: str, msg_id: int) -> dict | None:
    url = f"{API_BASE}?action=readMessage&login={login}&domain={domain}&id={msg_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
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
    uid  = user.id
    all_users.add(uid)

    # Username দেখানো (@username থাকলে সেটা, নাহলে first name)
    username_str = f"@{user.username}" if user.username else f"({user.first_name})"

    welcome = (
        f"┌─────────────────────────┐\n"
        f"│  🌟  {BOT_NAME}  🌟  │\n"
        f"└─────────────────────────┘\n\n"
        f"👋 স্বাগতম, <b>{user.first_name}</b>!\n"
        f"🔗 Username: <b>{username_str}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 ফ্রি টেম্পোরারি ইমেইল সার্ভিস\n"
        f"যেকোনো সাইটে রেজিস্ট্রেশনে ব্যবহার করো!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✨ <b>কি কি করতে পারবে?</b>\n\n"
        f"   📬 <b>GET MAIL</b>  → নতুন ইমেইল তৈরি\n"
        f"   🔑 <b>GET CODE</b>  → OTP / কোড দেখো\n"
        f"   👤 <b>PROFILE</b>   → তোমার মেইল দেখো\n"
        f"   👨‍💻 <b>DEVELOPER</b> → যোগাযোগ করো\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ নিচের বাটন থেকে শুরু করো!"
    )
    await update.message.reply_html(welcome, reply_markup=main_keyboard())


# ─────────────────────────────────────────────
#  /admin  command  (শুধু Admin)
# ─────────────────────────────────────────────
async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    all_users.add(uid)

    if not is_admin(uid):
        await update.message.reply_html(
            "🚫 <b>Access Denied!</b>\n\n"
            "এই কমান্ড শুধুমাত্র Admin ব্যবহার করতে পারবে।"
        )
        return

    text = (
        f"┌─────────────────────────┐\n"
        f"│  🛡️    ADMIN PANEL    🛡️  │\n"
        f"└─────────────────────────┘\n\n"
        f"👤 <b>Admin:</b> {DEVELOPER}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Bot Stats:</b>\n\n"
        f"   👥 Total Users    : <b>{len(all_users)}</b>\n"
        f"   📧 Active Sessions: <b>{len(user_sessions)}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ <b>Commands:</b>\n\n"
        f"   /cast   → সবার কাছে Broadcast করো\n"
        f"   /admin  → এই প্যানেল\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_html(text, reply_markup=admin_keyboard())


# ─────────────────────────────────────────────
#  /cast  command  (Broadcast — শুধু Admin)
# ─────────────────────────────────────────────
async def cast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    all_users.add(uid)

    if not is_admin(uid):
        await update.message.reply_html(
            "🚫 <b>Access Denied!</b>\n\n"
            "Broadcast শুধুমাত্র Admin ব্যবহার করতে পারবে।"
        )
        return

    # /cast এর পরে সরাসরি লেখা থাকলে
    if ctx.args:
        msg_text = " ".join(ctx.args)
        await _broadcast_text(update, ctx, msg_text)
        return

    # Reply করে /cast দিলে সেই মেসেজ broadcast করো
    if update.message.reply_to_message:
        await _broadcast_copy(update, ctx, update.message.reply_to_message)
        return

    # কিছুই না থাকলে broadcast mode এ ঢোকো
    awaiting_cast[uid] = True
    await update.message.reply_html(
        f"┌─────────────────────────┐\n"
        f"│  📢    BROADCAST MODE    │\n"
        f"└─────────────────────────┘\n\n"
        f"এখন যে মেসেজ পাঠাবে সেটি\n"
        f"সকল <b>{len(all_users)}</b> জন ইউজারের কাছে যাবে।\n\n"
        f"📝 টেক্সট, ছবি, ভিডিও — যেকোনো ধরনের মেসেজ!\n\n"
        f"❌ বাতিল করতে /cancel লেখো।"
    )


async def _broadcast_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    success = fail = 0
    status = await update.message.reply_html(
        f"⏳ <b>Broadcast শুরু হচ্ছে...</b>\n👥 মোট ইউজার: {len(all_users)}"
    )
    for user_id in list(all_users):
        try:
            await ctx.bot.send_message(
                chat_id=user_id,
                text=f"📢 <b>Broadcast:</b>\n\n{text}",
                parse_mode="HTML",
            )
            success += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await status.edit_text(
        f"✅ <b>Broadcast সম্পন্ন!</b>\n\n"
        f"✅ সফল  : {success}\n"
        f"❌ ব্যর্থ : {fail}\n"
        f"👥 মোট  : {success + fail}",
        parse_mode="HTML",
    )


async def _broadcast_copy(update: Update, ctx: ContextTypes.DEFAULT_TYPE, src_msg) -> None:
    """যেকোনো ধরনের মেসেজ সবার কাছে copy করে পাঠায়।"""
    success = fail = 0
    status = await update.message.reply_html(
        f"⏳ <b>Broadcast শুরু হচ্ছে...</b>\n👥 মোট ইউজার: {len(all_users)}"
    )
    for user_id in list(all_users):
        try:
            await ctx.bot.copy_message(
                chat_id=user_id,
                from_chat_id=src_msg.chat_id,
                message_id=src_msg.message_id,
            )
            success += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await status.edit_text(
        f"✅ <b>Broadcast সম্পন্ন!</b>\n\n"
        f"✅ সফল  : {success}\n"
        f"❌ ব্যর্থ : {fail}\n"
        f"👥 মোট  : {success + fail}",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
#  /cancel  command
# ─────────────────────────────────────────────
async def cancel_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if awaiting_cast.pop(uid, None):
        await update.message.reply_html("❌ <b>Broadcast বাতিল করা হয়েছে।</b>")
    else:
        await update.message.reply_html("ℹ️ কোনো সক্রিয় অপারেশন নেই।")


# ─────────────────────────────────────────────
#  General message handler  (Broadcast mode)
# ─────────────────────────────────────────────
async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    all_users.add(uid)

    # Admin broadcast mode চলছে কিনা চেক করো
    if is_admin(uid) and awaiting_cast.pop(uid, False):
        await _broadcast_copy(update, ctx, update.message)


# ─────────────────────────────────────────────
#  Callback query handler
# ─────────────────────────────────────────────
async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data  = query.data
    uid   = update.effective_user.id
    user  = update.effective_user

    # ── HOME ──────────────────────────────────
    if data == "home":
        text = (
            f"┌─────────────────────────┐\n"
            f"│  🌟  {BOT_NAME}  🌟  │\n"
            f"└─────────────────────────┘\n\n"
            f"👋 হ্যালো, <b>{user.first_name}</b>!\n\n"
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
            f"┌─────────────────────────┐\n"
            f"│  📬  নতুন মেইল তৈরি হয়েছে!  │\n"
            f"└─────────────────────────┘\n\n"
            f"✅ <b>তোমার টেম্প মেইল:</b>\n\n"
            f"<code>{email}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 উপরের মেইলটা ট্যাপ করে কপি করো!\n\n"
            f"⏳ যেকোনো সাইটে ব্যবহার করো, কোড আসলে\n"
            f"   👇 নিচের <b>GET CODE</b> বাটনে চাপো\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=mail_keyboard())

    # ── GET CODE ──────────────────────────────
    elif data == "get_code":
        session = user_sessions.get(uid)
        if not session:
            text = (
                f"⚠️ <b>কোনো ইমেইল পাওয়া গেল না!</b>\n\n"
                f"আগে 📬 <b>GET MAIL</b> বাটনে চেপে\n"
                f"একটি ইমেইল তৈরি করো।"
            )
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard())
            return

        await query.edit_message_text(
            "⏳ <b>ইনবক্স চেক করা হচ্ছে...</b>\n🔍 কোড খোঁজা হচ্ছে, একটু অপেক্ষা করো!",
            parse_mode="HTML",
        )

        messages = await fetch_inbox(session["login"], session["domain"])

        if not messages:
            text = (
                f"┌─────────────────────────┐\n"
                f"│  📭    ইনবক্স খালি!    │\n"
                f"└─────────────────────────┘\n\n"
                f"📧 তোমার মেইল:\n<code>{session['email']}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ মেইল আসতে ৩০–৬০ সেকেন্ড লাগতে পারে।\n"
                f"🔄 আবার চেক করতে <b>কোড রিফ্রেশ</b> চাপো।"
            )
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=code_keyboard())
            return

        # সর্বশেষ মেইলের বিস্তারিত নিয়ে আসো
        latest_id = messages[0]["id"]
        detail    = await fetch_message(session["login"], session["domain"], latest_id)

        if not detail:
            text = (
                f"❌ <b>মেইল লোড করতে সমস্যা হয়েছে!</b>\n\n"
                f"আবার চেষ্টা করো — কোড রিফ্রেশ চাপো।"
            )
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=code_keyboard())
            return

        # Raw body থেকে OTP বের করো (HTML সহ — better accuracy)
        raw_body  = detail.get("textBody") or detail.get("htmlBody") or ""
        body_text = clean_body(raw_body)
        otp       = extract_otp(raw_body)

        lines = [
            f"┌─────────────────────────┐\n"
            f"│  📨  সর্বশেষ মেইল  │\n"
            f"└─────────────────────────┘\n\n"
            f"📨 মোট মেইল : <b>{len(messages)}</b> টি\n"
            f"👤 From     : <code>{detail.get('from', 'Unknown')}</code>\n"
            f"📌 Subject  : {detail.get('subject', '(কোনো বিষয় নেই)')}\n"
            f"📅 Date     : {detail.get('date', '')}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        ]

        if otp:
            lines.append(
                f"\n"
                f"🎯 ━━━━━━━━━━━━━━━━━━━━ 🎯\n"
                f"🔑 <b>OTP / ভেরিফিকেশন কোড:</b>\n\n"
                f"        <code>{otp}</code>\n\n"
                f"👆 উপরের কোডটা ট্যাপ করে কপি করো!\n"
                f"🎯 ━━━━━━━━━━━━━━━━━━━━ 🎯"
            )
        else:
            lines.append(
                f"\n📄 <b>মেইলের বিষয়বস্তু:</b>\n\n"
                f"<code>{body_text if body_text else '(কোনো টেক্সট নেই)'}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 <i>কোনো OTP কোড ডিটেক্ট হয়নি।\n"
                f"উপরের বডি থেকে কোড নিজে খুঁজো।</i>"
            )

        await query.edit_message_text(
            "".join(lines), parse_mode="HTML", reply_markup=code_keyboard()
        )

    # ── PROFILE ───────────────────────────────
    elif data == "profile":
        session      = user_sessions.get(uid)
        username_str = f"@{user.username}" if user.username else "N/A"

        if not session:
            text = (
                f"┌─────────────────────────┐\n"
                f"│  👤    তোমার প্রোফাইল    │\n"
                f"└─────────────────────────┘\n\n"
                f"🙋 নাম      : <b>{user.first_name}</b>\n"
                f"🔗 Username : <b>{username_str}</b>\n"
                f"🆔 User ID  : <code>{uid}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"❌ এখনো কোনো ইমেইল তৈরি করোনি!\n\n"
                f"📬 <b>GET MAIL</b> চেপে প্রথম মেইল নাও।"
            )
        else:
            text = (
                f"┌─────────────────────────┐\n"
                f"│  👤    তোমার প্রোফাইল    │\n"
                f"└─────────────────────────┘\n\n"
                f"🙋 নাম      : <b>{user.first_name}</b>\n"
                f"🔗 Username : <b>{username_str}</b>\n"
                f"🆔 User ID  : <code>{uid}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📧 <b>বর্তমান ইমেইল:</b>\n"
                f"<code>{session['email']}</code>\n\n"
                f"🌐 ডোমেইন   : <code>{session['domain']}</code>\n"
                f"⏰ তৈরির সময়: {session['created_at']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔄 নতুন মেইল চাইলে GET MAIL চাপো!"
            )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard())

    # ── DEVELOPER ─────────────────────────────
    elif data == "developer":
        text = (
            f"┌─────────────────────────┐\n"
            f"│  👨‍💻   Developer Info   │\n"
            f"└─────────────────────────┘\n\n"
            f"🚀 <b>{BOT_NAME}</b> তৈরি করেছেন:\n\n"
            f"👤 <b>Developer:</b> {DEVELOPER}\n"
            f"💬 <b>Telegram:</b> <a href='https://t.me/muintop1'>{DEVELOPER}</a>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>যোগাযোগের কারণ:</b>\n\n"
            f"   🐛 বাগ রিপোর্ট করতে\n"
            f"   💎 ফিচার রিকোয়েস্ট করতে\n"
            f"   🤝 কোলাবোরেশনের জন্য\n"
            f"   ❓ যেকোনো প্রশ্নের জন্য\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❤️ <i>ধন্যবাদ {BOT_NAME} ব্যবহার করার জন্য!</i>"
        )
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=back_keyboard(),
            disable_web_page_preview=True,
        )

    # ── ADMIN STATS (callback) ─────────────────
    elif data == "admin_stats":
        if not is_admin(uid):
            await query.answer("🚫 Access Denied!", show_alert=True)
            return
        text = (
            f"┌─────────────────────────┐\n"
            f"│  📊    Bot Statistics    │\n"
            f"└─────────────────────────┘\n\n"
            f"👥 Total Users    : <b>{len(all_users)}</b>\n"
            f"📧 Active Sessions: <b>{len(user_sessions)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_keyboard())

    # ── ADMIN BROADCAST (callback) ─────────────
    elif data == "admin_broadcast":
        if not is_admin(uid):
            await query.answer("🚫 Access Denied!", show_alert=True)
            return
        awaiting_cast[uid] = True
        text = (
            f"┌─────────────────────────┐\n"
            f"│  📢   BROADCAST MODE    │\n"
            f"└─────────────────────────┘\n\n"
            f"এখন যে মেসেজ পাঠাবে সেটি\n"
            f"সকল <b>{len(all_users)}</b> জন ইউজারের কাছে যাবে।\n\n"
            f"📝 টেক্সট, ছবি, ভিডিও — যেকোনো!\n\n"
            f"❌ বাতিল করতে /cancel লেখো।"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_keyboard())


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("admin",  admin_cmd))
    app.add_handler(CommandHandler("cast",   cast_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(button_handler))

    # General messages (broadcast mode)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    logger.info("✅ %s bot is running...", BOT_NAME)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
