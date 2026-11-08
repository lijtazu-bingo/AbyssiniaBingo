import logging
import os
import sqlite3
import threading
import requests
import re
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Flask Web Server (ለ Render) ───
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Abisinya Bingo Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port, use_reloader=False)

# ─── ማስተካከያዎች ───
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = "https://abyssiniabingo.onrender.com"
SERVER_API_URL = os.getenv("SERVER_API_URL", WEBAPP_URL)
ADMIN_ID = os.getenv("ADMIN_ID")
DB_FILE = "abisinya_bot.db"

# ─── የውይይት ሁኔታዎች ───
DEPOSIT_AMOUNT, DEPOSIT_TXN = range(2)
WITHDRAW_METHOD, WITHDRAW_AMOUNT, WITHDRAW_PHONE = range(2, 5)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY, username TEXT, first_name TEXT, phone TEXT, lang TEXT DEFAULT 'am', registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS used_txns (txn_id TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

init_db()

def save_user(user_id, username, first_name, phone=None, lang=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (str(user_id),))
    exists = c.fetchone()
    
    if not exists:
        c.execute("INSERT INTO users (user_id, username, first_name, phone, lang) VALUES (?, ?, ?, ?, ?)",
                  (str(user_id), username, first_name, phone, lang or 'am'))
    else:
        if phone: c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, str(user_id)))
        if lang: c.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, str(user_id)))
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT phone, lang FROM users WHERE user_id = ?", (str(user_id),))
    result = c.fetchone()
    conn.close()
    return result if result else (None, 'am')

def is_txn_used(txn_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT txn_id FROM used_txns WHERE txn_id = ?", (txn_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def mark_txn_used(txn_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO used_txns (txn_id) VALUES (?)", (txn_id,))
    conn.commit()
    conn.close()

