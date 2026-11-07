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
.then(() => console.log('✅ MongoDB connected'))
.catch(err => { console.error('❌ DB Error:', err.message); process.exit(1); });

/* ─── SCHEMAS ─── */
const UserSchema = new mongoose.Schema({
    id: { type: String, index: true, unique: true }, name: String, username: String, phone: String,
    play_balance: { type: Number, default: 20, index: true }, win_balance: { type: Number, default: 0, index: true },
    referral_balance: { type: Number, default: 0 },
    total_games: { type: Number, default: 0 }, total_wins: { type: Number, default: 0 },
    referral_code: String, referred_by: { type: String, default: null, index: true },
    pending_referrer: { type: String, default: null }, registered: { type: Boolean, default: false, index: true },
    lang: String, registered_at: { type: String, default: () => new Date().toISOString(), index: true }
}, { collection: 'users' });

const TransactionSchema = new mongoose.Schema({
    id: { type: String, index: true, unique: true }, type: { type: String, index: true },
    user_id: { type: String, index: true }, user_name: String, amount: Number,
    method: String, reference: { type: String, index: true }, phone: String,
    status: { type: String, index: true }, created: { type: String, index: true }, notified: Boolean
}, { collection: 'transactions' });

const GameHistorySchema = new mongoose.Schema({
    gameId: String, winners: [{ id: String, name: String, cardNum: Number, prize: Number }],
    totalPrize: Number, totalPlayers: Number, calledNumbers: [Number], createdAt: { type: Date, default: Date.now }
}, { collection: 'game_history' });

const SettingsSchema = new mongoose.Schema({
    key: { type: String, default: 'payment_accounts', unique: true },
    telebirr_number: { type: String, default: '0968940123' },
    telebirr_name: { type: String, default: 'tazebew' },
    cbe_number: { type: String, default: '1000390803005' },
    cbe_name: { type: String, default: 'tazebew' },
    enable_cbe: { type: Boolean, default: true },
    maxCards: { type: Number, default: 1000 }
}, { collection: 'settings' });

const User = mongoose.model('User', UserSchema);
const Transaction = mongoose.model('Transaction', TransactionSchema);
const GameHistory = mongoose.model('GameHistory', GameHistorySchema);
const Settings = mongoose.model('Settings', SettingsSchema);

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
   GAME LOGIC (MUST MATCH CLIENT EXACTLY)
   ═══════════════════════════════════════════════════════════ */
