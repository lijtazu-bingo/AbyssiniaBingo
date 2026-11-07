import logging
import os
import sqlite3
import threading
import requests
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
DEPOSIT_METHOD, DEPOSIT_TXN_ID, DEPOSIT_AMOUNT = range(3)
WITHDRAW_METHOD, WITHDRAW_AMOUNT, WITHDRAW_PHONE = range(3, 6)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY, username TEXT, first_name TEXT, phone TEXT, lang TEXT DEFAULT 'am', registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
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

# ─── ትርጉሞች (Translations) ───
TEXTS = {
    'am': {
        'start': "🎉 <b>ወደ Abisinya Bingo መተግበሪያ በደህና መጡ!</b>\n\n👤 ስም፦ {name}\n🆔 መለያ፦ <code>{id}</code>\n💵 ባላንስ፦ <b>{balance} ETB</b>\n\n👇 ከታች ያለውን አማራጭ ይምረጡ",
        'play_prompt': "🎲 ወደ Abisinya Bingo እንኳን ደህና መጡ!\nይጫወቱ ያሸንፉ ድል በድል ይሁኑ!\n\n👇 ጨዋታ ለመጀመር ከታች ያለውን ቁልፍ ይጫኑ:",
        'play_inline_btn': "🎮 Play Bingo",
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
        'help_msg': "📚 <b>የቦት ትዕዛዞች እና አጋዥ መረጃ</b>\n\n/start - ቦቱን እንደገና ለመጀመር\n/play - ጨዋታውን ለመጫወት\n/balance - ባላንስዎን ለማየት\n/deposit - ገንዘብ ለማስገባት\n/withdraw - ገንዘብ ለማውጣት\n/invite - የግብዣ ሊንክ ለማግኘት\n/support - እርዳታ ለማግኘት\n/lang - ቋንቋ ለመቀየር\n\n💡 <i>ማንኛውንም አዝራር በመጫን ቦቱን መጠቀም ይችላሉ።</i>",
        'dep_choose': "💳 የክፍያ አማራጭ ይምረጡ፦",
        'dep_enter_amt': "💸 እባክዎ ማስገባት የሚፈልጉትን የብር መጠን ያስገቡ፦",
        'dep_instructions': "🏦 ባንክ፦ TeleBirr\n\n⚠️ <b>ማስጠንቀቂያ፦ ገንዘቡን ከTeleBirr ወደ TeleBirr ብቻ ይላኩ!</b>\n\nገንዘብ ይላኩ፦\n👤 ስም፦ <b>{name}</b>\n👉 አካውንት፦ <code>{acc}</code>\n\n👉 ከተላከ በኋላ የመጣውን የSMS ሙሉ ጽሁፍ ኮፒ አድርገው ከታች 👇 ፓስት (Paste) ያድርጉት፦",
        'dep_success': "✅ <b>የDeposit ጥያቄዎ ተልኳል!</b>\n\n👤 ስም፦ {name}\n💳 አማራጭ፦ {method}\n💰 መጠን፦ {amount} ETB\n⏳ Admin እስኪያጸድቅ ይጠብቁ።",
        'dep_fail': "⚠️ ጥያቄዎ ሊመዘገብ አልቻለም። እባክዎ በ @Tazikes ያግኙን።",
        'wd_choose': "🏦 ወደ የትኛው ባንክ ማውጣት ይፈልጋሉ?",
        'wd_enter_amt': "💸 እባክዎ ማውጣት የሚፈልጉትን መጠን ያስገቡ (ዝቅተኛው 100 ETB)፦",
        'wd_enter_phone': "📱 እባክዎ ወደሚወጣበትን የቴሌብር/ባንክ ስልክ ቁጥር ያስገቡ፦",
        'wd_success': "✅ <b>የWithdraw ጥያቄዎ ተልኳል!</b>\n\n👤 ስም፦ {name}\n💳 አማራጭ፦ {method}\n💰 መጠን፦ {amount} ETB\n📱 ስልክ፦ {phone}\n⏳ Admin እስኪያጸድቅ ይጠብቁ።",
        'wd_fail': "⚠️ ጥያቄዎ ሊመዘገብ አልቻለም። እባክዎ በ @Tazikes ያግኙን።",
        'invite_msg': "🔗 <b>የእርስዎ የግብዣ ሊንክ፦</b>\nhttps://t.me/Ethiobongo_bot?start={id}\n\n🎁 ወዳጅዎን ሲጋብዙ 30 ብር ያገኛሉ! ጓደኛዎም 20 ብር ያገኛል።",
        'support_msg': "💬 ማንኛውም ጥያቄ ካለዎት በ @Tazikes ያግኙን።",
        'history_msg': "📜 ታሪክዎን ለማየት ከዚህ በታች ይጫኑ፦",
        'register_prompt': "እባክዎ ለመመዝገብ የስልክ ቁጥርዎን ያጋሩ፦",
        'share_contact': "📱 ስልክ ቁጥሬን አጋራ",
        'registered': "✅ <b>በተሳካ ሁኔታ ተመዝግበዋል!</b>\n📱 ስልክ ቁጥርዎ፦ <code>{phone}</code>",
        'lang_choose': "🌐 እባክዎ ቋንቋ ይምረጡ፦",
        'lang_changed': "✅ ቋንቋ ተቀይሯል! አሁን ምናሌውን እንደገና ይመልከቱ።",
        'cancel': "❌ ሂደቱ ተሰርዟል።",
        'invalid_amt': "❌ እባክዎ ትክክለኛ ቁጥር ያስገቡ።",
        'min_wd': "❌ ዝቅተኛው የወጭ መጠን 100 ETB ነው።",
        'min_dep': "❌ ዝቅተኛው የገቢ መጠን 10 ETB ነው።",
        'invalid_phone': "❌ ትክክለኛ ስልክ ቁጥር ያስገቡ።"
    },
    'en': {
        'start': "🎉 <b>Welcome to the Abisinya Bingo App!</b>\n\n👤 Name: {name}\n🆔 ID: <code>{id}</code>\n💵 Balance: <b>{balance} ETB</b>\n\n👇 Choose an option below",
        'play_prompt': "🎲 Welcome to Abisinya Bingo!\nPlay and Win! May victory be yours!\n\n👇 Tap the button below to start playing:",
        'play_inline_btn': "🎮 Play Bingo",
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
        'help_msg': "📚 <b>Bot Commands & Guide</b>\n\n/start - Restart the bot\n/play - Play the game\n/balance - Check your balance\n/deposit - Make a deposit\n/withdraw - Make a withdrawal\n/invite - Get your invite link\n/support - Get help\n/lang - Change language\n\n💡 <i>You can also use the buttons below.</i>",
        'dep_choose': "💳 Choose a payment method:",
        'dep_enter_amt': "💸 Please enter the amount you want to deposit:",
        'dep_instructions': "🏦 Bank: TeleBirr\n\n⚠️ <b>WARNING: Send Telebirr to Telebirr ONLY!</b>\n\nSend money to:\n👤 Name: <b>{name}</b>\n👉 Account: <code>{acc}</code>\n\n👉 After sending, copy the full SMS and paste it below 👇",
        'dep_txn_prompt': "👉 Please paste the SMS text (Transaction ID) here:",
        'dep_success': "✅ <b>Deposit Request Sent!</b>\n\n👤 Name: {name}\n💳 Method: {method}\n💰 Amount: {amount} ETB\n⏳ Wait for Admin approval.",
        'dep_fail': "⚠️ Request failed. Please contact @Tazikes.",
        'wd_choose': "🏦 Choose a bank to withdraw:",
        'wd_enter_amt': "💸 Enter the amount to withdraw (minimum 100 ETB):",
        'wd_enter_phone': "📱 Enter the Phone/Account number to withdraw to:",
        'wd_success': "✅ <b>Withdraw Request Sent!</b>\n\n👤 Name: {name}\n💳 Method: {method}\n💰 Amount: {amount} ETB\n📱 Phone: {phone}\n⏳ Wait for Admin approval.",
        'wd_fail': "⚠️ Request failed. Please contact @Tazikes.",
        'invite_msg': "🔗 <b>Your Invite Link:</b>\nhttps://t.me/Ethiobongo_bot?start={id}\n\n🎁 Invite a friend and get 30 ETB! They get 20 ETB.",
        'support_msg': "💬 For any questions contact @Tazikes.",
        'history_msg': "📜 Click below to view your history:",
        'register_prompt': "Please share your phone number to register:",
        'share_contact': "📱 Share Phone Number",
        'registered': "✅ <b>Registered successfully!</b>\n📱 Phone: <code>{phone}</code>",
        'lang_choose': "🌐 Choose a language:",
        'lang_changed': "✅ Language changed! Check your updated menu below.",
        'cancel': "❌ Process cancelled.",
        'invalid_amt': "❌ Please enter a valid number.",
        'min_wd': "❌ Minimum withdrawal is 100 ETB.",
        'min_dep': "❌ Minimum deposit is 10 ETB.",
        'invalid_phone': "❌ Please enter a valid phone number."
    }
}

