import telebot, os, time, json, random, string, re, threading
from telebot import types
from flask import Flask, jsonify, request
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://tqxpo-196-189-145-59.free.pinggy.net')
ADMIN_IDS = [5925033073]
MIN_WITHDRAW = 100
MIN_DEPOSIT = 10
TELEBIRR_NUMBER = "0968940123"
CBE_NUMBER = "1000390803005"
ACCOUNT_NAME = "tazebew"
SUPPORT_USERNAME = "Tazikes"

if not BOT_TOKEN:
    print("❌ BOT_TOKEN missing in .env")
    exit()

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# ✅ JSON FILE STORAGE
# ==========================================
BASE_DIR = os.path.dirname(__file__)
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
TXNS_FILE = os.path.join(BASE_DIR, 'transactions.json')
BROADCASTS_FILE = os.path.join(BASE_DIR, 'broadcasts.json')

def load_json(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    except: return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ JSON storage initialized")

# ==========================================
# TRANSLATIONS
# ==========================================
T = {
    'am': {
        'welcome': "🎉 እንኳን ወደ Abisinya Bingo በደህና መጡ!",
        'name': "ስም", 'id': "መለያ", 'balance': "ባላንስ",
        'choose_below': "ከታች ካሉት አማራጮች ይምረጡ 👇",
        'play': "🎯 Abisinya Bingo ይጫወቱ", 'deposit': "💰 ገንዘብ ማስገባት",
        'withdraw': "💸 ገንዘብ ማውጣት", 'balance_btn': "🏦 ባላንስ ማየት",
        'invite': "👥 ጓደኛ መጋበዝ", 'history': "📜 ታሪክ",
        'support': "💬 ድጋፍ", 'register': "🔢 መመዝገብ",
        'language': "🌐 ቋንቋ", 'help': "ℹ️ እርዳታ", 'leaderboard': "🏆 ደረጃ",
        'your_balance': "የእርስዎ ባላንስ", 'play_bal': "🎮 Play", 'win_bal': "🏆 Win",
        'total': "💰 ጠቅላላ", 'share_contact': "📱 ግንኙነት አጋራ",
        'share_contact_prompt': "ከታች ያለውን <b>📱 ግንኙነት አጋራ</b> ቁልፍ ይጫኑ:",
        'registered': "✅ በተሳካ ሁኔታ ተመዝግበዋል!",
        'already_registered': "✅ አስቀድመው ተመዝግበዋል!",
        'cannot_register_again': "⚠️ ድጋሚ መመዝገብ አይቻልም።",
        'deposit_choose': "💳 የክፍያ ዘዴ ይምረጡ፦",
        'send_txn': "📝 የTransaction/SMS ጽሑፍ ይላኩ",
        'txn_example': "ለምሳሌ: <code>TB123456789 500</code> ወይም ሙሉ SMS",
        'deposit_sent': "✅ የገቢ ጥያቄ ተልኳል!",
        'deposit_approved': "ገቢ ያደረጉት {amt} ETB ወደ ዋሌትዎ ተደምሯል",
        'good_luck': "🍀 መልካም ዕድል!",
        'play_below': "👇 ጨዋታውን ለመጀመር እዚህ ይጫኑ:",
        'withdraw_choose': "💸 የወጭ ዘዴ ይምረጡ:",
        'to_self': "👤 ወደ ራስዎ", 'to_other': "👥 ወደ ሌላ ቁጥር",
        'insufficient': "❌ Insufficient Balance",
        'min_withdraw': "ዝቅተኛው የወጭ መጠን: {amt} ETB",
        'wd_approved_req': "✅ Your withdrawal {amt} birr request approved",
        'wd_success': "✅ ወጭዎ በተሳካ ሁኔታ ወደ አካውንትዎ ገብቷል!",
        'wd_rejected': "❌ የወጭ ጥያቄዎ ተከልክሏል",
        'refunded': "{amt} ETB ወደ Win Balance ተመልሷል።",
        'send_amount': "💰 የሚወጣውን መጠን ይላኩ (ቢያንስ {min} ETB):",
        'send_phone': "📱 የቴሌብር ቁጥር ይላኩ:",
        'invalid_amount': "❌ ትክክለኛ ቁጥር ያስገቡ።",
        'invalid_phone': "❌ ትክክለኛ ቁጥር ያስገቡ።",
        'unknown': "❓ ያልተለየ ትዕዛዝ።\n/start ይጫኑ።",
        'pick_lang': "🌐 ቋንቋ ይምረጡ",
        'lang_changed': "🇪🇹 ቋንቋ ወደ አማርኛ ተቀይሯል።",
        'your_history': "የ{name} ታሪክ", 'deposits': "💰 ገቢዎች:",
        'withdrawals': "💸 ወጮች:", 'no_txn': "📭 እስካሁን ግብይት የለም።",
        'leaderboard_title': "🏆 ከፍተኛ አሸናፊዎች",
        'no_winners': "📭 እስካሁን ማንም አልተመዘገበም።",
        'support_msg': "ለእርዳታ ያግኙን",
        'invite_msg': "👥 ጓደኞችዎን ይጋብዙ!",
        'invite_bonus': "✨ ለእያንዳንዱ ጓደኛ <b>30 ETB</b> ያግኙ!",
        'your_link': "🔗 የእርስዎ ሊንክ:",
        'txn_ref': "የTransaction ቁጥር:",
        'txn_pending': "⏳ Admin እስኪያጸድቅ ይጠብቁ።",
        'not_registered': "❌ መጀመሪያ ማስመዝገብ ያስፈልጋል!",
        'registered_phone': "📱 የተመዘገበ ስልክ:",
        'help_title': "📋 የእርዳታ ማዕከል",
    },
    'en': {
        'welcome': "🎉 Welcome to Abisinya Bingo!",
        'name': "Name", 'id': "ID", 'balance': "Balance",
        'choose_below': "Choose from the options below 👇",
        'play': "🎯 Play Abisinya Bingo", 'deposit': "💰 Deposit",
        'withdraw': "💸 Withdraw", 'balance_btn': "🏦 Check Balance",
        'invite': "👥 Invite Friends", 'history': "📜 History",
        'support': "💬 Support", 'register': "🔢 Register",
        'language': "🌐 Language", 'help': "ℹ️ Help", 'leaderboard': "🏆 Leaderboard",
        'your_balance': "Your Balance", 'play_bal': "🎮 Play", 'win_bal': "🏆 Win",
        'total': "💰 Total", 'share_contact': "📱 Share Contact",
        'share_contact_prompt': "Tap the <b>📱 Share Contact</b> button below:",
        'registered': "✅ Successfully registered!",
        'already_registered': "✅ You are already registered!",
        'cannot_register_again': "⚠️ You cannot register again.",
        'deposit_choose': "💳 Choose payment method:",
        'send_txn': "📝 Send the Transaction/SMS text",
        'txn_example': "Example: <code>TB123456789 500</code>",
        'deposit_sent': "✅ Deposit request sent!",
        'deposit_approved': "Your deposit of {amt} ETB has been added",
        'good_luck': "🍀 Good luck!",
        'play_below': "👇 Tap here to start:",
        'withdraw_choose': "💸 Choose withdrawal method:",
        'to_self': "👤 To Yourself", 'to_other': "👥 To Another Number",
        'insufficient': "❌ Insufficient Balance",
        'min_withdraw': "Minimum: {amt} ETB",
        'wd_approved_req': "✅ Withdrawal {amt} birr approved",
        'wd_success': "✅ Your withdrawal was successful!",
        'wd_rejected': "❌ Your withdrawal was rejected",
        'refunded': "{amt} ETB refunded to Win Balance.",
        'send_amount': "💰 Send amount (min {min} ETB):",
        'send_phone': "📱 Send Telebirr phone:",
        'invalid_amount': "❌ Enter a valid number.",
        'invalid_phone': "❌ Enter a valid phone number.",
        'unknown': "❓ Unknown command.\nPress /start.",
        'pick_lang': "🌐 Choose Language",
        'lang_changed': "🇬🇧 Language switched to English.",
        'your_history': "{name}'s History", 'deposits': "💰 Deposits:",
        'withdrawals': "💸 Withdrawals:", 'no_txn': "📭 No transactions yet.",
        'leaderboard_title': "🏆 Top Winners", 'no_winners': "📭 No one yet.",
        'support_msg': "Contact us for help",
        'invite_msg': "👥 Invite your friends!",
        'invite_bonus': "✨ Get <b>30 ETB</b> for each friend!",
        'your_link': "🔗 Your link:",
        'txn_ref': "Transaction ID:",
        'txn_pending': "⏳ Wait for admin approval.",
        'not_registered': "❌ Please register first!",
        'registered_phone': "📱 Registered phone:",
        'help_title': "📋 Help Center",
    },
    'ti': {
        'welcome': "🎉 እንቋዕ ናብ Abisinya Bingo ብደሓን መጻእኩም!",
        'name': "ስም", 'id': "መለለዪ", 'balance': "ባላንስ",
        'choose_below': "ካብ ኣማራጺታት ትሕቲ ምረጹ 👇",
        'play': "🎯 Abisinya Bingo ተጻወት", 'deposit': "💰 ገንዘብ ኣእቱ",
        'withdraw': "💸 ገንዘብ ኣውጽእ", 'balance_btn': "🏦 ባላንስ ርአ",
        'invite': "👥 ኣሕዋት ዓድም", 'history': "📜 ታሪኽ",
        'support': "💬 ደገፍ", 'register': "🔢 ተመዝገብ",
        'language': "🌐 ቋንቋ", 'help': "ℹ️ ሓገዝ", 'leaderboard': "🏆 ደረጃ",
        'your_balance': "ባላንስካ", 'play_bal': "🎮 Play", 'win_bal': "🏆 Win",
        'total': "💰 ጠቕላላ", 'share_contact': "📱 ርክብ ኣካፍል",
        'share_contact_prompt': "ነቲ <b>📱 ርክብ ኣካፍል</b> ጠውቕ:",
        'registered': "✅ ብዓወት ተመዝጊብካ!",
        'already_registered': "✅ ቀድሚሁ ተመዝጊብካ!",
        'cannot_register_again': "⚠️ እንደገና ክትመዝገብ ኣይትኽእልን።",
        'deposit_choose': "💳 ኣገባብ ክፍሊት ምረጽ:",
        'send_txn': "📝 ጽሑፍ Transaction/SMS ስደድ",
        'txn_example': "ኣብነት: <code>TB123456789 500</code>",
        'deposit_sent': "✅ ሕቶ ኣታዊ ተላኢኹ!",
        'deposit_approved': "ኣታዊኻ {amt} ETB ናብ wallet ተወሲኹ",
        'good_luck': "🍀 ጽቡቕ ዕድል!",
        'play_below': "👇 ጸወታ ንምጅማር እዚ ጠውቕ:",
        'withdraw_choose': "💸 ኣገባብ ወጻኢ ምረጽ:",
        'to_self': "👤 ናብ ርእስኻ", 'to_other': "👥 ናብ ካልእ ቁጽሪ",
        'insufficient': "❌ Insufficient Balance",
        'min_withdraw': "ትሕቲ ወጻኢ: {amt} ETB",
        'wd_approved_req': "✅ ሕቶ ወጻኢኻ {amt} birr ተቐቢሉ",
        'wd_success': "✅ ወጻኢኻ ብዓወት ናብ account ኣትዩ!",
        'wd_rejected': "❌ ሕቶ ወጻኢኻ ተነጺጉ",
        'refunded': "{amt} ETB ናብ Win Balance ተመሊሱ።",
        'send_amount': "💰 ወጻኢ መጠን ስደድ (min {min} ETB):",
        'send_phone': "📱 ቁጽሪ Telebirr ስደድ:",
        'invalid_amount': "❌ ቅኑዕ ቁጽሪ ኣእቱ።",
        'invalid_phone': "❌ ቅኑዕ ቁጽሪ ኣእቱ።",
        'unknown': "❓ ዘይተፈልጠ ትእዛዝ።\n/start ጠውቕ።",
        'pick_lang': "🌐 ቋንቋ ምረጽ",
        'lang_changed': "🇪🇹 ቋንቋ ናብ ትግርኛ ተቐይሩ።",
        'your_history': "ታሪኽ {name}", 'deposits': "💰 ኣታዊታት:",
        'withdrawals': "💸 ወጻኢታት:", 'no_txn': "📭 ክሳብ ሕጂ ግብይት የለን።",
        'leaderboard_title': "🏆 ላዕለዎት ተዓወትቲ",
        'no_winners': "📭 ክሳብ ሕጂ ዝተመዝገበ የለን።",
        'support_msg': "ንሓገዝ ርኸቡና",
        'invite_msg': "👥 ኣሕዋትካ ዓድም!",
        'invite_bonus': "✨ ንነፍሲ ወከፍ ዓርኪ <b>30 ETB</b> ርኸብ!",
        'your_link': "🔗 ሊንክካ:",
        'txn_ref': "ቁጽሪ Transaction:",
        'txn_pending': "⏳ ንፈቓድ admin ተጸበ።",
        'not_registered': "❌ ቅድም ተመዝገብ!",
        'registered_phone': "📱 ዝተመዝገበ ቁጽሪ:",
        'help_title': "📋 ማእከል ሓገዝ",
    },
    'om': {
        'welcome': "🎉 Baga gara Abisinya Bingo nagaan dhuftan!",
        'name': "Maqaa", 'id': "Eenyummaa", 'balance': "Baalaansii",
        'choose_below': "Filannoo gadii keessaa filadhu 👇",
        'play': "🎯 Abisinya Bingo Taphadhu", 'deposit': "💰 Maallaqa Galchi",
        'withdraw': "💸 Maallaqa Baas", 'balance_btn': "🏦 Baalaansii Ilaali",
        'invite': "👥 Hiriyoota Affeeri", 'history': "📜 Seenaa",
        'support': "💬 Deeggarsa", 'register': "🔢 Galmaa'i",
        'language': "🌐 Afaan", 'help': "ℹ️ Gargaarsa", 'leaderboard': "🏆 Sadarkaa",
        'your_balance': "Baalaansii Kee", 'play_bal': "🎮 Play", 'win_bal': "🏆 Win",
        'total': "💰 Waliigala", 'share_contact': "📱 Quunnamtii Qoodi",
        'share_contact_prompt': "Isaa <b>📱 Quunnamtii Qoodi</b> tuqi:",
        'registered': "✅ Milkaa'inaan galmaa'te!",
        'already_registered': "✅ Duraan galmaa'teerta!",
        'cannot_register_again': "⚠️ Ammas galmaa'uu hin dandeessu.",
        'deposit_choose': "💳 Mala kaffaltii filadhu:",
        'send_txn': "📝 Barruu Transaction/SMS ergi",
        'txn_example': "Fkn: <code>TB123456789 500</code>",
        'deposit_sent': "✅ Gaaffiin galii ergame!",
        'deposit_approved': "Galii kee {amt} ETB wallet keetti dabalame",
        'good_luck': "🍀 Carraa gaarii!",
        'play_below': "👇 Taphni jalqabuuf as tuqi:",
        'withdraw_choose': "💸 Mala baasii filadhu:",
        'to_self': "👤 Ofiif", 'to_other': "👥 Lakkoofsa Biroof",
        'insufficient': "❌ Insufficient Balance",
        'min_withdraw': "Baasii xiqqaan: {amt} ETB",
        'wd_approved_req': "✅ Gaaffiin baasii kee {amt} birr fudhatame",
        'wd_success': "✅ Baasiin kee milkaa'inaan account keetti gale!",
        'wd_rejected': "❌ Gaaffiin baasii kee didame",
        'refunded': "{amt} ETB gara Win Balance deebi'e.",
        'send_amount': "💰 Hanga baasii ergi (min {min} ETB):",
        'send_phone': "📱 Lakkoofsa Telebirr ergi:",
        'invalid_amount': "❌ Lakkoofsa sirrii galchi.",
        'invalid_phone': "❌ Lakkoofsa sirrii galchi.",
        'unknown': "❓ Ajaja hin beekamne.\n/start tuqi.",
        'pick_lang': "🌐 Afaan filadhu",
        'lang_changed': "🇪🇹 Afaan gara Afaan Oromoo jijjiirame.",
        'your_history': "Seenaa {name}", 'deposits': "💰 Galiwwan:",
        'withdrawals': "💸 Baasiiwwan:", 'no_txn': "📭 Ammaatti daldala hin jiru.",
        'leaderboard_title': "🏆 Mo'attoota Olii",
        'no_winners': "📭 Ammaatti namni hin galmaa'ne.",
        'support_msg': "Gargaarsaaf nu quunnamaa",
        'invite_msg': "👥 Hiriyoota kee affeeri!",
        'invite_bonus': "✨ Hiriyoota tokkoon tokkoon <b>30 ETB</b> argadhu!",
        'your_link': "🔗 Liinkii kee:",
        'txn_ref': "ID Transaction:",
        'txn_pending': "⏳ Eegaa admin mirkaneessu.",
        'not_registered': "❌ Duraan galmaa'i!",
        'registered_phone': "📱 Bilbila galmaa'e:",
        'help_title': "📋 Giddu-gala Gargaarsa",
    }
}

def t(uid, key, **kwargs):
    users = load_users()
    user = users.get(str(uid), {})
    lang = user.get('lang', 'am')
    text = T.get(lang, T['am']).get(key, T['am'].get(key, key))
    if kwargs:
        try: return text.format(**kwargs)
        except: return text
    return text

# ==========================================
# STORAGE FUNCTIONS
# ==========================================
def load_users(): return load_json(USERS_FILE, {})
def save_users(u): save_json(USERS_FILE, u)
def load_txns(): return load_json(TXNS_FILE, {"withdrawals": [], "deposits": []})
def save_txns(t): save_json(TXNS_FILE, t)

def get_user(uid): return load_users().get(str(uid))
def save_user(uid, data):
    users = load_users()
    users[str(uid)] = data
    save_users(users)

def ensure_user(message):
    uid = str(message.from_user.id)
    user = get_user(uid)
    if not user:
        u = message.from_user
        full_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or f"Player {uid}"
        user = {
            "id": uid, "name": full_name,
            "username": u.username or "",
            "phone": "", "play_balance": 100.0, "win_balance": 0.0,
            "referral_code": uid, "referred_by": None,
            "lang": "am", "registered": False,
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        save_user(uid, user)
    return user

def gen_txn_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# ==========================================
# EMOJI ACTION MAP
# ==========================================
EMOJI_MAP = {
    '🎯': 'play', '💰': 'deposit', '💸': 'withdraw', '🏦': 'balance_btn',
    '👥': 'invite', '📜': 'history', '💬': 'support', '🔢': 'register',
    '🌐': 'language', 'ℹ️': 'help', '🏆': 'leaderboard',
}

def get_action(text):
    if not text: return None
    for emoji, action in EMOJI_MAP.items():
        if text.startswith(emoji): return action
    return None

# ==========================================
# KEYBOARDS
# ==========================================
def main_reply_keyboard(uid):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton(
        text=t(uid, 'play'),
        web_app=types.WebAppInfo(url=WEB_APP_URL)
    ))
    markup.add(types.KeyboardButton(t(uid, 'deposit')), types.KeyboardButton(t(uid, 'withdraw')))
    markup.add(types.KeyboardButton(t(uid, 'balance_btn')), types.KeyboardButton(t(uid, 'invite')))
    markup.add(types.KeyboardButton(t(uid, 'history')), types.KeyboardButton(t(uid, 'support')))
    markup.add(types.KeyboardButton(t(uid, 'register')), types.KeyboardButton(t(uid, 'language')))
    markup.add(types.KeyboardButton(t(uid, 'help')), types.KeyboardButton(t(uid, 'leaderboard')))
    return markup

def webapp_inline_keyboard(uid):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        text=t(uid, 'play'),
        web_app=types.WebAppInfo(url=WEB_APP_URL)
    ))
    return markup