# ─── ትርጉሞች (Translations) ───
TEXTS = {
    'am': {
        'register_first': "👋 <b>እንኳን ደህና መጡ!</b>\n\nለመጀመር እባክዎ የስልክ ቁጥርዎን ያጋሩ። (ይህ ለደህንነትዎ ነው)",
        'share_contact': "📱 ስልክ ቁጥሬን አጋራ",
        'already_registered': "✅ እርስዎ አስቀድመው ተመዝግበዋል!",
        'registered': "✅ <b>በተሳካ ሁኔታ ተመዝግበዋል!</b>\n📱 ስልክ ቁጥርዎ፦ <code>{phone}</code>\n\n🎉 ወደ Abisinya Bingo መተግበሪያ በደህና መጡ!\n\n👇 ከታች ያለውን አማራጭ ይምረጡ",
        'welcome_back': "🎉 <b>ወደ Abisinya Bingo መተግበሪያ በደህና መጡ!</b>\n\n👇 ከታች ያለውን አማራጭ ይምረጡ",
        
        'menu_play': "🎮 Play Abyssinia Bingo",
        'menu_deposit': "💰 ገቢ (Deposit)",
        'menu_withdraw': "💸 ወጪ (Withdraw)",
        'menu_balance': "🏦 ባላንስ (Balance)",
        'menu_invite': "👥 ግብዣ (Invite)",
        'menu_history': "📜 ታሪክ (History)",
        'menu_support': "💬 ድጋፍ (Support)",
        'menu_register': "🔢 ምዝገባ (Register)",
        'menu_lang': "🌐 ቋንቋ (Language)",
        'menu_help': "ℹ️ እርዳታ (Help)",
        'menu_rank': "🏆 ደረጃ (Rank)",
        
        'play_prompt': "🎲 ወደ Abisinya Bingo እንኳን ደህና መጡ!\nይጫወቱ ያሸንፉ ድል በድል ይሁኑ!\n\n👇 ጨዋታ ለመጀመር ከታች ያለውን ቁልፍ ይጫኑ:",
        'play_inline_btn': "🎮 Play Bingo",
        
        'dep_choose': "💳 <b>የክፍያ አማራጭ ይምረጡ፦</b>",
        'dep_enter_amt': "💸 እባክዎ ማስገባት የሚፈልጉትን <b>የብር መጠን</b> ያስገቡ (ለምሳሌ፦ 100)፦",
        'dep_instructions': "🏦 <b>የክፍያ መረጃ</b>\n\n👤 ስም፦ <b>{name}</b>\n👉 አካውንት፦ <code>{acc}</code>\n\n⚠️ ከተላከ በኋላ የመጣውን የSMS ሙሉ ጽሁፍ (Transaction ID) ኮፒ አድርገው ከታች 👇 ፓስት ያድርጉት፦",
        'dep_success': "✅ <b>የDeposit ጥያቄዎ ተልኳል!</b>\n\n👤 ስም፦ {name}\n💳 አማራጭ፦ {method}\n💰 መጠን፦ {amount} ETB\n⏳ አድሚን እስኪያጸድቅ ይጠብቁ።",
        'dep_duplicate': "❌ ይህ የግብይት ቁጥር (Transaction ID) ቀድሞ ጥቅም ላይ ውሏል! እባክዎ አዲስ የሆነ የግብይት ቁጥር ያስገቡ።",
        
        'wd_choose': "🏦 <b>ወደ የትኛው ባንክ/አካውንት ማውጣት ይፈልጋሉ?</b>",
        'wd_enter_amt': "💸 እባክዎ ማውጣት የሚፈልጉትን <b>መጠን</b> ያስገቡ (ዝቅተኛው 100 ETB)፦",
        'wd_enter_phone': "📱 እባክዎ ወደሚወጣበትን የቴሌብር/ባንክ <b>ስልክ ቁጥር</b> ያስገቡ፦",
        'wd_success': "✅ <b>የWithdraw ጥያቄዎ ተልኳል!</b>\n\n👤 ስም፦ {name}\n💳 አማራጭ፦ {method}\n💰 መጠን፦ {amount} ETB\n📱 ስልክ፦ {phone}\n\n⏳ <b>እባክዎ አድሚን እስኪያጸድቅ ይጠብቁ።</b>",

        'bal_msg': "💵 <b>የሂሳብ ማጠቃለያ</b>\n\n🟢 Play Wallet: <b>{play} ETB</b>\n🟡 Win Wallet: <b>{win} ETB</b>\n👥 Referral Bonus: <b>{ref} ETB</b>\n\n💳 <b>አጠቃላይ ባላንስ፦ {total} ETB</b>",
        'invite_msg': "🔗 <b>የእርስዎ የግብዣ ሊንክ፦</b>\nhttps://t.me/Ethiobongo_bot?start={id}\n\n🎁 ወዳጅዎን ሲጋብዙ 30 ብር ያገኛሉ! ጓደኛዎም 20 ብር ያገኛል።",
        'support_msg': "💬 ማንኛውም ጥያቄ ካለዎት በ @Tazikes ያግኙን።",
        'history_msg': "📜 ታሪክዎን ለማየት ከዚህ በታች ይጫኑ፦",
        'help_msg': "📚 <b>የቦት ትዕዛዞች እና አጋዥ መረጃ</b>\n\n/start - ቦቱን እንደገና ለመጀመር\n/play - ጨዋታውን ለመጫወት\n/balance - ባላንስዎን ለማየት\n/deposit - ገንዘብ ለማስገባት\n/withdraw - ገንዘብ ለማውጣት\n/invite - የግብዣ ሊንክ ለማግኘት\n/support - እርዳታ ለማግኘት\n/lang - ቋንቋ ለመቀየር\n\n💡 <i>ማንኛውንም አዝራር በመጫን ቦቱን መጠቀም ይችላሉ።</i>",
        'leaderboard_msg': "🏆 የአሸናፊዎች ደረጃ ለማየት ከታች ይጫኑ፦",
        
        'lang_choose': "🌐 <b>እባክዎ ቋንቋ ይምረጡ፦</b>",
        'lang_changed': "✅ ቋንቋ ወደ አማርኛ ተቀይሯል!",
        'invalid_amt': "❌ እባክዎ ትክክለኛ ቁጥር ያስገቡ።",
        'min_wd': "❌ ዝቅተኛው የወጭ መጠን 100 ETB ነው።",
        'min_dep': "❌ ዝቅተኛው የገቢ መጠን 10 ETB ነው።",
        'invalid_phone': "❌ ትክክለኛ ስልክ ቁጥር ያስገቡ።",
        'cancelled': "❌ ሂደቱ ተሰርዟል።"
    },
    'en': {
        'register_first': "👋 <b>Welcome!</b>\n\nTo get started, please share your phone number. (This is for security)",
        'share_contact': "📱 Share Phone Number",
        'already_registered': "✅ You are already registered!",
        'registered': "✅ <b>Registered successfully!</b>\n📱 Phone: <code>{phone}</code>\n\n🎉 Welcome to the Abisinya Bingo App!\n\n👇 Choose an option below",
        'welcome_back': "🎉 <b>Welcome to the Abisinya Bingo App!</b>\n\n👇 Choose an option below",
        'menu_play': "🎮 Play Abyssinia Bingo",
        'menu_deposit': "💰 Deposit",
        'menu_withdraw': "💸 Withdraw",
        'menu_balance': "🏦 Balance",
        'menu_invite': "👥 Invite",
        'menu_history': "📜 History",
        'menu_support': "💬 Support",
        'menu_register': "🔢 Register",
        'menu_lang': "🌐 Language",
        'menu_help': "ℹ️ Help",
        'menu_rank': "🏆 Rank",
        'play_prompt': "🎲 Welcome to Abisinya Bingo!\nPlay and Win! May victory be yours!\n\n👇 Tap the button below to start playing:",
        'play_inline_btn': "🎮 Play Bingo",
        'dep_choose': "💳 <b>Choose a payment method:</b>",
        'dep_enter_amt': "💸 Please enter the <b>amount</b> you want to deposit (e.g., 100):",
        'dep_instructions': "🏦 <b>Payment Details</b>\n\n👤 Name: <b>{name}</b>\n👉 Account: <code>{acc}</code>\n\n⚠️ After sending, copy the full SMS (Transaction ID) and paste it below 👇",
        'dep_success': "✅ <b>Deposit Request Sent!</b>\n\n👤 Name: {name}\n💳 Method: {method}\n💰 Amount: {amount} ETB\n⏳ Wait for Admin approval.",
        'dep_duplicate': "❌ This Transaction ID has already been used! Please enter a new one.",
        'wd_choose': "🏦 <b>Choose a bank/account to withdraw:</b>",
        'wd_enter_amt': "💸 Enter the <b>amount</b> to withdraw (minimum 100 ETB):",
        'wd_enter_phone': "📱 Enter the Phone/Account <b>number</b> to withdraw to:",
        'wd_success': "✅ <b>Withdraw Request Sent!</b>\n\n👤 Name: {name}\n💳 Method: {method}\n💰 Amount: {amount} ETB\n📱 Phone: {phone}\n\n⏳ <b>Please wait for Admin approval.</b>",
        'bal_msg': "💵 <b>Balance Summary</b>\n\n🟢 Play Wallet: <b>{play} ETB</b>\n🟡 Win Wallet: <b>{win} ETB</b>\n👥 Referral Bonus: <b>{ref} ETB</b>\n\n💳 <b>Total Balance: {total} ETB</b>",
        'invite_msg': "🔗 <b>Your Invite Link:</b>\nhttps://t.me/Ethiobongo_bot?start={id}\n\n🎁 Invite a friend and get 30 ETB! They get 20 ETB.",
        'support_msg': "💬 For any questions contact @Tazikes.",
        'history_msg': "📜 Click below to view your history:",
        'help_msg': "📚 <b>Bot Commands & Guide</b>\n\n/start - Restart the bot\n/play - Play the game\n/balance - Check your balance\n/deposit - Make a deposit\n/withdraw - Make a withdrawal\n/invite - Get your invite link\n/support - Get help\n/lang - Change language\n\n💡 <i>You can also use the buttons below.</i>",
        'leaderboard_msg': "🏆 Click below to view the leaderboard:",
        'lang_choose': "🌐 <b>Choose a language:</b>",
        'lang_changed': "✅ Language changed to English!",
        'invalid_amt': "❌ Please enter a valid number.",
        'min_wd': "❌ Minimum withdrawal is 100 ETB.",
        'min_dep': "❌ Minimum deposit is 10 ETB.",
        'invalid_phone': "❌ Please enter a valid phone number.",
        'cancelled': "❌ Process cancelled."
    }
}

