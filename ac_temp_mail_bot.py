import os
import time
import random
import string
import re

import httpx

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing!")

DEVELOPER = "@muintop1"

API_URL = "https://www.1secmail.com/api/v1/"

TELEGRAM_MAX_LEN = 4096

# user_id -> mailbox information
users = {}

# Shared async HTTP client (created in main())
http_client: httpx.AsyncClient | None = None


# =========================
# KEYBOARD
# =========================

def main_keyboard():
    keyboard = [
        ["📧 GET MAIL", "📥 INBOX"],
        ["👤 PROFILE", "👨‍💻 DEVELOPER"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


# =========================
# MARKDOWN SAFETY
# =========================

def escape_md(text: str) -> str:
    """Escape characters that break legacy Telegram Markdown parsing."""
    if not text:
        return text
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def strip_html(text: str) -> str:
    """Very small HTML stripper for htmlBody fallback content."""
    if not text:
        return text
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text


async def send_long_message(update: Update, text: str, **kwargs):
    """Split a message into Telegram-safe chunks and send them in order."""
    if len(text) <= TELEGRAM_MAX_LEN:
        await update.message.reply_text(text, **kwargs)
        return

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= TELEGRAM_MAX_LEN:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, TELEGRAM_MAX_LEN)
        if split_at == -1:
            split_at = TELEGRAM_MAX_LEN
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]

    for chunk in chunks:
        await update.message.reply_text(chunk, **kwargs)


# =========================
# GENERATE RANDOM MAIL
# =========================

def generate_mail():
    domains = [
        "1secmail.com",
        "1secmail.org",
        "1secmail.net"
    ]

    login = (
        "ac"
        + ''.join(
            random.choices(
                string.ascii_lowercase + string.digits,
                k=10
            )
        )
    )

    domain = random.choice(domains)

    email = f"{login}@{domain}"

    return login, domain, email


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    welcome = f"""
╔══════════════════════╗
      🤖 AC TEMP MAIL
╚══════════════════════╝

👋 Welcome, {user.first_name}!

🚀 Your fast & simple temporary
email service is ready.

📧 Generate a new temporary email
📥 Check your inbox & verification codes
👤 View your profile
👨‍💻 Contact the developer

⚡ Fast • Simple • Free

👇 Choose an option from the menu.
"""

    await update.message.reply_text(
        welcome,
        reply_markup=main_keyboard()
    )


# =========================
# GET MAIL
# =========================

