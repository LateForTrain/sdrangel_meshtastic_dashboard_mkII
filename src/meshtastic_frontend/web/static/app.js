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

/* General Constants declared */
const SK = {
  START_TIME:    'meshStartTime',
  MSG_COUNT:     'meshMsgCount',
  MESSAGES:      'meshMessages',
  POSITIONS:     'meshPositions',
  NODES:         'meshNodes',
  SDR_STATUS:    'meshSdrStatus',   // {connected, port} — last known SDRangel heartbeat
};

const MAX_STORED_MESSAGES = 50;

/* DOM REFS  (present in base.html on every page) */
const _statNodes  = document.getElementById('stat-nodes');
const _statMsgs   = document.getElementById('stat-msgs');
const _statUptime = document.getElementById('stat-uptime');
const _wsStatus   = document.getElementById('ws-status');
const _sdrDot       = document.getElementById('sdr-dot');
const _sdrPortBadge = document.getElementById('sdr-port-badge');

/* WEBSOCKET */
let _ws                = null;
let _reconnectAttempts = 0;
const MAX_RECONNECTS   = 10;

/**
  * @function _persistState
  * @description Persists the current mesh state to sessionStorage to maintain state across page reloads and sessions.
  * @private
  * @memberof app
  * @instance
  * @returns {void}
  */
function _persistState() {
  const s = window.meshState;
  sessionStorage.setItem(SK.MSG_COUNT,  s.messageCount);
  sessionStorage.setItem(SK.MESSAGES,   JSON.stringify(s.sessionMessages));
  sessionStorage.setItem(SK.POSITIONS,  JSON.stringify(s.sessionPositions));
  sessionStorage.setItem(SK.NODES,      JSON.stringify(s.nodes));
}

/**
 * @function _loadState
 * @description Loads the mesh state from sessionStorage to restore state across page reloads and sessions.
 * @private
 * @memberof app
 * @instance
 * @returns {Object} An object containing the restored mesh state including start time, message count, session messages, session positions, and nodes.
 */
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

/**
 * @function updateSidebarStats
 * @description Updates the sidebar statistics by setting the message count and node count displayed in the UI.
 * @memberof app
 * @instance
 * @returns {void}
 */
function updateSidebarStats() {
    if (_statMsgs) {
        _statMsgs.textContent = window.meshState.messageCount;
    }

    if (_statNodes) {
        _statNodes.textContent = window.meshState.nodeCount;
    }
}

/**
 * @function updateUptime
 * @description Updates the uptime display in the sidebar by calculating the time elapsed since the mesh started.
 * @memberof app
 * @instance
 * @returns {void}
 */
function updateUptime() {
    const secs = Math.floor((Date.now() - window.meshState.startTime) / 1000);
    const m    = String(Math.floor(secs / 60)).padStart(2, '0');
    const s    = String(secs % 60).padStart(2, '0');
    if (_statUptime) _statUptime.textContent = `${m}:${s}`;
}

/**
 * @function connectWebSocket
 * @description Establishes a WebSocket connection to the server at /ws and handles reconnection logic.
 * @memberof app
 * @instance
 * @returns {void}
 */
function connectWebSocket() {
    _ws = new WebSocket(`ws://${window.location.host}/ws`);

    _ws.onopen = () => {
        console.log('✅ WebSocket connected');
        _reconnectAttempts       = 0;
        _wsStatus.textContent    = 'Connected';
        _wsStatus.style.color    = '#22c55e';
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
            } else if (data.type === 'sdr_status') {
                _handleSdrStatus(data.payload);
            }
        } catch (err) {
            console.error('app.js: failed to parse WS message', err);
        }
    };

    _ws.onclose = () => {
        _wsStatus.textContent = 'Reconnecting…';
        _wsStatus.style.color = '#f59e0b';
        _sdrDot.style.background = '#f59e0b';
        _sdrPortBadge.style.border = '1px solid #f59e0b';
        _sdrPortBadge.style.color = '#f59e0b';
        _sdrPortBadge.style.background = '#f59f0b2c';

        if (_reconnectAttempts < MAX_RECONNECTS) {
            _reconnectAttempts++;
            // Exponential back-off: 2 s → 4 s → … capped at 10 s
            const delay = Math.min(2000 * _reconnectAttempts, 10_000);
            setTimeout(connectWebSocket, delay);
        } else {
            _wsStatus.textContent = 'Reconnecting…';
            _wsStatus.style.color = '#ef4444';
            _sdrDot.style.background = '#ef4444';
            _sdrPortBadge.style.border = '1px solid #ef4444';
            _sdrPortBadge.style.color = '#ef4444';
            _sdrPortBadge.style.background = '#ef44443a';
        }
    };

    _ws.onerror = (err) => console.error('app.js: WebSocket error', err);
}

