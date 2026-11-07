import logging
import os
import sqlite3
import threading
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
from dotenv import load_dotenv

# .env ፋይልን ጫን
load_dotenv()

# የሎግ ማስተካከያ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Flask Web Server (ለ Render እንዳይዘጋ) ───
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Abyssinia Bingo Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port, use_reloader=False)

# ─── የቦት ማስተካከያ ───
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://abyssinia-bingo.onrender.com")
SERVER_API_URL = os.getenv("SERVER_API_URL", WEBAPP_URL)
ADMIN_ID = os.getenv("ADMIN_ID")

DB_FILE = "abisinya_bot.db"

# ─── የውይይት ሁኔታዎች (Conversation States) ───
DEPOSIT_METHOD, DEPOSIT_TXN_ID, DEPOSIT_AMOUNT = range(3)
WITHDRAW_AMOUNT, WITHDRAW_PHONE = range(3, 5)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY, username TEXT, first_name TEXT, phone TEXT, registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def save_user(user_id, username, first_name, phone=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if phone:
        c.execute("INSERT OR REPLACE INTO users (user_id, username, first_name, phone) VALUES (?, ?, ?, ?)",
                  (str(user_id), username, first_name, phone))
    else:
        c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                  (str(user_id), username, first_name))
    conn.commit()
    conn.close()

# ─── ዋናው ምናሌ (Main Menu) ───
def get_main_menu():
    keyboard = [
        [KeyboardButton(text="🎮 Play Bingo", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="💰 Deposit"), KeyboardButton(text="💸 Withdraw")],
        [KeyboardButton(text="🏦 Balance"), KeyboardButton(text="👥 Invite")],
        [KeyboardButton(text="📜 History"), KeyboardButton(text="💬 Support")],
        [KeyboardButton(text="🔢 Register"), KeyboardButton(text="🌐 Language")],
        [KeyboardButton(text="ℹ️ Help"), KeyboardButton(text="🏆 Rank")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ─── የቦት ትዕዛዞች ───

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)
    
    welcome_text = (
        f"ሰላም {user.first_name}! 👋\n\n"
        "🎉 <b>እንኳን ወደ Abyssinia Bingo በደህና መጡ!</b> 🎉\n\n"
        "ከታች ያለውን ምናሌ በመጠቀም ገንዘብ ማስገባት፣ ማውጣት ወይም ጨዋታ መጀመር ይችላሉ።"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=get_main_menu())

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact is not None:
        user = update.effective_user
        phone = contact.phone_number
        save_user(user.id, user.username, user.first_name, phone)
        await update.message.reply_text(
            f"✅ <b>በተሳካ ሁኔታ ተመዝግበዋል!</b>\n📱 <code>{phone}</code>", 
            parse_mode='HTML', 
            reply_markup=get_main_menu()
        )

# ─── 1. DEPOSIT FLOW ───
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📲 Telebirr", callback_data="dep_telebirr")],
        [InlineKeyboardButton("🏦 CBE", callback_data="dep_cbe")]
    ]
    await update.message.reply_text(
        "💵 <b>ገንዘብ ማስገባት (Deposit)</b>\n\nእባክዎ የክፍያ አማራጭ ይምረጡ፦", 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='HTML'
    )
    return DEPOSIT_METHOD

async def deposit_method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    method = "Telebirr" if query.data == "dep_telebirr" else "CBE"
    context.user_data['deposit_method'] = method
    
    try:
        res = requests.get(f"{SERVER_API_URL}/api/settings")
        settings = res.json().get("data", {})
    except:
        settings = {}
        
    if method == "Telebirr":
        acc = settings.get("telebirr_number", "0968940123")
        name = settings.get("telebirr_name", "Tazebew")
    else:
        acc = settings.get("cbe_number", "1000390803005")
        name = settings.get("cbe_name", "Tazebew")

    text = (
        f"🏦 <b>{method} አካውንት</b>\n\n"
        f"ቁጥር: <code>{acc}</code>\n"
        f"ስም: <b>{name}</b>\n\n"
        f"👉 ከላይ ወደሚገኘው አካውንት ገንዘቡን ያስገቡ።\n"
        f"👉 ከዚያ የላኩበትን <b>የግብይት ቁጥር (Transaction ID)</b> እዚህ ይላኩ፦"
    )
    
    await query.edit_message_text(text, parse_mode='HTML')
    return DEPOSIT_TXN_ID

