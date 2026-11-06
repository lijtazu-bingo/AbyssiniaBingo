import os
import re
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

TOKEN = "8019235278:AAERiDiVi1lSnQVaHEaasXpeKRSDbZfxaAA"
WEBAPP_URL = "https://gygvl-196-190-60-57.run.pinggy-free.link"
ADMIN_ID = 5925033073
BOT_USERNAME = "AbisinyaBingo_Bot"

def init_db():
    conn = sqlite3.connect("bingo.db", timeout=10)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, phone TEXT, balance REAL DEFAULT 100.0, win_balance REAL DEFAULT 0.0, language TEXT DEFAULT 'am', referred_by INTEGER, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount REAL, status TEXT, phone TEXT, sms TEXT, created_at TEXT)")
    conn.commit()
    conn.close()

def create_user(uid, uname, fname):
    conn = sqlite3.connect("bingo.db", timeout=10)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, balance, win_balance, language, created_at) VALUES (?, ?, ?, 100.0, 0.0, 'am', ?)", (uid, uname, fname, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_balance(uid):
    conn = sqlite3.connect("bingo.db", timeout=10)
    c = conn.cursor()
    c.execute("SELECT balance, win_balance FROM users WHERE user_id = ?", (uid,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"play": row[0] or 0, "win": row[1] or 0}
    return {"play": 0, "win": 0}

def get_language(uid):
    conn = sqlite3.connect("bingo.db", timeout=10)
    c = conn.cursor()
    c.execute("SELECT language FROM users WHERE user_id = ?", (uid,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return "am"

def update_language(uid, lang):
    conn = sqlite3.connect("bingo.db", timeout=10)
    c = conn.cursor()
    c.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, uid))
    conn.commit()
    conn.close()

TEXTS = {
    "am": {
        "welcome": "🎉 እንኳን ወደ Abisinya Bingo በደህና መጡ!",
        "play": "🎯 Play Abisinya Bingo",
        "deposit": "💰 Deposit",
        "withdraw": "📤 Withdraw",
        "balance": "💵 Check Balance",
        "invite": "👥 Invite Friends",
        "history": "📋 History",
        "support": "💬 Support",
        "language": "🌍 Language",
        "help": "ℹ️ Help",
        "leaderboard": "🏆 Leaderboard",
        "register": "📱 Register",
        "choose_lang": "🌐 ቋንቋ ይምረጡ:",
        "bal_msg": "💰 **ቀሪ ሂሳብ**\n\n🎯 PLAY: {play} ብር\n🏆 WIN: {win} ብር",
        "help_msg": "🆘 **እርዳታ**\n\n1. 🎯 Play Abisinya Bingo ይጫኑ\n2. ካርቴላ ይምረጡ\n3. BINGO ሲሆን ይጫኑ",
        "deposit_msg": "💰 **ገንዘብ ማስገባት**\n\nየክፍያ አማራጭ ይምረጡ:",
        "invite_msg": "👥 **የግብዣ ሊንክ**\n\n{link}\n\n✨ ጓደኛዎን ይጋብዙ እና 30 ብር ያግኙ!",
        "history_msg": "📋 **ታሪክ**\n\nእስካሁን ታሪክ የለም።",
        "support_msg": "💬 **ድጋፍ**\n\n👤 @Tazikes",
        "leaderboard_msg": "🏆 **Leaderboard**\n\n1. Abisinya_Pro - 14 ድል\n2. Winner_77 - 9 ድል\n3. BingoKing - 6 ድል",
        "telebirr_msg": "🏦 **Telebirr**\n\n👤 Name: tazebew\n👉 Account: 0968940123\n\n📩 SMS ይለጥፉ:",
        "cbe_msg": "🏦 **CBE**\n\n👤 Name: tazebew\n👉 Account: 1000390803005\n\n📩 SMS ይለጥፉ:",
        "wd_choose": "📤 **የወጭ አማራጭ ይምረጡ:**",
        "wd_telebirr": "🏦 **Telebirr**\n\nየወጭ መጠን (min 100 ETB):",
        "wd_cbe": "🏦 **CBE**\n\nየወጭ መጠን (min 100 ETB):",
        "reg_prompt": "📱 **ስልክ ቁጥር ምዝገባ**\n\nስልክ ቁጥርዎን ያስገቡ:\n\nለምሳሌ: `0912345678`",
        "reg_success": "✅ **ተመዝግቧል!**\n\n📱 {phone}",
        "invalid_amount": "⚠️ ትክክለኛ ቁጥር ያስገቡ (ለምሳሌ: 100)",
        "invalid_sms": "⚠️ የባንክ SMS ይለጥፉ",
        "tx_received": "✅ **ተቀብሏል!**\n\n💰 {amount} ETB\n🏦 {method}\n\nለአስተዳዳሪ ተልኳል።",
        "insufficient": "❌ **ቀሪ ሂሳብ አይበቃም!**\n\n💰 ያለዎት: {bal} ETB\n💸 የጠየቁት: {req} ETB",
        "min_withdraw": "⚠️ ዝቅተኛው የወጭ መጠን 100 ETB ነው።",
        "play_hint": "🎯 **Play Abisinya Bingo** ይጫኑ!",
        "wd_phone_prompt": "📱 የስልክ ቁጥር ያስገቡ:",
        "wd_received": "✅ **የወጭ ጥያቄዎ ተቀባይነት አግኝቷል!**\n\n💰 {amount} ETB\n📱 {phone}\n\nበቅርቡ ይደርስዎታል።",
    },
    "en": {
        "welcome": "🎉 Welcome to Abisinya Bingo!",
        "play": "🎯 Play Abisinya Bingo",
        "deposit": "💰 Deposit",
        "withdraw": "📤 Withdraw",
        "balance": "💵 Check Balance",
        "invite": "👥 Invite Friends",
        "history": "📋 History",
        "support": "💬 Support",
        "language": "🌍 Language",
        "help": "ℹ️ Help",
        "leaderboard": "🏆 Leaderboard",
        "register": "📱 Register",
        "choose_lang": "🌐 Choose Language:",
        "bal_msg": "💰 **Balance**\n\n🎯 PLAY: {play} ETB\n🏆 WIN: {win} ETB",
        "help_msg": "🆘 **Help**\n\n1. Click Play Abisinya Bingo\n2. Choose cards\n3. Click BINGO when ready",
        "deposit_msg": "💰 **Deposit**\n\nChoose payment method:",
        "invite_msg": "👥 **Invite Link**\n\n{link}\n\n✨ Invite friends and earn 30 ETB!",
        "history_msg": "📋 **History**\n\nNo history yet.",
        "support_msg": "💬 **Support**\n\n👤 @Tazikes",
        "leaderboard_msg": "🏆 **Leaderboard**\n\n1. Abisinya_Pro - 14 wins\n2. Winner_77 - 9 wins\n3. BingoKing - 6 wins",
        "telebirr_msg": "🏦 **Telebirr**\n\n👤 Name: tazebew\n👉 Account: 0968940123\n\n📩 Paste SMS:",
        "cbe_msg": "🏦 **CBE**\n\n👤 Name: tazebew\n👉 Account: 1000390803005\n\n📩 Paste SMS:",
        "wd_choose": "📤 **Choose withdrawal method:**",
        "wd_telebirr": "🏦 **Telebirr**\n\nWithdrawal amount (min 100 ETB):",
        "wd_cbe": "🏦 **CBE**\n\nWithdrawal amount (min 100 ETB):",
        "reg_prompt": "📱 **Phone Registration**\n\nEnter phone number:\n\nExample: `0912345678`",
        "reg_success": "✅ **Registered!**\n\n📱 {phone}",
        "invalid_amount": "⚠️ Enter valid number (e.g., 100)",
        "invalid_sms": "⚠️ Paste bank SMS",
        "tx_received": "✅ **Received!**\n\n💰 {amount} ETB\n🏦 {method}\n\nSent to admin.",
        "insufficient": "❌ **Insufficient balance!**\n\n💰 Your: {bal} ETB\n💸 Requested: {req} ETB",
        "min_withdraw": "⚠️ Minimum withdrawal is 100 ETB.",
        "play_hint": "🎯 Click **Play Abisinya Bingo**!",
        "wd_phone_prompt": "📱 Enter phone number:",
        "wd_received": "✅ **Withdrawal accepted!**\n\n💰 {amount} ETB\n📱 {phone}\n\nWill arrive soon.",
    },
}

def t(uid, key):
    lang = get_language(uid)
    texts = TEXTS.get(lang, TEXTS["am"])
    return texts.get(key, TEXTS["am"].get(key, key))

user_states = {}

def main_kb(uid):
    keyboard = [
        [KeyboardButton(t(uid, "play"), web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(t(uid, "deposit")), KeyboardButton(t(uid, "withdraw"))],
        [KeyboardButton(t(uid, "balance")), KeyboardButton(t(uid, "invite"))],
        [KeyboardButton(t(uid, "history")), KeyboardButton(t(uid, "support"))],
        [KeyboardButton(t(uid, "register")), KeyboardButton(t(uid, "language"))],
        [KeyboardButton(t(uid, "help")), KeyboardButton(t(uid, "leaderboard"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def deposit_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📲 Telebirr", callback_data="dep_telebirr")],
        [InlineKeyboardButton("🏦 CBE", callback_data="dep_cbe")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_main")]
    ])

def withdraw_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📲 Telebirr", callback_data="wd_telebirr")],
        [InlineKeyboardButton("🏦 CBE", callback_data="wd_cbe")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_main")]
    ])

def language_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am")]
    ])

def approval_kb(tx_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{tx_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"reject_{tx_id}")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    u = update.effective_user
    create_user(u.id, u.username or "", u.first_name or "")
    if context.args and context.args[0].isdigit():
        referrer_id = int(context.args[0])
        if referrer_id != u.id:
            try:
                conn = sqlite3.connect("bingo.db", timeout=10)
                c = conn.cursor()
                c.execute("UPDATE users SET balance = balance + 30 WHERE user_id = ?", (referrer_id,))
                conn.commit()
                conn.close()
                await context.bot.send_message(referrer_id, "🎉 አዲስ ጓደኛ ጋብዘሃል! +30 ETB")
            except Exception as e:
                print(f"Referral error: {e}")
    await update.message.reply_text(t(u.id, "welcome"), reply_markup=main_kb(u.id))

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    u = update.effective_user
    b = get_balance(u.id)
    await update.message.reply_text(t(u.id, "bal_msg").format(play=f"{b['play']:.2f}", win=f"{b['win']:.2f}"), parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    await update.message.reply_text(t(update.effective_user.id, "help_msg"), parse_mode="Markdown")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if not update.effective_user:
        return
    u = update.effective_user
    txt = update.message.text.strip()
    create_user(u.id, u.username or "", u.first_name or "")

    state = user_states.get(u.id, {})
    action = state.get("action")

    is_menu = any(x in txt for x in ["🎯", "💰", "📤", "💵", "👥", "📋", "💬", "📱", "🌍", "ℹ️", "🏆"])
    if is_menu:
        user_states.pop(u.id, None)
        action = None

    if action == "register":
        phone = txt.strip()
        conn = sqlite3.connect("bingo.db", timeout=10)
        c = conn.cursor()
        c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, u.id))
        conn.commit()
        conn.close()
        user_states.pop(u.id, None)
        await update.message.reply_text(t(u.id, "reg_success").format(phone=phone), parse_mode="Markdown", reply_markup=main_kb(u.id))
        return

    if action == "deposit":
        amount_match = re.search(r"(\d+(?:[.,]\d+)?)", txt)
        amount = float(amount_match.group(1).replace(",", "")) if amount_match else 0
        if amount < 1:
            await update.message.reply_text(t(u.id, "invalid_sms"))
            return
        method = state.get("method", "unknown")
        conn = sqlite3.connect("bingo.db", timeout=10)
        c = conn.cursor()
        c.execute("INSERT INTO transactions (user_id, type, amount, status, phone, sms, created_at) VALUES (?, 'deposit', ?, 'pending', ?, ?, ?)",
                  (u.id, amount, method, txt, datetime.now().isoformat()))
        tx_id = c.lastrowid
        conn.commit()
        conn.close()
        method_label = "📲 TeleBirr" if method == "telebirr" else "🏦 CBE"
        admin_msg = f"🔔 **አዲስ DEPOSIT**\n\n👤 {u.first_name} (@{u.username or 'N/A'})\n🆔 `{u.id}`\n💰 {amount:.2f} ETB — {method_label}\n🔖 Tx: `{tx_id}`"
        try:
            await context.bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=approval_kb(tx_id))
        except Exception as e:
            print(f"Admin notify: {e}")
        await update.message.reply_text(t(u.id, "tx_received").format(amount=f"{amount:.2f}", method=method), parse_mode="Markdown", reply_markup=main_kb(u.id))
        user_states.pop(u.id, None)
        return

    if action == "withdraw_amount":
        if not txt.isdigit():
            await update.message.reply_text(t(u.id, "invalid_amount"))
            return
        amount = float(txt)
        if amount < 100:
            await update.message.reply_text(t(u.id, "min_withdraw"))
            return
        b = get_balance(u.id)
        if amount > b["play"] + b["win"]:
            await update.message.reply_text(t(u.id, "insufficient").format(bal=f"{b['play'] + b['win']:.2f}", req=f"{amount:.2f}"))
            return
        user_states[u.id] = {"action": "withdraw_phone", "amount": amount, "method": state.get("method", "unknown")}
        await update.message.reply_text(t(u.id, "wd_phone_prompt"))
        return

    if action == "withdraw_phone":
        phone = txt.strip()
        amount = state.get("amount", 0)
        method = state.get("method", "unknown")
        conn = sqlite3.connect("bingo.db", timeout=10)
        c = conn.cursor()
        c.execute("INSERT INTO transactions (user_id, type, amount, status, phone, sms, created_at) VALUES (?, 'withdraw', ?, 'pending', ?, ?, ?)",
                  (u.id, amount, method, phone, datetime.now().isoformat()))
        tx_id = c.lastrowid
        conn.commit()
        conn.close()
        method_label = "📲 TeleBirr" if method == "telebirr" else "🏦 CBE"
        admin_msg = f"🔔 **አዲስ WITHDRAW**\n\n👤 {u.first_name} (@{u.username or 'N/A'})\n🆔 `{u.id}`\n💰 {amount:.2f} ETB — {method_label}\n📱 `{phone}`\n🔖 Tx: `{tx_id}`"
        try:
            await context.bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=approval_kb(tx_id))
        except Exception as e:
            print(f"Admin notify: {e}")
        await update.message.reply_text(t(u.id, "wd_received").format(amount=f"{amount:.2f}", phone=phone), parse_mode="Markdown", reply_markup=main_kb(u.id))
        user_states.pop(u.id, None)
        return

    if "🎯" in txt or "Play" in txt:
        await update.message.reply_text(t(u.id, "play_hint"), parse_mode="Markdown")
    elif "💰" in txt or "Deposit" in txt:
        await update.message.reply_text(t(u.id, "deposit_msg"), reply_markup=deposit_kb())
    elif "📤" in txt or "Withdraw" in txt:
        await update.message.reply_text(t(u.id, "wd_choose"), reply_markup=withdraw_kb())
    elif "💵" in txt or "Balance" in txt:
        b = get_balance(u.id)
        await update.message.reply_text(t(u.id, "bal_msg").format(play=f"{b['play']:.2f}", win=f"{b['win']:.2f}"), parse_mode="Markdown")
    elif "👥" in txt or "Invite" in txt:
        link = f"https://t.me/{BOT_USERNAME}?start={u.id}"
        await update.message.reply_text(t(u.id, "invite_msg").format(link=link))
    elif "📋" in txt or "History" in txt:
        await update.message.reply_text(t(u.id, "history_msg"))
    elif "💬" in txt or "Support" in txt:
        await update.message.reply_text(t(u.id, "support_msg"))
    elif "📱" in txt or "Register" in txt:
        user_states[u.id] = {"action": "register"}
        await update.message.reply_text(t(u.id, "reg_prompt"), parse_mode="Markdown")
    elif "🌍" in txt or "Language" in txt:
        await update.message.reply_text(t(u.id, "choose_lang"), reply_markup=language_kb())
    elif "ℹ️" in txt or "Help" in txt:
        await update.message.reply_text(t(u.id, "help_msg"), parse_mode="Markdown")
    elif "🏆" in txt or "Leaderboard" in txt:
        await update.message.reply_text(t(u.id, "leaderboard_msg"))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.from_user:
        return
    await q.answer()
    data = q.data
    u = q.from_user
    create_user(u.id, u.username or "", u.first_name or "")

    async def send_new(text, kb=None):
        try:
            await q.message.delete()
        except Exception:
            pass
        try:
            await context.bot.send_message(chat_id=u.id, text=text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            print(f"send_new: {e}")

    if data.startswith("approve_") or data.startswith("reject_"):
        if u.id != ADMIN_ID:
            return
        parts = data.split("_")
        act = parts[0]
        tx_id = int(parts[1])
        conn = sqlite3.connect("bingo.db", timeout=10)
        c = conn.cursor()
        c.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
        tx = c.fetchone()
        if not tx:
            conn.close()
            await q.edit_message_text("❌ Not found")
            return
        tx_uid, tx_type, amount = tx[1], tx[2], tx[3]
        if act == "approve":
            c.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (tx_id,))
            if tx_type == "deposit":
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, tx_uid))
                conn.commit()
                conn.close()
                try:
                    await context.bot.send_message(tx_uid, f"✅ **ጥያቄዎ ፀድቋል!**\n\n💰 {amount:.2f} ETB ወደ ዋሌትዎ ተጨምሯል::", parse_mode="Markdown")
                except Exception:
                    pass
                await q.edit_message_text(f"✅ DEPOSIT — {amount:.2f} ETB")
            elif tx_type == "withdraw":
                c.execute("UPDATE users SET win_balance = win_balance - ? WHERE user_id = ?", (amount, tx_uid))
                conn.commit()
                conn.close()
                try:
                    await context.bot.send_message(tx_uid, f"✅ **የወጭ ጥያቄዎ ፀድቋል!**\n\n💰 {amount:.2f} ETB\n📱 {tx[5]}", parse_mode="Markdown")
                except Exception:
                    pass
                await q.edit_message_text(f"✅ WITHDRAW — {amount:.2f} ETB")
        else:
            c.execute("UPDATE transactions SET status = 'rejected' WHERE id = ?", (tx_id,))
            conn.commit()
            conn.close()
            try:
                await context.bot.send_message(tx_uid, f"❌ **ጥያቄዎ ተሰርዟል!**\n\n💰 {amount:.2f} ETB", parse_mode="Markdown")
            except Exception:
                pass
            await q.edit_message_text(f"❌ REJECTED — {amount:.2f} ETB")
        return

    if data == "back_main":
        user_states.pop(u.id, None)
        await send_new(t(u.id, "welcome"), main_kb(u.id))
    elif data == "dep_telebirr":
        user_states[u.id] = {"action": "deposit", "method": "telebirr"}
        await send_new(t(u.id, "telebirr_msg"), deposit_kb())
    elif data == "dep_cbe":
        user_states[u.id] = {"action": "deposit", "method": "cbe"}
        await send_new(t(u.id, "cbe_msg"), deposit_kb())
    elif data == "wd_telebirr":
        user_states[u.id] = {"action": "withdraw_amount", "method": "telebirr"}
        await send_new(t(u.id, "wd_telebirr"), withdraw_kb())
    elif data == "wd_cbe":
        user_states[u.id] = {"action": "withdraw_amount", "method": "cbe"}
        await send_new(t(u.id, "wd_cbe"), withdraw_kb())
    elif data == "lang_en":
        update_language(u.id, "en")
        await send_new("✅ Language: English", main_kb(u.id))
    elif data == "lang_am":
        update_language(u.id, "am")
        await send_new("✅ ቋንቋ: አማርኛ", main_kb(u.id))

async def error_handler(update, context):
    print(f"⚠️ {context.error}")

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)
    print("🤖 Bot started...")
    app.run_polling()
