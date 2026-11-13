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

# ─── Flask Web Server ───
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Abyssinia Bingo Bot is running!"

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

# ─── ሙሉ ትርጉሞች ───
TEXTS = {
    'am': {
        'register_first': "👋 <b>እንኳን ደህና መጡ!</b>\n\nለመጀመር እባክዎ የስልክ ቁጥርዎን ያጋሩ።",
        'share_contact': "📱 ስልክ ቁጥሬን አጋራ", 'already_registered': "✅ እርስዎ አስቀድመው ተመዝግበዋል!",
        'registered': "✅ <b>በተሳካ ሁኔታ ተመዝግበዋል!</b>\n📱 ስልክ ቁጥርዎ፦ <code>{phone}</code>\n\n🎉 ወደ Abyssinia Bingo መተግበሪያ በደህና መጡ!\n\n👇 ከታች ያለውን አማራጭ ይምረጡ",
        'welcome_back': "🎉 <b>ወደ Abyssinia Bingo መተግበሪያ በደህና መጡ!</b>\n\n👇 ከታች ያለውን አማራጭ ይምረጡ",
        
        'menu_play': "🎮 Play Abyssinia Bingo", 'menu_deposit': "💰 ገቢ (Deposit)", 'menu_withdraw': "💸 ወጪ (Withdraw)",
        'menu_balance': "🏦 ባላንስ (Balance)", 'menu_invite': "👥 ግብዣ (Invite)", 'menu_history': "📜 ታሪክ (History)",
        'menu_support': "💬 ድጋፍ (Support)", 'menu_register': "🔢 ምዝገባ (Register)", 'menu_lang': "🌐 ቋንቋ (Language)",
        'menu_help': "ℹ️ እርዳታ (Help)", 'menu_rank': "🏆 ደረጃ (Rank)", 'menu_rules': "📜 ህግና መመሪያ",
        
        'play_prompt': "🎲 ወደ Abyssinia Bingo እንኳን ደህና መጡ!\n\n👇 ጨዋታ ለመጀመር ከታች ያለውን ቁልፍ ይጫኑ:",
        'play_inline_btn': "🎮 Play Bingo",
        
        'dep_choose': "💳 <b>የክፍያ አማራጭ ይምረጡ፦</b>",
        'dep_enter_amt': "💸 እባክዎ ማስገባት የሚፈልጉትን <b>የብር መጠን</b> ያስገቡ (ለምሳሌ፦ 100)፦",
        'dep_instructions': "🏦 <b>የክፍያ መረጃ</b>\n\n👤 ስም፦ <b>{name}</b>\n👉 አካውንት፦ <code>{acc}</code>\n\n⚠️ ከተላከ በኋላ የመጣውን የSMS ሙሉ ጽሁፍ (Transaction ID) ኮፒ አድርገው ከታች 👇 ፓስት ያድርጉት፦",
        'dep_success': "✅ <b>የDeposit ጥያቄዎ ተልኳል!</b>\n\n👤 ስም፦ {name}\n💳 አማራጭ፦ {method}\n💰 መጠን፦ {amount} ETB\n⏳ አድሚን እስኪያጸድቅ ይጠብቁ።",
        'dep_duplicate': "❌ ይህ የግብይት ቁጥር (Transaction ID) ቀድሞ ጥቅም ላይ ውሏል!",
        'dep_invalid_txn': "❌ <b>ትክክለኛ የባንክ ማረጋገጫ (Transaction ID) ያስገቡ!</b>\n\nያስገቡት ጽሑፍ ትክክል አይደለም። ከSMS የመጣውን ረጅም የግብይት ቁጥር (ለምሳሌ FT12345678) ብቻ ኮፒ አድርገው ይላኩ።",
        
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
        'lang_choose': "🌐 <b>እባክዎ ቋንቋ ይምረጡ፦</b>", 'lang_changed': "✅ ቋንቋ ወደ አማርኛ ተቀይሯል!",
        'invalid_amt': "❌ እባክዎ ትክክለኛ ቁጥር ያስገቡ።", 'min_wd': "❌ ዝቅተኛው የወጭ መጠን 100 ETB ነው።",
        'min_dep': "❌ ዝቅተኛው የገቢ መጠን 10 ETB ነው።", 'invalid_phone': "❌ ትክክለኛ ስልክ ቁጥር ያስገቡ።", 'cancelled': "❌ ሂደቱ ተሰርዟል።",
        'gw_success': "🎉 <b>እንኳን ደስ አለዎት!</b>\n\nየ {amount} ETB ቦነስ በተሳካ ሁኔታ አግኝተዋል። በ Play Walletዎ ውስጥ ይገኛል።",
        'gw_expired': "⏳ <b>ይቅርታ!</b>\n\nይህ ቦነስ ጊዜው አልፎበታል ወይም ተጠቃሚዎች ሙሉውን ወስደዋል። በሚቀጥለው ጊዜ ይሞክሩ!",
        'gw_claimed': "⚠️ ይህን ቦነስ አስቀድመው አግኝተዋል።",
        'gw_error': "❌ ስህተት ተከስቷል። እባክዎ በኋላ ይሞክሩ።",
        
        'rules_msg': """🎯 <b>የ Abyssinia Bingo ሙሉ ህግጋት እና መመሪያዎች</b>

እንኳን ወደ <b>Abyssinia Bingo</b> በደህና መጡ! ጨዋታችንን ከመጀመርዎ በፊት እባክዎን የሚከተሉትን የጨዋታ ህጎች፣ ደንቦች እና መመሪያዎች በጥንቃቄ ያንብቡ።

<b>1️⃣ የጨዋታ ህግ እና አጫወት (Gameplay)</b>
* <b>የካርቴላ ዋጋ፦</b> የ 1 ካርቴላ ዋጋ 10 ብር ሲሆን፣ በአንድ ጨዋታ እስከ 4 ካርቴላ ድረስ መያዝ ይችላሉ።
* <b>የካርቴላ ይዘት፦</b> በሚይዙት እያንዳንዱ ካርቴላ ላይ ከ 1 እስከ 75 ባሉት ቁጥሮች ውስጥ የተበተኑ 24 የእድል ቁጥሮች ያገኛሉ (የመሃሉ ሳጥን FREE/ነፃ ነው)።
* <b>የጊዜ ገደብ፦</b> ካርቴላ መምረጫ ሰዓት እንደተጠናቀቀ ጨዋታው ወዲያውኑ ይጀምራል፤ ቁጥሮችም በቅደም ተከተል መጠራት ይጀምራሉ።
* <b>የካርቴላ ቀለም፦</b> እርስዎ የመረጡት ካርቴላ ቢጫ (Yellow) ሆኖ ይታያል። ሌሎች ተጫዋቾች የመረጡት ካርቴላ ወርቃማ-ቡናማ (Gold/Brown) ሆኖ ይታያል። በተመሳሳይ ጊዜ አንድ ካርቴላ በሁለት ሰዎች ሊመረጥ አይችልም።

<b>2️⃣ የማሸነፊያ መስፈርቶች (Winning Conditions)</b>
በያዙት ካርቴላ ላይ የተጠሩትን ቁጥሮች በመጠቀም በሚከተሉት መንገዶች አሸናፊ መሆን ይችላሉ፦
* <b>አግድም (Horizontal Line)፦</b> በአንድ ረድፍ ያሉ 5 ቁጥሮች ሲሟሉ።
* <b>ቀጥ ያለ (Vertical Line)፦</b> በአንድ አምድ ያሉ 5 ቁጥሮች ሲሟሉ።
* <b>ደያግናል/ሰያፍ (Diagonal Line)፦</b> ከላይ ግራ ወደ ታች ቀኝ ወይም ከላይ ቀኝ ወደ ታች ግራ ያሉ 5 ቁጥሮች ሲሟሉ።
* <b>አራቱ ማዕዘናት (4 Corners)፦</b> በካርቴላው አራት ማዕዘን ያሉት ቁጥሮች ሲጠሩ።
* <b>የመጨረሻ ቁጥር ህግ (Last Call Rule)፦</b> የመጨረሻው የተጠራው ቁጥር (Last Call) በእርስዎ የማሸነፊያ መስመር ላይ መሆን አለበት። መስመር የሞሉበትን ቁጥር ወይም አራቱን ማዕዘናት እንደጨረሱ ሲስተሙ ራሱ በራሱ አሸናፊዎችን ይለያል።

<b>3️⃣ የሽልማት ክፍፍል (Prize Distribution)</b>
* <b>የደራሽ መጠን፦</b> በዚያ ዙር ከተሸጡት ካርቴላዎች የተሰበሰበው ጠቅላላ ገንዘብ (Derash) ነው።
* <b>አንድ አሸናፊ ካለ፦</b> ሙሉ የደራሽ መጠኑን ይወስዳል።
* <b>ብዙ አሸናፊዎች ካሉ (Multi-Winner)፦</b> ሁለት ወይም ከዚያ በላይ ተጫዋቾች በአንድ ጊዜ ቢያሸንፉ የጨዋታው አጠቃላይ ሽልማት በእኩል ይከፋፈላል። የእያንዳንዱ አሸናፊ የካርቴላ ቁጥር እና ስም በስክሪኑ ላይ በግልጽ ይታያል።

<b>4️⃣ ዲፖዚት፣ ዊዝድራው እና ቦነስ (Finance & Wallet)</b>
* <b>ዲፖዚት (Deposit / Play Wallet)፦</b> ያስገቡት ገንዘብ ለመጫወቻነት ብቻ የሚያገለግል ሲሆን የሚቀመጠውም Play Wallet ላይ ነው። ይህን ገንዘብ በቀጥታ ወጪ ማድረግ (Withdraw) አይቻልም።
* <b>ዊዝድራው (Withdraw / Win Wallet)፦</b> በጨዋታ ያሸነፉት ገንዘብ በቀጥታ ወደ Win Wallet የሚገባ ሲሆን፣ በማንኛውም ጊዜ ወጪ ማድረግ ይችላሉ።
    * ዝቅተኛው የማውጫ መጠን 100 ብር ነው።
    * የወጭ ጥያቄዎች በአስተዳዳሪው እስኪረጋገጡ ድረስ በመጠባበቅ ላይ (Pending) ሆነው ይቆያሉ።
* <b>ቦነስ እና ግብዣ (Bonus & Referral)፦</b>
    * አዲስ ተጫዋች ሲመዘገብ የዕለት ቦነስ (Daily Bonus) ያገኛል።
    * ጓደኛ ለሚጋብዙ ተጫዋቾች 30 ብር፣ ለተጋበዙት አዲስ ተጫዋቾች ደግሞ 20 ብር ቦነስ ይሰጣል።
    * የተለያዩ የፕሮሞ ኮዶች (Promo Codes) በመጠቀም ተጨማሪ ቦነስ ማግኘት ይችላሉ።

<b>5️⃣ የዕድሜ ገደብ እና ሀላፊነት (Age Limit & Responsibility)</b>
* <b>የዕድሜ ገደብ፦</b> እድሜያቸው ከ 21 ዓመት በታች ለሆኑ ወጣቶች መጫወት በጥብቅ የተከለከለ ነው።
* <b>በኃላፊነት ይጫወቱ፦</b> ጨዋታው ለመዝናናት እና ለትርፍ ጊዜ ማሳለፊያ የተዘጋጀ ነው። አስበውበትና ፈቅደው ለመጫወት ብቻ የሚሆን ገንዘብ ያስገቡ። ቢከሰር እንኳ የዕለት ተዕለት ህይወትዎን በማይጎዳ ገንዘብ ብቻ ይጫወቱ።

<b>6️⃣ የተከለከሉ ድርጊቶች (Prohibited Actions)</b>
* <b>ብዙ አካውንት መፍጠር (Multi-Accounting)፦</b> አንድ ተጫዋች ከአንድ በላይ የቴሌግራም አካውንት በመፍጠር መጫወት አይችልም። ከተገኘ ሁሉም አካውንቶቹ ይዘጋሉ።
* <b>ማጭበርበር (Fraud)፦</b> የተሳሳተ የክፍያ ማረጋገጫ (Fake Transaction ID) በማስገባት ገንዘብ ለማግኘት መሞከር ለዘላለም ከጨዋታው እንዲወገዱ ያደርጋል።
* <b>የስፓም ስርዓት (Anti-Spam)፦</b> ተጫዋቾች በአጭር ጊዜ ውስጥ ብዙ የ Deposit/Withdraw ጥያቄዎችን ማስገባት አይችሉም (በየ 2 ደቂቃው አንድ ጥያቄ ብቻ)።
* <b>ቦት መጠቀም፦</b> ጨዋታውን በራስ-ሰር (Automation/Bot) ለመጫወት የሚሞክሩ ሶፍትዌሮችን መጠቀም የተከለከለ ነው።

<b>7️⃣ የቴክኒክ ችግሮች እና ማስተካከያ (Technical Issues)</b>
* በኢንተርኔት መቋረጥ፣ በስልክ ባትሪ ማለቅ ወይም በሰርቨር ስህተት ምክንያት ጨዋታው ሊቋረጥ ይችላል።
* በዚህ ጊዜ ጨዋታው ወደ መጀመሪያው ተመልሶ የሚጀምር ሲሆን፣ የተከፈለው የካርቴላ ገንዘብ ወደ ዋሌትዎ ይመለሳል።
* በቴክኒክ ችግር ምክንያት የተፈጠረ ኪሳራ አስተዳዳሪው ተጠያቂ አይሆንም።
* <b>የአስተዳዳሪ መብት፦</b> አስተዳዳሪው ህጎችን ወይም የጨዋታ መለኪያዎችን (ለምሳሌ የካርቴላ ዋጋ፣ የጊዜ ገደብ) በማንኛውም ጊዜ የመቀየር መብቱ የተጠበቀ ነው።

🎮 መልካም እድል እና መልካም የመዝናኛ ጊዜ እንመኝልዎታለን!"""
    },
    'en': {
        'register_first': "👋 <b>Welcome!</b>\n\nTo get started, please share your phone number.",
        'share_contact': "📱 Share Phone Number", 'already_registered': "✅ You are already registered!",
        'registered': "✅ <b>Registered successfully!</b>\n📱 Phone: <code>{phone}</code>\n\n🎉 Welcome to the Abyssinia Bingo App!\n\n👇 Choose an option below",
        'welcome_back': "🎉 <b>Welcome to the Abyssinia Bingo App!</b>\n\n👇 Choose an option below",
        'menu_play': "🎮 Play Abyssinia Bingo", 'menu_deposit': "💰 Deposit", 'menu_withdraw': "💸 Withdraw",
        'menu_balance': "🏦 Balance", 'menu_invite': "👥 Invite", 'menu_history': "📜 History",
        'menu_support': "💬 Support", 'menu_register': "🔢 Register", 'menu_lang': "🌐 Language",
        'menu_help': "ℹ️ Help", 'menu_rank': "🏆 Rank", 'menu_rules': "📜 Rules & Guidelines",
        'play_prompt': "🎲 Welcome to Abyssinia Bingo!\nPlay and Win!\n\n👇 Tap the button below to start playing:",
        'play_inline_btn': "🎮 Play Bingo",
        'dep_choose': "💳 <b>Choose a payment method:</b>", 'dep_enter_amt': "💸 Please enter the amount:",
        'dep_instructions': "🏦 <b>Payment Details</b>\n\n👤 Name: <b>{name}</b>\n👉 Account: <code>{acc}</code>\n\n⚠️ Paste Transaction ID below 👇",
        'dep_success': "✅ <b>Deposit Request Sent!</b>\n\n👤 Name: {name}\n💳 Method: {method}\n💰 Amount: {amount} ETB\n⏳ Wait for Admin approval.",
        'dep_duplicate': "❌ This Transaction ID has already been used!",
        'dep_invalid_txn': "❌ <b>Invalid Transaction ID!</b>\n\nPlease copy and paste the correct long Transaction ID from your SMS (e.g., FT12345678).",
        'wd_choose': "🏦 <b>Choose a bank to withdraw:</b>", 'wd_enter_amt': "💸 Enter the amount (min 100 ETB):",
        'wd_enter_phone': "📱 Enter the Phone number:", 'wd_success': "✅ <b>Withdraw Request Sent!</b>\n\n👤 Name: {name}\n💳 Method: {method}\n💰 Amount: {amount} ETB\n📱 Phone: {phone}\n\n⏳ <b>Wait for Admin approval.</b>",
        'bal_msg': "💵 <b>Balance Summary</b>\n\n🟢 Play Wallet: <b>{play} ETB</b>\n🟡 Win Wallet: <b>{win} ETB</b>\n👥 Referral Bonus: <b>{ref} ETB</b>\n\n💳 <b>Total Balance: {total} ETB</b>",
        'invite_msg': "🔗 <b>Your Invite Link:</b>\nhttps://t.me/Ethiobongo_bot?start={id}\n\n🎁 Invite a friend and get 30 ETB! They get 20 ETB.",
        'support_msg': "💬 Contact @Tazikes.", 'history_msg': "📜 Click below to view your history:",
        'help_msg': "📚 <b>Bot Commands</b>\n\n/start - Restart\n/play - Play\n/balance - Balance\n/deposit - Deposit\n/withdraw - Withdraw\n/invite - Invite\n/support - Support\n/lang - Language\n\n💡 <i>Use the buttons below.</i>",
        'leaderboard_msg': "🏆 Click below to view the leaderboard:",
        'lang_choose': "🌐 <b>Choose a language:</b>", 'lang_changed': "✅ Language changed to English!",
        'invalid_amt': "❌ Please enter a valid number.", 'min_wd': "❌ Minimum withdrawal is 100 ETB.",
        'min_dep': "❌ Minimum deposit is 10 ETB.", 'invalid_phone': "❌ Please enter a valid phone number.", 'cancelled': "❌ Process cancelled.",
        'gw_success': "🎉 <b>Congratulations!</b>\n\nYou have successfully claimed {amount} ETB bonus. It is now in your Play Wallet.",
        'gw_expired': "⏳ <b>Sorry!</b>\n\nThis giveaway has expired or all bonuses have been claimed. Try again next time!",
        'gw_claimed': "⚠️ You already claimed this bonus.", 'gw_error': "❌ Error occurred. Try again later.",
        
        'rules_msg': """🎯 <b>Abyssinia Bingo Rules & Guidelines</b>

Welcome to <b>Abyssinia Bingo</b>! Please read the following rules and guidelines carefully before starting.

<b>1️⃣ Gameplay</b>
* <b>Card Price:</b> 1 Card is 10 ETB. You can hold up to 4 cards per game.
* <b>Card Content:</b> Each card has 24 random numbers from 1 to 75 (Center is FREE).
* <b>Time Limit:</b> Once the selection timer ends, the game starts and numbers are called automatically.
* <b>Card Colors:</b> Your selected card is Yellow. Other players' selected cards are Gold/Brown. A card can only be selected by one player.

<b>2️⃣ Winning Conditions</b>
You win by completing any of the following:
* <b>Horizontal Line:</b> 5 numbers in a row.
* <b>Vertical Line:</b> 5 numbers in a column.
* <b>Diagonal Line:</b> 5 numbers from corner to corner.
* <b>4 Corners:</b> The 4 corner numbers of the card.
* <b>Last Call Rule:</b> The last called number must be part of your winning line. The system automatically verifies and announces the winner.

<b>3️⃣ Prize Distribution</b>
* <b>Total Prize (Derash):</b> The total money collected from all sold cards in that round.
* <b>Single Winner:</b> Takes the entire prize pool.
* <b>Multi-Winner:</b> If two or more players win at the same time, the prize is split equally. Winner names and card numbers are displayed.

<b>4️⃣ Deposit, Withdraw & Bonus</b>
* <b>Deposit (Play Wallet):</b> Money deposited is for playing only and is stored in the Play Wallet. It cannot be withdrawn directly.
* <b>Withdraw (Win Wallet):</b> Money won in games goes to the Win Wallet and can be withdrawn anytime.
    * Minimum withdrawal: 100 ETB.
    * Withdraw requests are pending until approved by an admin.
* <b>Bonus & Referral:</b>
    * New players get a Daily Bonus.
    * Invite a friend and get 30 ETB, the new user gets 20 ETB.
    * Use Promo Codes for extra bonuses.

<b>5️⃣ Age Limit & Responsibility</b>
* <b>Age Limit:</b> Strictly 21+ only.
* <b>Play Responsibly:</b> This is for entertainment. Only play with money you can afford to lose.

<b>6️⃣ Prohibited Actions</b>
* <b>Multi-Accounting:</b> One player can only have one Telegram account. Multiple accounts will be banned.
* <b>Fraud:</b> Fake Transaction IDs will result in a permanent ban.
* <b>Anti-Spam:</b> You can only submit one Deposit/Withdraw request every 2 minutes.
* <b>Bots:</b> Using automation or bots to play is strictly prohibited.

<b>7️⃣ Technical Issues</b>
* If the game is interrupted due to internet, battery, or server issues, the round will reset, and card fees will be refunded.
* The admin is not responsible for losses due to technical issues.
* The admin reserves the right to change rules or game parameters at any time.

🎮 Good luck and have fun!"""
    },
    'ti': {
        'register_first': "👋 <b>እንቋዕ ደሓን መጻእኩም!</b>\n\nንምጅማር በጃኹም ቁጽሪ ተሌፎንኩም ኣካፍሉ።",
        'share_contact': "📱 ቁጽሪ ተሌፎነይ ኣካፍል", 'already_registered': "✅ ተመዝጊብኩም ኢኹም!",
        'registered': "✅ <b>ብዓወት ተመዝጊብኩም!</b>\n📱 ቁጽሪ ተሌፎን፦ <code>{phone}</code>\n\n🎉 እንቋዕ ናብ Abyssinia Bingo መጻእኩም!\n\n👇 ኣብ ታሕቲ ዘሎ ኣማራጺ ምረጹ",
        'welcome_back': "🎉 <b>እንቋዕ ናብ Abyssinia Bingo መጻእኩም!</b>\n\n👇 ኣብ ታሕቲ ዘሎ ኣማራጺ ምረጹ",
        'menu_play': "🎮 Play Abyssinia Bingo", 'menu_deposit': "💰 ኣታዊ (Deposit)", 'menu_withdraw': "💸 ወጻኢ (Withdraw)",
        'menu_balance': "🏦 ተረፍ (Balance)", 'menu_invite': "👥 ዕድመ (Invite)", 'menu_history': "📜 ታሪኽ (History)",
        'menu_support': "💬 ደገፍ (Support)", 'menu_register': "🔢 ምዝገባ (Register)", 'menu_lang': "🌐 ቋንቋ (Language)",
        'menu_help': "ℹ️ ሓገዝ (Help)", 'menu_rank': "🏆 ደረጃ (Rank)", 'menu_rules': "📜 ሕግን መምርሕን",
        'play_prompt': "🎲 እንቋዕ ናብ Abyssinia Bingo መጻእኩም!\nተጻወቱ ተዓወቱ!\n\n👇 ጸወታ ንምጅማር ኣብ ታሕቲ ዘሎ መጠወቒ ጠውቑ:",
        'play_inline_btn': "🎮 Play Bingo",
        'dep_choose': "💳 <b>የክፍሊት ኣማራጺ ምረጹ፦</b>", 'dep_enter_amt': "💸 እባክዎ ክትኣትዉ ትደልዩ መጠን ገንዘብ ኣእትዉ፦",
        'dep_instructions': "🏦 <b>ናይ ክፍሊት ሓበሬታ</b>\n\n👤 ስም፦ <b>{name}</b>\n👉 ኣካውንት፦ <code>{acc}</code>\n\n⚠️ ድሕሪ ምስዳድ ዝመጸ ናይ SMS ጽሑፍ ኣብዚ ለጥፉ 👇",
        'dep_success': "✅ <b>ናይ Deposit ሕቶኹም ተላኢኹ!</b>\n\n👤 ስም፦ {name}\n💳 ኣማራጺ፦ {method}\n💰 መጠን፦ {amount} ETB\n⏳ ንኣድሚን ጽበዩ።",
        'dep_duplicate': "❌ እዚ ናይ ግብይት ቁጽሪ ቀዲሙ ተጠቒሙ እዩ!",
        'dep_invalid_txn': "❌ <b>ትኽክለኛ ናይ ባንክ መረጋገጺ (Transaction ID) ኣእትዉ!</b>\n\nዝኣእተኩምዎ ጽሑፍ ትኽክል ኣይኮነን። ካብ SMS ዝመጸ ነዊሕ ናይ ግብይት ቁጽሪ (ኣብነት FT12345678) ጥራይ ኮፒ ገይሩ ስደዱ።",
        'wd_choose': "🏦 <b>ናብ ኣየናይ ባንክ ክትወጽኡ ትደልዩ?</b>", 'wd_enter_amt': "💸 እባክዎ ክትወጽኡ ትደልዩ መጠን ኣእትዉ (ዝቕነይ 100 ETB)፦",
        'wd_enter_phone': "📱 እባክዎ ናይ ተሌፎን ቁጽሪ ኣእትዉ፦", 'wd_success': "✅ <b>ናይ Withdraw ሕቶኹም ተላኢኹ!</b>\n\n👤 ስም፦ {name}\n💳 ኣማራጺ፦ {method}\n💰 መጠን፦ {amount} ETB\n📱 ስልኪ፦ {phone}\n\n⏳ <b>ንኣድሚን ጽበዩ።</b>",
        'bal_msg': "💵 <b>ናይ ሂሳብ ጥርዓን</b>\n\n🟢 Play Wallet: <b>{play} ETB</b>\n🟡 Win Wallet: <b>{win} ETB</b>\n👥 Referral Bonus: <b>{ref} ETB</b>\n\n💳 <b>ጠቕላላ ባላንስ፦ {total} ETB</b>",
        'invite_msg': "🔗 <b>ናይ ዕድመ ሊንክኩም፦</b>\nhttps://t.me/Ethiobongo_bot?start={id}\n\n🎁 ዓርኪኹም ምስ ትዕድሙ 30 ብር ትረኽቡ! ንሳቶም ድማ 20 ብር ይረኽቡ።",
        'support_msg': "💬 ዝኾነ ሕቶ እንተሎኩም ብ @Tazikes ርኸቡና።", 'history_msg': "📜 ታሪኽኩም ንምርኣይ ኣብ ታሕቲ ጠውቑ፦",
        'help_msg': "📚 <b>ናይ ቦት ትእዛዛት</b>\n\n/start - ቦት ንምጅማር\n/play - ንምጽዋት\n/balance - ባላንስ\n/deposit - ኣታዊ\n/withdraw - ወጻኢ\n/invite - ዕድመ\n/support - ደገፍ\n/lang - ቋንቋ\n\n💡 <i>ነቶም ኣብ ታሕቲ ዘለዉ መጠወቒታት ተጠቐሙ።</i>",
        'leaderboard_msg': "🏆 ደረጃ ንምርኣይ ኣብ ታሕቲ ጠውቑ፦",
        'lang_choose': "🌐 <b>ቋንቋ ምረጹ:</b>", 'lang_changed': "✅ ቋንቋ ናብ ትግርኛ ተቐይሩ!",
        'invalid_amt': "❌ ትኽክለኛ ቁጽሪ ኣእትዉ።", 'min_wd': "❌ ዝቕነይ ወጻኢ 100 ETB እዩ።",
        'min_dep': "❌ ዝቕነይ ኣታዊ 10 ETB እዩ።", 'invalid_phone': "❌ ትኽክለኛ ቁጽሪ ተሌፎን ኣእትዉ።", 'cancelled': "❌ መስርሕ ተሰሪዙ።",
        'gw_success': "🎉 <b>እንቋዕ ደስ ኣለኩም!</b>\n\nናይ {amount} ETB ቦነስ ብዓወት ረኺብኩም። ኣብ Play Walletኩም ይርከብ።",
        'gw_expired': "⏳ <b>ይቕሬታ!</b>\n\nእዚ ቦነስ ግዜኡ ሓሊፉ ወይ ተጠቀምቲ ኩሉ ወሲዶምዎ። ኣብ ዝቕጽል ግዜ ፈትኑ!",
        'gw_claimed': "⚠️ እዚ ቦነስ ቀዲምኩም ረኺብኩምዎ።", 'gw_error': "❌ ጌጋ ተፈጢሩ። ደሓር ፈትኑ።",
        'rules_msg': "📜 ሕግን መምርሕን ኣብ ምምሕዳር ክትረኽብዎ ትኽእሉ ኢኹም።" 
    },
    'om': {
        'register_first': "👋 <b>Baga nagaan dhuftan!</b>\n\nAkka jalqabdan, maaloo lakkoofsa bilbila keessan qoodaa.",
        'share_contact': "📱 Lakkoofsa Bilbilaa Qoodi", 'already_registered': "✅ Duraan galmeeffamtanii jirtu!",
        'registered': "✅ <b>Milkaa'inaan galmeeffameera!</b>\n📱 Bilbila: <code>{phone}</code>\n\n🎉 Baga gara Abyssinia Bingo dhuftan!\n\n👇 Filannoo gadii filadhaa",
        'welcome_back': "🎉 <b>Baga gara Abyssinia Bingo dhuftan!</b>\n\n👇 Filannoo gadii filadhaa",
        'menu_play': "🎮 Play Abyssinia Bingo", 'menu_deposit': "💰 Galii (Deposit)", 'menu_withdraw': "💸 Baasii (Withdraw)",
        'menu_balance': "🏦 Hajaa (Balance)", 'menu_invite': "👥 Affeera (Invite)", 'menu_history': "📜 Seenaa (History)",
        'menu_support': "💬 Deeggarsa (Support)", 'menu_register': "🔢 Galmee (Register)", 'menu_lang': "🌐 Afaan (Language)",
        'menu_help': "ℹ️ Gargaarsa (Help)", 'menu_rank': "🏆 Sadarkaa (Rank)", 'menu_rules': "📜 Seera fi Qajeelfama",
        'play_prompt': "🎲 Baga gara Abyssinia Bingo dhuftan!\nTaphadhaa Mo'adhaa!\n\n👇 Taphni akka jalqabuuf button gadii tuqaa:",
        'play_inline_btn': "🎮 Play Bingo",
        'dep_choose': "💳 <b>Mala kaffaltii filadhaa:</b>", 'dep_enter_amt': "💸 Maaloo maallaqa galii gochuu barbaaddan galchaa:",
        'dep_instructions': "🏦 <b>Odeeffannoo Kaffaltii</b>\n\n👤 Maqaa: <b>{name}</b>\n👉 Herrega: <code>{acc}</code>\n\n⚠️ Erga ergitanii booda SMS guutuu gadii maxxansaa 👇",
        'dep_success': "✅ <b>Gaaffiin Galii Ergameera!</b>\n\n👤 Maqaa: {name}\n💳 Mala: {method}\n💰 Hanga: {amount} ETB\n⏳ Admin eegaa.",
        'dep_duplicate': "❌ Lakkoofsi txn kun duraan tajaajilameera!",
        'dep_invalid_txn': "❌ <b>Lakkoofsa Txn sirrii galchaa!</b>\n\nBarruun galchitan sirrii miti. SMS irraa lakkoofsa txn dheeraa (fkn FT12345678) qofa garagalchii ergaa.",
        'wd_choose': "🏦 <b>Baankii baasii barbaaddan filadhaa:</b>", 'wd_enter_amt': "💸 Hanga baasii galchaa (xiqqaatee 100 ETB):",
        'wd_enter_phone': "📱 Lakkoofsa bilbila galchaa:", 'wd_success': "✅ <b>Gaaffiin Baasii Ergameera!</b>\n\n👤 Maqaa: {name}\n💳 Mala: {method}\n💰 Hanga: {amount} ETB\n📱 Bilbila: {phone}\n\n⏳ <b>Admin eegaa.</b>",
        'bal_msg': "💵 <b>Cuunfaa Hajaa</b>\n\n🟢 Play Wallet: <b>{play} ETB</b>\n🟡 Win Wallet: <b>{win} ETB</b>\n👥 Referral Bonus: <b>{ref} ETB</b>\n\n💳 <b>Hajaa Waliigalaa: {total} ETB</b>",
        'invite_msg': "🔗 <b>Liinkii Affeera Keessan:</b>\nhttps://t.me/Ethiobongo_bot?start={id}\n\n🎁 Hiriyyaa affeeruun 30 ETB argadhaa! Isaanis 20 ETB argatu.",
        'support_msg': "💬 Gaaffii yoo qabaattan @Tazikes qunnamaa.", 'history_msg': "📜 Seenaa keessan ilaaluuf gadii tuqaa:",
        'help_msg': "📚 <b>Ajaja Bot</b>\n\n/start - Jalqabi\n/play - Taphadhu\n/balance - Hajaa\n/deposit - Galii\n/withdraw - Baasii\n/invite - Affeera\n/support - Deeggarsa\n/lang - Afaan\n\n💡 <i>Button gadii fayyadamaa.</i>",
        'leaderboard_msg': "🏆 Sadarkaa ilaaluuf gadii tuqaa:",
        'lang_choose': "🌐 <b>Afaan filadhaa:</b>", 'lang_changed': "✅ Afaan gara Afaan Oromootti jijjiirameera!",
        'invalid_amt': "❌ Lakkoofsa sirrii galchaa.", 'min_wd': "❌ Baasiin xiqqaan 100 ETB dha.",
        'min_dep': "❌ Galiin xiqqaan 10 ETB dha.", 'invalid_phone': "❌ Lakkoofsa bilbila sirrii galchaa.", 'cancelled': "❌ Adeemsi haqameera.",
        'gw_success': "🎉 <b>Baga gammaddan!</b>\n\nBoonsii {amount} ETB milkaa'inaan argattan. Play Wallet keessan keessa jira.",
        'gw_expired': "⏳ <b>Dhiifama!</b>\n\nBoonsiin kun yeroon isaa darbeera ykn hunda fudhatameera. Yeroo biraa yaalaa!",
        'gw_claimed': "⚠️ Boonsii kana duraan argattaniittu.", 'gw_error': "❌ Dogoggorri uumameera. Booda yaalaa.",
        'rules_msg': "📜 Seera fi Qajeelfama Admin irraa argachuu dandeessu."
    }
}