TEXTS['ti'] = TEXTS['am']
TEXTS['om'] = TEXTS['am']

def get_text(user_id, key, **kwargs):
    _, lang = get_user_data(user_id)
    if lang not in TEXTS: lang = 'am'
    text = TEXTS[lang].get(key, TEXTS['am'].get(key, ''))
    return text.format(**kwargs) if kwargs else text

def get_main_menu(user_id):
    _, lang = get_user_data(user_id)
    if lang not in TEXTS: lang = 'am'
    t = TEXTS[lang]
    keyboard = [
        [KeyboardButton(text=t['menu_play'])],
        [KeyboardButton(text=t['menu_deposit']), KeyboardButton(text=t['menu_withdraw'])],
        [KeyboardButton(text=t['menu_balance']), KeyboardButton(text=t['menu_invite'])],
        [KeyboardButton(text=t['menu_history']), KeyboardButton(text=t['menu_support'])],
        [KeyboardButton(text=t['menu_register']), KeyboardButton(text=t['menu_lang'])],
        [KeyboardButton(text=t['menu_help']), KeyboardButton(text=t['menu_rank'])]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

# ─── Commands ───
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)
    
    # Referral system
    args = context.args
    if args and len(args) > 0 and not user.is_bot:
        referrer_id = args[0]
        if referrer_id != str(user.id):
            try:
                requests.post(f"{SERVER_API_URL}/api/user/referral", json={"new_user_id": str(user.id), "referrer_id": referrer_id}, timeout=5)
            except: pass
            
    balance = 0.00
    try:
        res = requests.get(f"{SERVER_API_URL}/api/wallet/me", headers={"X-User-Id": str(user.id)}, timeout=5)
        if res.ok:
            balance = res.json().get("data", {}).get("play_balance", 0.00)
    except: pass

    # Use 'start' key for the text
    welcome_text = get_text(user.id, 'start', name=user.first_name, id=user.id, balance=balance)
    await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=get_main_menu(user.id))

