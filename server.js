const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const crypto = require('crypto');
const mongoose = require('mongoose');
const compression = require('compression');
require('dotenv').config();

const dns = require('dns');
dns.setServers(['8.8.8.8', '1.1.1.1']);

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: '*' }, perMessageDeflate: { threshold: 1024 } });
const PORT = process.env.PORT || 3000;

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const MONGODB_URI = process.env.MONGODB_URI;
const REQUIRE_TG_AUTH = process.env.REQUIRE_TG_AUTH === 'true';
const ADMIN_USERNAME = process.env.ADMIN_USERNAME || "admin";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "admin123";

if (!BOT_TOKEN || !MONGODB_URI) { console.error('Missing env'); process.exit(1); }

app.use(compression({ level: 6, threshold: 1024 }));
app.use(cors());
app.use(express.json({ limit: '10kb' }));
app.use(express.static('public', { maxAge: '1d' }));

/* ─── MONGODB ─── */
mongoose.connect(MONGODB_URI, { serverSelectionTimeoutMS: 10000, maxPoolSize: 20, dbName: 'abisinya' })
.then(async () => {
    console.log('✅ MongoDB connected');
    const s = await Settings.findOne({ key: 'payment_accounts' }).lean();
    if (s) {
        if (s.maxCards) gameState.settings.maxCards = s.maxCards;
        if (s.countdownTime) gameState.settings.countdownTime = s.countdownTime;
        if (s.botEnabled !== undefined) gameState.settings.botEnabled = s.botEnabled;
        if (s.visualPlayers) gameState.settings.visualPlayers = s.visualPlayers;
        if (s.botWinRate) gameState.settings.botWinRate = s.botWinRate;
        if (s.botNames && s.botNames.length > 0) gameState.settings.botNames = s.botNames;
    }
})
.catch(err => { console.error('❌ DB Error:', err.message); process.exit(1); });

/* ─── SCHEMAS ─── */
const UserSchema = new mongoose.Schema({
    id: { type: String, index: true, unique: true }, name: String, username: String, phone: String,
    play_balance: { type: Number, default: 20, index: true }, win_balance: { type: Number, default: 0, index: true },
    referral_balance: { type: Number, default: 0 },
    total_games: { type: Number, default: 0 }, total_wins: { type: Number, default: 0 },
    referral_code: String, referred_by: { type: String, default: null, index: true },
    pending_referrer: { type: String, default: null }, registered: { type: Boolean, default: false, index: true },
    lang: String, registered_at: { type: String, default: () => new Date().toISOString(), index: true },
    last_daily_bonus: { type: String, default: null }
}, { collection: 'users' });

const TransactionSchema = new mongoose.Schema({
    id: { type: String, index: true, unique: true }, type: { type: String, index: true },
    user_id: { type: String, index: true }, user_name: String, amount: Number,
    method: String, reference: { type: String, index: true }, phone: String,
    status: { type: String, index: true }, created: { type: String, index: true }, notified: Boolean,
    hidden_by_user: { type: Boolean, default: false },
    is_bonus: { type: Boolean, default: false }
}, { collection: 'transactions' });

const GameHistorySchema = new mongoose.Schema({
    gameId: String, winners: [{ id: String, name: String, cardNum: Number, prize: Number }],
    totalPrize: Number, totalPlayers: Number, calledNumbers: [Number], createdAt: { type: Date, default: Date.now }
}, { collection: 'game_history' });

const SettingsSchema = new mongoose.Schema({
    key: { type: String, default: 'payment_accounts', unique: true },
    telebirr_number: { type: String, default: '0968940123' }, telebirr_name: { type: String, default: 'tazebew' },
    cbe_number: { type: String, default: '1000390803005' }, cbe_name: { type: String, default: 'tazebew' },
    enable_cbe: { type: Boolean, default: true }, maxCards: { type: Number, default: 1000 },
    doubleDepositActive: { type: Boolean, default: false },
    doubleDepositMultiplier: { type: Number, default: 2 },
    countdownTime: { type: Number, default: 50 },
    
    // ✅ የተሻሻለ እና ሰፊ የሮቦች ስም ዝርዝር (አማራ፣ ትግራይ፣ ኦሮሞ፣ ሙስሊም፣ ክርስቲያን የተካተቱበት)
    botEnabled: { type: Boolean, default: true },
    visualPlayers: { type: Number, default: 350 },
    botWinRate: { type: Number, default: 80 },
    botNames: { type: [String], default: [
        "Abebe", "Kebede", "Almaz", "Tigist", "Dawit", "Hanna", "Bereket", "Meron", "Aster", "Yonas", 
        "Selam", "Kalkidan", "Mahlet", "Samuel", "Girma", "Getachew", "Mulu", "Hiwot", "Frehiwot", "Eyob", 
        "Nahom", "Tewodros", "Mekdes", "Tsegaye", "Gebre", "Mulugeta", "Abdul", "Fatuma", "Ahmed", "Mohammed", 
        "Amina", "Zainab", "Yusuf", "Hussein", "Ibrahim", "Mariam", "Sara", "Ruth", "Dagmawi", "Meseret", 
        "Ephrem", "Tesfaye", "Gidey", "Hagos", "Kidane", "Tirhas", "Rahel", "Mihret", "Bruk", "Eyerusalem"
    ]}
}, { collection: 'settings' });

