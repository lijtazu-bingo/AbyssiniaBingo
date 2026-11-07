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

# ─── ዋናው ምናሌ (Main Menu) - ልክ እንደ Spark Bingo ───
def get_main_menu():
    keyboard = [
        [KeyboardButton(text="🎮 ጨዋታ ይጫወቱ (PLAY)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="📥 ገቢ (Deposit)"), KeyboardButton(text="📤 ወጪ (Withdraw)")],
        [KeyboardButton(text="💵 ሂሳብ"), KeyboardButton(text="👤 ትርፍዬል")],
        [KeyboardButton(text="🔗 ግብዣ እና አጋር"), KeyboardButton(text="📢 ድርጅተኛ አስተዋዋቂ")],
        [KeyboardButton(text="🌐 ቋንቋ (Language)"), KeyboardButton(text="🆘 እርዳታ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ─── የቦት ትዕዛዞች ───

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)
    
    welcome_text = (
        f"ሰላም {user.first_name}! 👋\n\n"
        "🎉 <b>እንኳን ወደ Abyssinia Bingo በደህና መጡ!</b> 🎉\n\n"
        "ከታች ያለውን ምናሌ በመጠቀም ጨዋታ መጫወት፣ ገንዘብ ማስገባት ወይም ማውጣት ይችላሉ።"
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

# ─── 1. DEPOSIT FLOW (ልክ እንደ ምስል 2) ───
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📱 TeleBirr", callback_data="dep_telebirr"), InlineKeyboardButton("🏦 CBEBirr", callback_data="dep_cbe")],
        [InlineKeyboardButton("🟢 M-Pesa", callback_data="dep_mpesa")]
    ]
    await update.message.reply_text(
        "🏦 የትኛውን የባንክ አማራጭ መጠቀም ይፈልጋሉ?", 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='HTML'
    )
    return DEPOSIT_METHOD

async def deposit_method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "dep_telebirr":
        method = "Telebirr"
    elif query.data == "dep_cbe":
        method = "CBEBirr"
    else:
        method = "M-Pesa"
        
    context.user_data['deposit_method'] = method
    
    try:
        res = requests.get(f"{SERVER_API_URL}/api/settings")
        settings = res.json().get("data", {})
    except:
        settings = {}
        
    if method == "Telebirr":
        acc = settings.get("telebirr_number", "0968940123")
        name = settings.get("telebirr_name", "Lij Tazu")
    else:
        acc = "1000390803005"
        name = "Lij Tazu"

    text = (
        f"🏦 <b>{method} የክፍያ አካውንት</b>\n\n"
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

# ─── 2. WITHDRAW FLOW (ልክ እንደ ምስል 2) ───
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📱 TeleBirr", callback_data="wd_telebirr"), InlineKeyboardButton("🏦 CBEBirr", callback_data="wd_cbe")],
        [InlineKeyboardButton("🟢 M-Pesa", callback_data="wd_mpesa")]
    ]
    await update.message.reply_text(
        "🏦 የትኛውን የባንክ ወጪ ማድረግ ይፈልጋሉ?", 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='HTML'
    )
    return 5 # WITHDRAW_METHOD

async def withdraw_method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💸 እባክዎ ማውጣት የሚፈልጉትን <b>መጠን (Amount)</b> በቁጥር ያስገቡ (ቢያንስ 100 ETB):", parse_mode='HTML')
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

# ─── 3. OTHER MENU BUTTONS (ልክ እንደ ምስል 2) ───
async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user

    if "ሂሳብ" in text:
        await update.message.reply_text("⏳ ሂሳብዎን በመፈለግ ላይ...")
        try:
            res = requests.get(f"{SERVER_API_URL}/api/wallet/me", headers={"X-User-Id": str(user.id)})
            data = res.json()
            if data.get("success"):
                bal = data.get("data", {})
                msg = (
                    f"💵 <b>የሂሳብ ማጠቃለያ፦</b>\n\n"
                    f"🟢 መጫወቻ ሂሳብ (Play): <b>{bal.get('play_balance', 0)} ETB</b>\n"
                    f"🟡 ዋና ሂሳብ (Main): <b>{bal.get('win_balance', 0)} ETB</b>"
                )
                await update.message.reply_text(msg, parse_mode='HTML')
            else:
                await update.message.reply_text("⚠️ ሂሳብ ማግኘት አልተቻለም።")
        except:
            await update.message.reply_text("❌ ሰርቨሩ ላይ ችግር ተፈጥሯል።")
            
    elif "ትርፍዬል" in text:
        msg = (
            f"👤 <b>የእርስዎ ትርፍዬል</b>\n\n"
            f"🔹 ስም: <b>{user.first_name}</b>\n"
            f"🔹 ስልክ: <b>{context.user_data.get('phone', 'አልተመዘገበም')}</b>\n"
            f"🔹 መጫወቻ ሂሳብ: <b>-- ETB</b>\n\n"
            f"👉 ጨዋታ ለመጀመር ከታች ያለውን '🎮 ጨዋታ ይጫወቱ (PLAY)' የሚለውን ይጫኑ።"
        )
        await update.message.reply_text(msg, parse_mode='HTML')
        
    elif "ግብዣ እና አጋር" in text:
        msg = (
            f"🔗 <b>ግብዣ እና አጋር</b>\n\n"
            f"ይህንን የራስዎ የሆነ መጋበዣ ሊንክ ለወዳጆችዎ ይላኩ።\n"
            f"ጋብዘው በእርስዎ ሊንክ ገብተው ሲመዘገቡ እርስዎም ሆነ እነሱ የመጫወቻ ቦነስ ያገኛሉ!\n\n"
            f"👉 የግብዣ ሊንክ:\nhttps://t.me/AbyssiniaBingoBot?start={user.id}"
        )
        await update.message.reply_text(msg, parse_mode='HTML')
        
    elif "ድርጅተኛ አስተዋዋቂ" in text:
        await update.message.reply_text("📢 ልዩ አስተዋዋቂ (Promoter) ይሁኑ!\n\nልዩ አስተዋዋቂ ለመሆን እና ኮሚሽን በየቀኑ ለመሰብሰብ እባክዎ አድሚንን ያግኙ፦\n@AbyssiniaSupport")
        
    elif "ቋንቋ" in text:
        keyboard = [
            [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am"), InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
            [InlineKeyboardButton("🌳 Afaan Oromoo", callback_data="lang_om"), InlineKeyboardButton("🇪🇹 ትግርኛ", callback_data="lang_ti")]
        ]
        await update.message.reply_text("🌐 እባክዎ ቋንቋ ይምረጡ (Choose Language):", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif "እርዳታ" in text:
        msg = (
            f"💬 ማንኛውም ጥያቄ ወይም አስተያየት ካለዎት አድሚኑን በቴሌግራም ቻት በ @AbyssiniaSupport ያግኙ።\n\n"
            f"📞 በተጨማሪም በቀጥታ በስልክ መስመራችን፦\n<b>0968940123</b> ይደውሉልን።"
        )
        await update.message.reply_text(msg, parse_mode='HTML')

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ ቋንቋው ተቀይሯል!", reply_markup=get_main_menu())

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    web_app_btn = InlineKeyboardButton(text="🎮 ጨዋታ ይጫወቱ (PLAY)", web_app=WebAppInfo(url=WEBAPP_URL))
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
    dep_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📥 ገቢ \\(Deposit\\)$"), deposit_start)],
        states={
            DEPOSIT_METHOD: [CallbackQueryHandler(deposit_method_chosen, pattern="^dep_")],
            DEPOSIT_TXN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_txn_received)],
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    wd_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📤 ወጪ \\(Withdraw\\)$"), withdraw_start)],
        states={
            5: [CallbackQueryHandler(withdraw_method_chosen, pattern="^wd_")], # Withdraw Method
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_received)],
            WITHDRAW_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play_game))
    
    application.add_handler(dep_conv)
    application.add_handler(wd_conv)
    
    application.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang_"))
    
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))
    
    application.add_error_handler(error_handler)

    print("🤖 Bot is running with full menu logic...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