async def deposit_txn_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txn_id = update.message.text
    context.user_data['deposit_txn'] = txn_id
    await update.message.reply_text("💰 አሁን የላኩትን <b>የገንዘብ መጠን (Amount)</b> በቁጥር ያስገቡ (ለምሳሌ: 100):", parse_mode='HTML')
    return DEPOSIT_AMOUNT

async def deposit_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
    except:
        await update.message.reply_text("❌ እባክዎ ትክክለኛ ቁጥር ያስገቡ።")
        return DEPOSIT_AMOUNT

    user = update.effective_user
    method = context.user_data.get('deposit_method')
    txn_id = context.user_data.get('deposit_txn')
    
    msg = (
        f"✅ <b>የDeposit ጥያቄዎ ተልኳል!</b>\n\n"
        f"👤 ስም: {user.first_name}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💳 አማራጭ: {method}\n"
        f"💰 መጠን: {amount} ETB\n"
        f"🧾 Txn ID: <code>{txn_id}</code>\n\n"
        f"⏳ Admin እስኪያጸድቅ ይጠብቁ።"
    )
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_main_menu())
    
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 <b>አዲስ Deposit ጥያቄ!</b>\n\n{msg}", parse_mode='HTML')
        except Exception as e:
            logger.error(f"Admin send error: {e}")
            
    return ConversationHandler.END

# ─── 2. WITHDRAW FLOW ───
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💸 እባክዎ ማውጣት የሚፈልጉትን <b>መጠን (Amount)</b> በቁጥር ያስገቡ (ቢያንስ 100 ETB):", parse_mode='HTML')
    return WITHDRAW_AMOUNT

async def withdraw_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount < 100:
            await update.message.reply_text("❌ ዝቅተኛው የወጭ መጠን 100 ETB ነው። እባክዎ በድጋሚ ያስገቡ፦")
            return WITHDRAW_AMOUNT
    except:
        await update.message.reply_text("❌ እባክዎ ትክክለኛ ቁጥር ያስገቡ።")
        return WITHDRAW_AMOUNT

    context.user_data['withdraw_amount'] = amount
    await update.message.reply_text("📱 አሁን ወደሚወጣበትን <b>የቴሌብር ስልክ ቁጥር</b> ያስገቡ፦", parse_mode='HTML')
    return WITHDRAW_PHONE

async def withdraw_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text
    amount = context.user_data.get('withdraw_amount')
    user = update.effective_user

    if len(phone) < 9:
        await update.message.reply_text("❌ እባክዎ ትክክለኛ ስልክ ቁጥር ያስገቡ።")
        return WITHDRAW_PHONE

    msg = (
        f"✅ <b>የWithdraw ጥያቄዎ ተልኳል!</b>\n\n"
        f"👤 ስም: {user.first_name}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💰 መጠን: {amount} ETB\n"
        f"📱 ስልክ: <code>{phone}</code>\n\n"
        f"⏳ Admin እስኪያጸድቅ ይጠብቁ።"
    )
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_main_menu())
    
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 <b>አዲስ Withdraw ጥያቄ!</b>\n\n{msg}", parse_mode='HTML')
        except Exception as e:
            logger.error(f"Admin send error: {e}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ሂደቱ ተሰርዟል።", reply_markup=get_main_menu())
    return ConversationHandler.END