# ✅ አዲስ፦ /play ኮማንድ
async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    play_text = get_text(user.id, 'play_prompt')
    web_app_btn = InlineKeyboardButton(text=get_text(user.id, 'play_inline_btn'), web_app=WebAppInfo(url=WEBAPP_URL))
    await update.message.reply_text(play_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[web_app_btn]]))

# ✅ አዲስ፦ /help ኮማንድ
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(get_text(user.id, 'help_msg'), parse_mode='HTML')

# ─── Register ───
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(text=get_text(update.effective_user.id, 'share_contact'), request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(get_text(update.effective_user.id, 'register_prompt'), reply_markup=reply_markup)

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact:
        user = update.effective_user
        phone = contact.phone_number
        save_user(user.id, user.username, user.first_name, phone)
        
        try: requests.post(f"{SERVER_API_URL}/api/user/phone", json={"user_id": str(user.id), "phone": phone, "name": user.first_name}, timeout=5)
        except: pass
        
        await update.message.reply_text(get_text(user.id, 'registered', phone=phone), parse_mode='HTML', reply_markup=get_main_menu(user.id))

# ─── Deposit ───
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("📱 TeleBirr", callback_data="dep_telebirr")]]
    await update.message.reply_text(get_text(user.id, 'dep_choose'), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return DEPOSIT_METHOD

async def deposit_method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    context.user_data['deposit_method'] = "Telebirr"
    
    await query.edit_message_text(get_text(user.id, 'dep_enter_amt'), parse_mode='HTML')
    return DEPOSIT_TXN_ID

async def deposit_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        amount = float(update.message.text)
        if amount < 10: 
            await update.message.reply_text(get_text(user.id, 'min_dep'))
            return DEPOSIT_TXN_ID
    except:
        await update.message.reply_text(get_text(user.id, 'invalid_amt'))
        return DEPOSIT_TXN_ID

    context.user_data['deposit_amount'] = amount
    
    try:
        res = requests.get(f"{SERVER_API_URL}/api/settings", timeout=5)
        settings = res.json().get("data", {})
    except: settings = {}
    
    acc = settings.get("telebirr_number", "0968940123")
    name = settings.get("telebirr_name", "tazebew")
    
    await update.message.reply_text(get_text(user.id, 'dep_instructions', name=name, acc=acc), parse_mode='HTML')
    return DEPOSIT_AMOUNT

async def deposit_txn_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    txn_ref = update.message.text
    amount = context.user_data.get('deposit_amount', 0)
    
    result = None
    try:
        result = requests.post(f"{SERVER_API_URL}/api/bot/create-txn", json={
            "type": "deposit", "user_id": str(user.id), "user_name": user.first_name,
            "amount": amount, "method": "telebirr", "reference": txn_ref
        }, timeout=10).json()
    except: pass
    
    if result and result.get('success'):
        msg = get_text(user.id, 'dep_success', name=user.first_name, method="Telebirr", amount=amount)
    else:
        msg = get_text(user.id, 'dep_fail')
        
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_main_menu(user.id))
    
    if ADMIN_ID:
        try: await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 New Deposit Request!\nUser ID: {user.id}\n{msg}", parse_mode='HTML')
        except: pass
    return ConversationHandler.END

