import telebot, os, time, random, string, re, threading, requests
from telebot import types
from dotenv import load_dotenv
from datetime import datetime
from pymongo import MongoClient
import dns.resolver

# ==========================================
# DNS & ENV SETUP
# ==========================================
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8', '1.1.1.1']
dns.resolver.default_resolver.lifetime = 10.0

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://example.com')
MONGODB_URI = os.getenv('MONGODB_URI')
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:3000')

ADMIN_IDS = [5925033073]
MIN_WITHDRAW = 100
MIN_DEPOSIT = 10
SUPPORT_USERNAME = "Tazikes"

if not BOT_TOKEN or not MONGODB_URI:
    print("❌ Missing env")
    exit()

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# ==========================================
# MONGODB SETUP
# ==========================================
try:
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
    db = mongo_client.get_database('abisinya')
    users_col = db['users']
    txns_col = db['transactions']
    settings_col = db['settings']
    print("✅ MongoDB connected (Bot)")
except Exception as e:
    print(f"❌ DB error: {e}")
    exit()

# ==========================================
# CACHES & HELPERS
# ==========================================
_user_cache = {}
_user_cache_lock = threading.Lock()

def get_user(uid, bypass_cache=False):
    uid = str(uid)
    now = time.time()
    if not bypass_cache:
        with _user_cache_lock:
            cached = _user_cache.get(uid)
            if cached and (now - cached['ts']) < 30:
                return cached['data']
    user = users_col.find_one({"id": uid})
    with _user_cache_lock:
        _user_cache[uid] = {'data': user, 'ts': now}
    return user

def invalidate_user_cache(uid):
    with _user_cache_lock:
        _user_cache.pop(str(uid), None)

def get_payment_settings():
    s = settings_col.find_one({"key": "payment_accounts"})
    if not s:
        return {"telebirr_number": "0968940123", "telebirr_name": "tazebew", "cbe_number": "1000390803005", "cbe_name": "tazebew"}
    return s

def ensure_user(message):
    uid = str(message.from_user.id)
    u = message.from_user
    full_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or f"Player {uid}"

    user = users_col.find_one_and_update(
        {"id": uid},
        {"$setOnInsert": {
            "id": uid, "name": full_name, "username": u.username or "",
            "phone": "", "play_balance": 20.0, "win_balance": 0.0,
            "total_games": 0, "total_wins": 0, "referral_code": uid,
            "referred_by": None, "pending_referrer": None, "lang": "am",
            "registered": False, "registered_at": datetime.utcnow().isoformat()
        }},
        upsert=True, return_document=True
    )
    with _user_cache_lock:
        _user_cache[uid] = {'data': user, 'ts': time.time()}
    return user

