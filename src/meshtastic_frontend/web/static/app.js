/**
 * app.js — Shared WebSocket client and state manager
 *
 * Loaded on every page via base.html.
 * Responsibilities:
 *   • Open (and reconnect) the WebSocket to /ws
 *   • Maintain shared state: nodesSeen, messageCount, startTime
 *   • Keep sidebar stats (#stat-nodes, #stat-msgs, #stat-uptime) up to date
 *   • Dispatch incoming messages to the current page via window.onMeshMessage()
 *
 * Each page template defines window.onMeshMessage(msg) to do its own rendering.
 * If no handler is defined, packets are silently tracked for stats only.
 */

/* ════════════════════════════════════════════════════════════════════════════
   SHARED STATE  (exposed as window.meshState for page scripts that need it)
════════════════════════════════════════════════════════════════════════════ */
window.meshState = {
    messageCount: 0,
    nodesSeen:    new Set(),   // Set<string>  — node IDs seen this session
    nodeData:     new Map(),   /* Map<nodeId, { lat, lon, snr, longName,
                                                lastMsg, timestamp }>
                                  Pages that don't need GPS can ignore this. */
    startTime:    Date.now()
};

/* ════════════════════════════════════════════════════════════════════════════
   DOM REFS  (present in base.html on every page)
════════════════════════════════════════════════════════════════════════════ */
const _statNodes  = document.getElementById('stat-nodes');
const _statMsgs   = document.getElementById('stat-msgs');
const _statUptime = document.getElementById('stat-uptime');
const _wsStatus   = document.getElementById('ws-status');
const _wsDot      = document.getElementById('ws-dot');

/* ════════════════════════════════════════════════════════════════════════════
   UPTIME TICKER
════════════════════════════════════════════════════════════════════════════ */
setInterval(() => {
    const secs = Math.floor((Date.now() - window.meshState.startTime) / 1000);
    const m    = String(Math.floor(secs / 60)).padStart(2, '0');
    const s    = String(secs % 60).padStart(2, '0');
    if (_statUptime) _statUptime.textContent = `${m}:${s}`;
}, 1000);

/* ════════════════════════════════════════════════════════════════════════════
   WEBSOCKET
════════════════════════════════════════════════════════════════════════════ */
let _ws                = null;
let _reconnectAttempts = 0;
const MAX_RECONNECTS   = 10;

function connectWebSocket() {
    _ws = new WebSocket(`ws://${window.location.host}/ws`);

    // Initialize uptime counter
    window.meshStats = window.meshStats || {};
    window.meshStats.uptime = window.meshStats.uptime || "00:00";

    // Update uptime every second
    setInterval(() => {
        const [hours, minutes] = window.meshStats.uptime.split(":").map(Number);
        let totalSeconds = hours * 3600 + minutes * 60;
        totalSeconds++;

        const newHours = Math.floor(totalSeconds / 3600);
        const newMinutes = Math.floor((totalSeconds % 3600) / 60);
        const newUptime = `${String(newHours).padStart(2, "0")}:${String(newMinutes).padStart(2, "0")}`;

        window.meshStats.uptime = newUptime;
        document.getElementById("stat-uptime").textContent = newUptime;
    }, 1000);

    _ws.onopen = () => {
        console.log('✅ WebSocket connected');
        _reconnectAttempts       = 0;
        _wsStatus.textContent    = 'Connected';
        _wsStatus.style.color    = '#22c55e';
        if (_wsDot) _wsDot.style.background = '#22c55e';
    };

    _ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'history') {
                // Full backlog sent once on connect — replay oldest→newest
                data.messages.forEach(msg => _handleMessage(msg));
            } else if (data.type === 'new_message') {
                _handleMessage(data.payload);
            }
        } catch (err) {
            console.error('app.js: failed to parse WS message', err);
        }
    };

    _ws.onclose = () => {
        _wsStatus.textContent = 'Reconnecting…';
        _wsStatus.style.color = '#f59e0b';
        if (_wsDot) _wsDot.style.background = '#f59e0b';

        if (_reconnectAttempts < MAX_RECONNECTS) {
            _reconnectAttempts++;
            // Exponential back-off: 2 s → 4 s → … capped at 10 s
            const delay = Math.min(2000 * _reconnectAttempts, 10_000);
            setTimeout(connectWebSocket, delay);
        } else {
            _wsStatus.textContent = 'Disconnected';
            _wsStatus.style.color = '#ef4444';
            if (_wsDot) _wsDot.style.background = '#ef4444';
        }
    };

    _ws.onerror = (err) => console.error('app.js: WebSocket error', err);
}

/* ════════════════════════════════════════════════════════════════════════════
   MESSAGE HANDLER
════════════════════════════════════════════════════════════════════════════ */
function _handleMessage(msg) {
    const state = window.meshState;

    // Update shared counters
    state.messageCount++;
    state.nodesSeen.add(msg.from_node);

    if (_statMsgs)  _statMsgs.textContent  = state.messageCount;
    if (_statNodes) _statNodes.textContent = state.nodesSeen.size;

    // Store GPS data for any node that reports position
    if (msg.lat != null && msg.lon != null) {
        const existing = state.nodeData.get(msg.from_node) || {};
        state.nodeData.set(msg.from_node, {
            ...existing,
            lat:       msg.lat,
            lon:       msg.lon,
            snr:       msg.snr ?? existing.snr,
            longName:  msg.long_name || existing.longName || msg.from_node,
            lastMsg:   msg.text,
            timestamp: msg.timestamp
        });
    } else if (!state.nodeData.has(msg.from_node)) {
        state.nodeData.set(msg.from_node, {
            lat: null, lon: null,
            longName:  msg.long_name || msg.from_node,
            lastMsg:   msg.text,
            timestamp: msg.timestamp
        });
    }

    // Dispatch to the active page's handler (defined in each template)
    if (typeof window.onMeshMessage === 'function') {
        window.onMeshMessage(msg);
    }
}

/* ════════════════════════════════════════════════════════════════════════════
   SHARED UTILITY: HTML escaping
   Exported on window so page scripts can call escapeHtml() without re-defining it.
════════════════════════════════════════════════════════════════════════════ */
window.escapeHtml = function(str) {
    return String(str)
        .replace(/&/g,  '&amp;')
        .replace(/</g,  '&lt;')
        .replace(/>/g,  '&gt;')
        .replace(/"/g,  '&quot;')
        .replace(/'/g,  '&#39;');
};

// Boot
connectWebSocket();