# ─── Withdraw ───
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📱 TeleBirr", callback_data="wd_telebirr")],
        [InlineKeyboardButton("🏦 CBE", callback_data="wd_cbe")]
    ]
    await update.message.reply_text(get_text(user.id, 'wd_choose'), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return WITHDRAW_METHOD

async def withdraw_method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    method_map = {'wd_telebirr': 'Telebirr', 'wd_cbe': 'CBE'}
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
    await update.message.reply_text(get_text(user.id, 'wd_enter_phone'), parse_mode='HTML')
    return WITHDRAW_PHONE

async def withdraw_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    phone = update.message.text.strip()
    if len(phone) < 9:
        await update.message.reply_text(get_text(user.id, 'invalid_phone'))
        return WITHDRAW_PHONE

    amount = context.user_data.get('withdraw_amount', 0)
    method = context.user_data.get('withdraw_method', 'Telebirr')
    
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
        msg = get_text(user.id, 'wd_fail')
        
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_main_menu(user.id))
    
    if ADMIN_ID:
        try: await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 New Withdraw Request!\nUser ID: {user.id}\n{msg}", parse_mode='HTML')
        except: pass
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_text(update.effective_user.id, 'cancel'), reply_markup=get_main_menu(update.effective_user.id))
    return ConversationHandler.END