def gen_txn_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# ==========================================
# TRANSLATIONS (4 Languages)
# ==========================================
T = {
    'am': {'welcome': "🎉 እንኳን ወደ Abisinya Bingo በደህና መጡ!", 'name': "ስም", 'id': "መለያ", 'balance': "ባላንስ", 'choose_below': "👇 ከታች ያለውን አማራጭ ይምረጡ", 'play': "🎯 Abisinya Bingo ይጫወቱ", 'deposit': "💰 ገንዘብ ማስገባት", 'withdraw': "💸 ገንዘብ ማውጣት", 'balance_btn': "🏦 ባላንስ ማየት", 'invite': "👥 ጓደኛ መጋበዝ", 'history': "📜 ታሪክ", 'support': "💬 ድጋፍ", 'register': "🔢 መመዝገብ", 'language': "🌐 ቋንቋ", 'help': "ℹ️ እርዳታ", 'leaderboard': "🏆 ደረጃ", 'your_balance': "የእርስዎ ባላንስ", 'play_bal': "🎮 Play", 'win_bal': "🏆 Win", 'total': "💰 ጠቅላላ", 'share_contact': "📱 ስልክ ቁጥር አጋራ", 'share_contact_prompt': "እባክዎ መጀመሪያ የስልክ ቁጥርዎን ያጋሩ።", 'registered': "✅ በተሳካ ሁኔታ ተመዝግበዋል!", 'already_registered': "✅ አስቀድመው ተመዝግበዋል!", 'deposit_choose': "💳 የክፍያ ዘዴ ይምረጡ፦", 'send_txn': "📝 የTransaction/SMS ጽሑፍ ይላኩ", 'txn_example': "ለምሳሌ: <code>TB123456789 500</code>", 'deposit_sent': "✅ የገቢ ጥያቄ ተልኳል!", 'play_below': "👇 ጨዋታውን ለመጀመር ከታች ያለውን ሜኑ ይጫኑ:", 'withdraw_choose': "💸 የወጭ ዘዴ ይምረጡ:", 'to_self': "👤 ወደ ራስዎ", 'to_other': "👥 ወደ ሌላ ቁጥር", 'insufficient': "❌ ቀሪ ሂሳብ በቂ አይደለም", 'min_withdraw': "ዝቅተኛው የወጭ መጠን: {amt} ETB", 'wd_approved_req': "✅ የወጭ ጥያቄዎ {amt} ብር ተልኳል", 'send_amount': "💰 የሚወጣውን መጠን ይላኩ (ቢያንስ {min} ETB):", 'send_phone': "📱 የቴሌብር ቁጥር ይላኩ:", 'send_cbe_acc': "🏦 የCBE አካውንት ቁጥርዎን ያስገቡ:", 'invalid_amount': "❌ ትክክለኛ ቁጥር ያስገቡ።", 'invalid_phone': "❌ ትክክለኛ ቁጥር ያስገቡ።", 'unknown': "❓ ያልተለየ ትዕዛዝ።\n/start ይጫኑ።", 'pick_lang': "🌐 ቋንቋ ይምረጡ", 'lang_changed': "🇪🇹 ቋንቋ ወደ አማርኛ ተቀይሯል።", 'your_history': "የ{name} ታሪክ", 'deposits': "💰 ገቢዎች:", 'withdrawals': "💸 ወጮች:", 'no_txn': "📭 እስካሁን ግብይት የለም።", 'leaderboard_title': "🏆 ከፍተኛ አሸናፊዎች", 'no_winners': "📭 እስካሁን ማንም አልተመዘገበም።", 'support_msg': "ለእርዳታ ያግኙን", 'invite_msg': "👥 ጓደኞችዎን ይጋብዙ!", 'invite_bonus': "✨ ለእያንዳንዱ ጓደኛ <b>30 ETB</b> ያግኙ!", 'your_link': "🔗 የእርስዎ ሊንክ:", 'txn_ref': "የTransaction ቁጥር:", 'txn_pending': "⏳ Admin እስኪያጸድቅ ይጠብቁ።", 'not_registered': "❌ መጀመሪያ ማስመዝገብ ያስፈልጋል!", 'registered_phone': "📱 የተመዘገበ ስልክ:", 'help_title': "📋 የእርዳታ ማዕከል", 'help_list': "/start - ቦቱን ጀምር\n/play - ቢንጎ ተጫወት\n/balance - ባላንስ ተመልከት\n/deposit - ገንዘብ አስገባ\n/withdraw - ገንዘብ አውጣ\n/register - ስልክ አስመዝግብ\n/invite - ጓደኛ ጋብዝ\n/history - ታሪክ"},
    'en': {'welcome': "🎉 Welcome to Abisinya Bingo!", 'name': "Name", 'id': "ID", 'balance': "Balance", 'choose_below': "👇 Choose an option below", 'play': "🎯 Play Bingo", 'deposit': "💰 Deposit", 'withdraw': "💸 Withdraw", 'balance_btn': "🏦 Balance", 'invite': "👥 Invite", 'history': "📜 History", 'support': "💬 Support", 'register': "🔢 Register", 'language': "🌐 Language", 'help': "ℹ️ Help", 'leaderboard': "🏆 Rank", 'your_balance': "Balance", 'play_bal': "🎮 Play", 'win_bal': "🏆 Win", 'total': "💰 Total", 'share_contact': "📱 Share Contact", 'share_contact_prompt': "Please share your contact first.", 'registered': "✅ Registered!", 'already_registered': "✅ Already registered!", 'deposit_choose': "💳 Choose method:", 'send_txn': "📝 Send TXN text", 'txn_example': "Ex: <code>TB123456789 500</code>", 'deposit_sent': "✅ Deposit sent!", 'play_below': "👇 Tap the Menu below:", 'withdraw_choose': "💸 Withdraw method:", 'to_self': "👤 Self", 'to_other': "👥 Other", 'insufficient': "❌ Insufficient", 'min_withdraw': "Min: {amt} ETB", 'wd_approved_req': "✅ Withdrawal {amt} birr approved", 'send_amount': "💰 Amount (min {min} ETB):", 'send_phone': "📱 Telebirr phone:", 'send_cbe_acc': "🏦 Enter your CBE account number:", 'invalid_amount': "❌ Invalid number.", 'invalid_phone': "❌ Invalid phone.", 'unknown': "❓ Unknown.\n/start", 'pick_lang': "🌐 Choose Language", 'lang_changed': "🇬🇧 English set.", 'your_history': "{name}'s History", 'deposits': "💰 Deposits:", 'withdrawals': "💸 Withdrawals:", 'no_txn': "📭 No transactions.", 'leaderboard_title': "🏆 Top Winners", 'no_winners': "📭 No one yet.", 'support_msg': "Contact us", 'invite_msg': "👥 Invite!", 'invite_bonus': "✨ Get <b>30 ETB</b>!", 'your_link': "🔗 Link:", 'txn_ref': "TXN ID:", 'txn_pending': "⏳ Pending...", 'not_registered': "❌ Register first!", 'registered_phone': "📱 Phone:", 'help_title': "📋 Help Center", 'help_list': "/start - Start\n/play - Play Bingo\n/balance - Balance\n/deposit - Deposit\n/withdraw - Withdraw\n/register - Register\n/invite - Invite\n/history - History"},
    'ti': {'welcome': "🎉 እንቋዕ ናብ Abisinya Bingo ብደሓን መጻእኩም!", 'name': "ስም", 'id': "መለለዪ", 'balance': "ባላንስ", 'choose_below': "👇 ካብ ትሕቲ ዘሎ ኣማራጺ ምረጹ", 'play': "🎯 Abisinya Bingo ተጻወት", 'deposit': "💰 ገንዘብ ኣእቱ", 'withdraw': "💸 ገንዘብ ኣውጽእ", 'balance_btn': "🏦 ባላንስ ርአ", 'invite': "👥 ኣሕዋት ዓድም", 'history': "📜 ታሪኽ", 'support': "💬 ደገፍ", 'register': "🔢 ተመዝገብ", 'language': "🌐 ቋንቋ", 'help': "ℹ️ ሓገዝ", 'leaderboard': "🏆 ደረጃ", 'your_balance': "ባላንስካ", 'play_bal': "🎮 Play", 'win_bal': "🏆 Win", 'total': "💰 ጠቕላላ", 'share_contact': "📱 ርክብ ኣካፍል", 'share_contact_prompt': "ቅድም ርክብካ ኣካፍል።", 'registered': "✅ ብዓወት ተመዝጊብካ!", 'already_registered': "✅ ቀድሚሁ ተመዝጊብካ!", 'deposit_choose': "💳 ኣገባብ ክፍሊት ምረጽ:", 'send_txn': "📝 ጽሑፍ Transaction/SMS ስደድ", 'txn_example': "ኣብነት: <code>TB123456789 500</code>", 'deposit_sent': "✅ ሕቶ ኣታዊ ተላኢኹ!", 'play_below': "👇 ነቲ ሜኑ ቁልፊ ጠውቕ:", 'withdraw_choose': "💸 ኣገባብ ወጻኢ ምረጽ:", 'to_self': "👤 ናብ ርእስኻ", 'to_other': "👥 ናብ ካልእ ቁጽሪ", 'insufficient': "❌ ቀሪ ሂሳብ አይእከለን", 'min_withdraw': "ትሕቲ ወጻኢ: {amt} ETB", 'wd_approved_req': "✅ ሕቶ ወጻኢኻ {amt} birr ተቐቢሉ", 'send_amount': "💰 ወጻኢ መጠን ስደድ (min {min} ETB):", 'send_phone': "📱 ቁጽሪ Telebirr ስደድ:", 'send_cbe_acc': "🏦 ቁጽሪ ኣካውንት CBE ኣእቱ:", 'invalid_amount': "❌ ቅኑዕ ቁጽሪ ኣእቱ።", 'invalid_phone': "❌ ቅኑዕ ቁጽሪ ኣእቱ።", 'unknown': "❓ ዘይተፈልጠ ትእዛዝ።\n/start ጠውቕ።", 'pick_lang': "🌐 ቋንቋ ምረጽ", 'lang_changed': "🇪🇹 ቋንቋ ናብ ትግርኛ ተቐይሩ።", 'your_history': "ታሪኽ {name}", 'deposits': "💰 ኣታዊታት:", 'withdrawals': "💸 ወጻኢታት:", 'no_txn': "📭 ክሳብ ሕጂ ግብይት የለን።", 'leaderboard_title': "🏆 ላዕለዎት ተዓወትቲ", 'no_winners': "📭 ክሳብ ሕጂ ዝተመዝገበ የለን።", 'support_msg': "ንሓገዝ ርኸቡና", 'invite_msg': "👥 ኣሕዋትካ ዓድም!", 'invite_bonus': "✨ ንነፍሲ ወከፍ ዓርኪ <b>30 ETB</b> ርኸብ!", 'your_link': "🔗 ሊንክካ:", 'txn_ref': "ቁጽሪ Transaction:", 'txn_pending': "⏳ ንፈቓድ admin ተጸበ።", 'not_registered': "❌ ቅድም ተመዝገብ!", 'registered_phone': "📱 ዝተመዝገበ ቁጽሪ:", 'help_title': "📋 ማእከል ሓገዝ", 'help_list': "/start - ጀምር\n/play - ተጻወት\n/balance - ባላንስ\n/deposit - ኣእቱ\n/withdraw - ኣውጽእ\n/register - ተመዝገብ\n/invite - ዓድም\n/history - ታሪኽ"},
    'om': {'welcome': "🎉 Baga gara Abisinya Bingo nagaan dhuftan!", 'name': "Maqaa", 'id': "Eenyummaa", 'balance': "Baalaansii", 'choose_below': "👇 Filannoo gadii keessaa filadhu", 'play': "🎯 Abisinya Bingo Taphadhu", 'deposit': "💰 Maallaqa Galchi", 'withdraw': "💸 Maallaqa Baas", 'balance_btn': "🏦 Baalaansii Ilaali", 'invite': "👥 Hiriyoota Affeeri", 'history': "📜 Seenaa", 'support': "💬 Deeggarsa", 'register': "🔢 Galmaa'i", 'language': "🌐 Afaan", 'help': "ℹ️ Gargaarsa", 'leaderboard': "🏆 Sadarkaa", 'your_balance': "Baalaansii Kee", 'play_bal': "🎮 Play", 'win_bal': "🏆 Win", 'total': "💰 Waliigala", 'share_contact': "📱 Quunnamtii Qoodi", 'share_contact_prompt': "Maaloo dura quunnamtii kee qoodi.", 'registered': "✅ Milkaa'inaan galmaa'te!", 'already_registered': "✅ Duraan galmaa'teerta!", 'deposit_choose': "💳 Mala kaffaltii filadhu:", 'send_txn': "📝 Barruu Transaction/SMS ergi", 'txn_example': "Fkn: <code>TB123456789 500</code>", 'deposit_sent': "✅ Gaaffiin galii ergame!", 'play_below': "👇 Menu button tuqi:", 'withdraw_choose': "💸 Mala baasii filadhu:", 'to_self': "👤 Ofiif", 'to_other': "👥 Lakkoofsa Biroof", 'insufficient': "❌ Baalaansii gahaa miti", 'min_withdraw': "Baasii xiqqaan: {amt} ETB", 'wd_approved_req': "✅ Gaaffiin baasii kee {amt} birr fudhatame", 'send_amount': "💰 Hanga baasii ergi (min {min} ETB):", 'send_phone': "📱 Lakkoofsa Telebirr ergi:", 'send_cbe_acc': "🏦 Lakkoofsa herrega CBE galchi:", 'invalid_amount': "❌ Lakkoofsa sirrii galchi.", 'invalid_phone': "❌ Lakkoofsa sirrii galchi.", 'unknown': "❓ Ajaja hin beekamne.\n/start tuqi.", 'pick_lang': "🌐 Afaan filadhu", 'lang_changed': "🇪🇹 Afaan gara Afaan Oromoo jijjiirame.", 'your_history': "Seenaa {name}", 'deposits': "💰 Galiwwan:", 'withdrawals': "💸 Baasiiwwan:", 'no_txn': "📭 Ammaatti daldala hin jiru.", 'leaderboard_title': "🏆 Mo'attoota Olii", 'no_winners': "📭 Ammaatti namni hin galmaa'ne.", 'support_msg': "Gargaarsaaf nu quunnamaa", 'invite_msg': "👥 Hiriyoota kee affeeri!", 'invite_bonus': "✨ Hiriyoota tokkoon tokkoon <b>30 ETB</b> argadhu!", 'your_link': "🔗 Liinkii kee:", 'txn_ref': "ID Transaction:", 'txn_pending': "⏳ Eegaa admin mirkaneessu.", 'not_registered': "❌ Duraan galmaa'i!", 'registered_phone': "📱 Bilbila galmaa'e:", 'help_title': "📋 Giddu-gala Gargaarsa", 'help_list': "/start - Jalqabi\n/play - Taphadhu\n/balance - Baalaansii\n/deposit - Galchi\n/withdraw - Baasi\n/register - Galmaa'i\n/invite - Affeeri\n/history - Seenaa"}
}