TEXTS['ti'] = TEXTS['am'] 
TEXTS['om'] = TEXTS['am'] 

def get_text(user_id, key, **kwargs):
    _, lang = get_user_data(user_id)
    if lang not in TEXTS: lang = 'en'
    
    text = TEXTS[lang].get(key)
    if not text:
        text = TEXTS['en'].get(key)
    if not text:
        text = TEXTS['am'].get(key, '')
        
    return text.format(**kwargs) if kwargs else text

def get_main_menu(user_id):
    t = lambda k: get_text(user_id, k)
    keyboard = [
        [KeyboardButton(text=t('menu_play'))],
        [KeyboardButton(text=t('menu_deposit')), KeyboardButton(text=t('menu_withdraw'))],
        [KeyboardButton(text=t('menu_balance')), KeyboardButton(text=t('menu_invite'))],
        [KeyboardButton(text=t('menu_history')), KeyboardButton(text=t('menu_support'))],
        [KeyboardButton(text=t('menu_register')), KeyboardButton(text=t('menu_lang'))],
        [KeyboardButton(text=t('menu_help')), KeyboardButton(text=t('menu_rank'))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

# ✅ INTERRUPT HANDLER
async def interrupt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await handle_menu_buttons(update, context)
    return ConversationHandler.END

# ─── Commands ───
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)
    
    phone, _ = get_user_data(user.id)
    
    if not phone:
        keyboard = [[KeyboardButton(text=get_text(user.id, 'share_contact'), request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(get_text(user.id, 'register_first'), parse_mode='HTML', reply_markup=reply_markup)
        return

    args = context.args
    if args and len(args) > 0 and not user.is_bot:
        referrer_id = args[0]
        if referrer_id != str(user.id):
            try:
                requests.post(f"{SERVER_API_URL}/api/user/referral", json={"new_user_id": str(user.id), "referrer_id": referrer_id}, timeout=5)
            except: pass

    await update.message.reply_text(get_text(user.id, 'welcome_back'), parse_mode='HTML', reply_markup=get_main_menu(user.id))

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    _, lang = get_user_data(user.id)
    webapp_url_with_lang = f"{WEBAPP_URL}?lang={lang}" 
    
    web_app_btn = InlineKeyboardButton(text=get_text(user.id, 'play_inline_btn'), web_app=WebAppInfo(url=webapp_url_with_lang))
    await update.message.reply_text(get_text(user.id, 'play_prompt'), parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[web_app_btn]]))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_text(update.effective_user.id, 'help_msg'), parse_mode='HTML')

# ─── Register ───
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact:
        user = update.effective_user
        phone = contact.phone_number
        save_user(user.id, user.username, user.first_name, phone)
        
        try: requests.post(f"{SERVER_API_URL}/api/user/phone", json={"user_id": str(user.id), "phone": phone, "name": user.first_name}, timeout=5)
        except: pass
        
        await update.message.reply_text(get_text(user.id, 'registered', phone=phone), parse_mode='HTML', reply_markup=get_main_menu(user.id))

# ─── Deposit Flow ───
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("📱 TeleBirr", callback_data="dep_telebirr")]]
    await update.message.reply_text(get_text(user.id, 'dep_choose'), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return DEPOSIT_AMOUNT

async def deposit_method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await query.edit_message_text(get_text(user.id, 'dep_enter_amt'), parse_mode='HTML')
    return DEPOSIT_AMOUNT

async def deposit_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        amount = float(update.message.text)
        if amount < 10: 
            await update.message.reply_text(get_text(user.id, 'min_dep'))
            return DEPOSIT_AMOUNT
    except:
        await update.message.reply_text(get_text(user.id, 'invalid_amt'))
        return DEPOSIT_AMOUNT

    context.user_data['deposit_amount'] = amount
    
    try:
        res = requests.get(f"{SERVER_API_URL}/api/settings", timeout=5)
        settings = res.json().get("data", {})
    except: settings = {}
    
    acc = settings.get("telebirr_number", "0968940123")
    name = settings.get("telebirr_name", "tazebew")
    
    await update.message.reply_text(get_text(user.id, 'dep_instructions', name=name, acc=acc), parse_mode='HTML')
    return DEPOSIT_TXN

async def deposit_txn_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    txn_ref = update.message.text.strip()
    amount = context.user_data.get('deposit_amount', 0)
    
    if is_txn_used(txn_ref):
        await update.message.reply_text(get_text(user.id, 'dep_duplicate'), reply_markup=get_main_menu(user.id))
        return ConversationHandler.END
    
    result = None
    try:
        result = requests.post(f"{SERVER_API_URL}/api/bot/create-txn", json={
            "type": "deposit", "user_id": str(user.id), "user_name": user.first_name,
            "amount": amount, "method": "telebirr", "reference": txn_ref
        }, timeout=10).json()
    except: pass
    
    if result and result.get('success'):
        mark_txn_used(txn_ref) 
        msg = get_text(user.id, 'dep_success', name=user.first_name, method="Telebirr", amount=amount)
    else:
        msg = "⚠️ Request failed. Please contact support."
        
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_main_menu(user.id))
    
    if ADMIN_ID:
        try: await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 New Deposit Request!\nUser ID: {user.id}\n{msg}", parse_mode='HTML')
        except: pass
    return ConversationHandler.END

