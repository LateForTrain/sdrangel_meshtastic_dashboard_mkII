/**
 * app.js — Shared WebSocket client and state manager
 *
 * Loaded on every page via base.html.
 * Responsibilities:
 *   • Open (and reconnect) the WebSocket to /ws
 *   • Maintain shared state
 *   • Keep sidebar stats
 *   • Dispatch incoming messages to the current page via window.onMeshMessage()
 *
 * Each page template defines window.onMeshMessage(msg) to do its own rendering.
 * If no handler is defined, packets are silently tracked for stats only.
 */

const SK = {
  START_TIME:    'meshStartTime',
  MSG_COUNT:     'meshMsgCount',
  MESSAGES:      'meshMessages',      // [] — full message log for chat replay
  POSITIONS:     'meshPositions',     // {} — nodeId → latest position for map replay
  NODES:         'meshNodes',         // {} — nodeId → { long_name, lastSeen }
};

const MAX_STORED_MESSAGES = 50;

/* ════════════════════════════════════════════════════════════════════════════
   SHARED STATE  (exposed as window.meshState for page scripts that need it)
════════════════════════════════════════════════════════════════════════════ */
function _loadState() {
  let startTime = Number(sessionStorage.getItem(SK.START_TIME));
  if (!Number.isFinite(startTime) || startTime <= 0) {
    startTime = Date.now();
    sessionStorage.setItem(SK.START_TIME, startTime);
  }

  const messageCount = Number(sessionStorage.getItem(SK.MSG_COUNT)) || 0;

  let sessionMessages = [];
  try {
    sessionMessages = JSON.parse(sessionStorage.getItem(SK.MESSAGES) || '[]');
  } catch { sessionMessages = []; }

  let sessionPositions = {};
  try {
    sessionPositions = JSON.parse(sessionStorage.getItem(SK.POSITIONS) || '{}');
  } catch { sessionPositions = {}; }

  let nodes = {};
  try {
    nodes = JSON.parse(sessionStorage.getItem(SK.NODES) || '{}');
  } catch { nodes = {}; }

  return { startTime, messageCount, sessionMessages, sessionPositions, nodes };
}
window.meshState = _loadState();

/* Derived — not stored, always computed */
Object.defineProperty(window.meshState, 'nodeCount', {
  get() { return Object.keys(this.nodes).length; }
});

function updateSidebarStats() {
    if (_statMsgs) {
        _statMsgs.textContent = window.meshState.messageCount;
    }

    if (_statNodes) {
        _statNodes.textContent = window.meshState.nodeCount;
    }
}

function _persistState() {
  const s = window.meshState;
  sessionStorage.setItem(SK.MSG_COUNT,  s.messageCount);
  sessionStorage.setItem(SK.MESSAGES,   JSON.stringify(s.sessionMessages));
  sessionStorage.setItem(SK.POSITIONS,  JSON.stringify(s.sessionPositions));
  sessionStorage.setItem(SK.NODES,      JSON.stringify(s.nodes));
}

/* ════════════════════════════════════════════════════════════════════════════
   DOM REFS  (present in base.html on every page)
════════════════════════════════════════════════════════════════════════════ */
const _statNodes  = document.getElementById('stat-nodes');
const _statMsgs   = document.getElementById('stat-msgs');
const _statUptime = document.getElementById('stat-uptime');
const _wsStatus   = document.getElementById('ws-status');
const _wsDot      = document.getElementById('ws-dot');

updateSidebarStats();
/* ════════════════════════════════════════════════════════════════════════════
   UPTIME TICKER
════════════════════════════════════════════════════════════════════════════ */
function updateUptime() {
    const secs = Math.floor((Date.now() - window.meshState.startTime) / 1000);
    const m    = String(Math.floor(secs / 60)).padStart(2, '0');
    const s    = String(secs % 60).padStart(2, '0');
    if (_statUptime) _statUptime.textContent = `${m}:${s}`;
}

updateUptime();
setInterval(updateUptime, 1000);

/* ════════════════════════════════════════════════════════════════════════════
   WEBSOCKET
════════════════════════════════════════════════════════════════════════════ */
let _ws                = null;
let _reconnectAttempts = 0;
const MAX_RECONNECTS   = 10;

function connectWebSocket() {
    _ws = new WebSocket(`ws://${window.location.host}/ws`);

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

            if (data.type === 'new_message') {
                _handleMessage(data.payload);
            } else if (data.type === 'position_update') {
                _handlePosition(data.payload);
            } else if (data.type === 'telemetry_update') {
                _handleTelemetry(data.payload);
            } else if (data.type === 'node_update'){
                _handleNode(data.payload);
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
   PAYLOAD HANDLER
════════════════════════════════════════════════════════════════════════════ */
function _handleMessage(msg) {
  //Handle payloads that contain message information 
  const s = window.meshState;
  const nodeId = msg.from_int;

  // 1. Count
  s.messageCount++;

  // 2. Track node + long_name (update if we get a better name)
  const existing = s.nodes[nodeId] || {};
  s.nodes[nodeId] = {
    long_name: msg.long_name || existing.long_name || nodeId,
    lastSeen: Date.now(),
  };

  // 3. Store message for chat replay
  s.sessionMessages.push({
    from_node:  nodeId,
    long_name:  s.nodes[nodeId].long_name,
    text:       msg.text,
    timestamp:  new Date().toLocaleTimeString(),
    snr:        msg.snr,
    rssi:       msg.rssi 
  });
  if (s.sessionMessages.length > MAX_STORED_MESSAGES) {
    s.sessionMessages.shift();
  }

  // 4. Store position for map replay (only if it has coords)
  if (msg.latitude != null && msg.longitude != null && !msg._replayed) {
    s.sessionPositions[nodeId] = {
      latitude: msg.latitude,
      longitude:msg.longitude,
      altitude: msg.altitude,
      snr:      msg.snr,
      rssi:     msg.rssi,
      long_name: s.nodes[nodeId].long_name,
      timestamp: new Date().toLocaleTimeString(),
    };
  }

  // 5. Update sidebar
  updateSidebarStats();

  _persistState();

  if (typeof window.onMeshMessage === 'function') {
    window.onMeshMessage(msg);
  }
}

function _handlePosition(msg) {
  const s = window.meshState;
  const nodeId = msg.from_int;

  // 1. Track node + long_name (update if we get a better name)
  const existing = s.nodes[nodeId] || {};
  s.nodes[nodeId] = {
    long_name: msg.long_name || existing.long_name || nodeId,
    lastSeen: Date.now(),
  };

  // 2. Store position for map replay (only if it has coords)
  s.sessionPositions[nodeId] = {
    latitude:  msg.latitude,
    longitude: msg.longitude,
    altitude:  msg.altitude,
    snr:       msg.snr,
    rssi:      msg.rssi,
    long_name:  s.nodes[nodeId]?.long_name || nodeId,
    timestamp: new Date().toLocaleTimeString(),
  };

  // 3. Update sidebar
  updateSidebarStats();

  _persistState();

  if (typeof window.onMeshMessage === 'function') {
    window.onMeshMessage(msg);
  }
}

function _handleTelemetry(msg){
 //Handle payloads that contain telemety information
}

function _handleNode(msg){
 //Handle payloads that contain node information
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

/* ════════════════════════════════════════════════════════════════════════════
   CLEANUP
════════════════════════════════════════════════════════════════════════════ */
window.addEventListener('beforeunload', () => {
    if (_ws) {
        _ws.close();
    }
});

window.persistMeshState = _persistState;
window.updateSidebarStats = updateSidebarStats;

// Boot
connectWebSocket();