const GiveawaySchema = new mongoose.Schema({
    id: String, amount: Number, totalUsers: Number, claimedBy: [String],
    status: { type: String, default: 'active' }, createdAt: { type: Date, default: Date.now }, expiresAt: Date,
    message: String, sentMessages: [{ user_id: String, message_id: Number }]
}, { collection: 'giveaways' });

const BroadcastSchema = new mongoose.Schema({
    id: String, message: String, sentAt: { type: Date, default: Date.now },
    status: { type: String, default: 'active' }, sentMessages: [{ user_id: String, message_id: Number }]
}, { collection: 'broadcasts' });

const PromoCodeSchema = new mongoose.Schema({
    code: { type: String, unique: true, index: true },
    amount: Number, maxUses: Number, usedCount: { type: Number, default: 0 }, usedBy: [String],
    expiresAt: Date, status: { type: String, default: 'active' }, createdAt: { type: Date, default: Date.now }
}, { collection: 'promo_codes' });

const User = mongoose.model('User', UserSchema);
const Transaction = mongoose.model('Transaction', TransactionSchema);
const GameHistory = mongoose.model('GameHistory', GameHistorySchema);
const Settings = mongoose.model('Settings', SettingsSchema);
const Giveaway = mongoose.model('Giveaway', GiveawaySchema);
const Broadcast = mongoose.model('Broadcast', BroadcastSchema);
const PromoCode = mongoose.model('PromoCode', PromoCodeSchema);

/* ─── AUTH ─── */
function verifyTelegramInitData(initData, botToken) {
    try {
        if (!initData) return null;
        const params = new URLSearchParams(initData); const hash = params.get('hash'); if (!hash) return null;
        params.delete('hash');
        const dataCheckString = Array.from(params.entries()).map(([k, v]) => `${k}=${v}`).sort().join('\n');
        const secretKey = crypto.createHmac('sha256', 'WebAppData').update(botToken).digest();
        const calculatedHash = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');
        if (calculatedHash !== hash) return null;
        const authDate = parseInt(params.get('auth_date')) || 0;
        if (authDate === 0 || (Math.floor(Date.now() / 1000) - authDate) > 86400) return null;
        const userJson = params.get('user'); if (!userJson) return null;
        const userObj = JSON.parse(userJson); return userObj.id ? userObj : null;
    } catch (e) { return null; }
}

function adminAuth(req, res, next) {
    const authHeader = req.headers.authorization;
    if (authHeader && authHeader.startsWith('Basic ')) {
        try {
            const creds = Buffer.from(authHeader.split(' ')[1], 'base64').toString().split(':');
            if (creds[0] === ADMIN_USERNAME && creds[1] === ADMIN_PASSWORD) return next();
        } catch (e) {}
    }
    return res.status(401).json({ success: false, error: 'Unauthorized' });
}

function authFromHeaders(req) { return verifyTelegramInitData(req.headers['x-telegram-init-data'], BOT_TOKEN); }

/* ═══════════════════════════════════════════════════════════
   GAME LOGIC & BOT SYSTEM
   ═══════════════════════════════════════════════════════════ */