async def get_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    login, domain, email = generate_mail()

    users[user_id] = {
        "login": login,
        "domain": domain,
        "email": email,
        "created": time.time()
    }

    message = f"""
╔══════════════════════╗
       📧 NEW MAIL
╚══════════════════════╝

✅ Temporary email generated!

📮 Email:
`{email}`

🌐 Domain:
`{domain}`

📥 Press **INBOX** to check incoming
messages and verification codes.

🔄 Want another email?
Just press **GET MAIL** again.
"""

    await update.message.reply_text(
        message,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


# =========================
# INBOX
# =========================

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in users:

        await update.message.reply_text(
            """
📥 **INBOX**

❌ You don't have a temporary email yet.

👉 First press **📧 GET MAIL**
to generate one.
""",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )

        return

    mailbox = users[user_id]

    login = mailbox["login"]
    domain = mailbox["domain"]
    email = mailbox["email"]

    try:

        params = {
            "action": "getMessages",
            "login": login,
            "domain": domain
        }

        response = await http_client.get(API_URL, params=params)

        if response.status_code != 200:

            await update.message.reply_text(
                "⚠️ Inbox service is temporarily unavailable. Please try again.",
                reply_markup=main_keyboard()
            )

            return

        messages = response.json()

        if not messages:

            await update.message.reply_text(
                f"""
📥 **INBOX**

📮 `{email}`

📭 No new messages yet.

⏳ Waiting for incoming mail...

🔄 Press **INBOX** again after a few seconds.
""",
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )

            return

        text = f"""
╔══════════════════════╗
       📥 YOUR INBOX
╚══════════════════════╝

📮 `{email}`

📨 Messages: {len(messages)}

"""

        for msg in messages[:10]:

            msg_id = msg.get("id")
            sender = escape_md(msg.get("from", "Unknown"))
            subject = escape_md(msg.get("subject", "No subject"))
            date = msg.get("date", "")

            text += f"""
━━━━━━━━━━━━━━━━━━

🆔 ID: `{msg_id}`
👤 From: `{sender}`
📌 Subject: `{subject}`
🕐 Date: `{date}`

"""

            # Try to get complete message
            try:

                read_params = {
                    "action": "readMessage",
                    "login": login,
                    "domain": domain,
                    "id": msg_id
                }

                detail_response = await http_client.get(API_URL, params=read_params)

                if detail_response.status_code == 200:

                    detail = detail_response.json()

                    body = detail.get("textBody") or strip_html(detail.get("htmlBody") or "")

                    if body:

                        # Keep message reasonably short
                        body = escape_md(body[:2000])

                        text += f"""
📄 Message:

{body}

"""

            except Exception:
                pass

        text += """
━━━━━━━━━━━━━━━━━━

🔄 Press **INBOX** again to refresh.
"""

        await send_long_message(
            update,
            text,
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )

    except httpx.RequestError:

        await update.message.reply_text(
            """
⚠️ Unable to connect to the temporary
mail service right now.

🔄 Please try **INBOX** again.
""",
            reply_markup=main_keyboard()
        )

    except Exception as e:

        print("Inbox error:", e)

        await update.message.reply_text(
            """
❌ Something went wrong while loading
your inbox.

🔄 Please try again.
""",
            reply_markup=main_keyboard()
        )


# =========================
# PROFILE
# =========================

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id

    if user_id in users:

        email = users[user_id]["email"]

    else:

        email = "❌ No temporary mail"

    username = (
        f"@{user.username}"
        if user.username
        else "Not set"
    )

    text = f"""
╔══════════════════════╗
        👤 PROFILE
╚══════════════════════╝

🧑 Name:
{escape_md(user.first_name)}

🔹 Username:
{escape_md(username)}

🆔 Telegram ID:
`{user_id}`

📧 Current Mail:
`{email}`

━━━━━━━━━━━━━━━━━━

🤖 Bot: AC temp mail
⚡ Temporary Email Service
"""

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


# =========================
# DEVELOPER
# =========================

async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = f"""
╔══════════════════════╗
       👨‍💻 DEVELOPER
╚══════════════════════╝

🤖 AC temp mail

🛠 Developer:
{DEVELOPER}

💬 Need help or want to report
a problem?

👉 Contact the developer directly:

{DEVELOPER}

❤️ Thanks for using AC temp mail!
"""

    await update.message.reply_text(
        text,
        reply_markup=main_keyboard()
    )


# =========================
# TEXT HANDLER
# =========================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "📧 GET MAIL":
        await get_mail(update, context)

    elif text == "📥 INBOX":
        await inbox(update, context)

    elif text == "👤 PROFILE":
        await profile(update, context)

    elif text == "👨‍💻 DEVELOPER":
        await developer(update, context)

    else:

        await update.message.reply_text(
            """
🤖 I didn't understand that command.

👇 Please use the buttons below.
""",
            reply_markup=main_keyboard()
        )


# =========================
# ERROR HANDLER
# =========================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):

    print("Bot error:", context.error)


# =========================
# LIFECYCLE HOOKS
# =========================

async def post_init(application: Application):
    global http_client
    http_client = httpx.AsyncClient(timeout=15)


async def post_shutdown(application: Application):
    global http_client
    if http_client is not None:
        await http_client.aclose()


# =========================
# MAIN
# =========================

def main():

    print("🚀 AC temp mail is starting...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    application.add_error_handler(error_handler)

    print("✅ AC temp mail is running!")

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