# ─── 3. OTHER MENU BUTTONS (ይህ ክፍል ሙሉ በሙሉ ተስተካክሏል) ───
async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user

    if "Balance" in text:
        await update.message.reply_text("⏳ ባላንስዎን በመፈለግ ላይ...")
        try:
            res = requests.get(f"{SERVER_API_URL}/api/wallet/me", headers={"X-User-Id": str(user.id)})
            data = res.json()
            if data.get("success"):
                bal = data.get("data", {})
                msg = (
                    f"🏦 <b>የእርስዎ ባላንስ</b>\n\n"
                    f"🎮 Play: <b>{bal.get('play_balance', 0)} ETB</b>\n"
                    f"🏆 Win: <b>{bal.get('win_balance', 0)} ETB</b>"
                )
                await update.message.reply_text(msg, parse_mode='HTML')
            else:
                await update.message.reply_text("⚠️ ባላንስ ማግኘት አልተቻለም።")
        except:
            await update.message.reply_text("❌ ሰርቨሩ ላይ ችግር ተፈጥሯል።")
            
    elif "Invite" in text:
        await update.message.reply_text(f"👥 የእርስዎ የግብዣ ሊንክ፦\nhttps://t.me/Ethiobingo_bot?start={user.id}")
        
    elif "History" in text:
        await update.message.reply_text("📜 የግብይት ታሪክዎን ለማየት ወደ Bingo ገጽ ይግቡ ወይም /start ይጫኑ።")
        
    elif "Support" in text:
        await update.message.reply_text("💬 ለድጋፍ እባክዎ @AbyssiniaSupport ያግኙ።")
        
    elif "Register" in text:
        keyboard = [[KeyboardButton(text="📱 ስልክ ቁጥሬን አጋራ", request_contact=True)]]
        await update.message.reply_text("እባክዎ ስልክ ቁጥርዎን ያጋሩ፦", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))
        
    elif "Language" in text:
        await update.message.reply_text("🌐 ቋንቋን ለመቀየር በቅርቡ ይገኛል።")
        
    elif "Help" in text:
        help_text = (
            "ℹ️ <b>የእርዳታ ማዕከል</b>\n\n"
            "/start - ቦቱን እንደገና ለመጀመር\n"
            "/play - ወደ ጨዋታው ለመግባት\n\n"
            "❓ ሌላ ጥያቄ ካለዎት የድጋፍ ሰሌዳችንን ያግኙን።"
        )
        await update.message.reply_text(help_text, parse_mode='HTML')
        
    elif "Rank" in text:
        await update.message.reply_text("🏆 ከፍተኛ አሸናፊዎችን ለማየት ወደ Bingo ገጽ ይግቡ።")
        
    elif "Abisinya Bingo" in text:
        # የራሱን መልእክት ሲያገኝ
        pass

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    web_app_btn = InlineKeyboardButton(text="🎮 Play Bingo", web_app=WebAppInfo(url=WEBAPP_URL))
    markup = InlineKeyboardMarkup([[web_app_btn]])
    await update.message.reply_text("🎮 ጨዋታውን ለመጀመር ከታች ያለውን ቁልፍ ይጫኑ፦", reply_markup=markup)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    if not BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN is missing!")
        return

    threading.Thread(target=run_web, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()

    # ─── Conversation Handlers (Deposit & Withdraw) ───
    # እዚህ ጋር የ አዝራሮቹን ስም በትክክል ማስገባት አለብን
    dep_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Deposit$"), deposit_start)],
        states={
            DEPOSIT_METHOD: [CallbackQueryHandler(deposit_method_chosen, pattern="^dep_")],
            DEPOSIT_TXN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_txn_received)],
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    wd_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Withdraw$"), withdraw_start)],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_received)],
            WITHDRAW_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ✅ ቅደም ተከተሉ በጣም አስፈላጊ ነው!
    # 1. Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play_game))
    
    # 2. Conversation handlers (ለ Deposit እና Withdraw)
    application.add_handler(dep_conv)
    application.add_handler(wd_conv)
    
    # 3. Contact handler
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    # 4. General text handler (ለሌሎቹ አዝራሮች)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))
    
    application.add_error_handler(error_handler)

    print("🤖 Bot is running with full menu logic...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
