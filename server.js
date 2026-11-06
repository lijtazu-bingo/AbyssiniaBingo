require('dotenv').config();
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');
const cors = require('cors');

const PORT = process.env.PORT || 5000;

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: '*' } });

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

let gameState = {
    status: 'waiting',
    calledNumbers: [],
    currentCall: null,
    timer: 30
};

let countdownInterval = null;
let callInterval = null;
let resetTimeout = null;

const MIN_NUMBER = 1;
const MAX_NUMBER = 75;
const takenCardsMap = {};  // { cardNum: "clientId" }

function clearAllIntervals() {
    clearInterval(countdownInterval);
    clearInterval(callInterval);
    clearTimeout(resetTimeout);
}

function getPlayersCount() {
    return new Set(Object.values(takenCardsMap)).size;
}

function getInitState() {
    return {
        phase: gameState.status,
        gameStarted: gameState.status === 'calling',
        calledNumbers: gameState.calledNumbers,
        takenCards: takenCardsMap,
        remainingTime: gameState.timer,
        totalSelected: Object.keys(takenCardsMap).length
    };
}

function startCountdown() {
    if (gameState.status !== 'waiting') return;
    gameState.status = 'countdown';
    gameState.timer = 30;
    gameState.calledNumbers = [];
    gameState.currentCall = null;

    console.log('⏳ Countdown started (30s)');
    io.emit('game_started', { status: 'countdown' });
    io.emit('timer_tick', { remaining: 30 });

    countdownInterval = setInterval(() => {
        gameState.timer--;
        io.emit('timer_tick', { remaining: gameState.timer });
        if (gameState.timer <= 0) {
            clearInterval(countdownInterval);
            if (getPlayersCount() > 0) {
                startCalling();
            } else {
                resetToWaiting();
            }
        }
    }, 1000);
}

function startCalling() {
    if (gameState.status === 'calling') return;
    gameState.status = 'calling';
    gameState.calledNumbers = [];
    gameState.currentCall = null;
    console.log(`🎮 Game started — ${getPlayersCount()} players`);
    io.emit('game_started', { status: 'calling' });

    callInterval = setInterval(() => {
        if (gameState.calledNumbers.length >= MAX_NUMBER) return;
        let num, attempts = 0;
        do {
            num = Math.floor(Math.random() * MAX_NUMBER) + MIN_NUMBER;
            attempts++;
            if (attempts > 200) break;
        } while (gameState.calledNumbers.includes(num));
        if (gameState.calledNumbers.includes(num)) return;
        gameState.calledNumbers.push(num);
        gameState.currentCall = num;
        console.log(`📢 Called: ${num}`);
        io.emit('new_number_called', { number: num, allCalled: gameState.calledNumbers });
    }, 3000);
}

function endGame() {
    clearAllIntervals();
    gameState.status = 'finished';
    io.emit('game_over', { reason: 'timeout' });
    resetTimeout = setTimeout(resetToWaiting, 10000);
}

function resetToWaiting() {
    clearAllIntervals();
    Object.keys(takenCardsMap).forEach(k => delete takenCardsMap[k]);
    gameState = { status: 'waiting', calledNumbers: [], currentCall: null, timer: 30 };
    console.log('🔄 Reset to waiting');
    io.emit('reset_game');
    io.emit('init_state', getInitState());
}

app.get('/api/game-state', (req, res) => res.json(gameState));

io.on('connection', (socket) => {
    console.log('🔌 Connected:', socket.id);
    socket.emit('init_state', getInitState());

    socket.on('join_room', (room) => { socket.join(room); });

    socket.on('select_card', (data) => {
        const cardNum = data.cardNum;
        const clientId = String(data.clientId);  // ✅ Force String
        const action = data.action;

        if (gameState.status === 'calling' || gameState.status === 'finished') {
            socket.emit('need_more_cards', { message: 'ጨዋታ ተጀምሯል!' });
            return;
        }

        if (action === 'select') {
            // ✅ ካርቴላ በሌላ ተጫዋች ተይዞ ካለ — አትፍቀድ
            if (takenCardsMap[cardNum] && String(takenCardsMap[cardNum]) !== clientId) {
                socket.emit('need_more_cards', { message: 'ይህ ካርቴላ በሌላ ተጫዋች ተይዟል!' });
                console.log(`❌ Card ${cardNum} already taken by ${takenCardsMap[cardNum]}`);
                return;
            }
            takenCardsMap[cardNum] = clientId;
            console.log(`✅ Card ${cardNum} selected by ${clientId}`);

            if (gameState.status === 'waiting') {
                startCountdown();
            }
        } else if (action === 'deselect') {
            // ✅ የራሱን ካርቴላ ብቻ ነው መሰረዝ የሚችለው
            if (String(takenCardsMap[cardNum]) === clientId) {
                delete takenCardsMap[cardNum];
                console.log(`🗑️ Card ${cardNum} deselected by ${clientId}`);
            }
        }

        io.emit('sync_taken_cards', takenCardsMap);
        io.emit('update_total_selected', Object.keys(takenCardsMap).length);
    });

    socket.on('claim_bingo', (data) => {
        console.log(`🎉 BINGO! ${data.winnerName}`);
        clearAllIntervals();
        gameState.status = 'finished';
        io.emit('game_over', {
            reason: 'bingo',
            winner: data.winnerName,
            cardNum: data.cardNum,
            prize: data.prize,
            winDesc: data.winDesc,
            winType: data.winType,
            winIndex: data.winIndex
        });
        resetTimeout = setTimeout(resetToWaiting, 10000);
    });

    socket.on('disconnect', () => { console.log('🔌 Disconnected:', socket.id); });
});

server.listen(PORT, () => {
    console.log(`✅ Server on port ${PORT}`);
});

process.on('SIGINT', () => { clearAllIntervals(); process.exit(0); });