function mulberry32(a) {
    return function() {
        a |= 0; a = a + 0x6D2B79F5 | 0;
        var t = Math.imul(a ^ a >>> 15, 1 | a);
        t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
        return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
}

const cardCache = new Map();

function getCardCols(cardNum) {
    if (cardCache.has(cardNum)) return cardCache.get(cardNum);
    const cols = [[], [], [], [], []];
    const seedBase = cardNum * 100;
    for (let c = 0; c < 5; c++) {
        const min = c * 15 + 1, max = c * 15 + 15;
        const avail = [];
        for (let n = min; n <= max; n++) avail.push(n);
        const seed = seedBase + c;
        const rand = mulberry32(seed);
        for (let i = avail.length - 1; i > 0; i--) {
            const j = Math.floor(rand() * (i + 1));
            [avail[i], avail[j]] = [avail[j], avail[i]];
        }
        cols[c] = avail.slice(0, 5); 
    }
    cols[2][2] = 'FREE';
    cardCache.set(cardNum, cols);
    return cols;
}

function checkWinningLine(cardNum, calledNumbers) {
    const n = Number(cardNum);
    if (!Number.isFinite(n) || n < 1 || calledNumbers.length === 0) return null;
    const cols = getCardCols(n);
    const calledSet = new Set(calledNumbers);
    const m = [];
    
    for (let r = 0; r < 5; r++) {
        const row = [];
        for (let c = 0; c < 5; c++) {
            const val = cols[c][r];
            row.push(val === 'FREE' || calledSet.has(val));
        }
        m.push(row);
    }

    for (let r = 0; r < 5; r++) {
        if (m[r].every(v => v)) return { type: 'row', index: r, desc: 'Row ' + (r + 1) };
    }
    for (let c = 0; c < 5; c++) {
        if (m.every(row => row[c])) return { type: 'col', index: c, desc: 'Col ' + (c + 1) };
    }
    let d1 = true; for (let i = 0; i < 5; i++) if (!m[i][i]) { d1 = false; break; }
    if (d1) return { type: 'diag1', desc: 'Diag 1' };
    
    let d2 = true; for (let i = 0; i < 5; i++) if (!m[i][4 - i]) { d2 = false; break; }
    if (d2) return { type: 'diag2', desc: 'Diag 2' };
    
    if (m[0][0] && m[0][4] && m[4][0] && m[4][4]) return { type: 'corners', desc: '4 Corners' };
    return null;
}

const gameState = {
    phase: 'waiting', currentCall: null, calledNumbers: [], takenCards: {},
    isAutoOn: true, isRunning: false, settings: { callInterval: 5, maxCards: 1000 }
};
let gameTimerInterval = null, callInterval = null, autoRestartTimer = null;
let remainingTime = 50, roundWinners = [], isEndingRound = false;
const CARD_PRICE = 10, DERASH_PER_CARD = 8;

/* ─── ADMIN & API ─── */
app.get('/api/settings', async (req, res) => {
    try {
        let settings = await Settings.findOne({ key: 'payment_accounts' }).lean();
        if (!settings) settings = await Settings.create({ key: 'payment_accounts' });
        if (settings.maxCards) gameState.settings.maxCards = settings.maxCards;
        res.json({ success: true, data: settings });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/settings', adminAuth, async (req, res) => {
    try {
        const { telebirr_number, telebirr_name, cbe_number, cbe_name, enable_cbe, maxCards } = req.body;
        const update = {};
        if (telebirr_number) update.telebirr_number = telebirr_number;
        if (telebirr_name) update.telebirr_name = telebirr_name;
        if (cbe_number) update.cbe_number = cbe_number;
        if (cbe_name) update.cbe_name = cbe_name;
        if (typeof enable_cbe === 'boolean') update.enable_cbe = enable_cbe;
        if (maxCards) { update.maxCards = Number(maxCards); gameState.settings.maxCards = Number(maxCards); io.emit('update_max_cards', { maxCards: Number(maxCards) }); }
        const updatedSettings = await Settings.findOneAndUpdate({ key: 'payment_accounts' }, update, { upsert: true, new: true });
        io.emit('settings_updated', { settings: updatedSettings });
        res.json({ success: true });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/admin/dashboard', adminAuth, async (req, res) => {
    try {
        const [totalPlayers, pendingDeposits, pendingWithdrawals, depAgg, wdAgg] = await Promise.all([
            User.countDocuments(),
            Transaction.countDocuments({ type: 'deposit', status: 'pending' }),
            Transaction.countDocuments({ type: 'withdrawal', status: 'pending' }),
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

app.post('/api/admin/users/:id/balance', adminAuth, async (req, res) => {
    try {
        const { id } = req.params; const { play_balance, win_balance } = req.body;
        const update = {};
        if (typeof play_balance === 'number') update.play_balance = play_balance;
        if (typeof win_balance === 'number') update.win_balance = win_balance;
        if (!Object.keys(update).length) return res.status(400).json({ success: false });
        const user = await User.findOneAndUpdate({ id: String(id) }, { $set: update }, { new: true, lean: true });
        if (!user) return res.status(404).json({ success: false });
        io.to(`user_${id}`).emit('wallet_updated', {});
        res.json({ success: true, data: user });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/admin/transactions', adminAuth, async (req, res) => {
    try {
        const filter = {};
        if (req.query.type) filter.type = req.query.type;
        if (req.query.method) filter.method = req.query.method;
        const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
        filter.$or = [{ status: 'pending' }, { status: { $in: ['approved', 'rejected'] }, created: { $gte: oneHourAgo } }];
        const txns = await Transaction.find(filter).sort({ created: -1 }).limit(200).lean();
        res.json({ success: true, data: txns });
    } catch (e) { res.status(500).json({ success: false }); }
});

// ✅ Approved API (Added Notification)
app.post('/api/admin/transactions/:id/approve', adminAuth, async (req, res) => {
    try {
        const txn = await Transaction.findOneAndUpdate({ id: req.params.id, status: 'pending' }, { $set: { status: 'approved' } }, { new: true });
        if (!txn) return res.status(400).json({ success: false });
        
        let msgText = '';
        if (txn.type === 'deposit') { 
            await User.updateOne({ id: String(txn.user_id) }, { $inc: { play_balance: txn.amount } }); 
            io.to(`user_${txn.user_id}`).emit('wallet_updated', {}); 
            msgText = `✅ <b>Deposit Approved!</b>\n\nYour deposit of ${txn.amount} ETB has been approved and added to your Play Wallet.`;
        } else if (txn.type === 'withdrawal') {
            msgText = `✅ <b>Withdrawal Approved!</b>\n\nYour withdrawal of ${txn.amount} ETB has been approved and is on its way to your account.`;
        }

        if (msgText) {
            fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: txn.user_id, text: msgText, parse_mode: 'HTML' })
            }).catch(err => console.error('TG notify error', err));
        }

        res.json({ success: true });
    } catch (e) { res.status(500).json({ success: false }); }
});

// ✅ Reject API (Added Notification & Balance Refund for Withdraw)
app.post('/api/admin/transactions/:id/reject', adminAuth, async (req, res) => {
    try {
        const txn = await Transaction.findOneAndUpdate({ id: req.params.id, status: 'pending' }, { $set: { status: 'rejected' } }, { new: true });
        if (!txn) return res.status(400).json({ success: false });
        
        let msgText = '';
        if (txn.type === 'withdrawal') { 
            await User.updateOne({ id: String(txn.user_id) }, { $inc: { win_balance: txn.amount } }); 
            io.to(`user_${txn.user_id}`).emit('wallet_updated', {}); 
            msgText = `❌ <b>Withdrawal Rejected!</b>\n\nYour withdrawal request of ${txn.amount} ETB was rejected. The amount has been refunded to your Win Wallet.`;
        } else if (txn.type === 'deposit') {
            msgText = `❌ <b>Deposit Rejected!</b>\n\nYour deposit request of ${txn.amount} ETB was rejected. Please contact support if you believe this is an error.`;
        }

        if (msgText) {
            fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: txn.user_id, text: msgText, parse_mode: 'HTML' })
            }).catch(err => console.error('TG notify error', err));
        }

        res.json({ success: true });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/giveaway', adminAuth, async (req, res) => {
    try {
        const { amount, target, userId } = req.body;
        const amt = Number(amount);
        if (!amt || amt <= 0) return res.status(400).json({ success: false, error: 'Invalid amount' });

        if (target === 'all') {
            await User.updateMany({}, { $inc: { play_balance: amt } });
            io.emit('wallet_updated', {}); 
            res.json({ success: true, message: 'Sent to all users' });
        } else {
            const user = await User.findOneAndUpdate({ id: String(userId) }, { $inc: { play_balance: amt } }, { new: true });
            if (!user) return res.status(404).json({ success: false, error: 'User not found' });
            io.to(`user_${userId}`).emit('wallet_updated', {});
            res.json({ success: true });
        }
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/broadcast', adminAuth, async (req, res) => {
    try {
        const { message } = req.body;
        if (!message) return res.status(400).json({ success: false, error: 'Message required' });

        const users = await User.find({}, { id: 1 }).lean();
        
        users.forEach(async (u) => {
            try {
                await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: u.id, text: message, parse_mode: 'HTML' })
                });
            } catch (err) { }
        });

        res.json({ success: true, count: users.length });
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

app.get('/api/wallet/me', async (req, res) => {
    try {
        const user = authFromHeaders(req);
        if (!user && !req.headers['x-user-id']) return res.status(401).json({ success: false });
        const userId = user ? String(user.id) : String(req.headers['x-user-id']);
        
        const dbUser = await User.findOne({ id: userId }).lean();
        if (!dbUser) return res.json({ success: true, data: { play_balance: 0, win_balance: 0, total_games: 0, total_wins: 0, phone: "", referral_balance: 0 } });
        dbUser.play_balance = Number(dbUser.play_balance) || 0; 
        dbUser.win_balance = Number(dbUser.win_balance) || 0;
        dbUser.referral_balance = Number(dbUser.referral_balance) || 0;
        res.json({ success: true, data: dbUser });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/wallet/history', async (req, res) => {
    try {
        const user = authFromHeaders(req); if (!user) return res.status(401).json({ success: false });
        const history = await Transaction.find({ user_id: String(user.id) }).sort({ created: -1 }).limit(50).lean();
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

app.get('/api/admin/game-history', adminAuth, async (req, res) => {
    try {
        const history = await GameHistory.find({}).sort({ createdAt: -1 }).limit(50).lean();
        res.json({ success: true, data: history });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/admin/game-status', adminAuth, async (req, res) => {
    try {
        const playerIds = [...new Set(Object.values(gameState.takenCards).map(c => c.userId))];
        const players = await User.find({ id: { $in: playerIds } }, { id: 1, name: 1 }).lean();
        const playerMap = new Map(players.map(p => [p.id, p.name]));
        const takenCardsDetails = {};
        for (const [card, data] of Object.entries(gameState.takenCards)) takenCardsDetails[card] = { userId: data.userId, userName: playerMap.get(data.userId) || "Unknown" };
        res.json({ success: true, data: { ...gameState, takenCardsDetails, totalPlayers: playerIds.length, totalCards: Object.keys(gameState.takenCards).length } });
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
    let num; do { num = Math.floor(Math.random() * 75) + 1; } while (gameState.calledNumbers.includes(num));
    gameState.calledNumbers.push(num);
    gameState.currentCall = num;
    io.emit('new_number_called', { number: num, allCalled: gameState.calledNumbers });
    const winnerFound = await checkForAutoWinner();
    if (winnerFound) await endRound(roundWinners);
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
            gameState.calledNumbers.push(num);
            gameState.currentCall = num;
            io.emit('new_number_called', { number: num, allCalled: gameState.calledNumbers });
            const winnerFound = await checkForAutoWinner();
            if (winnerFound) { clearInterval(callInterval); callInterval = null; await endRound(roundWinners); }
        }, gameState.settings.callInterval * 1000);
    }
    res.json({ success: true });
});

app.post('/api/user/phone', async (req, res) => {
    try {
        const { user_id, phone, name } = req.body;
        if (!user_id || !phone) return res.status(400).json({ success: false, error: 'Missing fields' });
        await User.findOneAndUpdate({ id: String(user_id) }, { $set: { phone: String(phone), name: name || 'Player' } }, { upsert: true });
        io.to(`user_${user_id}`).emit('wallet_updated', {});
        res.json({ success: true });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/user/referral', async (req, res) => {
    try {
        const { new_user_id, referrer_id } = req.body;
        if (!new_user_id || !referrer_id || new_user_id === referrer_id) {
            return res.status(400).json({ success: false, error: 'Invalid referral' });
        }

        const newUser = await User.findOne({ id: String(new_user_id) });
        if (newUser && newUser.referred_by) return res.status(400).json({ success: false, error: 'Already referred' });

        const referrer = await User.findOne({ id: String(referrer_id) });
        if (!referrer) return res.status(404).json({ success: false, error: 'Referrer not found' });

        await User.updateOne({ id: String(referrer_id) }, { $inc: { play_balance: 30, referral_balance: 30 } });
        
        await User.findOneAndUpdate(
            { id: String(new_user_id) },
            { $inc: { play_balance: 20 }, $set: { referred_by: String(referrer_id) } },
            { upsert: true }
        );

        io.to(`user_${referrer_id}`).emit('wallet_updated', {});
        io.to(`user_${new_user_id}`).emit('wallet_updated', {});

        res.json({ success: true, message: 'Referral bonus applied' });
    } catch (e) {
        console.error('Referral error:', e);
        res.status(500).json({ success: false, error: e.message });
    }
});

app.post('/api/bot/create-txn', async (req, res) => {
    try {
        const { type, user_id, user_name, amount, method, phone, reference } = req.body;
        if (!type || !user_id || !amount) return res.status(400).json({ success: false, error: 'Missing required fields' });
        if (!['deposit', 'withdrawal'].includes(type)) return res.status(400).json({ success: false, error: 'Invalid type' });
        const amt = Number(amount);
        if (!Number.isFinite(amt) || amt <= 0) return res.status(400).json({ success: false, error: 'Invalid amount' });

        if (type === 'withdrawal') {
            const user = await User.findOne({ id: String(user_id) });
            if (!user || Number(user.win_balance) < amt) return res.status(400).json({ success: false, error: 'Insufficient win balance' });
            await User.updateOne({ id: String(user_id) }, { $inc: { win_balance: -amt } });
        }

        const txnId = (type === 'deposit' ? 'dep_' : 'wdr_') + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
        await Transaction.create({
            id: txnId, type, user_id: String(user_id), user_name: user_name || 'Unknown',
            amount: amt, method: method || 'telebirr', reference: reference || '', phone: phone || '',
            status: 'pending', created: new Date().toISOString(), notified: false
        });
        io.to(`user_${user_id}`).emit('wallet_updated', {});
        res.json({ success: true, txnId });
    } catch (e) { res.status(500).json({ success: false, error: e.message }); }
});

io.on('connection', (socket) => {
    socket.on('join_room', (payload) => {
        socket.join('abisinya_global_room');
        let userId = null;
        if (payload?.initData && BOT_TOKEN) { const tgUser = verifyTelegramInitData(payload.initData, BOT_TOKEN); if (tgUser) userId = String(tgUser.id); }
        if (!userId && REQUIRE_TG_AUTH) { socket.emit('auth_error'); return socket.disconnect(); }
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
            maxCards: gameState.settings.maxCards, totalPlayers: totalCards, totalCards
        });
    });

    socket.on('select_card', async (data) => {
        try {
            if (!socket.verifiedId) return socket.emit('card_error', { message: 'ያልተረጋገጠ ተጠቃሚ' });
            if (gameState.phase !== 'waiting' && gameState.phase !== 'countdown') return socket.emit('card_error', { message: 'ጨዋታ ተጀምሯል' });
            const cardNum = Number(data?.cardNum);
            
            if (data.action === 'select') {
                if (gameState.takenCards[cardNum]) {
                    if (gameState.takenCards[cardNum].userId === socket.verifiedId) return;
                    return socket.emit('card_error', { message: '❌ ይህ ካርቴላ በሌላ ተጫዋች ተይዟል!' });
                }
                let updated = await User.findOneAndUpdate({ id: String(socket.verifiedId), play_balance: { $gte: CARD_PRICE } }, { $inc: { play_balance: -CARD_PRICE } }, { new: true });
                if (!updated) updated = await User.findOneAndUpdate({ id: String(socket.verifiedId), win_balance: { $gte: CARD_PRICE } }, { $inc: { win_balance: -CARD_PRICE } }, { new: true });
                if (!updated) updated = await User.findOneAndUpdate({ id: String(socket.verifiedId), referral_balance: { $gte: CARD_PRICE } }, { $inc: { referral_balance: -CARD_PRICE } }, { new: true });
                if (!updated) return socket.emit('card_error', { message: '❌ ቀሪ ሂሳብ በቂ አይደለም!' });
                
                gameState.takenCards[cardNum] = { userId: socket.verifiedId }; 
                socket.emit('wallet_updated', {});
            } else if (data.action === 'deselect') {
                if (gameState.takenCards[cardNum] && gameState.takenCards[cardNum].userId === socket.verifiedId) { 
                    delete gameState.takenCards[cardNum]; 
                    await User.updateOne({ id: String(socket.verifiedId) }, { $inc: { play_balance: CARD_PRICE } }); 
                    socket.emit('wallet_updated', {}); 
                }
            }
            const totalCards = Object.keys(gameState.takenCards).length;
            io.emit('sync_taken_cards', { takenCards: Object.keys(gameState.takenCards).map(Number), totalPlayers: totalCards, totalCards });
        } catch (err) { socket.emit('card_error', { message: 'ሰርቨር ስህተት' }); }
    });
});

async function checkForAutoWinner() {
    if (isEndingRound || gameState.phase !== 'calling') return false;
    const entries = Object.entries(gameState.takenCards); 
    if (entries.length === 0) return false;
    
    let firstWinner = null;
    for (const [cardNum, data] of entries) {
        const win = checkWinningLine(cardNum, gameState.calledNumbers);
        if (win) {
            firstWinner = { cardNum: Number(cardNum), userId: data.userId, win };
            break;
        }
    }
    
    if (!firstWinner) return false;
    
    const user = await User.findOne({ id: firstWinner.userId }, { id: 1, name: 1 }).lean();
    const winnerName = user?.name || 'Player';
    
    roundWinners = [{ 
        id: firstWinner.userId, name: winnerName, cardNum: firstWinner.cardNum, 
        winDesc: firstWinner.win.desc, winType: firstWinner.win.type, winIndex: firstWinner.win.index, 
        allLines: [firstWinner.win] 
    }];
    
    isEndingRound = true; 
    gameState.phase = 'claiming';
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
    roundWinners = []; isEndingRound = false; remainingTime = 50;
    
    io.emit('phase_change', { phase: 'countdown' }); 
    io.emit('timer_tick', { remaining: remainingTime });
    
    gameTimerInterval = setInterval(() => {
        if (!gameState.isRunning) return;
        remainingTime--; io.emit('timer_tick', { remaining: remainingTime });
        if (remainingTime <= 0) {
            const totalCards = Object.keys(gameState.takenCards).length;
            if (totalCards < 3) { 
                remainingTime = 50; 
                io.emit('timer_tick', { remaining: remainingTime }); 
                io.emit('game_status_msg', { message: 'ቢያንስ 3 ካርቴላ ያስፈልጋል! ሰዓቱ እንደገና ተጀምሯል።' }); 
                return; 
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
                    
                    const winnerFound = await checkForAutoWinner();
                    if (winnerFound) {
                        clearInterval(callInterval); callInterval = null;
                        await endRound(roundWinners);
                    }
                }, gameState.settings.callInterval * 1000);
            }
        }
    }, 1000);
}

async function endRound(winnersData) {
    if (gameState.phase === 'gameover') return; 
    isEndingRound = true;
    gameState.phase = 'gameover';
    if (gameTimerInterval) { clearInterval(gameTimerInterval); gameTimerInterval = null; }
    if (callInterval) { clearInterval(callInterval); callInterval = null; }
    
    try {
        const playersInRound = [...new Set(Object.values(gameState.takenCards).map(c => c.userId))];
        const totalCards = Object.keys(gameState.takenCards).length; 
        const totalPrize = totalCards * DERASH_PER_CARD; 
        const promises = [];
        
        if (playersInRound.length > 0) promises.push(User.updateMany({ id: { $in: playersInRound } }, { $inc: { total_games: 1 } }));
        
        if (!winnersData || winnersData.length === 0) {
            await Promise.all(promises); io.emit('reset_game');
            autoRestartTimer = setTimeout(() => {
                autoRestartTimer = null; gameState.takenCards = {}; gameState.phase = 'waiting'; 
                gameState.calledNumbers = []; gameState.currentCall = null; roundWinners = []; isEndingRound = false;
                if (gameState.isRunning) startRound();
            }, 3000); 
            return;
        }
        
        const prizePerWinner = Math.floor(totalPrize / winnersData.length); 
        const winnerIds = winnersData.map(w => String(w.id));
        
        promises.push(User.updateMany({ id: { $in: winnerIds } }, { $inc: { win_balance: prizePerWinner, total_wins: 1 } }));
        
        promises.push(GameHistory.create({
            gameId: 'game_' + Date.now(),
            winners: winnersData.map(w => ({ id: w.id, name: w.name, cardNum: w.cardNum, prize: prizePerWinner })),
            totalPrize, totalPlayers: totalCards, calledNumbers: gameState.calledNumbers
        }));
        
        await Promise.all(promises);
        
        for (const w of winnersData) io.to(`user_${w.id}`).emit('wallet_updated', {});
        
        const lastCall = gameState.calledNumbers[gameState.calledNumbers.length - 1]; 
        const firstWinner = winnersData[0];
        
        io.emit('game_over', { 
            reason: 'bingo', winners: winnersData, totalPrize, prizePerWinner, 
            winningCard: firstWinner.cardNum, lastCall, calledNumbers: gameState.calledNumbers 
        });
        
        autoRestartTimer = setTimeout(() => {
            autoRestartTimer = null; gameState.takenCards = {}; gameState.phase = 'waiting'; 
            gameState.calledNumbers = []; gameState.currentCall = null; roundWinners = []; isEndingRound = false;
            io.emit('reset_game'); 
            if (gameState.isRunning) startRound();
        }, 10000);
    } catch (err) { console.error('❌ endRound error:', err); }
}

server.listen(PORT, () => { console.log(`🚀 Server running on port ${PORT}`); });
