/**
 * map.js — Leaflet map initialisation and node marker management
 *
 * Loaded only on /map (map.html).
 * Exposes two globals consumed by map.html's inline <script>:
 *
 *   window.initLeafletMap(containerId)
 *     → Creates the Leaflet map inside the element with that id.
 *     → Replays any nodes already in window.meshState.nodeData.
 *
 *   window.mapAddOrUpdateNode(nodeId, data)
 *     → Called by window.onMeshMessage in map.html for every packet that
 *       carries GPS coords.
 *     → data: { lat, lon, snr?, longName?, lastMsg?, timestamp? }
 *
 * Toolbar buttons (fitMapToNodes, clearMapMarkers) are also exported so the
 * HTML onclick attributes in map.html can reach them.
 */

/* ════════════════════════════════════════════════════════════════════════════
   MODULE STATE
════════════════════════════════════════════════════════════════════════════ */
let _map        = null;           // Leaflet map instance
let _markers    = new Map();      // nodeId → L.CircleMarker
let _osmLayer   = null;
let _cartoLayer = null;

/* ════════════════════════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════════════════════════ */
window.initLeafletMap = function(containerId) {
    if (_map) return;   // guard against double-init

    _map = L.map(containerId, {
        center:      [20, 0],
        zoom:        2,
        zoomControl: true
    });

    // ── Tile layers ────────────────────────────────────────────────────────
    _osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom:     19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    });

    // CARTO Dark — great dark-mode tile set, also open-source-backed
    _cartoLayer = L.tileLayer(
        'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom:     19,
        attribution: '© <a href="https://carto.com/">CARTO</a>'
    });

    _osmLayer.addTo(_map);

    // Auto-fallback: if OSM tiles fail (e.g. offline), switch to CARTO
    let _osmFailed = false;
    _osmLayer.on('tileerror', () => {
        if (!_osmFailed) {
            _osmFailed = true;
            console.warn('map.js: OSM tiles unreachable — switching to CARTO');
            _map.removeLayer(_osmLayer);
            _cartoLayer.addTo(_map);
        }
    });

    // Layer switcher control (top-right)
    L.control.layers({
        'OpenStreetMap': _osmLayer,
        'CARTO Dark':    _cartoLayer
    }).addTo(_map);

    // ── Offline banner check ───────────────────────────────────────────────
    _checkTileReachability();

    // ── Replay nodes already received before the map page was opened ───────
    const state = window.meshState;
    if (state && state.nodeData) {
        state.nodeData.forEach((data, nodeId) => {
            if (data.lat != null && data.lon != null) {
                _addOrUpdateMarker(nodeId, data);
            }
        });
    }
};

/* ════════════════════════════════════════════════════════════════════════════
   PUBLIC: add or move a node marker
════════════════════════════════════════════════════════════════════════════ */
window.mapAddOrUpdateNode = function(nodeId, data) {
    if (!_map) return;   // map not yet initialised
    _addOrUpdateMarker(nodeId, data);
};

/* ════════════════════════════════════════════════════════════════════════════
   INTERNAL: create or update a CircleMarker
════════════════════════════════════════════════════════════════════════════ */
function _addOrUpdateMarker(nodeId, data) {
    if (data.lat == null || data.lon == null) return;

    const label = data.longName || nodeId;
    const popup = _buildPopupHtml(nodeId, label, data);

    if (_markers.has(nodeId)) {
        // Move and refresh the existing marker
        const m = _markers.get(nodeId);
        m.setLatLng([data.lat, data.lon]);
        m.setPopupContent(popup);
    } else {
        // Create a new marker
        const m = L.circleMarker([data.lat, data.lon], {
            radius:      8,
            fillColor:   '#3b82f6',
            color:       '#1d4ed8',
            weight:      2,
            opacity:     1,
            fillOpacity: 0.85
        }).bindPopup(popup);

        m.addTo(_map);
        _markers.set(nodeId, m);
    }

    _updateNodeCountPill();
}

function _buildPopupHtml(nodeId, label, data) {
    const esc = window.escapeHtml || (s => String(s));
    return `
        <div class="popup-node">
            <strong>${esc(label)}</strong>
            <small>ID: ${esc(nodeId)}</small>
            ${data.lastMsg  ? `<small>Msg: ${esc(data.lastMsg)}</small>`         : ''}
            ${data.timestamp? `<small>Seen: ${esc(data.timestamp)}</small>`      : ''}
            ${data.snr != null ? `<small>SNR: ${esc(data.snr)} dB</small>`       : ''}
            <small>📍 ${data.lat.toFixed(5)}, ${data.lon.toFixed(5)}</small>
        </div>`;
}

function _updateNodeCountPill() {
    const el = document.getElementById('map-node-count');
    if (el) el.textContent = `${_markers.size} node${_markers.size !== 1 ? 's' : ''}`;
}

/* ════════════════════════════════════════════════════════════════════════════
   TOOLBAR ACTIONS  (called from map.html onclick attributes)
════════════════════════════════════════════════════════════════════════════ */
window.fitMapToNodes = function() {
    if (!_map || _markers.size === 0) return;
    const latlngs = [..._markers.values()].map(m => m.getLatLng());
    _map.fitBounds(L.latLngBounds(latlngs), { padding: [48, 48] });
};

window.clearMapMarkers = function() {
    _markers.forEach(m => _map.removeLayer(m));
    _markers.clear();
    _updateNodeCountPill();
};

/* ════════════════════════════════════════════════════════════════════════════
   OFFLINE DETECTION
   Uses a HEAD request in no-cors mode. A successful fetch (no throw) means
   the network reached the tile CDN. A failure (CORS error thrown by fetch)
   indicates we're offline and shows the warning banner.
════════════════════════════════════════════════════════════════════════════ */
async function _checkTileReachability() {
    try {
        await fetch('https://tile.openstreetmap.org/0/0/0.png', {
            method: 'HEAD',
            mode:   'no-cors',
            cache:  'no-store'
        });
        // If we reach here, at least the request didn't throw — tiles likely reachable
    } catch {
        const banner = document.getElementById('map-offline-banner');
        if (banner) banner.style.display = 'block';
    }
}