# ─── Withdraw Flow ───
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📱 TeleBirr (Self)", callback_data="wd_telebirr_self")],
        [InlineKeyboardButton("📱 TeleBirr (Other)", callback_data="wd_telebirr_other")],
        [InlineKeyboardButton("🏦 CBE", callback_data="wd_cbe")]
    ]
    await update.message.reply_text(get_text(user.id, 'wd_choose'), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return WITHDRAW_METHOD

async def withdraw_method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    method_map = {
        'wd_telebirr_self': 'Telebirr (Self)', 
        'wd_telebirr_other': 'Telebirr (Other)', 
        'wd_cbe': 'CBE'
    }
    method = method_map.get(query.data, 'Telebirr')
    context.user_data['withdraw_method'] = method
    
    await query.edit_message_text(get_text(user.id, 'wd_enter_amt'), parse_mode='HTML')
    return WITHDRAW_AMOUNT

async def withdraw_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        amount = float(update.message.text)
        if amount < 100:
            await update.message.reply_text(get_text(user.id, 'min_wd'))
            return WITHDRAW_AMOUNT
    except:
        await update.message.reply_text(get_text(user.id, 'invalid_amt'))
        return WITHDRAW_AMOUNT

    context.user_data['withdraw_amount'] = amount
    
    method = context.user_data.get('withdraw_method', '')
    if method == 'Telebirr (Self)':
        phone, _ = get_user_data(user.id)
        if phone:
            context.user_data['withdraw_phone'] = phone
            return await process_withdraw_final(update, context)
            
    await update.message.reply_text(get_text(user.id, 'wd_enter_phone'), parse_mode='HTML')
    return WITHDRAW_PHONE

async def withdraw_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    phone = update.message.text.strip()
    if len(phone) < 9:
        await update.message.reply_text(get_text(user.id, 'invalid_phone'))
        return WITHDRAW_PHONE

    context.user_data['withdraw_phone'] = phone
    return await process_withdraw_final(update, context)

async def process_withdraw_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount = context.user_data.get('withdraw_amount', 0)
    method = context.user_data.get('withdraw_method', '')
    phone = context.user_data.get('withdraw_phone', '')
    
    result = None
    try:
        result = requests.post(f"{SERVER_API_URL}/api/bot/create-txn", json={
            "type": "withdrawal", "user_id": str(user.id), "user_name": user.first_name,
            "amount": amount, "method": method, "phone": phone
        }, timeout=10).json()
    except: pass

    if result and result.get('success'):
        msg = get_text(user.id, 'wd_success', name=user.first_name, method=method, amount=amount, phone=phone)
    else:
        msg = "⚠️ Request failed. Please contact support."
        
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_main_menu(user.id))
    
    if ADMIN_ID:
        try: await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 New Withdraw Request!\nUser ID: {user.id}\n{msg}", parse_mode='HTML')
        except: pass
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_text(update.effective_user.id, 'cancelled'), reply_markup=get_main_menu(update.effective_user.id))
    return ConversationHandler.END

