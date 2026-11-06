require('dotenv').config();
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const { Telegraf, Markup } = require('telegraf');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

const PORT = process.env.PORT || 3000;
const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD;
const WEB_APP_URL = process.env.WEB_APP_URL;

if (!BOT_TOKEN || !WEB_APP_URL) {
    console.log("❌ Missing .env variables (BOT_TOKEN or WEB_APP_URL).");
    process.exit(1);
}

let users = {}; 
const bot = new Telegraf(BOT_TOKEN);

bot.start((ctx) => {
    ctx.reply("🎯 እንኳን ወደ Abisinya Bingo በደህና መጡ!\n\n👇 ከታች ያለውን ቁልፍ በመጠቀም ጨዋታውን ይጀምሩ።", Markup.keyboard([
        [Markup.button.webApp("🎮 ጨዋታ መጫወት", WEB_APP_URL)]
    ]).resize());
});

bot.launch().then(() => console.log("🤖 Telegram Bot is running..."));

// ================= GAME LOGIC =================
let gamePhase = 'waiting';
let calledNumbers = [];
let availableNumbers = [];
let takenCardsMap = {}; 
let timer = 30;
let countdownInterval = null;
let autoCallInterval = null;

function resetGameData() {
    calledNumbers = [];
    availableNumbers = Array.from({length: 75}, (_, i) => i + 1);
    takenCardsMap = {};
    gamePhase = 'waiting';
    timer = 30;
    if(countdownInterval) clearInterval(countdownInterval);
    if(autoCallInterval) clearInterval(autoCallInterval);
    io.emit('reset_game');
    io.emit('sync_taken_cards', []);
}

function startGameCountdown() {
    if (gamePhase !== 'waiting') return;
    gamePhase = 'countdown';
    timer = 30;
    io.emit('phase_change', { phase: 'countdown' });
    io.emit('timer_tick', { remaining: timer });
    countdownInterval = setInterval(() => {
        timer--;
        io.emit('timer_tick', { remaining: timer });
        if (timer <= 0) {
            clearInterval(countdownInterval);
            startCallingPhase();
        }
    }, 1000);
}

function startCallingPhase() {
    if (Object.keys(takenCardsMap).length === 0) {
        gamePhase = 'waiting';
        io.emit('reset_game');
        return;
    }
    gamePhase = 'calling';
    io.emit('phase_change', { phase: 'calling' });
    autoCallInterval = setInterval(() => {
        if (gamePhase !== 'calling' || availableNumbers.length === 0) {
            clearInterval(autoCallInterval);
            return;
        }
        const randomIndex = Math.floor(Math.random() * availableNumbers.length);
        const number = availableNumbers.splice(randomIndex, 1)[0];
        calledNumbers.push(number);
        io.emit('new_number_called', { number: number, allCalled: calledNumbers });
        if (availableNumbers.length === 0) {
            clearInterval(autoCallInterval);
            gamePhase = 'gameover';
            io.emit('game_over', { reason: 'draw' });
        }
    }, 4000); 
}

io.on('connection', (socket) => {
    socket.emit('init_state', {
        phase: gamePhase,
        takenCards: Object.keys(takenCardsMap),
        calledNumbers: calledNumbers,
        remainingTime: timer
    });

    socket.on('join_room', (data) => { socket.clientId = data.clientId; });

    socket.on('select_card', (data) => {
        if (data.action === 'select') takenCardsMap[data.cardNum] = data.clientId;
        else delete takenCardsMap[data.cardNum];
        io.emit('sync_taken_cards', Object.keys(takenCardsMap));
        if (Object.keys(takenCardsMap).length === 1 && gamePhase === 'waiting') startGameCountdown();
    });

    socket.on('claim_bingo', (data) => {
        if (gamePhase !== 'calling') return;
        gamePhase = 'gameover';
        if(autoCallInterval) clearInterval(autoCallInterval);
        const totalCards = Object.keys(takenCardsMap).length;
        const prize = totalCards * 8; 
        if (!users[data.clientId]) users[data.clientId] = { play_balance: 100, win_balance: 0 };
        users[data.clientId].win_balance += prize;
        io.emit('game_over', {
            reason: 'bingo', winner: data.winnerName, clientId: data.clientId, cardNum: data.cardNum,
            prize: prize, winDesc: data.winDesc, winType: data.winType, winIndex: data.winIndex, winningCard: data.winningCard
        });
        setTimeout(() => { resetGameData(); }, 12000); 
    });
});

// ================= REST APIS =================
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

function getUserId(req) {
    const initData = req.headers['x-telegram-init-data'];
    if (!initData) return "123456789";
    try {
        const urlParams = new URLSearchParams(initData);
        return JSON.parse(urlParams.get('user')).id.toString();
    } catch (e) { return "123456789"; }
}

app.get('/api/wallet/me', (req, res) => {
    const userId = getUserId(req);
    if (!users[userId]) users[userId] = { play_balance: 100, win_balance: 0 };
    res.json({ success: true, data: users[userId] });
});

app.post('/api/wallet/deduct', (req, res) => {
    const userId = getUserId(req);
    if (!users[userId]) users[userId] = { play_balance: 100, win_balance: 0 };
    if (users[userId].play_balance >= req.body.amount) {
        users[userId].play_balance -= req.body.amount;
        res.json({ success: true, data: users[userId] });
    } else res.json({ success: false, error: 'በቂ ቀሪ ሂሳብ የለም' });
});

app.post('/api/wallet/add', (req, res) => {
    const userId = getUserId(req);
    if (!users[userId]) users[userId] = { play_balance: 100, win_balance: 0 };
    users[userId].play_balance += req.body.amount;
    res.json({ success: true, data: users[userId] });
});

server.listen(PORT, () => console.log(`✅ Server running on port ${PORT}`));