def t(uid, key, **kwargs):
    user = get_user(uid) or {}
    lang = user.get('lang', 'am') or 'am'
    text = T.get(lang, T['am']).get(key, T['am'].get(key, key))
    if kwargs:
        try: return text.format(**kwargs)
        except (KeyError, ValueError): return text
    return text

def get_action(text):
    if not text: return None
    text = text.lower()
    if 'bingo' in text or 'ቢንጎ' in text or 'taphadhu' in text or 'ጫወት' in text or 'ጨዋታ' in text: return 'play'
    if 'deposit' in text or 'ማስገባት' in text or 'galchi' in text or 'ኣእቱ' in text: return 'deposit'
    if 'withdraw' in text or 'ማውጣት' in text or 'baas' in text or 'አውጽእ' in text or 'ኣውጽእ' in text: return 'withdraw'
    if 'balance' in text or 'ባላንስ' in text or 'baalaansii' in text: return 'balance_btn'
    if 'invite' in text or 'መጋበዝ' in text or 'affeeri' in text or 'ዓድም' in text: return 'invite'
    if 'history' in text or 'ታሪክ' in text or 'seenaa' in text or 'ታሪኽ' in text: return 'history'
    if 'support' in text or 'ድጋፍ' in text or 'deeggarsa' in text or 'ደገፍ' in text: return 'support'
    if 'register' in text or 'መመዝገብ' in text or 'galmaa' in text or 'ተመዝገብ' in text: return 'register'
    if 'language' in text or 'ቋንቋ' in text or 'afaan' in text: return 'language'
    if 'help' in text or 'እርዳታ' in text or 'gargaarsa' in text or 'ሓገዝ' in text: return 'help'
    if 'rank' in text or 'ደረጃ' in text or 'sadarkaa' in text: return 'leaderboard'
    return None

