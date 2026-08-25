# 🤖 AC Temp Mail Bot — Deployment Guide

## 📁 ফাইল লিস্ট
```
main.py          ← সম্পূর্ণ বট কোড
requirements.txt ← Python লাইব্রেরি
Procfile         ← Railway এর জন্য
```

---

## 🚀 Step 1 — BotFather থেকে Token নাও

1. Telegram এ [@BotFather](https://t.me/BotFather) খোলো
2. `/newbot` কমান্ড দাও
3. বটের নাম দাও: `AC Temp Mail`
4. Username দাও: `ac_temp_mail_bot` (বা যা খুশি)
5. Token কপি করো → এরকম দেখাবে: `7xxxxxxxx:AAFxxx...`

---

## 🐙 Step 2 — GitHub এ Push করো

```bash
git init
git add .
git commit -m "AC Temp Mail Bot - Initial"
git branch -M main
git remote add origin https://github.com/তোমার-username/ac-temp-mail-bot.git
git push -u origin main
```

---

## 🚂 Step 3 — Railway তে Deploy করো

1. [railway.app](https://railway.app) এ যাও → GitHub দিয়ে Login করো
2. **New Project** → **Deploy from GitHub repo** → তোমার repo সিলেক্ট করো
3. **Variables** ট্যাবে গিয়ে Environment Variable যোগ করো:
   ```
   BOT_TOKEN = তোমার_টোকেন_এখানে
   ```
4. **Deploy** বাটনে চাপো ✅

---

## ✅ বট টেস্ট করো

Telegram এ তোমার বটে যাও → `/start` দাও → সব বাটন কাজ করছে কিনা দেখো!

---

## 📌 নোট

- বট সম্পূর্ণ **ফ্রি** Railway Hobby plan এ চলবে
- `user_sessions` in-memory — বট restart হলে session রিসেট হয়
- প্রতিবার `GET MAIL` চাপলে নতুন ইমেইল তৈরি হবে
