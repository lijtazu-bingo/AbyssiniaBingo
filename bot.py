import logging
import os
import sqlite3
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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
    app_web.run(host='0.0.0.0', port=port)

# ─── የቦት ማስተካከያ ───
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://abyssinia-bingo.onrender.com") # የ Render ሊንክህን እዚህ አስተካክል
SERVER_API_URL = os.getenv("SERVER_API_URL", WEBAPP_URL)
ADMIN_ID = os.getenv("ADMIN_ID")

DB_FILE = "abisinya_bot.db"

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

# ─── የቦት ትዕዛዞች ───

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)
    
    welcome_text = (
        f"ሰላም {user.first_name}! 👋\n\n"
        "🎉 <b>እንኳን ወደ Abyssinia Bingo በደህና መጡ!</b> 🎉\n\n"
        "ለመጫወት እና ለማሸነፍ ዝግጁ ነዎት? የእርስዎን የቴሌግራም ስልክ ቁጥር በማጋራት ይመዝገቡ።\n\n"
        "👇 <b>ከታች ያለውን ቁልፍ በመጠቀም ስልክ ቁጥርዎን ያጋሩ።</b>"
    )
    
    keyboard = [[KeyboardButton(text="📱 ስልክ ቁጥሬን አጋራ", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=reply_markup)

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact is not None:
        user = update.effective_user
        phone = contact.phone_number
        save_user(user.id, user.username, user.first_name, phone)
        
        success_text = (
            "✅ <b>በተሳካ ሁኔታ ተመዝግበዋል!</b>\n\n"
            f"📱 ስልክ ቁጥርዎ፦ <code>{phone}</code>\n\n"
            "🎮 አሁን ጨዋታውን ለመጀመር ከታች ያለውን <b>Play Bingo</b> የሚለውን ቁልፍ ይጫኑ።"
        )
        
        web_app_btn = InlineKeyboardButton(
            text="🎮 Play Bingo", 
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
        markup = InlineKeyboardMarkup([[web_app_btn]])
        
        await update.message.reply_text(success_text, parse_mode='HTML', reply_markup=markup)

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT phone FROM users WHERE user_id = ?", (str(user.id),))
    result = c.fetchone()
    conn.close()
    
    if not result or not result[0]:
        await update.message.reply_text("⚠️ እባክዎ መጀመሪያ ስልክ ቁጥርዎን ያጋሩ! /start በማለት ይመዝገቡ።")
        return
    
    web_app_btn = InlineKeyboardButton(
        text="🎮 Play Bingo", 
        web_app=WebAppInfo(url=WEBAPP_URL)
    )
    markup = InlineKeyboardMarkup([[web_app_btn]])
    await update.message.reply_text("🎮 ጨዋታውን ለመጀመር ከታች ያለውን ቁልፍ ይጫኑ፦", reply_markup=markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "ℹ️ <b>የእርዳታ ማዕከል</b>\n\n"
        "/start - ቦቱን እንደገና ለመጀመር\n"
        "/play - ወደ ጨዋታው ለመግባት\n"
        "/help - ይህንን መልእክት ለማየት\n\n"
        "❓ ሌላ ጥያቄ ካለዎት የድጋፍ ሰሌዳችንን ያግኙን።"
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    if not BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN is missing in .env file!")
        return

    # Flask ሰርቨሩን በተለየ Thread አስጀምር
    threading.Thread(target=run_web, daemon=True).start()
    print("🌐 Flask Web Server started.")

    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play_game))
    application.add_handler(CommandHandler("help", help_command))
    
    # Contact handler
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    # Log errors
    application.add_error_handler(error_handler)

    print("🤖 Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