/**
 * @function _handleMessage
 * @description Processes incoming message payloads, updates the mesh state, and dispatches the message to the current page via window.onMeshMessage(msg).
 * @private
 * @memberof app
 * @instance
 * @param {Object} msg - The message payload containing message details.
 * @returns {void}
 */
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
/**
 * @function _handlePosition
 * @description Processes incoming position payloads, updates the mesh state, and dispatches the position to the current page via window.onMeshMessage(msg).
 * @private
 * @memberof app
 * @instance
 * @param {Object} msg - The position payload containing position details.
 * @returns {void}
 */
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

function _handleTelemetry(msg) {
     if (typeof window.onTelemetryUpdate === 'function') {
       window.onTelemetryUpdate(msg);
     }
   }

function _handleNode(msg){
 //Handle payloads that contain node information
}

/**
 * @function _handleSdrStatus
 * @description Updates the SDRangel connectivity indicator (header dot + UDP port badge)
 * based on backend heartbeat status. This is independent of the WebSocket connection
 * status shown in the footer.
 * @private
 * @memberof app
 * @instance
 * @param {Object} status - { connected: boolean, port: number }
 * @returns {void}
 */
function _handleSdrStatus(status) {
  if (_sdrDot) {
    _sdrDot.style.background = status.connected ? '#22c55e' : '#ef4444';
  }
  if (_sdrPortBadge) {
    _sdrPortBadge.textContent = status.connected ? `UDP ${status.port}` : `UDP ----`;
    _sdrPortBadge.style.border = status.connected ? '1px solid #22c55e' : '1px solid #ef4444';
    _sdrPortBadge.style.color = status.connected ? '#22c55e' : '#ef4444';
    _sdrPortBadge.style.background = status.connected ? '#22c55e3a' : '#ef44443a';
  }

  try {
    sessionStorage.setItem(SK.SDR_STATUS, JSON.stringify(status));
  } catch { /* sessionStorage full or unavailable — non-critical */ }
}

/* Main App starts here */
window.meshState = _loadState();

/* Derived — not stored, always computed */
Object.defineProperty(window.meshState, 'nodeCount', {
  get() { return Object.keys(this.nodes).length; }
});

updateSidebarStats();

updateUptime();
setInterval(updateUptime, 1000);

/* SHARED UTILITY: HTML escaping on window so page scripts can call escapeHtml() without re-defining it. */
window.escapeHtml = function(str) {
    return String(str)
        .replace(/&/g,  '&amp;')
        .replace(/</g,  '&lt;')
        .replace(/>/g,  '&gt;')
        .replace(/"/g,  '&quot;')
        .replace(/'/g,  '&#39;');
};
/* CLEANUP */
window.addEventListener('beforeunload', () => {
    if (_ws) {
        _ws.close();
    }
});
window.persistMeshState = _persistState;
window.updateSidebarStats = updateSidebarStats;

/* Restore last known SDR status immediately on load, before the new
   WS connection has a chance to report anything — this is what stops
   the dot flashing red on every page navigation. */
try {
  const lastSdrStatus = JSON.parse(sessionStorage.getItem(SK.SDR_STATUS) || 'null');
  if (lastSdrStatus) {
    _handleSdrStatus(lastSdrStatus);
  }
} catch { /* corrupt or missing entry — fall back to default red, fine */ }

/* Boot */
connectWebSocket();