# የአማርኛ ህጎችን ለሁሉም ቋንቋዎች መመደብ
TEXTS['ti']['rules_msg'] = TEXTS['am']['rules_msg']
TEXTS['om']['rules_msg'] = TEXTS['am']['rules_msg']
TEXTS['en']['rules_msg'] = TEXTS['am']['rules_msg']

def get_text(user_id, key, **kwargs):
    _, lang = get_user_data(user_id)
    if lang not in TEXTS: lang = 'en'
    text = TEXTS[lang].get(key) or TEXTS['en'].get(key) or TEXTS['am'].get(key, '')
    return text.format(**kwargs) if kwargs else text

def get_main_menu(user_id):
    t = lambda k: get_text(user_id, k)
    keyboard = [
        [KeyboardButton(text=t('menu_play'))],
        [KeyboardButton(text=t('menu_deposit')), KeyboardButton(text=t('menu_withdraw'))],
        [KeyboardButton(text=t('menu_balance')), KeyboardButton(text=t('menu_invite'))],
        [KeyboardButton(text=t('menu_register')), KeyboardButton(text=t('menu_lang'))],
        [KeyboardButton(text=t('menu_support')), KeyboardButton(text=t('menu_help'))],
        [KeyboardButton(text=t('menu_rules'))]
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
            try: requests.post(f"{SERVER_API_URL}/api/user/referral", json={"new_user_id": str(user.id), "referrer_id": referrer_id}, timeout=5)
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
    
    if not re.match(r'^[A-Z0-9]{8,}$', txn_ref, re.IGNORECASE):
        await update.message.reply_text(get_text(user.id, 'dep_invalid_txn'), parse_mode='HTML')
        return DEPOSIT_TXN 
    
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
    method_map = {'wd_telebirr_self': 'Telebirr (Self)', 'wd_telebirr_other': 'Telebirr (Other)', 'wd_cbe': 'CBE'}
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
    
    is_play = any(text == TEXTS[l].get('menu_play') for l in TEXTS) or "Play Abyssinia Bingo" in text
    is_balance = any(text == TEXTS[l].get('menu_balance') for l in TEXTS)
    is_invite = any(text == TEXTS[l].get('menu_invite') for l in TEXTS)
    is_support = any(text == TEXTS[l].get('menu_support') for l in TEXTS)
    is_help = any(text == TEXTS[l].get('menu_help') for l in TEXTS)
    is_register = any(text == TEXTS[l].get('menu_register') for l in TEXTS)
    is_lang = any(text == TEXTS[l].get('menu_lang') for l in TEXTS)
    is_history = any(text == TEXTS[l].get('menu_history') for l in TEXTS)
    is_rank = any(text == TEXTS[l].get('menu_rank') for l in TEXTS)
    is_rules = any(text == TEXTS[l].get('menu_rules') for l in TEXTS)

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
            else: await update.message.reply_text("❌ Failed to load balance.")
        except: await update.message.reply_text("❌ Server Error")
    elif is_invite: await update.message.reply_text(t('invite_msg').format(id=user.id), parse_mode='HTML')
    elif is_support: await update.message.reply_text(t('support_msg'), parse_mode='HTML')
    elif is_help: await update.message.reply_text(t('help_msg'), parse_mode='HTML')
    elif is_rank:
        await update.message.reply_text(t('leaderboard_msg'))
        web_app_btn = InlineKeyboardButton(text="🏆 Open Leaderboard", web_app=WebAppInfo(url=f"{WEBAPP_URL}?page=rank&lang={lang}"))
        await update.message.reply_text("👇", reply_markup=InlineKeyboardMarkup([[web_app_btn]]))
    elif is_register:
        phone, _ = get_user_data(user.id)
        if phone: await update.message.reply_text(t('already_registered'), parse_mode='HTML', reply_markup=get_main_menu(user.id))
        else:
            keyboard = [[KeyboardButton(text=t('share_contact'), request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(t('register_first'), parse_mode='HTML', reply_markup=reply_markup)
    elif is_lang: await lang_menu(update, context)
    elif is_history:
        await update.message.reply_text(t('history_msg'))
        web_app_btn = InlineKeyboardButton(text="📜 Open History", web_app=WebAppInfo(url=f"{WEBAPP_URL}?page=history&lang={lang}"))
        await update.message.reply_text("👇", reply_markup=InlineKeyboardMarkup([[web_app_btn]]))
    elif is_rules:
        await update.message.reply_text(t('rules_msg'), parse_mode='HTML')

# ✅✅✅ የተስተካከለ: GIVEAWAY CLAIM CALLBACK (የተሻሻለ error handling) ✅✅✅
async def claim_giveaway_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    giveaway_id = query.data.replace("claim_gw_", "")
    
    try:
        response = requests.post(
            f"{SERVER_API_URL}/api/bot/giveaway-claim",
            json={"giveaway_id": giveaway_id, "user_id": str(user.id)},
            timeout=10
        )
        
        # ✅ HTTP status ፍተሻ
        if not response.ok:
            logger.error(f"Giveaway API HTTP {response.status_code}: {response.text[:200]}")
            await query.edit_message_text(get_text(user.id, 'gw_error'), parse_mode='HTML')
            return
        
        # ✅ JSON parse ስህተት ከሆነ
        try:
            res = response.json()
        except ValueError:
            logger.error(f"Invalid JSON from giveaway API: {response.text[:200]}")
            await query.edit_message_text(get_text(user.id, 'gw_error'), parse_mode='HTML')
            return
        
        if res.get('success'):
            success_msg = get_text(user.id, 'gw_success', amount=res.get('amount'))
            await query.edit_message_text(success_msg, parse_mode='HTML')
        else:
            error_msg = (res.get('error') or '').lower()
            if 'expired' in error_msg or 'all bonuses' in error_msg:
                txt = get_text(user.id, 'gw_expired')
            elif 'already' in error_msg:
                txt = get_text(user.id, 'gw_claimed')
            else:
                txt = get_text(user.id, 'gw_error')
            await query.edit_message_text(txt, parse_mode='HTML')
            
    except requests.exceptions.Timeout:
        logger.error("Giveaway claim timeout")
        await query.edit_message_text(get_text(user.id, 'gw_error'), parse_mode='HTML')
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Giveaway connection error: {e}")
        await query.edit_message_text(get_text(user.id, 'gw_error'), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Giveaway claim error: {e}", exc_info=True)
        await query.edit_message_text(get_text(user.id, 'gw_error'), parse_mode='HTML')
# ✅✅✅ የተስተካከለ መጨረሻ ✅✅✅

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    if not BOT_TOKEN: return
    threading.Thread(target=run_web, daemon=True).start()
    application = Application.builder().token(BOT_TOKEN).build()

    all_menu_buttons = []
    for l in TEXTS:
        for k in ['menu_play', 'menu_deposit', 'menu_withdraw', 'menu_balance', 'menu_invite', 'menu_history', 'menu_support', 'menu_register', 'menu_lang', 'menu_help', 'menu_rank', 'menu_rules']:
            if k in TEXTS[l]: all_menu_buttons.append(re.escape(TEXTS[l][k]))
    
    menu_filter = filters.Regex(f"^({'|'.join(all_menu_buttons)})$")
    dep_entry_filter = filters.Regex(f"^({'|'.join([re.escape(TEXTS[l].get('menu_deposit', 'Deposit')) for l in TEXTS])})$")
    wd_entry_filter = filters.Regex(f"^({'|'.join([re.escape(TEXTS[l].get('menu_withdraw', 'Withdraw')) for l in TEXTS])})$")

    dep_conv = ConversationHandler(
        entry_points=[MessageHandler(dep_entry_filter, deposit_start)],
        states={
            DEPOSIT_AMOUNT: [
                CallbackQueryHandler(deposit_method_chosen, pattern="^dep_"), 
                MessageHandler(menu_filter, interrupt_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_received)
            ],
            DEPOSIT_TXN: [
                MessageHandler(menu_filter, interrupt_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_txn_received)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    wd_conv = ConversationHandler(
        entry_points=[MessageHandler(wd_entry_filter, withdraw_start)],
        states={
            WITHDRAW_METHOD: [
                CallbackQueryHandler(withdraw_method_chosen, pattern="^wd_"),
                MessageHandler(menu_filter, interrupt_handler),
            ],
            WITHDRAW_AMOUNT: [
                MessageHandler(menu_filter, interrupt_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_received)
            ],
            WITHDRAW_PHONE: [
                MessageHandler(menu_filter, interrupt_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone_received)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(dep_conv)
    application.add_handler(wd_conv)
    
    application.add_handler(CallbackQueryHandler(claim_giveaway_callback, pattern="^claim_gw_"))
    application.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang_"))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))
    application.add_error_handler(error_handler)

    print("🤖 Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