# ==========================================
# KEYBOARDS
# ==========================================
def webapp_inline_keyboard(uid):
    markup = types.InlineKeyboardMarkup()
    safe_url = WEB_APP_URL if WEB_APP_URL.startswith("https://") else "https://example.com"
    markup.add(types.InlineKeyboardButton(text="🎮 Play Bingo", web_app=types.WebAppInfo(url=safe_url)))
    return markup

def main_reply_keyboard(uid):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton(text="🎯 Abisinya Bingo"))
    markup.add(types.KeyboardButton(t(uid, 'deposit')), types.KeyboardButton(t(uid, 'withdraw')))
    markup.add(types.KeyboardButton(t(uid, 'balance_btn')), types.KeyboardButton(t(uid, 'invite')))
    markup.add(types.KeyboardButton(t(uid, 'history')), types.KeyboardButton(t(uid, 'support')))
    markup.add(types.KeyboardButton(t(uid, 'register')), types.KeyboardButton(t(uid, 'language')))
    markup.add(types.KeyboardButton(t(uid, 'help')), types.KeyboardButton(t(uid, 'leaderboard')))
    return markup

def contact_button(uid):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton(text=t(uid, 'share_contact'), request_contact=True))
    return markup

def notify_admins(text, skip_id=None):
    def _send():
        for aid in ADMIN_IDS:
            if skip_id and str(aid) == str(skip_id): continue
            try: bot.send_message(aid, text, parse_mode='HTML')
            except Exception: pass
    threading.Thread(target=_send, daemon=True).start()

def safe_answer_callback(call_id, text=None):
    try: bot.answer_callback_query(call_id, text or "")
    except Exception: pass

# ==========================================
# START, LANGUAGE & PLAY
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = ensure_user(message)
    uid = str(message.from_user.id)
    
    # Referral Logic
    args = message.text.split()
    if len(args) > 1 and not user.get('referred_by'):
        ref_code = args[1].strip()
        if ref_code != uid and users_col.find_one({"id": ref_code}):
            users_col.update_one({"id": uid}, {"$set": {"pending_referrer": ref_code}})
            invalidate_user_cache(uid)

    if not user.get('registered'):
        return bot.send_message(message.chat.id, f"👋 <b>{t(uid, 'welcome')}</b>\n\n{t(uid, 'share_contact_prompt')}", reply_markup=contact_button(uid), parse_mode='HTML')

    bot.send_message(message.chat.id, f"🎉 {t(uid, 'welcome')}\n\n{t(uid, 'choose_below')}", reply_markup=main_reply_keyboard(uid), parse_mode='HTML')

