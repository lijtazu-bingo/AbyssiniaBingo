const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const crypto = require('crypto');
const mongoose = require('mongoose');
const compression = require('compression');
const helmet = require('helmet');
const morgan = require('morgan');
const rateLimit = require('express-rate-limit');
require('express-async-errors');
require('dotenv').config();

const dns = require('dns');
dns.setServers(['8.8.8.8', '1.1.1.1']);

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: '*' }, perMessageDeflate: { threshold: 1024 } });
const PORT = process.env.PORT || 3000;

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const MONGODB_URI = process.env.MONGODB_URI;
const ADMIN_USERNAME = process.env.ADMIN_USERNAME || "admin";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "admin123";

if (!BOT_TOKEN || !MONGODB_URI) { console.error('Missing env'); process.exit(1); }

app.use(helmet({ contentSecurityPolicy: false }));
app.use(compression({ level: 6, threshold: 1024 }));
app.use(cors());
app.use(express.json({ limit: '10kb' }));
app.use(morgan('combined'));

const apiLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 300 });
app.use('/api/', apiLimiter);

app.use(express.static('public', { maxAge: '1d' }));

mongoose.connect(MONGODB_URI, { serverSelectionTimeoutMS: 10000, maxPoolSize: 20, dbName: 'abisinya' })
.then(async () => {
    console.log('✅ MongoDB connected');
    const s = await Settings.findOne({ key: 'payment_accounts' }).lean();
    if (s && s.maxCards) gameState.settings.maxCards = s.maxCards;
})
.catch(err => { console.error('❌ DB Error:', err.message); process.exit(1); });

const UserSchema = new mongoose.Schema({
    id: { type: String, index: true, unique: true }, name: String, username: String, phone: String,
    play_balance: { type: Number, default: 20, index: true }, win_balance: { type: Number, default: 0, index: true },
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
    gameId: { type: String, index: true }, winners: [{ id: String, name: String, cardNum: Number, prize: Number }],
    totalPrize: Number, totalPlayers: Number, calledNumbers: [Number], createdAt: { type: Date, default: Date.now }
}, { collection: 'game_history' });

const SettingsSchema = new mongoose.Schema({
    key: { type: String, default: 'payment_accounts', unique: true },
    telebirr_number: { type: String, default: '0968940123' }, telebirr_name: { type: String, default: 'tazebew' },
    cbe_number: { type: String, default: '1000390803005' }, cbe_name: { type: String, default: 'tazebew' },
    enable_cbe: { type: Boolean, default: true }, maxCards: { type: Number, default: 1000 }
}, { collection: 'settings' });

const User = mongoose.model('User', UserSchema);
const Transaction = mongoose.model('Transaction', TransactionSchema);
const GameHistory = mongoose.model('GameHistory', GameHistorySchema);
const Settings = mongoose.model('Settings', SettingsSchema);