def contact_button(uid):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton(text=t(uid, 'share_contact'), request_contact=True))
    return markup

def notify_admins(text, skip_id=None):
    for aid in ADMIN_IDS:
        if skip_id and str(aid) == str(skip_id):
            continue
        try:
            bot.send_message(aid, text, parse_mode='HTML')
        except Exception as e:
            print(f"Admin notify: {e}")

user_state = {}

def build_help_text(uid):
    return (
        f"{t(uid,'help_title')}\n\n"
        "<b>📋 Commands:</b>\n"
        "/start — Start\n/play — Play game\n/balance — Check balance\n"
        "/invite — Invite friends\n/help — Help\n\n"
        "<b>🎮 Main Buttons:</b>\n"
        f"{t(uid,'play')}\n{t(uid,'deposit')}\n{t(uid,'withdraw')}\n"
        f"{t(uid,'balance_btn')}\n{t(uid,'invite')}\n{t(uid,'history')}\n"
        f"{t(uid,'support')}\n{t(uid,'register')}\n{t(uid,'language')}\n"
        f"{t(uid,'help')}\n{t(uid,'leaderboard')}"
    )

# ==========================================
# /start
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = ensure_user(message)
    uid = str(message.from_user.id)
    args = message.text.split()
    if len(args) > 1:
        ref_code = args[1]
        if ref_code and ref_code != uid:
            users = load_users()
            if ref_code in users and not user.get('referred_by'):
                user['referred_by'] = ref_code
                referrer = users[ref_code]
                referrer['play_balance'] = referrer.get('play_balance', 0) + 30
                users[ref_code] = referrer
                save_users(users)
                user['play_balance'] = user.get('play_balance', 0) + 30
                save_user(uid, user)
                try:
                    bot.send_message(int(ref_code), "🎉 Friend joined via your link! +30 ETB")
                except: pass

    bot.send_message(
        message.chat.id,
        f"{t(uid,'welcome')}\n\n"
        f"👤 {t(uid,'name')}: <b>{user['name']}</b>\n"
        f"🆔 {t(uid,'id')}: <code>{user['id']}</code>\n"
        f"💰 {t(uid,'balance')}: <b>{user['play_balance']:.2f} ETB</b>\n\n"
        f"{t(uid,'choose_below')}",
        reply_markup=main_reply_keyboard(uid),
        parse_mode='HTML'
    )
    bot.send_message(
        message.chat.id,
        f"{t(uid,'play_below')}",
        reply_markup=webapp_inline_keyboard(uid),
        parse_mode='HTML'
    )