# ─── Language ───
async def lang_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am")],
        [InlineKeyboardButton("🇪🇹 ትግርኛ", callback_data="lang_ti")],
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇹 Afaan Oromoo", callback_data="lang_om")]
    ]
    await update.message.reply_text(get_text(update.effective_user.id, 'lang_choose'), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = query.data.replace('lang_', '')
    
    save_user(user_id, query.from_user.username, query.from_user.first_name, lang=lang_code)
    
    await query.edit_message_text(get_text(user_id, 'lang_changed'), parse_mode='HTML')
    await query.message.reply_text("👇", reply_markup=get_main_menu(user_id))

# ─── Other Menu Buttons ───
async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    t = lambda key: get_text(user.id, key)
    
    _, lang = get_user_data(user.id)
    texts = TEXTS.get(lang, TEXTS['en'])

    is_play = any(text == TEXTS[l].get('menu_play') for l in TEXTS) or "Play Abyssinia Bingo" in text
    is_balance = any(text == TEXTS[l].get('menu_balance') for l in TEXTS)
    is_invite = any(text == TEXTS[l].get('menu_invite') for l in TEXTS)
    is_support = any(text == TEXTS[l].get('menu_support') for l in TEXTS)
    is_help = any(text == TEXTS[l].get('menu_help') for l in TEXTS)
    is_register = any(text == TEXTS[l].get('menu_register') for l in TEXTS)
    is_lang = any(text == TEXTS[l].get('menu_lang') for l in TEXTS)
    is_history = any(text == TEXTS[l].get('menu_history') for l in TEXTS)
    is_rank = any(text == TEXTS[l].get('menu_rank') for l in TEXTS)

    if is_play:
        webapp_url_with_lang = f"{WEBAPP_URL}?lang={lang}"
        web_app_btn = InlineKeyboardButton(text=t('play_inline_btn'), web_app=WebAppInfo(url=webapp_url_with_lang))
        await update.message.reply_text(t('play_prompt'), parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[web_app_btn]]))

    elif is_balance:
        await update.message.reply_text("⏳ Loading...")
        try:
            res = requests.get(f"{SERVER_API_URL}/api/wallet/me", headers={"X-User-Id": str(user.id)}, timeout=10)
            if res.ok:
                data = res.json().get("data", {})
                play = float(data.get('play_balance', 0))
                win = float(data.get('win_balance', 0))
                ref = float(data.get('referral_balance', 0)) 
                total = play + win + ref
                
                msg = t('bal_msg').format(play=f"{play:.2f}", win=f"{win:.2f}", ref=f"{ref:.2f}", total=f"{total:.2f}")
                await update.message.reply_text(msg, parse_mode='HTML')
            else:
                await update.message.reply_text("❌ Failed to load balance.")
        except: 
            await update.message.reply_text("❌ Server Error")

    elif is_invite:
        await update.message.reply_text(t('invite_msg').format(id=user.id), parse_mode='HTML')
        
    elif is_support:
        await update.message.reply_text(t('support_msg'), parse_mode='HTML')
    
    elif is_help:
        await update.message.reply_text(t('help_msg'), parse_mode='HTML')

    elif is_rank:
        await update.message.reply_text(t('leaderboard_msg'))
        web_app_btn = InlineKeyboardButton(text="🏆 Open Leaderboard", web_app=WebAppInfo(url=f"{WEBAPP_URL}?page=rank&lang={lang}"))
        await update.message.reply_text("👇", reply_markup=InlineKeyboardMarkup([[web_app_btn]]))

    elif is_register:
        phone, _ = get_user_data(user.id)
        if phone:
            await update.message.reply_text(t('already_registered'), parse_mode='HTML', reply_markup=get_main_menu(user.id))
        else:
            keyboard = [[KeyboardButton(text=t('share_contact'), request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(t('register_first'), parse_mode='HTML', reply_markup=reply_markup)

    elif is_lang:
        await lang_menu(update, context)

    elif is_history:
        await update.message.reply_text(t('history_msg'))
        web_app_btn = InlineKeyboardButton(text="📜 Open History", web_app=WebAppInfo(url=f"{WEBAPP_URL}?page=history&lang={lang}"))
        await update.message.reply_text("👇", reply_markup=InlineKeyboardMarkup([[web_app_btn]]))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    if not BOT_TOKEN: return
    threading.Thread(target=run_web, daemon=True).start()
    application = Application.builder().token(BOT_TOKEN).build()

    all_menu_buttons = []
    for l in TEXTS:
        for k in ['menu_play', 'menu_deposit', 'menu_withdraw', 'menu_balance', 'menu_invite', 'menu_history', 'menu_support', 'menu_register', 'menu_lang', 'menu_help', 'menu_rank']:
            if k in TEXTS[l]:
                all_menu_buttons.append(re.escape(TEXTS[l][k]))
                
    menu_filter = filters.Regex(f"^({'|'.join(all_menu_buttons)})$")
    
    dep_entry_filter = filters.Regex(f"^({'|'.join([re.escape(TEXTS[l].get('menu_deposit', 'Deposit')) for l in TEXTS])})$")
    wd_entry_filter = filters.Regex(f"^({'|'.join([re.escape(TEXTS[l].get('menu_withdraw', 'Withdraw')) for l in TEXTS])})$")

    dep_conv = ConversationHandler(
        entry_points=[MessageHandler(dep_entry_filter, deposit_start)],
        states={
            DEPOSIT_AMOUNT: [CallbackQueryHandler(deposit_method_chosen, pattern="^dep_"), MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_received)],
            DEPOSIT_TXN: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_txn_received)],
        },
        fallbacks=[MessageHandler(menu_filter, interrupt_handler), CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    wd_conv = ConversationHandler(
        entry_points=[MessageHandler(wd_entry_filter, withdraw_start)],
        states={
            WITHDRAW_METHOD: [CallbackQueryHandler(withdraw_method_chosen, pattern="^wd_")],
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_received)],
            WITHDRAW_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone_received)],
        },
        fallbacks=[MessageHandler(menu_filter, interrupt_handler), CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play_command))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(dep_conv)
    application.add_handler(wd_conv)
    application.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang_"))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))
    
    application.add_error_handler(error_handler)

    print("🤖 Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