function verifyTelegramInitData(initData, botToken) {
    try {
        if (!initData) return null;
        const params = new URLSearchParams(initData); 
        const hash = params.get('hash'); 
        if (!hash) return null;
        params.delete('hash');
        const dataCheckString = Array.from(params.entries()).map(([k, v]) => `${k}=${v}`).sort().join('\n');
        const secretKey = crypto.createHmac('sha256', 'WebAppData').update(botToken).digest();
        const calculatedHash = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');
        if (calculatedHash !== hash) return null;
        const authDate = parseInt(params.get('auth_date')) || 0;
        if (authDate === 0 || (Math.floor(Date.now() / 1000) - authDate) > 86400) return null;
        const userJson = params.get('user'); 
        if (!userJson) return null;
        const userObj = JSON.parse(userJson); 
        return userObj.id ? userObj : null;
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

function mulberry32(a) { return function() { a |= 0; a = a + 0x6D2B79F5 | 0; var t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; } }
const cardCache = new Map();
function getCardCols(cardNum) {
    if (cardCache.has(cardNum)) return cardCache.get(cardNum);
    const cols = [[], [], [], [], []];
    for (let c = 0; c < 5; c++) {
        const min = c * 15 + 1, max = c * 15 + 15; const avail = [];
        for (let n = min; n <= max; n++) avail.push(n);
        let seed = cardNum * 100 + c; let rand = mulberry32(seed);
        for (let i = avail.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [avail[i], avail[j]] = [avail[j], avail[i]]; }
        cols[c] = avail.slice(0, 5).sort((a, b) => a - b);
    }
    cols[2][2] = 'FREE'; cardCache.set(cardNum, cols); return cols;
}

// 🔥 የተስተካከለው የማሸነፊያ ስሌት 🔥
function checkWinningLine(cardNum, calledNumbers) {
    const n = Number(cardNum); 
    if (!Number.isFinite(n) || n < 1 || calledNumbers.length === 0) return null;
    
    const latestCall = calledNumbers[calledNumbers.length - 1];
    const cols = getCardCols(n); 
    const calledSet = new Set(calledNumbers); 
    const m = [];
    
    for (let r = 0; r < 5; r++) { 
        const row = []; 
        for (let c = 0; c < 5; c++) {
            row.push(cols[c][r] === 'FREE' || calledSet.has(cols[c][r])); 
        }
        m.push(row); 
    }
    
    // 1. Horizontal (Rows)
    for (let r = 0; r < 5; r++) { 
        if (m[r][0] && m[r][1] && m[r][2] && m[r][3] && m[r][4]) { 
            let hasL = false; 
            for (let c = 0; c < 5; c++) if (cols[c][r] === latestCall) hasL = true; 
            if (hasL) return { type: 'row', index: r, desc: 'Row ' + (r + 1) }; 
        } 
    }
    
    // 2. Vertical (Columns)
    for (let c = 0; c < 5; c++) { 
        if (m[0][c] && m[1][c] && m[2][c] && m[3][c] && m[4][c]) { 
            let hasL = false; 
            for (let r = 0; r < 5; r++) if (cols[c][r] === latestCall) hasL = true; 
            if (hasL) return { type: 'col', index: c, desc: 'Col ' + (c + 1) }; 
        } 
    }
    
    // 3. Diagonals
    if (m[0][0] && m[1][1] && m[2][2] && m[3][3] && m[4][4]) { 
        let hasL = false; 
        for (let i = 0; i < 5; i++) if (cols[i][i] === latestCall) hasL = true; 
        if (hasL) return { type: 'diag1', desc: 'Diag 1' }; 
    }
    if (m[0][4] && m[1][3] && m[2][2] && m[3][1] && m[4][0]) { 
        let hasL = false; 
        for (let i = 0; i < 5; i++) if (cols[4 - i][i] === latestCall) hasL = true; 
        if (hasL) return { type: 'diag2', desc: 'Diag 2' }; 
    }
    
    // 4. Four Corners
    if (m[0][0] && m[0][4] && m[4][0] && m[4][4]) { 
        let hasL = false; 
        if (cols[0][0] === latestCall) hasL = true; 
        if (cols[4][0] === latestCall) hasL = true; 
        if (cols[0][4] === latestCall) hasL = true; 
        if (cols[4][4] === latestCall) hasL = true; 
        if (hasL) return { type: 'corners', desc: '4 Corners' }; 
    }
    
    return null;
}

const gameState = { phase: 'waiting', currentCall: null, calledNumbers: [], takenCards: {}, isAutoOn: false, isRunning: false, settings: { callInterval: 5, maxCards: 1000 } };
let gameTimerInterval = null, callInterval = null, autoRestartTimer = null, claimTimer = null, remainingTime = 50;
let roundWinners = [], isEndingRound = false;
const CARD_PRICE = 10, DERASH_PER_CARD = 8;

const socketCooldowns = new Map();
function checkSocketRate(socketId, action, cooldownMs = 500) {
    const now = Date.now(); const key = `${socketId}_${action}`;
    const lastTime = socketCooldowns.get(key) || 0;
    if (now - lastTime < cooldownMs) return false;
    socketCooldowns.set(key, now); return true;
}

app.get('/api/settings', async (req, res) => {
    try {
        let settings = await Settings.findOne({ key: 'payment_accounts' }).lean();
        if (!settings) settings = await Settings.create({ key: 'payment_accounts' });
        res.json({ success: true, data: settings });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/wallet/me', async (req, res) => {
    try {
        const user = authFromHeaders(req); 
        if (!user) return res.status(401).json({ success: false });
        
        let dbUser = await User.findOne({ id: String(user.id) }).lean();
        
        if (!dbUser) {
            const newUser = new User({ id: String(user.id), name: ((user.first_name || '') + ' ' + (user.last_name || '')).trim() || 'Player', username: user.username || '', play_balance: 20, win_balance: 0 });
            await newUser.save();
            dbUser = newUser.toObject();
        }
        
        dbUser.play_balance = Number(dbUser.play_balance) || 0; 
        dbUser.win_balance = Number(dbUser.win_balance) || 0;
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
        if (phone.replace(/\D/g, '').length < 9) return res.status(400).json({ success: false, error: 'Invalid phone' });
        const result = await User.findOneAndUpdate({ id: String(user.id), win_balance: { $gte: amt } }, { $inc: { win_balance: -amt } }, { new: true });
        if (!result) return res.status(400).json({ success: false, error: 'Insufficient win balance' });
        const txnId = 'wdr_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
        await Transaction.create({ id: txnId, type: 'withdrawal', user_id: String(user.id), user_name: result.name || 'Unknown', amount: amt, method: 'telebirr', phone, status: 'pending', created: new Date().toISOString(), notified: false });
        io.to(`user_${user.id}`).emit('wallet_updated', {});
        res.json({ success: true, data: { txnId } });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/leaderboard', async (req, res) => { try { const top = await User.find().sort({ win_balance: -1 }).limit(10).select({ name: 1, win_balance: 1, _id: 0 }).lean(); res.json({ success: true, data: top }); } catch (e) { res.status(500).json({ success: false }); } });

io.on('connection', (socket) => {
    socket.on('join_room', (payload) => {
        socket.join('abisinya_global_room');
        let userId = null;
        
        if (payload?.initData && BOT_TOKEN) { 
            const tgUser = verifyTelegramInitData(payload.initData, BOT_TOKEN); 
            if (tgUser) userId = String(tgUser.id); 
        }
        
        if (!userId && payload?.clientId) userId = String(payload.clientId);
        socket.verifiedId = userId; 
        if (userId) socket.join(`user_${userId}`);
        
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
            maxCards: gameState.settings.maxCards, totalPlayers: totalCards, totalCards: totalCards
        });
    });

    socket.on('select_card', async (data) => {
        if (!checkSocketRate(socket.id, 'select_card', 500)) return socket.emit('card_error', { message: 'እባክዎ ትንሽ ይጠብቁ (Spam)' });
        try {
            if (!socket.verifiedId) return socket.emit('card_error', { message: 'ያልተረጋገጠ ተጠቃሚ' });
            if (gameState.phase !== 'waiting' && gameState.phase !== 'countdown') return socket.emit('card_error', { message: 'ጨዋታ ተጀምሯል' });
            
            const cardNum = Number(data?.cardNum);
            if (!Number.isInteger(cardNum) || cardNum < 1 || cardNum > gameState.settings.maxCards) {
                return socket.emit('card_error', { message: '❌ ልክ ያልሆነ ካርቴላ ቁጥር' });
            }

            if (data.action === 'select') {
                if (gameState.takenCards[cardNum]) {
                    if (gameState.takenCards[cardNum].userId === socket.verifiedId) return;
                    return socket.emit('card_error', { message: '❌ ይህ ካርቴላ በሌላ ተጫዋች ተይዟል!' });
                }
                let updated = await User.findOneAndUpdate({ id: String(socket.verifiedId), play_balance: { $gte: CARD_PRICE } }, { $inc: { play_balance: -CARD_PRICE } }, { new: true });
                let paidFrom = 'play';
                if (!updated) {
                    updated = await User.findOneAndUpdate({ id: String(socket.verifiedId), win_balance: { $gte: CARD_PRICE } }, { $inc: { win_balance: -CARD_PRICE } }, { new: true });
                    paidFrom = 'win';
                }
                if (!updated) return socket.emit('card_error', { message: '❌ ቀሪ ሂሳብ በቂ አይደለም! (Play & Win)' });
                
                gameState.takenCards[cardNum] = { userId: socket.verifiedId, paidFrom }; 
                socket.emit('wallet_updated', {});
            } else if (data.action === 'deselect') {
                if (gameState.takenCards[cardNum] && gameState.takenCards[cardNum].userId === socket.verifiedId) { 
                    const paidFrom = gameState.takenCards[cardNum].paidFrom || 'play';
                    delete gameState.takenCards[cardNum]; 
                    await User.updateOne({ id: String(socket.verifiedId) }, { $inc: paidFrom === 'win' ? { win_balance: CARD_PRICE } : { play_balance: CARD_PRICE } }); 
                    socket.emit('wallet_updated', {}); 
                }
            }
            
            const totalCards = Object.keys(gameState.takenCards).length;
            io.emit('sync_taken_cards', { takenCards: Object.keys(gameState.takenCards).map(Number), totalPlayers: totalCards, totalCards: totalCards });
        } catch (err) { socket.emit('card_error', { message: 'ሰርቨር ስህተት' }); }
    });
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

app.post('/api/admin/set-max-cards', adminAuth, async (req, res) => {
    const maxCards = Number(req.body.maxCards);
    if (!maxCards || maxCards < 10 || maxCards > 1000) return res.status(400).json({ success: false });
    gameState.settings.maxCards = maxCards;
    await Settings.findOneAndUpdate({ key: 'payment_accounts' }, { maxCards }, { upsert: true });
    io.emit('update_max_cards', { maxCards });
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

app.get('/api/admin/users', adminAuth, async (req, res) => { try { const users = await User.find({}).sort({ registered_at: -1 }).lean(); res.json({ success: true, data: users }); } catch (e) { res.status(500).json({ success: false }); } });

app.post('/api/admin/users/:id/balance', adminAuth, async (req, res) => {
    try {
        const { id } = req.params; const { play_balance, win_balance } = req.body;
        const update = {}; if (typeof play_balance === 'number') update.play_balance = play_balance; if (typeof win_balance === 'number') update.win_balance = win_balance;
        if (!Object.keys(update).length) return res.status(400).json({ success: false });
        const user = await User.findOneAndUpdate({ id: String(id) }, { $set: update }, { new: true, lean: true });
        if (!user) return res.status(404).json({ success: false });
        io.to(`user_${id}`).emit('wallet_updated', {}); res.json({ success: true, data: user });
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

app.get('/api/admin/transactions', adminAuth, async (req, res) => {
    try {
        const type = req.query.type;
        const filter = type ? { type } : {};
        const txns = await Transaction.find(filter).sort({ created: -1 }).limit(200).lean();
        res.json({ success: true, data: txns });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/transactions/:id/:action', adminAuth, async (req, res) => {
    try {
        const { id, action } = req.params;
        const txn = await Transaction.findOne({ id });
        if (!txn) return res.status(404).json({ success: false, error: 'Not found' });
        if (txn.status !== 'pending') return res.status(400).json({ success: false, error: 'Already processed' });

        if (action === 'approve') {
            if (txn.type === 'deposit') {
                await User.updateOne({ id: txn.user_id }, { $inc: { play_balance: txn.amount } });
            }
        } else if (action === 'reject') {
            if (txn.type === 'withdrawal') {
                await User.updateOne({ id: txn.user_id }, { $inc: { win_balance: txn.amount } });
            }
        }
        txn.status = action === 'approve' ? 'approved' : 'rejected';
        await txn.save();
        io.to(`user_${txn.user_id}`).emit('wallet_updated', {});
        res.json({ success: true });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/admin/game-history', adminAuth, async (req, res) => {
    try {
        const history = await GameHistory.find().sort({ createdAt: -1 }).limit(100).lean();
        res.json({ success: true, data: history });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.get('/api/admin/referrals', adminAuth, async (req, res) => {
    try {
        const refs = await User.aggregate([
            { $match: { referred_by: { $ne: null } } },
            { $group: { _id: '$referred_by', count: { $sum: 1 } } },
            { $sort: { count: -1 } },
            { $limit: 50 }
        ]);
        const ids = refs.map(r => r._id);
        const users = await User.find({ id: { $in: ids } }, { id: 1, name: 1, phone: 1, _id: 0 }).lean();
        const userMap = new Map(users.map(u => [u.id, u]));
        const result = refs.map(r => ({
            id: r._id,
            name: userMap.get(r._id)?.name || 'Unknown',
            phone: userMap.get(r._id)?.phone || '',
            count: r.count,
            bonus_earned: r.count * 30
        }));
        res.json({ success: true, data: result });
    } catch (e) { res.status(500).json({ success: false }); }
});

app.post('/api/admin/broadcast', adminAuth, async (req, res) => {
    try {
        const { message } = req.body;
        if (!message || message.length > 4000) return res.status(400).json({ success: false });
        const users = await User.find({ registered: true }, { id: 1 }).lean();
        const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`;
        let sent = 0, failed = 0;
        for (const u of users) {
            try {
                const r = await fetch(TELEGRAM_API, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: u.id, text: message, parse_mode: 'HTML' })
                });
                if (r.ok) sent++; else failed++;
            } catch (e) { failed++; }
            await new Promise(r => setTimeout(r, 50)); 
        }
        res.json({ success: true, data: { sent, failed } });
    } catch (e) { res.status(500).json({ success: false }); }
});

let activeGiveaway = null;
app.post('/api/admin/giveaway/start', adminAuth, (req, res) => {
    const { prizeAmount, maxWinners, customMessage } = req.body;
    activeGiveaway = { active: true, prizeAmount: Number(prizeAmount), maxWinners: Number(maxWinners), winners: new Set(), message: customMessage };
    io.emit('giveaway_started', { amount: prizeAmount, message: customMessage });
    res.json({ success: true });
});

app.post('/api/admin/giveaway/stop', adminAuth, (req, res) => {
    activeGiveaway = null;
    io.emit('giveaway_stopped');
    res.json({ success: true });
});

app.post('/api/bot/giveaway/claim', async (req, res) => {
    if (req.headers['x-bot-token'] !== BOT_TOKEN) return res.status(401).json({ success: false });
    if (!activeGiveaway || !activeGiveaway.active) return res.json({ success: false, message: 'ምንም ንቁ ጊቭአዌይ የለም' });
    const userId = String(req.body.userId);
    if (activeGiveaway.winners.has(userId)) return res.json({ success: false, message: 'አስቀድመው ተቀብለዋል' });
    if (activeGiveaway.winners.size >= activeGiveaway.maxWinners) return res.json({ success: false, message: 'ጊቭአዌው አልቋል' });
    
    await User.updateOne({ id: userId }, { $inc: { play_balance: activeGiveaway.prizeAmount } });
    activeGiveaway.winners.add(userId);
    io.to(`user_${userId}`).emit('wallet_updated', {});
    res.json({ success: true, amount: activeGiveaway.prizeAmount });
});

app.post('/api/admin/start-game', adminAuth, (req, res) => { gameState.isRunning = true; if (gameState.phase === 'waiting') startRound(); res.json({ success: true }); });
app.post('/api/admin/stop-game', adminAuth, (req, res) => {
    gameState.isRunning = false;
    if (gameTimerInterval) clearInterval(gameTimerInterval); if (callInterval) clearInterval(callInterval); if (autoRestartTimer) clearTimeout(autoRestartTimer); if (claimTimer) clearTimeout(claimTimer);
    gameState.phase = 'waiting'; gameState.calledNumbers = []; gameState.takenCards = {}; gameState.isAutoOn = false; gameState.currentCall = null;
    isEndingRound = false; roundWinners = []; io.emit('reset_game'); res.json({ success: true });
});

app.post('/api/admin/call-number', adminAuth, async (req, res) => {
    if (gameState.phase !== 'calling' || gameState.calledNumbers.length >= 75) return res.status(400).json({ success: false });
    let num; do { num = Math.floor(Math.random() * 75) + 1; } while (gameState.calledNumbers.includes(num));
    gameState.calledNumbers.push(num); gameState.currentCall = num;
    io.emit('new_number_called', { number: num, allCalled: gameState.calledNumbers });
    if (gameState.calledNumbers.length >= 75) { setTimeout(() => { if (!isEndingRound) endRound([]); }, 5000); } else { setImmediate(() => checkForAutoWinner()); }
    res.json({ success: true });
});

app.post('/api/admin/auto-game', adminAuth, (req, res) => {
    const { isAutoOn, speed } = req.body;
    if (callInterval) { clearInterval(callInterval); callInterval = null; }
    gameState.isAutoOn = !!isAutoOn; if (Number(speed) > 0) gameState.settings.callInterval = Number(speed);
    if (isAutoOn && gameState.phase === 'calling') {
        callInterval = setInterval(async () => {
            if (gameState.phase !== 'calling') return;
            if (gameState.calledNumbers.length >= 75) { clearInterval(callInterval); callInterval = null; endRound([]); return; }
            let num; do { num = Math.floor(Math.random() * 75) + 1; } while (gameState.calledNumbers.includes(num));
            gameState.calledNumbers.push(num); gameState.currentCall = num;
            io.emit('new_number_called', { number: num, allCalled: gameState.calledNumbers });
            await checkForAutoWinner();
        }, gameState.settings.callInterval * 1000);
    }
    res.json({ success: true });
});

async function checkForAutoWinner() {
    if (isEndingRound) return;
    const entries = Object.entries(gameState.takenCards); if (entries.length === 0) return;
    const potentialWinners = [];
    for (const [cardNum, data] of entries) {
        const win = checkWinningLine(cardNum, gameState.calledNumbers);
        if (win) { potentialWinners.push({ cardNum: Number(cardNum), userId: data.userId, win }); }
    }
    if (potentialWinners.length === 0) return;
    
    isEndingRound = true; gameState.phase = 'claiming';
    if (callInterval) { clearInterval(callInterval); callInterval = null; }
    if (gameTimerInterval) { clearInterval(gameTimerInterval); gameTimerInterval = null; }
    
    const userIds = [...new Set(potentialWinners.map(p => p.userId))];
    const users = await User.find({ id: { $in: userIds } }, { id: 1, name: 1 }).lean();
    const userMap = new Map(users.map(u => [u.id, u.name]));
    
    roundWinners = []; 
    for (const p of potentialWinners) { 
        roundWinners.push({ id: p.userId, name: userMap.get(p.userId) || 'Player', cardNum: p.cardNum, winDesc: p.win.desc, winType: p.win.type, winIndex: p.win.index, allLines: [p.win] }); 
    }
    
    claimTimer = setTimeout(async () => { await endRound(roundWinners); }, 2000);
}

function startRound() {
    if (!gameState.isRunning) return;
    if (gameTimerInterval) clearInterval(gameTimerInterval); if (callInterval) clearInterval(callInterval); if (autoRestartTimer) clearTimeout(autoRestartTimer); if (claimTimer) clearTimeout(claimTimer);
    gameState.phase = 'countdown'; gameState.currentCall = null; gameState.calledNumbers = []; roundWinners = []; isEndingRound = false; remainingTime = 50;
    io.emit('phase_change', { phase: 'countdown' }); io.emit('timer_tick', { remaining: remainingTime });
    gameTimerInterval = setInterval(() => {
        if (!gameState.isRunning) return;
        remainingTime--; io.emit('timer_tick', { remaining: remainingTime });
        if (remainingTime <= 0) {
            const totalCards = Object.keys(gameState.takenCards).length;
            if (totalCards < 3) { remainingTime = 50; io.emit('timer_tick', { remaining: remainingTime }); io.emit('game_status_msg', { message: 'ቢያንስ 3 ካርቴላ ያስፈልጋል! ሰዓቱ እንደገና ተጀምሯል።' }); return; }
            clearInterval(gameTimerInterval); gameTimerInterval = null; gameState.phase = 'calling'; io.emit('phase_change', { phase: 'calling' });
            if (gameState.isAutoOn) {
                callInterval = setInterval(async () => {
                    if (gameState.phase !== 'calling') return;
                    if (gameState.calledNumbers.length >= 75) { clearInterval(callInterval); callInterval = null; endRound([]); return; }
                    let num; do { num = Math.floor(Math.random() * 75) + 1; } while (gameState.calledNumbers.includes(num));
                    gameState.calledNumbers.push(num); gameState.currentCall = num;
                    io.emit('new_number_called', { number: num, allCalled: gameState.calledNumbers });
                    await checkForAutoWinner();
                }, gameState.settings.callInterval * 1000);
            }
        }
    }, 1000);
}

async function endRound(winnersData) {
    if (autoRestartTimer) { clearTimeout(autoRestartTimer); autoRestartTimer = null; }
    if (claimTimer) { clearTimeout(claimTimer); claimTimer = null; }
    if (gameTimerInterval) { clearInterval(gameTimerInterval); gameTimerInterval = null; }
    if (callInterval) { clearInterval(callInterval); callInterval = null; }
    gameState.phase = 'gameover';
    
    try {
        const playersInRound = [...new Set(Object.values(gameState.takenCards).map(c => c.userId))];
        const totalCards = Object.keys(gameState.takenCards).length; 
        const totalPrize = totalCards * DERASH_PER_CARD; 
        const promises = [];
        
        if (playersInRound.length > 0) promises.push(User.updateMany({ id: { $in: playersInRound } }, { $inc: { total_games: 1 } }));
        
        if (!winnersData || winnersData.length === 0) {
            promises.push(GameHistory.create({ gameId: 'GAME_' + Date.now(), winners: [], totalPrize: 0, totalPlayers: playersInRound.length, calledNumbers: gameState.calledNumbers }));
            await Promise.all(promises); 
            
            io.emit('game_over', { reason: 'no_winner', winners: [], totalPrize: 0, winningCard: null, lastCall: null });
            io.emit('reset_game');
            
            autoRestartTimer = setTimeout(() => {
                autoRestartTimer = null; gameState.takenCards = {}; gameState.phase = 'waiting'; gameState.calledNumbers = []; gameState.currentCall = null; roundWinners = []; isEndingRound = false;
                if (gameState.isRunning) startRound();
            }, 3000); return;
        }
        
        const basePrize = Math.floor(totalPrize / winnersData.length); 
        const remainder = totalPrize - (basePrize * winnersData.length);
        const winnerIds = winnersData.map(w => String(w.id));
        
        winnersData[0].prize = basePrize + remainder;
        for(let i=1; i<winnersData.length; i++) winnersData[i].prize = basePrize;

        const bulkOps = winnersData.map(w => ({
            updateOne: { filter: { id: String(w.id) }, update: { $inc: { win_balance: w.prize, total_wins: 1 } } }
        }));
        promises.push(User.bulkWrite(bulkOps));
        
        promises.push(GameHistory.create({ gameId: 'GAME_' + Date.now(), winners: winnersData.map(w => ({ id: w.id, name: w.name, cardNum: w.cardNum, prize: w.prize })), totalPrize, totalPlayers: playersInRound.length, calledNumbers: gameState.calledNumbers }));
        await Promise.all(promises);
        
        for (const w of winnersData) { io.to(`user_${w.id}`).emit('wallet_updated', {}); }
        const lastCall = gameState.calledNumbers[gameState.calledNumbers.length - 1]; 
        const firstWinner = winnersData[0];
        
        io.emit('game_over', { 
            reason: 'bingo', 
            winners: winnersData.map(w => ({ id: w.id, name: w.name, cardNum: w.cardNum, prize: w.prize, winDesc: w.winDesc, winType: w.winType, winIndex: w.winIndex, allLines: w.allLines || [] })), 
            totalPrize, 
            prizePerWinner: basePrize, 
            winningCard: firstWinner.cardNum, 
            winDesc: firstWinner.winDesc, 
            winType: firstWinner.winType, 
            winIndex: firstWinner.winIndex, 
            allLines: firstWinner.allLines || [], 
            lastCall 
        });
    } catch (err) { 
        console.error('❌ endRound error:', err); 
    }
    
    autoRestartTimer = setTimeout(() => {
        autoRestartTimer = null; gameState.takenCards = {}; gameState.phase = 'waiting'; gameState.calledNumbers = []; gameState.currentCall = null; roundWinners = []; isEndingRound = false;
        io.emit('reset_game'); if (gameState.isRunning) startRound();
    }, 10000);
}

server.listen(PORT, () => { console.log(`🚀 Server running on port ${PORT}`); });