# ─── Language ───
async def lang_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am")],
        [InlineKeyboardButton("🇪🇹 ትግርኛ", callback_data="lang_ti")],
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇹 Afaan Oromoo", callback_data="lang_om")]
    ]
    await update.message.reply_text(get_text(update.effective_user.id, 'lang_choose'), reply_markup=InlineKeyboardMarkup(keyboard))

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = query.data.replace('lang_', '')
    
    # Save new language
    save_user(user_id, query.from_user.username, query.from_user.first_name, lang=lang_code)
    
    # Confirm in the new language
    await query.edit_message_text(get_text(user_id, 'lang_changed'))
    
    # Force update the persistent menu by sending a new message
    await query.message.reply_text("👇", reply_markup=get_main_menu(user_id))

# ─── Other Menu Buttons ───
async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    t = lambda key: get_text(user.id, key)
    
    # Get current language strings for matching
    _, lang = get_user_data(user.id)
    if lang not in TEXTS: lang = 'am'
    texts = TEXTS[lang]

    if text in [texts['menu_play'], "🎮 Play Abyssinia Bingo"]:
        play_text = t('play_prompt')
        web_app_btn = InlineKeyboardButton(text=t('play_inline_btn'), web_app=WebAppInfo(url=WEBAPP_URL))
        await update.message.reply_text(play_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[web_app_btn]]))

    elif text in [texts['menu_balance'], "🏦 Balance", "💵 ሂሳብ"]:
        await update.message.reply_text("⏳ Loading balance...")
        try:
            res = requests.get(f"{SERVER_API_URL}/api/wallet/me", headers={"X-User-Id": str(user.id)}, timeout=10)
            bal = res.json().get("data", {})
            msg = f"💵 <b>Balance:</b>\n\n🟢 Play: <b>{bal.get('play_balance', 0)} ETB</b>\n🟡 Win: <b>{bal.get('win_balance', 0)} ETB</b>"
            await update.message.reply_text(msg, parse_mode='HTML')
        except: await update.message.reply_text("❌ Server Error")

    elif text in [texts['menu_invite'], "👥 Invite", "🔗 ግብዣ እና አጋር"]:
        await update.message.reply_text(t('invite_msg').format(id=user.id), parse_mode='HTML')
        
    elif text in [texts['menu_support'], "💬 Support", "🆘 እርዳታ"]:
        await update.message.reply_text(t('support_msg'), parse_mode='HTML')
    
    elif text in [texts['menu_help'], "ℹ️ Help"]:
        await update.message.reply_text(t('help_msg'), parse_mode='HTML')

    elif text in [texts['menu_register'], "🔢 Register"]:
        await register_start(update, context)

    elif text in [texts['menu_lang'], "🌐 Language", "🌐 ቋንቋ (Language)"]:
        await lang_menu(update, context)

    elif text in [texts['menu_history'], "📜 History"]:
        await update.message.reply_text(t('history_msg'))
        web_app_btn = InlineKeyboardButton(text="📜 Open History", web_app=WebAppInfo(url=f"{WEBAPP_URL}?page=history"))
        await update.message.reply_text("👇", reply_markup=InlineKeyboardMarkup([[web_app_btn]]))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    if not BOT_TOKEN: return
    threading.Thread(target=run_web, daemon=True).start()
    application = Application.builder().token(BOT_TOKEN).build()

    dep_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(💰 Deposit|📥 ገቢ \(Deposit\))$"), deposit_start)],
        states={
            DEPOSIT_METHOD: [CallbackQueryHandler(deposit_method_chosen, pattern="^dep_")],
            DEPOSIT_TXN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_received)],
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_txn_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    wd_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(💸 Withdraw|📤 ወጪ \(Withdraw\))$"), withdraw_start)],
        states={
            WITHDRAW_METHOD: [CallbackQueryHandler(withdraw_method_chosen, pattern="^wd_")],
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_received)],
            WITHDRAW_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play_command))
    application.add_handler(CommandHandler("help", help_command))

    # Conversations
    application.add_handler(dep_conv)
    application.add_handler(wd_conv)
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang_"))
    
    # Contacts & Messages
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))
    
    application.add_error_handler(error_handler)

    print("🤖 Bot is running with Multi-language support...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