@bot.message_handler(commands=['language'])
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
    bot.send_message(message.chat.id, t(uid, 'pick_lang'), reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def cb_language(call):
    uid = str(call.from_user.id)
    lang = call.data.replace('lang_', '')
    if lang not in ['am', 'en', 'ti', 'om']: return safe_answer_callback(call.id, "❌")
    safe_answer_callback(call.id, "✅")
    users_col.update_one({"id": uid}, {"$set": {"lang": lang}}, upsert=True)
    invalidate_user_cache(uid)
    bot.send_message(call.message.chat.id, t(uid, 'lang_changed'))
    u = get_user(uid, bypass_cache=True)
    if u and u.get('registered'):
        bot.send_message(call.message.chat.id, t(uid, 'choose_below'), reply_markup=main_reply_keyboard(uid), parse_mode='HTML')

@bot.message_handler(commands=['play'])
def cmd_play(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    if not u.get('registered'): return bot.send_message(message.chat.id, t(uid, 'share_contact_prompt'), reply_markup=contact_button(uid), parse_mode='HTML')
    bot.send_message(message.chat.id, f"{t(uid, 'play_below')}", reply_markup=webapp_inline_keyboard(uid), parse_mode='HTML')

@bot.message_handler(func=lambda m: get_action(m.text) == 'play')
def h_play_btn(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    text = f"🎲 ወደ Abisinya Bingo እንኳን ደህና መጡ!\nይጫወቱ ያሸንፉ ድል በድል ይሁኑ!\n\n👇 ጨዋታ ለመጀመር ከታች ያለውን ቁልፍ ይጫኑ:"
    markup = webapp_inline_keyboard(uid)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')

@bot.message_handler(commands=['balance'])
def cmd_balance(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    play = float(u.get('play_balance', 0) or 0)
    win = float(u.get('win_balance', 0) or 0)
    bot.send_message(message.chat.id, f"🏦 <b>{t(uid, 'your_balance')}</b>\n\n{t(uid, 'play_bal')}: <b>{play:.2f} ETB</b>\n{t(uid, 'win_bal')}: <b>{win:.2f} ETB</b>\n{t(uid, 'total')}: <b>{play + win:.2f} ETB</b>", parse_mode='HTML')

@bot.message_handler(commands=['invite'])
def cmd_invite(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    try: bot_username = bot.get_me().username
    except: bot_username = "AbisinyaBingo_Bot"
    link = f"https://t.me/{bot_username}?start={u['referral_code']}"
    bot.send_message(message.chat.id, f"{t(uid, 'invite_msg')}\n\n{t(uid, 'invite_bonus')}\n\n{t(uid, 'your_link')}\n<code>{link}</code>", parse_mode='HTML')

# ==========================================
# REGISTER & CONTACT
# ==========================================
@bot.message_handler(commands=['register'])
def handle_register(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    if u.get('registered'):
        return bot.send_message(message.chat.id, f"{t(uid, 'already_registered')}\n\n👤 {u['name']}\n📱 {u.get('phone', 'N/A')}", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
    bot.send_message(message.chat.id, f"🔢 <b>{t(uid, 'register')}</b>\n\n{t(uid, 'share_contact_prompt')}", reply_markup=contact_button(uid), parse_mode='HTML')

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    if message.contact.user_id != message.from_user.id:
        return bot.send_message(message.chat.id, "❌ Share your own contact only.", reply_markup=main_reply_keyboard(uid))

    phone = message.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone
    if u.get('registered'): return bot.send_message(message.chat.id, t(uid, 'already_registered'), reply_markup=main_reply_keyboard(uid))

    users_col.update_one({"id": uid}, {"$set": {"phone": phone, "registered": True}})
    invalidate_user_cache(uid)

    if u.get('pending_referrer'):
        ref_id = u['pending_referrer']
        if get_user(ref_id):
            users_col.update_one({"id": ref_id}, {"$inc": {"play_balance": 30}})
            invalidate_user_cache(ref_id)
            users_col.update_one({"id": uid}, {"$set": {"referred_by": ref_id}, "$unset": {"pending_referrer": ""}})
            invalidate_user_cache(uid)
            try: bot.send_message(ref_id, "🎉 አንድ አዲስ ተጫዋች በግብዣ ሊንክዎ ተቀላቅሏል!\n\n💰 ለሽልማት <b>30 ETB</b> ወደ Play ባላንስዎ ተጨምሯል።", parse_mode='HTML')
            except: pass

    u = get_user(uid, bypass_cache=True)
    bot.send_message(message.chat.id, f"{t(uid, 'registered')}\n\n👤 {u['name']}\n📱 {phone}\n💰 {t(uid, 'balance')}: <b>{u['play_balance']:.2f} ETB</b>\n\n{t(uid, 'choose_below')}", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))

# ==========================================
# DEPOSIT
# ==========================================
def parse_deposit_text(text):
    text_clean = (text or "").strip()
    if not text_clean: return None, None
    amount, reference = None, None
    for pat in [r'transaction\s+number\s+is\s+([A-Z0-9]{6,})', r'transaction\s+(?:id|no)\s*[:\-]?\s*([A-Z0-9]{6,})', r'txn\s*[:\-]?\s*([A-Z0-9]{6,})', r'reference\s*[:\-]?\s*([A-Z0-9]{6,})']:
        m = re.search(pat, text_clean, re.IGNORECASE)
        if m: reference = m.group(1).upper(); break
    for pat in [r'you\s+have\s+received\s+ETB\s+(\d+(?:[.,]\d+)?)', r'received\s+ETB\s+(\d+(?:[.,]\d+)?)', r'credited\s+with\s+(?:ETB|Birr)\s+(\d+(?:[.,]\d+)?)', r'(?:ETB|Birr)\s+(\d+(?:[.,]\d+)?)']:
        m = re.search(pat, text_clean, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(',', ''))
                if MIN_DEPOSIT <= val <= 100000: amount = val; break
            except: pass
    if not amount:
        for p in reversed(text_clean.split()[-5:]):
            try:
                val = float(p.replace(',', ''))
                if MIN_DEPOSIT <= val <= 100000: amount = val; break
            except: pass
    return reference, amount

@bot.message_handler(commands=['deposit'])
def handle_deposit(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📲 Telebirr", callback_data="dep_telebirr"), types.InlineKeyboardButton("🏦 CBE", callback_data="dep_cbe"))
    bot.send_message(message.chat.id, f"💳 <b>{t(uid, 'deposit_choose')}</b>", reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "dep_telebirr")
def cb_dep_telebirr(call):
    uid = str(call.from_user.id); safe_answer_callback(call.id)
    settings = get_payment_settings()
    msg = bot.send_message(call.message.chat.id, f"📲 <b>Telebirr</b>\n\n📞 <code>{settings.get('telebirr_number')}</code>\n👤 <b>{settings.get('telebirr_name', 'tazebew')}</b>\n\n{t(uid, 'send_txn')}\n{t(uid, 'txn_example')}", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_deposit_reference, 'Telebirr')

@bot.callback_query_handler(func=lambda call: call.data == "dep_cbe")
def cb_dep_cbe(call):
    uid = str(call.from_user.id); safe_answer_callback(call.id)
    settings = get_payment_settings()
    msg = bot.send_message(call.message.chat.id, f"🏦 <b>CBE</b>\n\n🔢 <code>{settings.get('cbe_number')}</code>\n👤 <b>{settings.get('cbe_name', 'tazebew')}</b>\n\n{t(uid, 'send_txn')}\n{t(uid, 'txn_example')}", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_deposit_reference, 'CBE')

def process_deposit_reference(message, method):
    uid = str(message.from_user.id)
    reference, amount = parse_deposit_text(message.text or "")
    if not amount or amount < MIN_DEPOSIT:
        return bot.send_message(message.chat.id, f"❌ {t(uid, 'invalid_amount')}\n\n{t(uid, 'txn_example')}", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))

    if not reference: reference = gen_txn_id()
    if txns_col.find_one({"reference": reference}):
        return bot.send_message(message.chat.id, f"⚠️ ይህ የTransaction ቁጥር (<code>{reference}</code>) ከዚህ በፊት ተልኳል!", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))

    u = ensure_user(message); txn_id = gen_txn_id()
    txns_col.insert_one({"id": txn_id, "type": "deposit", "user_id": u['id'], "user_name": u['name'], "amount": amount, "method": method, "reference": reference, "status": "pending", "created": datetime.utcnow().isoformat(), "notified": False})
    bot.send_message(message.chat.id, f"{t(uid, 'deposit_sent')}\n\n🆔 <code>{txn_id}</code>\n💳 {method}\n💰 <b>{amount:.2f} ETB</b>\n{t(uid, 'txn_ref')} <code>{reference}</code>\n\n{t(uid, 'txn_pending')}", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
    notify_admins(f"💰 <b>New Deposit</b>\n\n👤 {u['name']} (<code>{u['id']}</code>)\n💳 {method}\n💰 {amount:.2f} ETB\n🔢 <code>{reference}</code>", skip_id=u['id'])

# ==========================================
# 🎁 GIVEAWAY CLAIM
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data == "claim_giveaway")
def cb_claim_giveaway(call):
    uid = str(call.from_user.id)
    safe_answer_callback(call.id, "⏳ በመስራት ላይ...")
    
    try:
        res = requests.post(
            f"{SERVER_URL}/api/bot/giveaway/claim",
            json={"userId": uid},
            headers={"x-bot-token": BOT_TOKEN, "Content-Type": "application/json"},
            timeout=10
        )
        data = res.json()
        
        if data.get("success"):
            amount = data.get("amount", 0)
            bot.answer_callback_query(call.id, f"🎉 እንኳን ደስ አለዎት! {amount} ብር አግኝተዋል።", show_alert=True)
            bot.send_message(
                call.message.chat.id, 
                f"✅ <b>ተሳክቷል!</b>\n\n💰 {amount} ETB ወደ Play ባላንስዎ ተጨምሯል።", 
                parse_mode='HTML'
            )
        else:
            msg = data.get("message", "ስህተት ተከስቷል")
            bot.answer_callback_query(call.id, f"❌ {msg}", show_alert=True)
            
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ የኢንተርኔት ስህተት! እባክዎ በድጋሚ ይሞክሩ።", show_alert=True)

# ==========================================
# WITHDRAW (Telebirr & CBE)
# ==========================================
@bot.message_handler(commands=['withdraw'])
def handle_withdraw(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)
    if not u.get('registered'):
        return bot.send_message(message.chat.id, t(uid, 'not_registered'), reply_markup=contact_button(uid))

    win_balance = float(u.get('win_balance', 0) or 0)
    if win_balance < MIN_WITHDRAW:
        return bot.send_message(
            message.chat.id,
            f"{t(uid, 'insufficient')}\n\n"
            f"{t(uid, 'win_bal')}: <b>{win_balance:.2f} ETB</b>\n"
            f"{t(uid, 'min_withdraw', amt=MIN_WITHDRAW)}",
            parse_mode='HTML',
            reply_markup=main_reply_keyboard(uid)
        )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📲 Telebirr", callback_data="wd_telebirr"),
        types.InlineKeyboardButton("🏦 CBE", callback_data="wd_cbe")
    )
    bot.send_message(
        message.chat.id,
        f"💸 <b>{t(uid, 'withdraw_choose')}</b>\n\n"
        f"{t(uid, 'win_bal')}: <b>{win_balance:.2f} ETB</b>\n"
        f"{t(uid, 'min_withdraw', amt=MIN_WITHDRAW)}",
        reply_markup=markup,
        parse_mode='HTML'
    )

# --- TELEBIRR WITHDRAW ---
@bot.callback_query_handler(func=lambda call: call.data == "wd_telebirr")
def cb_wd_telebirr(call):
    uid = str(call.from_user.id)
    safe_answer_callback(call.id)
    u = get_user(uid)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(t(uid, 'to_self'), callback_data="wd_self_tb"),
        types.InlineKeyboardButton(t(uid, 'to_other'), callback_data="wd_other_tb")
    )
    bot.send_message(
        call.message.chat.id,
        f"📲 <b>Telebirr Withdrawal</b>\n\n{t(uid, 'withdraw_choose')}",
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == "wd_self_tb")
def cb_wd_self(call):
    uid = str(call.from_user.id)
    safe_answer_callback(call.id)
    u = get_user(uid)
    if u and u.get('phone'):
        msg = bot.send_message(
            call.message.chat.id,
            f"👤 <b>{t(uid, 'to_self')}</b>\n\n{t(uid, 'registered_phone')} <b>{u['phone']}</b>\n\n{t(uid, 'send_amount', min=MIN_WITHDRAW)}",
            parse_mode='HTML',
            reply_markup=main_reply_keyboard(uid)
        )
        bot.register_next_step_handler(msg, process_withdraw_amount_final, 'Telebirr', u['phone'])
    else:
        bot.send_message(call.message.chat.id, t(uid, 'share_contact_prompt'), reply_markup=contact_button(uid), parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "wd_other_tb")
def cb_wd_other(call):
    uid = str(call.from_user.id)
    safe_answer_callback(call.id)
    msg = bot.send_message(call.message.chat.id, f"👥 <b>{t(uid, 'to_other')}</b>\n\n{t(uid, 'send_phone')}", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_wd_other_phone)

def process_wd_other_phone(message):
    uid = str(message.from_user.id)
    phone = (message.text or "").strip()
    if not phone.replace('+', '').isdigit() or len(phone) < 9:
        return bot.send_message(message.chat.id, t(uid, 'invalid_phone'), reply_markup=main_reply_keyboard(uid))
    msg = bot.send_message(message.chat.id, f"✅ <b>{phone}</b>\n\n{t(uid, 'send_amount', min=MIN_WITHDRAW)}", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
    bot.register_next_step_handler(msg, process_withdraw_amount_final, 'Telebirr', phone)

# --- CBE WITHDRAW ---
@bot.callback_query_handler(func=lambda call: call.data == "wd_cbe")
def cb_wd_cbe(call):
    uid = str(call.from_user.id)
    safe_answer_callback(call.id)
    msg = bot.send_message(call.message.chat.id, f"🏦 <b>CBE Withdrawal</b>\n\n{t(uid, 'send_cbe_acc')}", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
    bot.register_next_step_handler(msg, process_wd_cbe_acc)

def process_wd_cbe_acc(message):
    uid = str(message.from_user.id)
    acc_num = (message.text or "").strip()
    if len(acc_num) < 5:
        return bot.send_message(message.chat.id, "❌ ትክክለኛ የCBE አካውንት ቁጥር ያስገቡ!", reply_markup=main_reply_keyboard(uid))
    msg = bot.send_message(message.chat.id, f"✅ <b>{acc_num}</b>\n\n{t(uid, 'send_amount', min=MIN_WITHDRAW)}", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
    bot.register_next_step_handler(msg, process_withdraw_amount_final, 'CBE', acc_num)

def process_withdraw_amount_final(message, method, account_info):
    uid = str(message.from_user.id)
    try:
        amount = float((message.text or "").strip())
    except (ValueError, TypeError):
        return bot.send_message(message.chat.id, t(uid, 'invalid_amount'), reply_markup=main_reply_keyboard(uid))

    u = ensure_user(message)
    if amount < MIN_WITHDRAW:
        return bot.send_message(message.chat.id, f"{t(uid, 'insufficient')}\n\n{t(uid, 'min_withdraw', amt=MIN_WITHDRAW)}", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))

    result = users_col.update_one({"id": uid, "win_balance": {"$gte": amount}}, {"$inc": {"win_balance": -amount}})
    if result.modified_count == 0:
        u = get_user(uid, bypass_cache=True)
        return bot.send_message(message.chat.id, f"{t(uid, 'insufficient')}\n\n{t(uid, 'win_bal')}: <b>{u['win_balance']:.2f} ETB</b>", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))

    invalidate_user_cache(uid)
    u = get_user(uid, bypass_cache=True)
    txn_id = gen_txn_id()

    txns_col.insert_one({"id": txn_id, "type": "withdrawal", "user_id": u['id'], "user_name": u['name'], "amount": amount, "method": method, "phone": account_info, "status": "pending", "created": datetime.utcnow().isoformat(), "notified": False})

    bot.send_message(message.chat.id, f"{t(uid, 'wd_approved_req', amt=f'{amount:.2f}')}\n\n🆔 <code>{txn_id}</code>\n💳 <b>{method}</b>\n📱 <b>{account_info}</b>\n💰 <b>{amount:.2f} ETB</b>\n\n{t(uid, 'txn_pending')}", parse_mode='HTML', reply_markup=main_reply_keyboard(uid))
    notify_admins(f"💸 <b>New Withdrawal ({method})</b>\n\n👤 {u['name']} (<code>{u['id']}</code>)\n💰 {amount:.2f} ETB\n📱 {account_info}\n🆔 <code>{txn_id}</code>", skip_id=u['id'])

# ==========================================
# ⚠️ ADMIN COMMAND: DELETE PLAYER
# ==========================================
@bot.message_handler(commands=['delete'])
def admin_delete_user(message):
    uid = str(message.from_user.id)
    if uid not in [str(a) for a in ADMIN_IDS]:
        return bot.send_message(message.chat.id, "❌ ይህ ትዕዛዝ ለአድሚን ብቻ ነው!")
    
    args = message.text.split()
    if len(args) < 2:
        return bot.send_message(message.chat.id, "⚠️ እባክዎ የሚጠፋውን ተጫዋች ID ያስገቡ።\nለምሳሌ: <code>/delete 5925033073</code>", parse_mode='HTML')
    
    target_id = args[1]
    target_user = get_user(target_id)
    if not target_user:
        return bot.send_message(message.chat.id, f"❌ በ ID <code>{target_id}</code> የተመዘገበ ተጫዋች አልተገኘም!", parse_mode='HTML')
    
    users_col.delete_one({"id": target_id})
    txns_col.delete_many({"user_id": target_id})
    invalidate_user_cache(target_id)
    
    bot.send_message(message.chat.id, f"✅ ተጫዋች <b>{target_user.get('name')}</b> (<code>{target_id}</code>) በተሳካ ሁኔታ ጠፍቷል።", parse_mode='HTML')

# ==========================================
# HISTORY, HELP, LEADERBOARD & OTHER BUTTONS
# ==========================================
@bot.message_handler(commands=['history'])
def h_history(message):
    uid = str(message.from_user.id)
    u = ensure_user(message)

    result = list(txns_col.aggregate([
        {"$match": {"user_id": uid}},
        {"$sort": {"_id": -1}},
        {"$facet": {"deposits": [{"$match": {"type": "deposit"}}, {"$limit": 5}], "withdrawals": [{"$match": {"type": "withdrawal"}}, {"$limit": 5}]}}
    ]))
    
    deps = result[0].get('deposits', []) if result else []
    wds = result[0].get('withdrawals', []) if result else []
    text = f"📜 <b>{t(uid, 'your_history', name=u['name'])}</b>\n\n"

    if deps:
        text += f"<b>{t(uid, 'deposits')}</b>\n"
        for tt in deps:
            icon = '✅' if tt['status'] == 'approved' else '❌' if tt['status'] == 'rejected' else '⏳'
            text += f"{icon} {tt['amount']:.2f} ETB\n"
        text += "\n"
    
    if wds:
        text += f"<b>{t(uid, 'withdrawals')}</b>\n"
        for tt in wds:
            icon = '✅' if tt['status'] == 'approved' else '❌' if tt['status'] == 'rejected' else '⏳'
            text += f"{icon} {tt['amount']:.2f} ETB\n"
        text += "\n"
    
    if not deps and not wds:
        text += t(uid, 'no_txn')
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['help'])
def h_help(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    bot.send_message(message.chat.id, f"{t(uid, 'help_title')}\n\n{t(uid, 'help_list')}", parse_mode='HTML')

# ✅ የሜኑ ቁልፎች አያያዥ
@bot.message_handler(func=lambda m: get_action(m.text) == 'deposit')
def h_dep_btn(message): handle_deposit(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'withdraw')
def h_wd_btn(message): handle_withdraw(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'balance_btn')
def h_bal_btn(message): cmd_balance(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'invite')
def h_inv_btn(message): cmd_invite(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'history')
def h_hist_btn(message): h_history(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'register')
def h_reg_btn(message): handle_register(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'language')
def h_lang_btn(message): handle_language(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'help')
def h_help_btn(message): h_help(message)

@bot.message_handler(func=lambda m: get_action(m.text) == 'support')
def h_sup_btn(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(f"📞 @{SUPPORT_USERNAME}", url=f"https://t.me/{SUPPORT_USERNAME}"))
    bot.send_message(message.chat.id, f"💬 <b>{t(uid, 'support_msg')}</b>\n\n📞 @{SUPPORT_USERNAME}\n⏰ 24/7", reply_markup=markup, parse_mode='HTML')

@bot.message_handler(func=lambda m: get_action(m.text) == 'leaderboard')
def h_lead_btn(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    sorted_u = list(users_col.find().sort("win_balance", -1).limit(5))
    text = f"<b>{t(uid, 'leaderboard_title')}</b>\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, uu in enumerate(sorted_u):
        name = (uu.get('name', '?') or '?')[:20]
        bal = float(uu.get('win_balance', 0) or 0)
        text += f"{medals[i]} <b>{name}</b> — {bal:.2f} ETB\n"
    if not sorted_u: text += t(uid, 'no_winners')
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: True)
def fallback(message):
    uid = str(message.from_user.id)
    ensure_user(message)
    bot.send_message(message.chat.id, t(uid, 'unknown'))

# ==========================================
# NOTIFIER & STARTUP
# ==========================================
def notify_txn_users():
    print("🔔 Txn notifier started")
    while True:
        try:
            time.sleep(3)
            pending = list(txns_col.find({"status": {"$in": ["approved", "rejected"]}, "notified": {"$ne": True}}).limit(50))
            for txn in pending:
                tid = txn.get('id')
                uid = str(txn.get('user_id', ''))
                if not tid or not uid: continue
                try:
                    amount_str = f"{txn.get('amount', 0):.2f}"
                    txn_type = txn.get('type')
                    status = txn['status']

                    if txn_type == 'deposit' and status == 'approved':
                        user = get_user(uid, bypass_cache=True)
                        bal = f"{float(user.get('play_balance', 0) or 0):.2f}" if user else "0.00"
                        bot.send_message(int(uid), f"✅ <b>ገቢ ያደረጉት {amount_str} ETB ወደ ዋሌትዎ ተደምሯል</b>\n\n💰 አዲስ ባላንስ: <b>{bal} ETB</b>", parse_mode='HTML')
                    elif txn_type == 'withdrawal' and status == 'approved':
                        bot.send_message(int(uid), f"✅ <b>ወጭዎ በተሳካ ሁኔታ ገብቷል!</b>\n\n💰 መጠን: <b>{amount_str} ETB</b>", parse_mode='HTML')
                    elif status == 'rejected':
                        bot.send_message(int(uid), f"❌ <b>የ{txn_type} ጥያቄዎ ተከልክሏል</b>\n\n💰 መጠን: <b>{amount_str} ETB</b>", parse_mode='HTML')

                    txns_col.update_one({"id": tid}, {"$set": {"notified": True}})
                    invalidate_user_cache(uid)
                except Exception as e:
                    print(f"⚠️ Notifier error for {tid}: {e}")
        except Exception as e:
            print(f"⚠️ Notifier loop error: {e}")

if __name__ == '__main__':
    print("🤖 Bot starting...")
    try:
        _bot_username = bot.get_me().username
        print(f"✅ Bot username: @{_bot_username}")
    except Exception as e:
        print(f"⚠️ Could not fetch bot username: {e}")

    try:
        bot.remove_webhook()
        time.sleep(1)
    except: pass

    threading.Thread(target=notify_txn_users, daemon=True).start()

    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Polling error: {e}")
            time.sleep(5)