# ==========================================
# COMMANDS
# ==========================================
@bot.message_handler(commands=['play'])
def cmd_play(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    bot.send_message(message.chat.id, t(uid,'play_below'),
        reply_markup=webapp_inline_keyboard(uid), parse_mode='HTML')

@bot.message_handler(commands=['balance'])
def cmd_balance(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    bot.send_message(message.chat.id,
        f"🏦 <b>{t(uid,'your_balance')}</b>\n\n"
        f"{t(uid,'play_bal')}: <b>{u['play_balance']:.2f} ETB</b>\n"
        f"{t(uid,'win_bal')}: <b>{u['win_balance']:.2f} ETB</b>\n"
        f"{t(uid,'total')}: <b>{u['play_balance'] + u['win_balance']:.2f} ETB</b>",
        parse_mode='HTML')

@bot.message_handler(commands=['help'])
def cmd_help(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    bot.send_message(message.chat.id, build_help_text(uid), parse_mode='HTML')

@bot.message_handler(commands=['invite'])
def cmd_invite(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    try: bot_username = bot.get_me().username
    except: bot_username = "Ethiobongo_bot"
    link = f"https://t.me/{bot_username}?start={u['referral_code']}"
    bot.send_message(message.chat.id,
        f"{t(uid,'invite_msg')}\n\n{t(uid,'invite_bonus')}\n\n"
        f"{t(uid,'your_link')}\n<code>{link}</code>",
        parse_mode='HTML')

# ==========================================
# LANGUAGE
# ==========================================
@bot.message_handler(func=lambda m: get_action(m.text) == 'language')
def handle_language(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    markup.add(
        types.InlineKeyboardButton("🇪🇹 ትግርኛ", callback_data="lang_ti"),
        types.InlineKeyboardButton("🇪🇹 Afaan Oromoo", callback_data="lang_om")
    )
    bot.send_message(message.chat.id, t(uid,'pick_lang'),
        reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def cb_language(call):
    uid = str(call.from_user.id)
    lang = call.data.replace('lang_', '')
    users = load_users()
    u = users.get(uid)
    if u:
        u['lang'] = lang
        save_user(uid, u)
    bot.answer_callback_query(call.id, "✅")
    bot.send_message(call.message.chat.id, t(uid,'lang_changed'))
    bot.send_message(call.message.chat.id, t(uid,'choose_below'),
        reply_markup=main_reply_keyboard(uid))
    bot.send_message(call.message.chat.id, t(uid,'play_below'),
        reply_markup=webapp_inline_keyboard(uid), parse_mode='HTML')

# ==========================================
# REGISTER
# ==========================================
@bot.message_handler(func=lambda m: get_action(m.text) == 'register')
def handle_register(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    if u.get('registered'):
        bot.send_message(message.chat.id,
            f"{t(uid,'already_registered')}\n\n"
            f"👤 {u['name']}\n📱 {u.get('phone','N/A')}\n\n"
            f"{t(uid,'cannot_register_again')}",
            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
        return
    bot.send_message(message.chat.id,
        f"🔢 <b>{t(uid,'register')}</b>\n\n{t(uid,'share_contact_prompt')}",
        reply_markup=contact_button(uid), parse_mode='HTML')

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    if message.contact.user_id != message.from_user.id:
        bot.send_message(message.chat.id, "❌ Share your own contact only.",
            reply_markup=main_reply_keyboard(uid))
        return
    phone = message.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone

    # Withdrawal flow
    if user_state.get(uid) == 'withdraw_self':
        user_state.pop(uid, None)
        msg = bot.send_message(message.chat.id,
            f"✅ {phone}\n\n{t(uid,'send_amount', min=MIN_WITHDRAW)}",
            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
        bot.register_next_step_handler(msg, process_withdraw_amount_final, phone)
        return

    # Registration
    if u.get('registered'):
        bot.send_message(message.chat.id, t(uid,'already_registered'),
            reply_markup=main_reply_keyboard(uid))
        return
    u['phone'] = phone
    u['registered'] = True
    save_user(uid, u)
    bot.send_message(message.chat.id,
        f"{t(uid,'registered')}\n\n"
        f"👤 {u['name']}\n📱 {phone}\n"
        f"💰 {t(uid,'balance')}: <b>{u['play_balance']:.2f} ETB</b>",
        parse_mode='HTML', reply_markup=main_reply_keyboard(uid))

# ==========================================
# SMART DEPOSIT PARSER
# ==========================================
def parse_deposit_text(text):
    text_clean = (text or "").strip()
    if not text_clean:
        return None, None
    amount = None
    reference = None

    ref_patterns = [
        r'transaction\s+number\s+is\s+([A-Z0-9]{6,})',
        r'transaction\s+(?:id|no)\s*[:\-]?\s*([A-Z0-9]{6,})',
        r'txn\s*[:\-]?\s*([A-Z0-9]{6,})',
        r'reference\s*[:\-]?\s*([A-Z0-9]{6,})',
    ]
    for pat in ref_patterns:
        m = re.search(pat, text_clean, re.IGNORECASE)
        if m:
            reference = m.group(1).upper()
            break

    amt_patterns = [
        r'you\s+have\s+received\s+ETB\s+(\d+(?:[.,]\d+)?)',
        r'received\s+ETB\s+(\d+(?:[.,]\d+)?)',
        r'credited\s+with\s+(?:ETB|Birr)\s+(\d+(?:[.,]\d+)?)',
        r'has\s+been\s+credited\s+(?:with\s+)?(?:ETB|Birr)\s+(\d+(?:[.,]\d+)?)',
        r'(?:ETB|Birr)\s+(\d+(?:[.,]\d+)?)',
    ]
    for pat in amt_patterns:
        m = re.search(pat, text_clean, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(',', ''))
                if 10 <= val <= 100000:
                    amount = val
                    break
            except: pass

    if not amount:
        parts = text_clean.split()
        for p in reversed(parts[-5:]):
            try:
                val = float(p.replace(',', ''))
                if 10 <= val <= 100000:
                    amount = val
                    break
            except: pass

    if not reference:
        tokens = re.findall(r'[A-Z0-9]{8,}', text_clean.upper())
        tokens = [tk for tk in tokens if not tk.isdigit() and not tk.startswith('ETB')]
        if tokens:
            reference = tokens[0]

    return reference, amount

# ==========================================
# DEPOSIT
# ==========================================
@bot.message_handler(func=lambda m: get_action(m.text) == 'deposit')
def handle_deposit(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📲 Telebirr", callback_data="dep_telebirr"),
        types.InlineKeyboardButton("🏦 CBE", callback_data="dep_cbe")
    )
    bot.send_message(message.chat.id,
        f"💳 <b>{t(uid,'deposit_choose')}</b>",
        reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "dep_telebirr")
def cb_dep_telebirr(call):
    uid = str(call.from_user.id)
    bot.answer_callback_query(call.id)
    text = (
        f"📲 <b>Telebirr</b>\n\n"
        f"📞 <code>{TELEBIRR_NUMBER}</code>\n"
        f"👤 <b>{ACCOUNT_NAME}</b>\n\n"
        f"1️⃣ {t(uid,'txn_example')}\n"
        f"2️⃣ {t(uid,'send_txn')}"
    )
    bot.send_message(call.message.chat.id, text, parse_mode='HTML')
    msg = bot.send_message(call.message.chat.id,
        f"📝 <b>{t(uid,'send_txn')}</b>\n\n{t(uid,'txn_example')}",
        parse_mode='HTML')
    bot.register_next_step_handler(msg, process_deposit_reference, 'Telebirr')

@bot.callback_query_handler(func=lambda call: call.data == "dep_cbe")
def cb_dep_cbe(call):
    uid = str(call.from_user.id)
    bot.answer_callback_query(call.id)
    text = (
        f"🏦 <b>CBE</b>\n\n"
        f"🔢 <code>{CBE_NUMBER}</code>\n"
        f"👤 <b>{ACCOUNT_NAME}</b>\n\n"
        f"1️⃣ {t(uid,'txn_example')}\n"
        f"2️⃣ {t(uid,'send_txn')}"
    )
    bot.send_message(call.message.chat.id, text, parse_mode='HTML')
    msg = bot.send_message(call.message.chat.id,
        f"📝 <b>{t(uid,'send_txn')}</b>\n\n{t(uid,'txn_example')}",
        parse_mode='HTML')
    bot.register_next_step_handler(msg, process_deposit_reference, 'CBE')

def process_deposit_reference(message, method):
    uid = str(message.from_user.id)
    text = message.text or ""
    reference, amount = parse_deposit_text(text)

    if not amount or amount < MIN_DEPOSIT:
        bot.send_message(message.chat.id,
            f"❌ {t(uid,'invalid_amount')}\n\n{t(uid,'txn_example')}",
            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
        return

    if not reference:
        reference = gen_txn_id()

    # Duplicate check
    if reference and reference.upper() not in ('NUMBER', ''):
        txns_check = load_txns()
        ref_upper = reference.upper()
        existing = None
        for tt in txns_check.get('deposits', []) + txns_check.get('withdrawals', []):
            if tt.get('reference', '').upper() == ref_upper:
                existing = tt
                break
        if existing:
            status_icon = "✅" if existing['status'] == 'approved' else "❌" if existing['status'] == 'rejected' else "⏳"
            bot.send_message(message.chat.id,
                f"❌ <b>ይህ Transaction ID አስቀድሞ ተጠቅሟል!</b>\n\n"
                f"🆔 <code>{reference}</code>\n"
                f"{status_icon} ሁኔታ: <b>{existing['status']}</b>\n"
                f"💰 መጠን: <b>{existing['amount']:.2f} ETB</b>\n"
                f"📅 ቀን: {existing.get('created','')[:16]}\n\n"
                f"እባክዎ አዲስ የTransaction ቁጥር ይላኩ።",
                parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
            return

    u = ensure_user(message)
    txn_id = gen_txn_id()
    txns = load_txns()
    txn = {
        "id": txn_id, "type": "deposit",
        "user_id": u['id'], "user_name": u['name'],
        "amount": amount, "method": method,
        "reference": reference, "status": "pending",
        "created": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    txns['deposits'].append(txn)
    save_txns(txns)

    amount_str = f"{amount:.2f}"
    bot.send_message(message.chat.id,
        f"{t(uid,'deposit_sent')}\n\n"
        f"🆔 <code>{txn_id}</code>\n"
        f"💳 {method}\n"
        f"💰 <b>{amount_str} ETB</b>\n"
        f"{t(uid,'txn_ref')} <code>{reference}</code>\n\n"
        f"{t(uid,'txn_pending')}",
        parse_mode='HTML', reply_markup=main_reply_keyboard(uid))

    notify_admins(
        f"💰 <b>New Deposit Request</b>\n\n"
        f"👤 {u['name']} (<code>{u['id']}</code>)\n"
        f"💳 {method}\n"
        f"💰 {amount_str} ETB\n"
        f"🔢 <code>{reference}</code>\n"
        f"🆔 <code>{txn_id}</code>\n\n"
        f"📊 <a href='{WEB_APP_URL}/admin.html'>Open Admin Panel</a>",
        skip_id=u['id']
    )

# ==========================================
# WITHDRAW
# ==========================================
@bot.message_handler(func=lambda m: get_action(m.text) == 'withdraw')
def handle_withdraw(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    if not u.get('registered'):
        bot.send_message(message.chat.id, t(uid,'not_registered'),
            reply_markup=main_reply_keyboard(uid))
        return
    if u['win_balance'] < MIN_WITHDRAW:
        bot.send_message(message.chat.id,
            f"{t(uid,'insufficient')}\n\n"
            f"{t(uid,'win_bal')}: <b>{u['win_balance']:.2f} ETB</b>\n"
            f"{t(uid,'min_withdraw', amt=MIN_WITHDRAW)}",
            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(t(uid,'to_self'), callback_data="wd_self"),
        types.InlineKeyboardButton(t(uid,'to_other'), callback_data="wd_other")
    )
    bot.send_message(message.chat.id,
        f"💸 <b>{t(uid,'withdraw_choose')}</b>\n\n"
        f"{t(uid,'win_bal')}: <b>{u['win_balance']:.2f} ETB</b>\n"
        f"{t(uid,'min_withdraw', amt=MIN_WITHDRAW)}",
        reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "wd_self")
def cb_wd_self(call):
    uid = str(call.from_user.id)
    bot.answer_callback_query(call.id)
    u = get_user(uid)
    if u and u.get('phone'):
        bot.send_message(call.message.chat.id,
            f"👤 <b>{t(uid,'to_self')}</b>\n\n"
            f"{t(uid,'registered_phone')} <b>{u['phone']}</b>\n\n"
            f"{t(uid,'send_amount', min=MIN_WITHDRAW)}",
            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
        user_state[uid] = 'withdraw_self_amount'
        bot.register_next_step_handler_by_chat_id(
            call.message.chat.id, process_withdraw_amount_final, u['phone'])
    else:
        bot.send_message(call.message.chat.id,
            t(uid,'share_contact_prompt'),
            reply_markup=contact_button(uid), parse_mode='HTML')
        user_state[uid] = 'withdraw_self'

@bot.callback_query_handler(func=lambda call: call.data == "wd_other")
def cb_wd_other(call):
    uid = str(call.from_user.id)
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id,
        f"👥 <b>{t(uid,'to_other')}</b>\n\n{t(uid,'send_phone')}",
        parse_mode='HTML')
    bot.register_next_step_handler(msg, process_wd_other_phone)

def process_wd_other_phone(message):
    uid = str(message.from_user.id)
    phone = (message.text or "").strip()
    if not phone.replace('+', '').isdigit() or len(phone) < 9:
        bot.send_message(message.chat.id, t(uid,'invalid_phone'),
            reply_markup=main_reply_keyboard(uid))
        return
    bot.send_message(message.chat.id,
        f"✅ <b>{phone}</b>\n\n{t(uid,'send_amount', min=MIN_WITHDRAW)}",
        parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
    bot.register_next_step_handler(message, process_withdraw_amount_final, phone)

def process_withdraw_amount_final(message, phone):
    uid = str(message.from_user.id)
    try:
        amount = float((message.text or "").strip())
    except:
        bot.send_message(message.chat.id, t(uid,'invalid_amount'),
            reply_markup=main_reply_keyboard(uid))
        return
    u = ensure_user(message)
    if amount < MIN_WITHDRAW:
        bot.send_message(message.chat.id,
            f"{t(uid,'insufficient')}\n\n{t(uid,'min_withdraw', amt=MIN_WITHDRAW)}",
            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
        return
    if amount > u['win_balance']:
        bot.send_message(message.chat.id,
            f"{t(uid,'insufficient')}\n\n"
            f"{t(uid,'win_bal')}: <b>{u['win_balance']:.2f} ETB</b>\n"
            f"Requested: <b>{amount:.2f} ETB</b>",
            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
        return

    u['win_balance'] -= amount
    save_user(uid, u)

    txn_id = gen_txn_id()
    txns = load_txns()
    txn = {
        "id": txn_id, "type": "withdrawal",
        "user_id": u['id'], "user_name": u['name'],
        "amount": amount, "phone": phone,
        "status": "pending",
        "created": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    txns['withdrawals'].append(txn)
    save_txns(txns)

    amount_str = f"{amount:.2f}"
    balance_str = f"{u['win_balance']:.2f}"
    bot.send_message(message.chat.id,
        f"{t(uid,'wd_approved_req', amt=amount_str)}\n\n"
        f"🆔 <code>{txn_id}</code>\n"
        f"📱 <b>{phone}</b>\n"
        f"💰 <b>{amount_str} ETB</b>\n"
        f"🏆 {t(uid,'win_bal')}: <b>{balance_str} ETB</b>\n\n"
        f"{t(uid,'txn_pending')}",
        parse_mode='HTML', reply_markup=main_reply_keyboard(uid))

    notify_admins(
        f"💸 <b>New Withdrawal Request</b>\n\n"
        f"👤 {u['name']} (<code>{u['id']}</code>)\n"
        f"💰 {amount_str} ETB\n"
        f"📱 {phone}\n"
        f"🆔 <code>{txn_id}</code>\n\n"
        f"📊 <a href='{WEB_APP_URL}/admin.html'>Open Admin Panel</a>",
        skip_id=u['id']
    )

# ==========================================
# OTHER BUTTONS
# ==========================================
@bot.message_handler(func=lambda m: get_action(m.text) == 'balance_btn')
def h_balance(message): cmd_balance(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'invite')
def h_invite(message): cmd_invite(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'history')
def h_history(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    txns = load_txns()
    deps = [tt for tt in txns['deposits'] if tt['user_id'] == uid][-5:]
    wds = [tt for tt in txns['withdrawals'] if tt['user_id'] == uid][-5:]
    text = f"📜 <b>{t(uid,'your_history', name=u['name'])}</b>\n\n"
    if deps:
        text += f"<b>{t(uid,'deposits')}</b>\n"
        for tt in reversed(deps):
            ic = "✅" if tt['status'] == 'approved' else "❌" if tt['status'] == 'rejected' else "⏳"
            text += f"{ic} {tt['amount']:.2f} ETB ({tt['method']})\n"
        text += "\n"
    if wds:
        text += f"<b>{t(uid,'withdrawals')}</b>\n"
        for tt in reversed(wds):
            ic = "✅" if tt['status'] == 'approved' else "❌" if tt['status'] == 'rejected' else "⏳"
            text += f"{ic} {tt['amount']:.2f} ETB\n"
        text += "\n"
    if not deps and not wds:
        text += t(uid,'no_txn')
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: get_action(m.text) == 'support')
def h_support(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"📞 @{SUPPORT_USERNAME}", url=f"https://t.me/{SUPPORT_USERNAME}"))
    bot.send_message(message.chat.id,
        f"💬 <b>{t(uid,'support_msg')}</b>\n\n📞 @{SUPPORT_USERNAME}\n⏰ 24/7",
        reply_markup=markup, parse_mode='HTML')

@bot.message_handler(func=lambda m: get_action(m.text) == 'help')
def h_help(message): cmd_help(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'leaderboard')
def h_leaderboard(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    users = load_users()
    sorted_u = sorted(users.values(), key=lambda u: u.get('win_balance', 0), reverse=True)[:5]
    text = f"<b>{t(uid,'leaderboard_title')}</b>\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, uu in enumerate(sorted_u):
        text += f"{medals[i]} <b>{uu.get('name','?')[:20]}</b> — {uu.get('win_balance',0):.2f} ETB\n"
    if not sorted_u:
        text += t(uid,'no_winners')
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: True)
def fallback(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    bot.send_message(message.chat.id, t(uid,'unknown'))

# ==========================================
# TXN NOTIFIER (JSON)
# ==========================================
def notify_txn_users():
    notified = set()
    try:
        txns = load_json(TXNS_FILE, {"deposits": [], "withdrawals": []})
        for t in txns.get('deposits', []) + txns.get('withdrawals', []):
            if t.get('status') in ('approved', 'rejected'):
                notified.add(t['id'])
    except Exception as e:
        print(f"Preload error: {e}")
    print(f"🔔 Txn notifier started (skipped {len(notified)} old)")
    while True:
        try:
            time.sleep(5)
            txns = load_json(TXNS_FILE, {"deposits": [], "withdrawals": []})
            all_txns = txns.get('deposits', []) + txns.get('withdrawals', [])
            for t in all_txns:
                tid = t.get('id')
                if not tid or tid in notified: continue
                status = t.get('status')
                if status not in ('approved', 'rejected'): continue
                uid = str(t.get('user_id', ''))
                amount = t.get('amount', 0)
                ttype = t.get('type')
                if not uid:
                    notified.add(tid); continue
                try:
                    amount_str = f"{amount:.2f}"
                    if ttype == 'deposit' and status == 'approved':
                        user = get_user(uid)
                        bal = f"{user.get('play_balance', 0):.2f}" if user else "0.00"
                        bot.send_message(int(uid),
                            f"✅ <b>ገቢ ያደረጉት {amount_str} ETB ወደ ዋሌትዎ ተደምሯል</b>\n\n"
                            f"💰 አዲስ ባላንስ: <b>{bal} ETB</b>\n\n"
                            f"🍀 <b>መልካም ዕድል!</b>\n\n"
                            f"👇 ጨዋታውን ለመጀመር እዚህ ይጫኑ:",
                            parse_mode='HTML', reply_markup=webapp_inline_keyboard(uid))
                    elif ttype == 'deposit' and status == 'rejected':
                        bot.send_message(int(uid),
                            f"❌ <b>የገቢ ጥያቄዎ ተከልክሏል</b>\n\n"
                            f"💰 መጠን: <b>{amount_str} ETB</b>\n\n"
                            f"ለተጨማሪ መረጃ @{SUPPORT_USERNAME} ያግኙ።",
                            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
                    elif ttype == 'withdrawal' and status == 'approved':
                        bot.send_message(int(uid),
                            f"✅ <b>ወጭዎ በተሳካ ሁኔታ ወደ አካውንትዎ ገብቷል!</b>\n\n"
                            f"💰 መጠን: <b>{amount_str} ETB</b>\n"
                            f"📱 ስልክ: <b>{t.get('phone', 'N/A')}</b>\n\n"
                            f"🍀 <b>መልካም ዕድል!</b>",
                            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
                    elif ttype == 'withdrawal' and status == 'rejected':
                        user = get_user(uid)
                        bal = f"{user.get('win_balance', 0):.2f}" if user else "0.00"
                        bot.send_message(int(uid),
                            f"❌ <b>የወጭ ጥያቄዎ ተከልክሏል</b>\n\n"
                            f"💰 <b>{amount_str} ETB</b> ወደ Win Balance ተመልሷል።\n"
                            f"🏆 ቀሪ: <b>{bal} ETB</b>",
                            parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
                    notified.add(tid)
                except Exception as e:
                    print(f"Notify failed {tid}: {e}")
                    notified.add(tid)
        except Exception as e:
            print(f"Txn poll error: {e}")

# ==========================================
# BROADCAST SENDER (JSON)
# ==========================================
def broadcast_sender():
    sent = set()
    print("📢 Broadcast sender started")
    while True:
        try:
            time.sleep(3)
            data = load_json(BROADCASTS_FILE, {"pending": []})
            pending = data.get('pending', [])
            for bc in pending:
                bc_id = bc.get('id')
                if not bc_id or bc_id in sent: continue
                message = bc.get('message', '')
                if not message:
                    sent.add(bc_id); continue
                users = load_users()
                sent_count = 0
                for uid in users.keys():
                    try:
                        bot.send_message(int(uid),
                            f"📢 <b>ማስታወቂያ</b>\n\n{message}",
                            parse_mode='HTML')
                        sent_count += 1
                    except: pass
                print(f"📢 Broadcast sent to {sent_count} users")
                sent.add(bc_id)
        except Exception as e:
            print(f"Broadcast poll error: {e}")

# ==========================================
# FLASK WEBHOOK
# ==========================================
flask_app = Flask(__name__)
@flask_app.route('/notify', methods=['POST'])
def notify_user():
    return jsonify({'ok': True})
def run_webhook():
    flask_app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)

# ==========================================
# RUN
# ==========================================
if __name__ == '__main__':
    print("🤖 AbisinyaBingo Bot started...")
    print(f"🔗 Web App URL: {WEB_APP_URL}")
    print(f"👑 Admins: {ADMIN_IDS}")

    threading.Thread(target=notify_txn_users, daemon=True).start()
    threading.Thread(target=broadcast_sender, daemon=True).start()
    threading.Thread(target=run_webhook, daemon=True).start()

    print("✅ All background services started")

    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(5)