function mulberry32(a) { return function() { a |= 0; a = a + 0x6D2B79F5 | 0; var t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const cardCache = new Map();
function getCardCols(cardNum) {
    if (cardCache.has(cardNum)) return cardCache.get(cardNum);
    const cols = [[], [], [], [], []]; const seedBase = cardNum * 100;
    for (let c = 0; c < 5; c++) {
        const min = c * 15 + 1, max = c * 15 + 15; const avail = [];
        for (let n = min; n <= max; n++) avail.push(n);
        const seed = seedBase + c; const rand = mulberry32(seed);
        for (let i = avail.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [avail[i], avail[j]] = [avail[j], avail[i]]; }
        cols[c] = avail.slice(0, 5); 
    }
    cols[2][2] = 'FREE'; cardCache.set(cardNum, cols); return cols;
}

function checkWinningLine(cardNum, calledNumbers) {
    const n = Number(cardNum); if (!Number.isFinite(n) || n < 1 || calledNumbers.length === 0) return null;
    const cols = getCardCols(n); const calledSet = new Set(calledNumbers); const m = [];
    for (let r = 0; r < 5; r++) { const row = []; for (let c = 0; c < 5; c++) { const val = cols[c][r]; row.push(val === 'FREE' || calledSet.has(val)); } m.push(row); }
    for (let r = 0; r < 5; r++) if (m[r].every(v => v)) return { type: 'row', index: r, desc: 'Row ' + (r + 1) };
    for (let c = 0; c < 5; c++) if (m.every(row => row[c])) return { type: 'col', index: c, desc: 'Col ' + (c + 1) };
    let d1 = true; for (let i = 0; i < 5; i++) if (!m[i][i]) { d1 = false; break; }
    if (d1) return { type: 'diag1', desc: 'Diag 1' };
    let d2 = true; for (let i = 0; i < 5; i++) if (!m[i][4 - i]) { d2 = false; break; }
    if (d2) return { type: 'diag2', desc: 'Diag 2' };
    if (m[0][0] && m[0][4] && m[4][0] && m[4][4]) return { type: 'corners', desc: '4 Corners' };
    return null;
}

const gameState = { 
    phase: 'waiting', currentCall: null, calledNumbers: [], takenCards: {}, 
    isAutoOn: true, isRunning: false, 
    settings: { 
        callInterval: 5, maxCards: 1000, countdownTime: 50,
        botEnabled: true, visualPlayers: 350, botWinRate: 80,
        botNames: ["Abebe", "Kebede", "Almaz", "Tigist", "Dawit", "Hanna", "Bereket", "Meron", "Aster", "Yonas", "Selam", "Kalkidan", "Mahlet", "Samuel", "Girma", "Getachew", "Mulu", "Hiwot", "Frehiwot", "Eyob", "Nahom", "Tewodros", "Mekdes", "Tsegaye", "Gebre", "Mulugeta", "Abdul", "Fatuma", "Ahmed", "Mohammed", "Amina", "Zainab", "Yusuf", "Hussein", "Ibrahim", "Mariam", "Sara", "Ruth", "Dagmawi", "Meseret", "Ephrem", "Tesfaye", "Gidey", "Hagos", "Kidane", "Tirhas", "Rahel", "Mihret", "Bruk", "Eyerusalem"]
    },
    numberToCardsMap: {} 
};
let gameTimerInterval = null, callInterval = null, autoRestartTimer = null;
let remainingTime = 50, roundWinners = [], isEndingRound = false;
const CARD_PRICE = 10, DERASH_PER_CARD = 8;

function spawnBots() {
    if (!gameState.settings.botEnabled) return;
    
    const availableCards = [];
    for (let i = 1; i <= gameState.settings.maxCards; i++) {
        if (!gameState.takenCards[i]) availableCards.push(i);
    }
    
    const botCount = Math.min(15, Math.floor(availableCards.length / 2));
    
    for (let b = 0; b < botCount; b++) {
        if (availableCards.length === 0) break;
        
        const randomIndex = Math.floor(Math.random() * availableCards.length);
        const cardNum = availableCards.splice(randomIndex, 1)[0];
        
        const randomName = gameState.settings.botNames[Math.floor(Math.random() * gameState.settings.botNames.length)];
        const botId = `bot_${Math.floor(Math.random() * 10000)}`;
        
        gameState.takenCards[cardNum] = { userId: botId, isBot: true, botName: randomName };
        
        const cardCols = getCardCols(cardNum);
        cardCols.forEach(col => {
            col.forEach(num => {
                if (num !== 'FREE') {
                    if (!gameState.numberToCardsMap[num]) gameState.numberToCardsMap[num] = new Set();
                    gameState.numberToCardsMap[num].add(cardNum);
                }
            });
        });
    }
}

/* ─── ADMIN & API ─── */
app.get('/api/settings', async (req, res) => {
    try {
        let settings = await Settings.findOne({ key: 'payment_accounts' }).lean();
        if (!settings) settings = await Settings.create({ key: 'payment_accounts' });
        
        gameState.settings.botEnabled = settings.botEnabled;
        gameState.settings.visualPlayers = settings.visualPlayers;
        gameState.settings.botWinRate = settings.botWinRate;
        gameState.settings.botNames = settings.botNames;

        res.json({ success: true, data: settings });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/settings', adminAuth, async (req, res) => {
    try {
        const { telebirr_number, telebirr_name, enable_cbe, maxCards, doubleDepositActive, countdownTime,
                botEnabled, visualPlayers, botWinRate, botNames } = req.body;
        const update = {};
        if (telebirr_number) update.telebirr_number = telebirr_number;
        if (telebirr_name) update.telebirr_name = telebirr_name;
        if (typeof enable_cbe === 'boolean') update.enable_cbe = enable_cbe;
        if (maxCards) { update.maxCards = Number(maxCards); gameState.settings.maxCards = Number(maxCards); io.emit('update_max_cards', { maxCards: Number(maxCards) }); }
        if (typeof doubleDepositActive === 'boolean') update.doubleDepositActive = doubleDepositActive;
        if (countdownTime) { update.countdownTime = Number(countdownTime); gameState.settings.countdownTime = Number(countdownTime); io.emit('update_countdown_time', { countdownTime: Number(countdownTime) }); }
        
        if (typeof botEnabled === 'boolean') { update.botEnabled = botEnabled; gameState.settings.botEnabled = botEnabled; }
        if (visualPlayers) { update.visualPlayers = Number(visualPlayers); gameState.settings.visualPlayers = Number(visualPlayers); }
        if (botWinRate) { update.botWinRate = Number(botWinRate); gameState.settings.botWinRate = Number(botWinRate); }
        if (botNames && Array.isArray(botNames)) { update.botNames = botNames; gameState.settings.botNames = botNames; }

        const updatedSettings = await Settings.findOneAndUpdate({ key: 'payment_accounts' }, update, { upsert: true, new: true });
        io.emit('settings_updated', { settings: updatedSettings });
        res.json({ success: true });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/admin/referrals', adminAuth, async (req, res) => {
    try {
        const referredUsers = await User.find({ referred_by: { $ne: null } }).lean();
        const referrerIds = [...new Set(referredUsers.map(u => u.referred_by))];
        const referrers = await User.find({ id: { $in: referrerIds } }, { id: 1, name: 1 }).lean();
        const referrerMap = new Map(referrers.map(r => [r.id, r.name]));
        
        const data = referredUsers.map(u => ({
            referrer_id: u.referred_by, 
            referrer_name: referrerMap.get(u.referred_by) || 'Unknown',
            new_user_id: u.id, 
            new_user_name: u.name || 'Player', 
            created_at: u.registered_at
        }));
        res.json({ success: true, data });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/user/referral', async (req, res) => {
    try {
        const { new_user_id, referrer_id } = req.body;
        if (!new_user_id || !referrer_id || new_user_id === referrer_id) return res.status(400).json({ success: false, error: 'Invalid referral' });
        
        const newUser = await User.findOne({ id: String(new_user_id) });
        if (newUser && newUser.referred_by) return res.status(400).json({ success: false, error: 'Already referred' });
        
        const referrer = await User.findOne({ id: String(referrer_id) });
        if (!referrer) return res.status(404).json({ success: false, error: 'Referrer not found' });
        
        await User.updateOne({ id: String(referrer_id) }, { $inc: { play_balance: 30, referral_balance: 30 } });
        await User.findOneAndUpdate({ id: String(new_user_id) }, { $inc: { play_balance: 20 }, $set: { referred_by: String(referrer_id) } }, { upsert: true });
        
        io.to(`user_${referrer_id}`).emit('wallet_updated', {});
        io.to(`user_${new_user_id}`).emit('wallet_updated', {});
        res.json({ success: true, message: 'Referral bonus applied' });
    } catch (e) { res.status(500).json({ success: false, error: e.message }); }
});

app.delete('/api/admin/users/:id', adminAuth, async (req, res) => {
    try {
        const userId = String(req.params.id);
        await User.deleteOne({ id: userId });
        await Transaction.deleteMany({ user_id: userId });
        
        for (const [cardNum, data] of Object.entries(gameState.takenCards)) {
            if (data.userId === userId) {
                delete gameState.takenCards[cardNum];
                if (gameState.numberToCardsMap) {
                     Object.keys(gameState.numberToCardsMap).forEach(num => gameState.numberToCardsMap[num].delete(Number(cardNum)));
                }
            }
        }
        io.emit('sync_taken_cards', { takenCards: Object.keys(gameState.takenCards).map(Number), totalPlayers: Object.keys(gameState.takenCards).length, totalCards: Object.keys(gameState.takenCards).length });
        res.json({ success: true });
    } catch (e) { res.status(500).json({ success: false, error: e.message }); }
});

app.get('/api/admin/game-status', adminAuth, async (req, res) => {
    try {
        const realPlayersIds = [...new Set(Object.values(gameState.takenCards).filter(c => !c.isBot).map(c => c.userId))];
        const realPlayers = await User.find({ id: { $in: realPlayersIds } }, { id: 1, name: 1 }).lean();
        const playerMap = new Map(realPlayers.map(p => [p.id, p.name]));
        
        const takenCardsDetails = {};
        for (const [card, data] of Object.entries(gameState.takenCards)) {
            takenCardsDetails[card] = { 
                userId: data.userId, 
                userName: data.isBot ? data.botName : (playerMap.get(data.userId) || "Unknown"),
                isBot: !!data.isBot
            };
        }
        
        const visualTotal = gameState.settings.visualPlayers + realPlayersIds.length;

        res.json({ success: true, data: { ...gameState, takenCardsDetails, totalPlayers: visualTotal, realPlayersCount: realPlayersIds.length, totalCards: Object.keys(gameState.takenCards).length } });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/start-game', adminAuth, (req, res) => { gameState.isRunning = true; if (gameState.phase === 'waiting') startRound(); res.json({ success: true }); });
app.post('/api/admin/stop-game', adminAuth, (req, res) => {
    gameState.isRunning = false;
    if (gameTimerInterval) clearInterval(gameTimerInterval);
    if (callInterval) clearInterval(callInterval);
    if (autoRestartTimer) clearTimeout(autoRestartTimer);
    gameState.phase = 'waiting'; gameState.calledNumbers = []; gameState.takenCards = {}; gameState.isAutoOn = false; gameState.currentCall = null;
    isEndingRound = false; roundWinners = [];
    io.emit('reset_game');
    res.json({ success: true });
});

app.post('/api/admin/call-number', adminAuth, async (req, res) => {
    if (gameState.phase !== 'calling' || gameState.calledNumbers.length >= 75 || isEndingRound) {
        return res.status(400).json({ success: false, message: 'ጨዋታ አልተጀመረም ወይም አልቋል' });
    }
    const reqNumber = Number(req.body.number);
    if (!reqNumber || reqNumber < 1 || reqNumber > 75) return res.status(400).json({ success: false, message: 'እባክዎ ከ1 እስከ 75 ያለ ትክክለኛ ቁጥር ያስገቡ' });
    if (gameState.calledNumbers.includes(reqNumber)) return res.status(400).json({ success: false, message: 'ይህ ቁጥር ቀድሞ ተጠርቷል!' });

    gameState.calledNumbers.push(reqNumber); gameState.currentCall = reqNumber;
    io.emit('new_number_called', { number: reqNumber, allCalled: gameState.calledNumbers });
    
    const winnerFound = await checkForAutoWinner(reqNumber);
    if (winnerFound) { await endRound(roundWinners); return res.json({ success: true }); }

    if (callInterval) { clearInterval(callInterval); callInterval = null; }
    if (gameState.isAutoOn) {
        callInterval = setInterval(async () => {
            if (gameState.phase !== 'calling' || isEndingRound) return;
            if (gameState.calledNumbers.length >= 75) { clearInterval(callInterval); callInterval = null; endRound([]); return; }
            let num; do { num = Math.floor(Math.random() * 75) + 1; } while (gameState.calledNumbers.includes(num));
            gameState.calledNumbers.push(num); gameState.currentCall = num;
            io.emit('new_number_called', { number: num, allCalled: gameState.calledNumbers });
            const winnerFound = await checkForAutoWinner(num);
            if (winnerFound) { clearInterval(callInterval); callInterval = null; await endRound(roundWinners); }
        }, gameState.settings.callInterval * 1000);
    }
    res.json({ success: true });
});

app.post('/api/admin/auto-game', adminAuth, (req, res) => {
    const { isAutoOn, speed } = req.body;
    if (callInterval) { clearInterval(callInterval); callInterval = null; }
    gameState.isAutoOn = !!isAutoOn;
    if (Number(speed) > 0) gameState.settings.callInterval = Number(speed);
    if (isAutoOn && gameState.phase === 'calling') {
        callInterval = setInterval(async () => {
            if (gameState.phase !== 'calling' || isEndingRound) return;
            if (gameState.calledNumbers.length >= 75) { clearInterval(callInterval); callInterval = null; endRound([]); return; }
            let num; do { num = Math.floor(Math.random() * 75) + 1; } while (gameState.calledNumbers.includes(num));
            gameState.calledNumbers.push(num); gameState.currentCall = num;
            io.emit('new_number_called', { number: num, allCalled: gameState.calledNumbers });
            const winnerFound = await checkForAutoWinner(num);
            if (winnerFound) { clearInterval(callInterval); callInterval = null; await endRound(roundWinners); }
        }, gameState.settings.callInterval * 1000);
    }
    res.json({ success: true });
});

app.get('/api/admin/dashboard', adminAuth, async (req, res) => {
    try {
        const [totalPlayers, pendingDeposits, pendingWithdrawals, depAgg, wdAgg] = await Promise.all([
            User.countDocuments(), Transaction.countDocuments({ type: 'deposit', status: 'pending' }), Transaction.countDocuments({ type: 'withdrawal', status: 'pending' }),
            Transaction.aggregate([{ $match: { type: 'deposit', status: 'approved' } }, { $group: { _id: null, total: { $sum: '$amount' } } }]),
            Transaction.aggregate([{ $match: { type: 'withdrawal', status: 'approved' } }, { $group: { _id: null, total: { $sum: '$amount' } } }])
        ]);
        res.json({ success: true, data: { totalPlayers, pendingDeposits, pendingWithdrawals, totalDeposits: depAgg[0]?.total || 0, totalWithdrawals: wdAgg[0]?.total || 0, netBalance: (depAgg[0]?.total || 0) - (wdAgg[0]?.total || 0) } });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/admin/users', adminAuth, async (req, res) => {
    try { const users = await User.find({}).sort({ registered_at: -1 }).lean(); res.json({ success: true, data: users }); }
    catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/admin/users/:id', adminAuth, async (req, res) => {
    try { const user = await User.findOne({ id: req.params.id }).lean(); if (!user) return res.status(404).json({ success: false }); res.json({ success: true, data: user }); }
    catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/users/:id/balance', adminAuth, async (req, res) => {
    try {
        const { id } = req.params; const { play_balance, win_balance } = req.body;
        const update = {};
        if (typeof play_balance === 'number') update.play_balance = play_balance;
        if (typeof win_balance === 'number') update.win_balance = win_balance;
        const user = await User.findOneAndUpdate({ id: String(id) }, { $set: update }, { new: true, lean: true });
        io.to(`user_${id}`).emit('wallet_updated', {});
        res.json({ success: true, data: user });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/admin/transactions', adminAuth, async (req, res) => {
    try {
        const filter = {};
        if (req.query.type) filter.type = req.query.type;
        const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
        filter.$or = [{ status: 'pending' }, { status: { $in: ['approved', 'rejected'] }, created: { $gte: oneHourAgo } }];
        const txns = await Transaction.find(filter).sort({ created: -1 }).limit(200).lean();
        res.json({ success: true, data: txns });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/transactions/:id/approve', adminAuth, async (req, res) => {
    try {
        const txn = await Transaction.findOneAndUpdate({ id: req.params.id, status: 'pending' }, { $set: { status: 'approved' } }, { new: true });
        if (!txn) return res.status(400).json({ success: false });
        if (txn.type === 'deposit') {
            await User.updateOne({ id: String(txn.user_id) }, { $inc: { play_balance: txn.amount } }); 
            io.to(`user_${txn.user_id}`).emit('wallet_updated', {}); 
        }
        res.json({ success: true });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/transactions/:id/reject', adminAuth, async (req, res) => {
    try {
        const txn = await Transaction.findOneAndUpdate({ id: req.params.id, status: 'pending' }, { $set: { status: 'rejected' } }, { new: true });
        if (!txn) return res.status(400).json({ success: false });
        if (txn.type === 'withdrawal') { 
            await User.updateOne({ id: String(txn.user_id) }, { $inc: { win_balance: txn.amount } }); 
            io.to(`user_${txn.user_id}`).emit('wallet_updated', {}); 
        }
        res.json({ success: true });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/wallet/me', async (req, res) => {
    try {
        const user = authFromHeaders(req);
        if (!user && !req.headers['x-user-id']) return res.status(401).json({ success: false });
        const userId = user ? String(user.id) : String(req.headers['x-user-id']);
        
        const todayStr = new Date().toISOString().split('T')[0];
        let dbUser = await User.findOne({ id: userId });
        if (!dbUser) dbUser = new User({ id: userId });

        if (dbUser.last_daily_bonus !== todayStr) {
            dbUser.last_daily_bonus = todayStr;
            dbUser.play_balance = (Number(dbUser.play_balance) || 0) + 5;
            await dbUser.save();
            io.to(`user_${userId}`).emit('daily_bonus_claimed', { amount: 5 });
        }
        res.json({ success: true, data: dbUser });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/wallet/history', async (req, res) => {
    try {
        const user = authFromHeaders(req); 
        if (!user && !req.headers['x-user-id']) return res.status(401).json({ success: false });
        const userId = user ? String(user.id) : String(req.headers['x-user-id']);
        const history = await Transaction.find({ user_id: userId }).sort({ created: -1 }).limit(50).lean();
        res.json({ success: true, data: history });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/wallet/withdraw-request', async (req, res) => {
    try {
        const user = authFromHeaders(req); if (!user) return res.status(401).json({ success: false });
        const amt = Number(req.body.amount); const phone = String(req.body.phone || '').trim();
        if (!Number.isFinite(amt) || amt < 100) return res.status(400).json({ success: false, error: 'Min 100 ETB' });
        const result = await User.findOneAndUpdate({ id: String(user.id), win_balance: { $gte: amt } }, { $inc: { win_balance: -amt } }, { new: true });
        if (!result) return res.status(400).json({ success: false, error: 'Insufficient win balance' });
        const txnId = 'wdr_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
        await Transaction.create({ id: txnId, type: 'withdrawal', user_id: String(user.id), user_name: result.name || 'Unknown', amount: amt, method: 'telebirr', phone, status: 'pending', created: new Date().toISOString(), notified: false });
        io.to(`user_${user.id}`).emit('wallet_updated', {});
        res.json({ success: true, data: { txnId } });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/leaderboard', async (req, res) => { try { const top = await User.find().sort({ win_balance: -1 }).limit(10).select({ name: 1, win_balance: 1, _id: 0 }).lean(); res.json({ success: true, data: top }); } catch (e) { res.status(500).json({ success: false }); } });

app.post('/api/bot/create-txn', async (req, res) => {
    try {
        const { type, user_id, user_name, amount, method, phone, reference } = req.body;
        const amt = Number(amount);
        if (type === 'deposit' && reference) {
            const existingTxn = await Transaction.findOne({ type: 'deposit', reference: reference });
            if (existingTxn) return res.status(400).json({ success: false, error: 'This Transaction ID has already been submitted!' });
        }
        const txnId = (type === 'deposit' ? 'dep_' : 'wdr_') + Date.now();
        await Transaction.create({ id: txnId, type, user_id: String(user_id), user_name: user_name || 'Unknown', amount: amt, method: method || 'telebirr', reference: reference || '', phone: phone || '', status: 'pending', created: new Date().toISOString() });
        io.to(`user_${user_id}`).emit('wallet_updated', {});
        res.json({ success: true, txnId });
    } catch (e) { res.status(500).json({ success: false, error: e.message }); }
});

io.on('connection', (socket) => {
    socket.on('join_room', (payload) => {
        socket.join('abisinya_global_room');
        let userId = null;
        if (payload?.initData && BOT_TOKEN) { const tgUser = verifyTelegramInitData(payload.initData, BOT_TOKEN); if (tgUser) userId = String(tgUser.id); }
        if (!userId && payload?.clientId) userId = String(payload.clientId);
        socket.verifiedId = userId; if (userId) socket.join(`user_${userId}`);
        const myCards = [];
        if (socket.verifiedId) {
            for (const [num, data] of Object.entries(gameState.takenCards)) {
                if (String(data.userId) === String(socket.verifiedId)) myCards.push(Number(num));
            }
        }
        const totalCards = Object.keys(gameState.takenCards).length;
        socket.emit('init_state', {
            phase: gameState.phase, takenCards: Object.keys(gameState.takenCards).map(Number), myCards,
            calledNumbers: gameState.calledNumbers, remainingTime, currentCall: gameState.currentCall,
            maxCards: gameState.settings.maxCards, totalPlayers: gameState.settings.visualPlayers + totalCards, totalCards
        });
    });

    socket.on('select_card', async (data) => {
        try {
            if (!socket.verifiedId) return socket.emit('card_error', { message: 'ያልተረጋገጠ ተጠቃሚ' });
            if (gameState.phase !== 'waiting' && gameState.phase !== 'countdown') return socket.emit('card_error', { message: 'ጨዋታ ተጀምሯል' });
            const cardNum = Number(data?.cardNum);
            if (!cardNum || isNaN(cardNum)) return;

            if (data.action === 'select') {
                if (gameState.takenCards[cardNum]) {
                    return socket.emit('card_error', { message: '❌ ይህ ካርቴላ በሌላ ተጫዋች ተይዟል!' });
                }
                let updated = await User.findOneAndUpdate({ id: String(socket.verifiedId), play_balance: { $gte: CARD_PRICE } }, { $inc: { play_balance: -CARD_PRICE } }, { new: true });
                if (!updated) return socket.emit('card_error', { message: '❌ ቀሪ ሂሳብ በቂ አይደለም!' });
                
                gameState.takenCards[cardNum] = { userId: socket.verifiedId, isBot: false }; 
                socket.emit('wallet_updated', {});

                const cardCols = getCardCols(cardNum);
                cardCols.forEach(col => {
                    col.forEach(num => {
                        if (num !== 'FREE') {
                            if (!gameState.numberToCardsMap[num]) gameState.numberToCardsMap[num] = new Set();
                            gameState.numberToCardsMap[num].add(cardNum);
                        }
                    });
                });

            } else if (data.action === 'deselect') {
                if (gameState.takenCards[cardNum] && gameState.takenCards[cardNum].userId === socket.verifiedId) { 
                    delete gameState.takenCards[cardNum]; 
                    await User.updateOne({ id: String(socket.verifiedId) }, { $inc: { play_balance: CARD_PRICE } }); 
                    socket.emit('wallet_updated', {}); 

                    const cardCols = getCardCols(cardNum);
                    cardCols.forEach(col => {
                        col.forEach(num => {
                            if (num !== 'FREE' && gameState.numberToCardsMap[num]) {
                                gameState.numberToCardsMap[num].delete(cardNum);
                            }
                        });
                    });
                }
            }
            const totalCards = Object.keys(gameState.takenCards).length;
            io.emit('sync_taken_cards', { takenCards: Object.keys(gameState.takenCards).map(Number), totalPlayers: gameState.settings.visualPlayers + totalCards, totalCards });
        } catch (err) { socket.emit('card_error', { message: 'ሰርቨር ስህተት' }); }
    });

    socket.on('disconnect', () => {
        socket.removeAllListeners();
        if (socket.verifiedId) socket.leave(`user_${socket.verifiedId}`);
    });
});

async function checkForAutoWinner(newNumber) {
    if (isEndingRound || gameState.phase !== 'calling') return false;
    const potentialCards = gameState.numberToCardsMap[newNumber];
    if (!potentialCards || potentialCards.size === 0) return false;

    let potentialWinners = [];
    
    for (const cardNum of potentialCards) {
        const data = gameState.takenCards[cardNum];
        if (!data) continue;
        
        const win = checkWinningLine(cardNum, gameState.calledNumbers);
        if (win) {
            if (data.isBot) {
                const chance = Math.random() * 100;
                if (chance > gameState.settings.botWinRate) continue; 
            }
            potentialWinners.push({ cardNum: Number(cardNum), userId: data.userId, isBot: !!data.isBot, name: data.isBot ? data.botName : null, win });
        }
    }
    
    if (potentialWinners.length === 0) return false;
    
    const realUserIds = [...new Set(potentialWinners.filter(p => !p.isBot).map(p => p.userId))];
    const users = await User.find({ id: { $in: realUserIds } }, { id: 1, name: 1 }).lean();
    const userMap = new Map(users.map(u => [u.id, u.name]));
    
    roundWinners = potentialWinners.map(p => ({
        id: p.userId, name: p.isBot ? p.name : (userMap.get(p.userId) || 'Player'), cardNum: p.cardNum,
        isBot: p.isBot, winDesc: p.win.desc, winType: p.win.type, winIndex: p.win.index, allLines: [p.win]
    }));
    
    isEndingRound = true; gameState.phase = 'claiming';
    if (callInterval) { clearInterval(callInterval); callInterval = null; }
    if (gameTimerInterval) { clearInterval(gameTimerInterval); gameTimerInterval = null; }
    return true;
}

function startRound() {
    if (!gameState.isRunning) return;
    if (gameTimerInterval) clearInterval(gameTimerInterval); 
    if (callInterval) clearInterval(callInterval); 
    if (autoRestartTimer) clearTimeout(autoRestartTimer); 
    gameState.phase = 'countdown'; gameState.currentCall = null; gameState.calledNumbers = []; 
    roundWinners = []; isEndingRound = false; 
    remainingTime = gameState.settings.countdownTime || 50;
    
    io.emit('phase_change', { phase: 'countdown' }); io.emit('timer_tick', { remaining: remainingTime });
    
    setTimeout(() => { if(gameState.phase === 'countdown') spawnBots(); }, 10000);
    
    gameTimerInterval = setInterval(() => {
        if (!gameState.isRunning) return;
        remainingTime--; io.emit('timer_tick', { remaining: remainingTime });
        if (remainingTime <= 0) {
            const totalCards = Object.keys(gameState.takenCards).length;
            if (totalCards < 3) { 
                remainingTime = gameState.settings.countdownTime || 50; 
                io.emit('timer_tick', { remaining: remainingTime }); 
                io.emit('game_status_msg', { message: 'ቢያንስ 3 ካርቴላ ያስፈልጋል! ሰዓቱ እንደገና ተጀምሯል።' }); return; 
            }
            clearInterval(gameTimerInterval); gameTimerInterval = null; 
            gameState.phase = 'calling'; io.emit('phase_change', { phase: 'calling' });
            if (gameState.isAutoOn) {
                callInterval = setInterval(async () => {
                    if (gameState.phase !== 'calling' || isEndingRound) return;
                    if (gameState.calledNumbers.length >= 75) { clearInterval(callInterval); callInterval = null; endRound([]); return; }
                    let num; do { num = Math.floor(Math.random() * 75) + 1; } while (gameState.calledNumbers.includes(num));
                    gameState.calledNumbers.push(num); gameState.currentCall = num;
                    io.emit('new_number_called', { number: num, allCalled: gameState.calledNumbers });
                    const winnerFound = await checkForAutoWinner(num);
                    if (winnerFound) { clearInterval(callInterval); callInterval = null; await endRound(roundWinners); }
                }, gameState.settings.callInterval * 1000);
            }
        }
    }, 1000);
}

async function endRound(winnersData) {
    if (gameState.phase === 'gameover') return; 
    isEndingRound = true; gameState.phase = 'gameover';
    if (gameTimerInterval) { clearInterval(gameTimerInterval); gameTimerInterval = null; }
    if (callInterval) { clearInterval(callInterval); callInterval = null; }
    try {
        const realPlayers = [...new Set(Object.values(gameState.takenCards).filter(c => !c.isBot).map(c => c.userId))];
        const totalCards = Object.keys(gameState.takenCards).length; 
        const totalPrize = totalCards * DERASH_PER_CARD; 
        const promises = [];
        
        if (realPlayers.length > 0) promises.push(User.updateMany({ id: { $in: realPlayers } }, { $inc: { total_games: 1 } }));
        
        if (!winnersData || winnersData.length === 0) {
            await Promise.all(promises); io.emit('reset_game');
            autoRestartTimer = setTimeout(() => {
                gameState.takenCards = {}; gameState.phase = 'waiting'; 
                gameState.calledNumbers = []; gameState.currentCall = null; roundWinners = []; isEndingRound = false;
                if (gameState.isRunning) startRound();
            }, 3000); return;
        }
        
        const realWinners = winnersData.filter(w => !w.isBot);
        if (realWinners.length > 0) {
            const prizePerWinner = Math.floor(totalPrize / winnersData.length); 
            const winnerIds = realWinners.map(w => String(w.id));
            promises.push(User.updateMany({ id: { $in: winnerIds } }, { $inc: { win_balance: prizePerWinner, total_wins: 1 } }));
        }

        promises.push(GameHistory.create({
            gameId: 'game_' + Date.now(), winners: winnersData.map(w => ({ id: w.id, name: w.name, cardNum: w.cardNum, prize: Math.floor(totalPrize / winnersData.length) })),
            totalPrize, totalPlayers: totalCards, calledNumbers: gameState.calledNumbers
        }));
        await Promise.all(promises);
        
        for (const w of realWinners) io.to(`user_${w.id}`).emit('wallet_updated', {});
        
        const lastCall = gameState.calledNumbers[gameState.calledNumbers.length - 1]; 
        io.emit('game_over', { reason: 'bingo', winners: winnersData, totalPrize, prizePerWinner: Math.floor(totalPrize / winnersData.length), lastCall, calledNumbers: gameState.calledNumbers });
        
        autoRestartTimer = setTimeout(() => {
            gameState.takenCards = {}; gameState.phase = 'waiting'; 
            gameState.calledNumbers = []; gameState.currentCall = null; roundWinners = []; isEndingRound = false;
            io.emit('reset_game'); if (gameState.isRunning) startRound();
        }, 10000);
    } catch (err) { console.error('❌ endRound error:', err); }
}

server.listen(PORT, () => { console.log(`🚀 Server running on port ${PORT}`); });
