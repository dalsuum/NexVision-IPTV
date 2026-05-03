// ── TV platform mode ─────────────────────────────────────────────────────────
// Activated by ?platform=tv (set by the before_request redirect for Android TV
// and Chromecast user-agents). Adds body.tv-mode which drives the CSS layer,
// and wires a MutationObserver to tabindex-stamp tiles as they're rendered
// (channels/movies/radio load via API, so they don't exist at parse time).
(function () {
  if (new URLSearchParams(window.location.search).get('platform') !== 'tv') return;

  document.body.classList.add('tv-mode');

  // Selectors that need tabindex=0 to be D-pad focusable (non-native elements).
  // <button> and <a> are already focusable; only divs/spans used as tiles need it.
  const TV_FOCUSABLE =
    '.ch-card,.ch-row,.mv-card,.movie-tile,.station-card,' +
    '.svc-tile,.info-tile,.sec-link,.info-list-row,.msg-card-inbox';

  function stampFocusable(root) {
    root.querySelectorAll(TV_FOCUSABLE).forEach(el => {
      if (!el.hasAttribute('tabindex')) el.tabIndex = 0;
    });
  }

  // Stamp anything already in the DOM (static markup, early-rendered content).
  stampFocusable(document.body);

  // Stamp dynamically rendered tiles as the API populates the page.
  new MutationObserver(mutations => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (node.matches?.(TV_FOCUSABLE) && !node.hasAttribute('tabindex')) node.tabIndex = 0;
        stampFocusable(node);
      }
    }
  }).observe(document.body, { childList: true, subtree: true });
})();
// ─────────────────────────────────────────────────────────────────────────────

const API = window.location.origin + '/api'; // auto-detect server address
const THEME_KEY = 'nv_theme_mode';
let allChannels = [], allMovies = [], allRadio = [], allGroups = [];
let allSeries = [];
let _vodSearchQ = '', _vodActiveGenre = null, _vodShowFavs = false;
let _vodTab = 'all', _vodGenreActive = null;
let _vodFavs    = new Set(JSON.parse(localStorage.getItem('nv_fav_movies')  || '[]'));
let _seriesFavs = new Set(JSON.parse(localStorage.getItem('nv_fav_series') || '[]'));
let currentChId  = -1;
let currentStation = null;
let _epgNowMap = {};  // channel_id → current programme title
let _epgNextMap = {}; // channel_id → next programme title
let _epgNowTimeMap = {};  // channel_id → now time range HH:MM-HH:MM
let _epgNextTimeMap = {}; // channel_id → next time range HH:MM-HH:MM
let radioAudio = null;
let isMuted = false;
let activeScreen = 'home';
let hlsInstance  = null;
let _tvPlaySeq   = 0;
const _badLogoUrls = new Set();
const _badLogoHosts = new Set();
const _logoHostFailCount = new Map();

function logoHost(url) {
  try {
    const u = new URL(String(url || '').trim(), window.location.origin);
    return (u.hostname || '').toLowerCase();
  } catch (_) {
    return '';
  }
}

function usableLogo(url) {
  const u = String(url || '').trim();
  if (!u) return '';
  const host = logoHost(u);
  if (host && _badLogoHosts.has(host)) return '';
  return _badLogoUrls.has(u) ? '' : u;
}

function markLogoFailed(img) {
  if (!img) return;
  try {
    const raw = (img.getAttribute('data-logo-src') || '').trim();
    const abs = (img.currentSrc || img.src || '').trim();
    if (raw) _badLogoUrls.add(raw);
    if (abs) _badLogoUrls.add(abs);

    const host = logoHost(raw || abs);
    if (host) {
      const n = (_logoHostFailCount.get(host) || 0) + 1;
      _logoHostFailCount.set(host, n);
      if (n >= 3) _badLogoHosts.add(host);
    }
  } catch (_) {}
  img.style.display = 'none';
  const next = img.nextElementSibling;
  if (next && next.classList && next.classList.contains('ch-mono-lbl')) {
    next.style.display = 'flex';
  }
}

function parseEpgDate(v) {
  // Support SQLite datetime format: YYYY-MM-DD HH:MM:SS
  const s = String(v || '').trim();
  if (!s) return new Date(NaN);
  return new Date(s.includes('T') ? s : s.replace(' ', 'T'));
}

// ── Room Token & Registration ─────────────────────────────────────────────────
const ROOM_TOKEN_KEY = 'nv_room_token';
const ROOM_INFO_KEY  = 'nv_room_info';

function getRoomToken() {
  return localStorage.getItem(ROOM_TOKEN_KEY) || '';
}
function getRoomInfo() {
  try { return JSON.parse(localStorage.getItem(ROOM_INFO_KEY) || 'null'); }
  catch(e) { return null; }
}
function isRegistered() {
  return !!getRoomToken();
}
function clearRegistration() {
  localStorage.removeItem(ROOM_TOKEN_KEY);
  localStorage.removeItem(ROOM_INFO_KEY);
}

// ── On-screen numpad helpers ──────────────────────────────────────────────────
function regKey(k) {
  const inp = document.getElementById('reg-input');
  if (!inp) return;
  if (k === 'del') {
    inp.value = inp.value.slice(0, -1);
  } else {
    if (inp.value.length < 10) inp.value += k;
  }
  regInputChange();
}
function regInputChange() {
  const inp = document.getElementById('reg-input');
  const btn = document.getElementById('reg-btn');
  const err = document.getElementById('reg-error');
  if (!inp || !btn) return;
  btn.disabled = inp.value.trim().length === 0;
  if (err) err.textContent = '';
}

// ── Registration by room number ───────────────────────────────────────────────
async function doRegister() {
  const inp  = document.getElementById('reg-input');
  const btn  = document.getElementById('reg-btn');
  const err  = document.getElementById('reg-error');
  const room = inp ? inp.value.trim() : '';
  if (!room) return;

  btn.disabled = true;
  btn.textContent = 'Connecting...';
  if (err) err.textContent = '';

  try {
    const res = await fetch(API + '/rooms/register', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({ room_number: room })
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      if (err) err.textContent = data.error || 'Registration failed. Try again.';
      btn.disabled = false;
      btn.textContent = 'Confirm';
      return;
    }

    // Success — save token and room info (including guest data from PMS)
    localStorage.setItem(ROOM_TOKEN_KEY, data.token);
    localStorage.setItem(ROOM_INFO_KEY, JSON.stringify({
      room_number:  data.room_number,
      tv_name:      data.tv_name,
      guest_name:   data.guest_name   || '',
      checkin_time: data.checkin_time || '',
      checkout_time:data.checkout_time|| '',
    }));
    sessionStorage.removeItem('nv_welcome_shown');

    // Hide registration screen
    const regScreen = document.getElementById('register-screen');
    if (regScreen) regScreen.classList.add('hidden');

    // Update header room badge
    updateRoomBadge();
    const _unit = (window._deployMode||'hotel')!=='commercial' ? 'Room' : 'Screen';
    showSetupBanner('✅ ' + _unit + ' <b>' + data.room_number + '</b> — ' + data.tv_name, 'green');
    setTimeout(() => {
      const b = document.getElementById('setup-banner');
      if (b) b.style.display = 'none';
    }, 4000);

    // Load the app
    await loadApp();
    initCastQR();
    initAlarmChecker();

  } catch(e) {
    if (err) err.textContent = 'Cannot reach server. Check network connection.';
    btn.disabled = false;
    btn.textContent = 'Confirm';
  }
}


// ── Show registration screen (blocks until registered) ────────────────────────
function showRegisterScreen() {
  const el = document.getElementById('register-screen');
  if (el) el.classList.remove('hidden');
  // Hide splash
  const splash = document.getElementById('splash');
  if (splash) { splash.classList.add('hide'); }
  // Focus input after a moment
  setTimeout(() => {
    const inp = document.getElementById('reg-input');
    if (inp) inp.focus();
  }, 300);
}

function applyDeployMode() {
  const isHotel = (window._deployMode || 'hotel') !== 'commercial';

  // Registration screen labels
  const sub   = document.getElementById('reg-sub');
  const label = document.getElementById('reg-label');
  const hint  = document.getElementById('reg-hint');
  const inp   = document.getElementById('reg-input');
  if (sub)   sub.textContent   = isHotel ? 'Room Registration'      : 'Screen Registration';
  if (label) label.textContent = isHotel ? 'Enter your room number' : 'Enter your screen / location ID';
  if (hint)  hint.innerHTML    = isHotel
    ? 'Ask your supervisor if your room number is not accepted.<br>This only needs to be done once on this device.'
    : 'Ask your administrator if your screen ID is not accepted.<br>This only needs to be done once on this device.';
  if (inp && !isHotel) { inp.inputMode = 'text'; inp.placeholder = 'e.g. LOBBY-1'; }

  // Rebuild nav to apply hotel-only filter (if nav already loaded)
  if (_navConfig && _navConfig.items && _navConfig.items.length) buildNav();
}

function updateRoomBadge() {
  const info = getRoomInfo();
  const el   = document.getElementById('hdr-room');
  if (!el) return;
  if (info && info.room_number) {
    const isHotel = (window._deployMode || 'hotel') !== 'commercial';
    el.textContent = (isHotel ? 'Room ' : 'Screen ') + info.room_number;
    el.style.display = 'inline-flex';
  } else {
    el.style.display = 'none';
  }
}

function showSetupBanner(html, color) {
  const el = document.getElementById('setup-banner');
  if (!el) return;
  el.innerHTML = html;
  const isGreen = color === 'green';
  el.style.background    = isGreen ? 'rgba(61,220,132,0.15)' : 'rgba(232,72,85,0.15)';
  el.style.borderColor   = isGreen ? 'rgba(61,220,132,0.4)'  : 'rgba(232,72,85,0.4)';
  el.style.display = 'flex';
}

// TV pagination
let _tvPage      = 0;
let _tvTotal     = 0;
let _tvSearchQ   = '';
let _tvGroupId   = null;
let _tvSearchTimer = null;

// 12 tiles (3×4) in TV remote mode; 100 rows in normal browser mode.
function tvPageSize() {
  return document.body.classList.contains('tv-mode') ? 12 : 100;
}

const channelEmoji = ['📺','🎬','📡','🎭','🏆','🌍','🎵','🎪','📰','🌟','🎯','💫'];

function applyTheme(mode) {
  const m = (mode === 'light') ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', m);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = (m === 'dark') ? 'NORMAL' : 'DARK';
}

function toggleTheme() {
  const cur = localStorage.getItem(THEME_KEY) || 'dark';
  const next = (cur === 'dark') ? 'light' : 'dark';
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}

applyTheme(localStorage.getItem(THEME_KEY) || 'dark');

// ── API ───────────────────────────────────────────────────────────────────────
async function api(path, opts={}) {
  try {
    const headers = { ...(opts.headers || {}) };
    const t = getRoomToken();
    if (t) headers['X-Room-Token'] = t;
    const res = await fetch(API + path, { ...opts, headers });
    if (!res.ok) return null;
    return await res.json();
  } catch(e) { return null; }
}
async function apiChannels(params={}) {
  const size = tvPageSize();
  const p = new URLSearchParams({limit: size, offset: (_tvPage||0)*size, ...params});
  if (_tvSearchQ) p.set('search', _tvSearchQ);
  if (_tvGroupId)  p.set('group_id', _tvGroupId);
  p.set('active','1');
  p.set('envelope','1');
  const data = await api('/channels?' + p.toString());
  if (!data) return [];
  if (Array.isArray(data)) { allChannels = data; _tvTotal = data.length; return data; }
  allChannels = data.channels || [];
  _tvTotal    = data.total    || 0;
  return allChannels;
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, dur=2500) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'), dur);
}

// ── Clock ─────────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  const t = now.toLocaleTimeString('en-US', {hour:'2-digit',minute:'2-digit',hour12:false});
  document.getElementById('hdr-time').textContent = t;
}
setInterval(updateClock, 1000);
updateClock();

// ── Fullscreen OSD ────────────────────────────────────────────────────────────
// Self-contained controller for #fs-osd.  Call show(ch) to reveal it;
// it auto-hides after HIDE_MS.  Any D-pad keypress while in fullscreen
// calls show() with no argument to refresh the timer without re-rendering.
const FsOsd = (() => {
  const HIDE_MS = 4000;
  let _hideTimer  = null;
  let _clockTimer = null;
  let _epgStart   = 0;   // ms since epoch — current programme start
  let _epgEnd     = 0;   // ms since epoch — current programme end

  const $  = id => document.getElementById(id);
  const hm = d  => d.getHours().toString().padStart(2,'0') + ':' +
                   d.getMinutes().toString().padStart(2,'0');

  function _tickClock() {
    const el = $('fs-osd-time');
    if (el) el.textContent = hm(new Date());
  }

  function _tickBar() {
    if (!_epgStart || !_epgEnd) return;
    const pct = Math.min(100, Math.max(0,
      (Date.now() - _epgStart) / (_epgEnd - _epgStart) * 100
    ));
    const el = $('fs-osd-bar');
    if (el) el.style.width = pct + '%';
  }

  function _resetTimer() {
    clearTimeout(_hideTimer);
    _hideTimer = setTimeout(hide, HIDE_MS);
  }

  // Called from the EPG fetch callback in playChannel once we know the
  // current programme's window, giving the bar real timestamps to work with.
  function setEpg(title, startMs, endMs) {
    _epgStart = startMs;
    _epgEnd   = endMs;
    const el = $('fs-osd-epg');
    if (el) el.textContent = title ? '▶ ' + title : '';  // ▶ thin-sp title
    _tickBar();
  }

  // Populate logo, name, and EPG text from a channel object.
  function _update(ch) {
    // Logo
    const logoEl = $('fs-osd-logo');
    if (logoEl) {
      const url = typeof usableLogo === 'function' ? usableLogo(ch.tvg_logo_url) : '';
      logoEl.innerHTML = url
        ? `<img src="${url}" style="width:64px;height:64px;object-fit:contain" onerror="this.outerHTML='📺'">`
        : '📺';
    }
    // Name
    const nameEl = $('fs-osd-name');
    if (nameEl) nameEl.textContent = ch.name || '—';
    // EPG title from the live map (may be populated before setEpg fires)
    const epgEl = $('fs-osd-epg');
    if (epgEl && !epgEl.textContent) {
      const t = (typeof _epgNowMap !== 'undefined') && _epgNowMap[ch.id];
      if (t) epgEl.textContent = '▶ ' + t;
    }
  }

  // show(ch) — reveal OSD and start/restart the 4-second hide timer.
  // Pass a channel object the first time; omit it on subsequent D-pad presses
  // (content stays the same, only the timer resets).
  function show(ch) {
    const osd = $('fs-osd');
    if (!osd) return;
    if (ch) {
      // Clear stale EPG bar whenever a new channel is selected.
      _epgStart = _epgEnd = 0;
      $('fs-osd-bar') && ($('fs-osd-bar').style.width = '0%');
      $('fs-osd-epg') && ($('fs-osd-epg').textContent = '');
      _update(ch);
    }
    _tickClock();
    _tickBar();
    osd.classList.add('fs-osd--visible');
    // Restart per-second ticks while OSD is on screen.
    clearInterval(_clockTimer);
    _clockTimer = setInterval(() => { _tickClock(); _tickBar(); }, 1000);
    _resetTimer();
  }

  function hide() {
    clearTimeout(_hideTimer);
    clearInterval(_clockTimer);
    _hideTimer = _clockTimer = null;
    const osd = $('fs-osd');
    if (osd) osd.classList.remove('fs-osd--visible');
  }

  return { show, hide, setEpg };
})();

// ── Google Cast Web Sender ────────────────────────────────────────────────────
// App ID is read from admin settings (cast_app_id). Falls back to Google's
// Default Media Receiver if the field is left blank.
const CAST_APP_ID_DEFAULT = 'CC1AD845';

const CastMgr = (() => {
  let _ctx        = null;  // cast.framework.CastContext
  let _session    = null;  // CastSession, non-null while a device is connected
  let _pendingVod = null;  // { url, title, posterUrl } — queued VOD cast waiting for a session

  // The SDK fires this callback asynchronously after it finishes loading.
  // Because our main <script> block runs synchronously before the async SDK
  // fires, this assignment is always in place when the callback lands.
  window['__onGCastApiAvailable'] = function (isAvailable) {
    if (!isAvailable) return;

    const appId = (_settings?.cast_app_id || '').trim() || CAST_APP_ID_DEFAULT;
    _ctx = cast.framework.CastContext.getInstance();
    _ctx.setOptions({
      receiverApplicationId: appId,
      autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
    });

    _ctx.addEventListener(
      cast.framework.CastContextEventType.SESSION_STATE_CHANGED,
      _onSessionState
    );

    _updateButtons();
  };

  function _onSessionState(e) {
    const SS = cast.framework.SessionState;
    const s  = e.sessionState;

    if (s === SS.SESSION_STARTED || s === SS.SESSION_RESUMED) {
      _session = _ctx.getCurrentSession();
      if (_pendingVod) {
        // Session was requested from the VOD player — cast the queued VOD.
        const { url, title, posterUrl } = _pendingVod;
        _pendingVod = null;
        loadVod(url, title, posterUrl);
      } else {
        // Auto-cast whatever channel is already playing when a session opens.
        const ch = allChannels.find(c => c.id === currentChId);
        if (ch) _doLoad(ch);
      }
    } else if (s === SS.SESSION_ENDED || s === SS.NO_SESSION) {
      _session    = null;
      _pendingVod = null;
    }
    _updateButtons();
  }

  function _doLoad(ch) {
    if (!_session || !ch) return;
    const url = (ch.stream_url || '').trim();
    // UDP/RTP multicast is not routable to a Cast receiver.
    if (!url || url.startsWith('udp://') || url.startsWith('rtp://')) return;

    const mediaInfo = new chrome.cast.media.MediaInfo(url, 'application/x-mpegURL');
    mediaInfo.streamType = chrome.cast.media.StreamType.LIVE;

    const meta = new chrome.cast.media.GenericMediaMetadata();
    meta.title = ch.name;
    const logo = (typeof usableLogo === 'function') ? usableLogo(ch.tvg_logo_url) : '';
    if (logo) meta.images = [new chrome.cast.Image(logo)];
    mediaInfo.metadata = meta;

    _session.loadMedia(new chrome.cast.media.LoadRequest(mediaInfo))
      .catch(err => console.warn('[CastMgr] loadMedia failed:', err));
  }

  function _updateButtons() {
    const available = !!_ctx;
    const connected = !!_session;
    document.querySelectorAll('.cast-btn').forEach(btn => {
      btn.style.display = available ? '' : 'none';
      btn.classList.toggle('cast-btn--connected', connected);
      btn.title = connected ? 'Casting — click to disconnect' : 'Cast to TV';
    });
  }

  // Public: open the Cast device-picker dialog.
  function requestSession() {
    if (!_ctx) return;
    _ctx.requestSession().catch(() => {});
  }

  // Public: open the device-picker with a VOD queued — sent to receiver once session connects.
  function requestSessionForVod(url, title, posterUrl) {
    if (!_ctx) return;
    _pendingVod = { url, title, posterUrl };
    _ctx.requestSession().catch(() => { _pendingVod = null; });
  }

  // Public: called from playChannel() to mirror the live stream to the receiver.
  function loadMedia(ch) {
    _doLoad(ch);
  }

  // Public: send a VOD item to the Cast receiver.
  function loadVod(url, title, posterUrl) {
    if (!_session) return;
    const absUrl = url.startsWith('/') ? `${location.origin}${url}` : url;
    const ct = absUrl.includes('.m3u8') ? 'application/x-mpegURL' : 'video/mp4';
    const mediaInfo = new chrome.cast.media.MediaInfo(absUrl, ct);
    mediaInfo.streamType = chrome.cast.media.StreamType.BUFFERED;
    const meta = new chrome.cast.media.MovieMediaMetadata();
    meta.title = title || '';
    if (posterUrl) meta.images = [new chrome.cast.Image(posterUrl)];
    mediaInfo.metadata = meta;
    _session.loadMedia(new chrome.cast.media.LoadRequest(mediaInfo))
      .catch(err => console.warn('[CastMgr] VOD loadMedia failed:', err));
  }

  // Public: whether a Cast session is currently active.
  function isConnected() { return !!_session; }

  return { requestSession, requestSessionForVod, loadMedia, loadVod, isConnected };
})();

// ── Screen ────────────────────────────────────────────────────────────────────
const screenLoaders = {
  home: loadHome, tv: loadTV, vod: loadVoD,
  radio: loadRadio, weather: loadWeather, info: loadInfo, cast: loadCast,
  clock: loadWorldClock,
};
let loadedScreens = new Set();

// ── Stop video playback (call when leaving TV screen) ────────────────────────
function stopVideoPlayback() {
  try {
    _tvPlaySeq++;
    if (hlsInstance) { hlsInstance.destroy(); hlsInstance = null; }
    const video = document.getElementById('player');
    if (video) { video.pause(); video.src = ''; video.load(); }
    const overlay = document.getElementById('player-overlay');
    if (overlay) overlay.style.display = 'flex';
    closeEpg();
  } catch(e) {}
}

// Named bulk delete functions (needed after filter re-render)
async function bulkDeleteChs() {
  const ids = getSelected('ch');
  if (!ids.length) { toast('Select channels first'); return; }
  if (!confirm('Delete ' + ids.length + ' channel(s)?')) return;
  const r = await req('/channels/bulk-delete', {method:'POST', body:JSON.stringify({ids})});
  if (r?.ok) { toast('Deleted ' + r.deleted + ' channels'); await pages.channels(); }
}

async function showScreen(name) {
  // v8: block disabled nav screens — but always allow 'messages' (header button)
  if (name !== 'home' && name !== 'messages') {
    const navItems = _navConfig && _navConfig.items ? _navConfig.items : [];
    const item = navItems.find(it => it.key === name || it.target_url === name);
    if (item && !item.enabled) return; // screen disabled in nav config
  }
  // v8: dynamic nav highlight
  setNavActive(name);
  document.querySelectorAll('.screen').forEach(s=>{
    s.classList.remove('active','show');
  });
  const el = document.getElementById('screen-'+name);
  if (el) {
    el.classList.add('active');
    // stop world clock tick when navigating away
    if (name !== 'clock') clearInterval(_wcTickTimer);
    // stop video when navigating away from TV screen
    if (name !== 'tv') { stopVideoPlayback(); closeEpg(); }
    // stop radio when navigating away from radio screen
    if (name !== 'radio' && radioAudio && !radioAudio.paused) {
      radioAudio.pause();
      radioAudio.src = '';
      currentStation = null;
      const vinyl = document.getElementById('radio-vinyl');
      if (vinyl) vinyl.classList.remove('spinning');
      const nowEl = document.getElementById('radio-now');
      if (nowEl) nowEl.textContent = '';
    }
    // v7: render dynamic screens on demand
    if (name === 'services') { _services = []; renderServicesScreen(); } // always fresh
    if (name === 'messages') { loadInbox().then(() => renderInbox()).catch(()=>{}); }
    if (name === 'prayers')  { renderPrayerScreen(); }
    if (name === 'cast')     { loadedScreens.delete('cast'); } // always re-render (settings may change)
    if (name === 'clock')    { loadedScreens.delete('clock'); clearInterval(_wcTickTimer); } // restart tick
    requestAnimationFrame(()=>el.classList.add('show'));
  }
  activeScreen = name;
  if (!loadedScreens.has(name)) {
    loadedScreens.add(name);
    await screenLoaders[name]?.();
  }
}

// ── HOME ──────────────────────────────────────────────────────────────────────
async function loadHome() {
  const [chData, movies, groups, slides, featuredMovies, epgData] = await Promise.all([
    api('/channels?limit=300&active=1&envelope=1'),
    api('/vod'),
    api('/media-groups'),
    api('/slides'),
    api('/vod?featured=1'),
    api('/epg?hours=8')
  ]);

  if (Array.isArray(epgData) && epgData.length) {
    const nowMs = Date.now();
    const map = {};
    const nextMap = {};
    const nowTimeMap = {};
    const nextTimeMap = {};
    const nextStartByChannel = {};
    const fmtHm = ms => {
      const d = new Date(ms);
      return d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
    };
    for (const e of epgData) {
      const chId = parseInt(e.channel_id);
      if (!chId) continue;
      const startMs = parseEpgDate(e.start_time).getTime();
      const endMs = parseEpgDate(e.end_time).getTime();
      if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) continue;

      if (startMs <= nowMs && endMs > nowMs) {
        map[chId] = e.title;
        nowTimeMap[chId] = fmtHm(startMs) + '-' + fmtHm(endMs);
      }
      if (startMs > nowMs && (!nextStartByChannel[chId] || startMs < nextStartByChannel[chId])) {
        nextStartByChannel[chId] = startMs;
        nextMap[chId] = e.title;
        nextTimeMap[chId] = fmtHm(startMs) + '-' + fmtHm(endMs);
      }
    }
    _epgNowMap = map;
    _epgNextMap = nextMap;
    _epgNowTimeMap = nowTimeMap;
    _epgNextTimeMap = nextTimeMap;
  } else {
    _epgNowMap = {};
    _epgNextMap = {};
    _epgNowTimeMap = {};
    _epgNextTimeMap = {};
  }

  if (chData && Array.isArray(chData)) { allChannels = chData; _tvTotal = chData.length; }
  else if (chData && chData.channels)  { allChannels = chData.channels; _tvTotal = chData.total; }
  allMovies  = movies  || [];
  _vodPlaylist = allMovies;
  allGroups  = groups  || [];
  _promoSlides = slides || [];

  const homeChannelsLimit = Math.max(8, Math.min(40, parseInt(_settings.home_channels_limit || '20') || 20));
  let withEpg = allChannels.filter(c => _epgNowMap[c.id] || _epgNextMap[c.id]);

  // If the first page of channels has no EPG overlap, fetch a wider active list.
  if (!withEpg.length) {
    try {
      const chWide = await api('/channels?limit=3000&active=1&envelope=1');
      const wideChannels = (chWide && chWide.channels) ? chWide.channels : (Array.isArray(chWide) ? chWide : []);
      if (wideChannels.length) {
        allChannels = wideChannels;
        _tvTotal = (chWide && chWide.total) ? chWide.total : wideChannels.length;
        withEpg = allChannels.filter(c => _epgNowMap[c.id] || _epgNextMap[c.id]);
      }
    } catch (_) {}
  }

  // Any EPG channel still missing from allChannels (beyond the 3000 limit)?
  // Fetch them individually so EPG cards always appear on the home screen.
  if (!withEpg.length && Object.keys(_epgNowMap).length) {
    const epgIds = [...new Set([...Object.keys(_epgNowMap), ...Object.keys(_epgNextMap)].map(Number))];
    const knownIds = new Set(allChannels.map(c => c.id));
    const missingIds = epgIds.filter(id => !knownIds.has(id));
    if (missingIds.length) {
      const fetched = await Promise.all(missingIds.map(id => api('/channels/' + id).catch(() => null)));
      const valid = fetched.filter(Boolean);
      if (valid.length) {
        allChannels = [...valid, ...allChannels];
        withEpg = allChannels.filter(c => _epgNowMap[c.id] || _epgNextMap[c.id]);
      }
    }
  }

  const withoutEpg = allChannels.filter(c => !(_epgNowMap[c.id] || _epgNextMap[c.id]));
  const homeChannels = [...withEpg, ...withoutEpg].slice(0, homeChannelsLimit);

  const showFeatured = (_settings.home_show_featured !== '0');
  const showSlides   = (_settings.home_show_slides   !== '0');
  const showWelcome  = (_settings.home_show_welcome  === '1');
  const showChannels = (_settings.home_show_channels !== '0');
  const showVod      = (_settings.home_show_vod      !== '0');
  const slidesStyle  = _settings.home_slides_style   || 'full';
  const welcomeStyle   = _settings.welcome_style       || _settings.home_welcome_type || 'text';
  const welcomeText    = _settings.home_welcome_text   || _settings.welcome_message   || '';
  const welcomePhoto   = _settings.home_welcome_photo  || _settings.welcome_image     || '';
  const photoPos       = _settings.home_welcome_photo_pos     || 'center';
  const photoOverlayPct= parseInt(_settings.home_welcome_photo_overlay ?? 40);
  const overlayRgba    = `rgba(0,0,0,${(photoOverlayPct/100).toFixed(2)})`;
  const hotelName    = _settings.hotel_name          || 'Welcome';
  const featured     = (featuredMovies && featuredMovies[0]) || allMovies[0];
  const el           = document.getElementById('screen-home');

  let heroHTML = '';

  // ── SIDE-BY-SIDE: promo slides + welcome message left/right ───────────────
  if (showSlides && _promoSlides.length > 0 && showWelcome && slidesStyle === 'side') {
    heroHTML += `<div class="home-split-hero">
      <div class="split-welcome">
        <div style="position:relative;z-index:1">
          <div class="welcome-hotel">${escHtml(hotelName)}</div>
          <div class="welcome-title" style="font-size:clamp(20px,2.5vw,32px)">Welcome</div>
          <div class="welcome-msg">${welcomeText}</div>
        </div>
      </div>
      <div id="promo-slides-wrap" style="position:relative;overflow:hidden">
        ${_buildSlideItems()}
        ${_promoSlides.length > 1 ? `<div class="promo-dots">${_promoSlides.map((_,i)=>`<div class="promo-dot ${i===0?'active':''}" onclick="goToSlide(${i})"></div>`).join('')}</div>` : ''}
      </div>
    </div>`;
  } else {
    // ── Promo slides section (full width) ──────────────────────────────────
    if (showSlides && _promoSlides.length > 0) {
      heroHTML += `
      <div id="promo-slides-wrap" class="style-full">
        ${_buildSlideItems()}
        ${_promoSlides.length > 1 ? `<div class="promo-dots">${_promoSlides.map((_,i)=>`<div class="promo-dot ${i===0?'active':''}" onclick="goToSlide(${i})"></div>`).join('')}</div>` : ''}
      </div>`;
    }

    // ── Welcome message / banner ──────────────────────────────────────────
    if (showWelcome && (welcomeText || welcomePhoto)) {
      if ((welcomeStyle === 'fullscreen' || welcomeStyle === 'photo' || welcomeStyle === 'both') && welcomePhoto) {
        heroHTML += `<div class="welcome-full" style="background-image:url('${welcomePhoto}');background-position:${photoPos} center">
          <div class="welcome-full-overlay" style="background:${overlayRgba}"></div>
          <div class="welcome-full-content">
            <div class="welcome-hotel">${escHtml(hotelName)}</div>
            <div class="welcome-title">Welcome</div>
            ${welcomeText ? `<div class="welcome-msg">${welcomeText}</div>` : ''}
          </div>
        </div>`;
      } else if (welcomeStyle === 'side-photo' && welcomePhoto) {
        heroHTML += `<div class="welcome-section">
          <img class="welcome-photo" src="${welcomePhoto}" alt="Welcome" onerror="this.style.display='none'" style="object-position:${photoPos} center">
          <div class="welcome-text-wrap">
            <div class="welcome-hotel">${escHtml(hotelName)}</div>
            <div class="welcome-title">Welcome</div>
            <div class="welcome-msg">${welcomeText}</div>
          </div>
        </div>`;
      } else {
        heroHTML += `<div class="welcome-section" style="justify-content:center;text-align:center">
          <div>
            <div class="welcome-hotel">${escHtml(hotelName)}</div>
            <div class="welcome-title">Welcome</div>
            <div class="welcome-msg">${welcomeText}</div>
          </div>
        </div>`;
      }
    }
  }

  // ── Featured movie hero ─────────────────────────────────────────────────
  if (showFeatured && featured) {
    heroHTML += `
    <div class="hero-banner">
      <div class="hero-bg"></div>
      <div class="hero-overlay"></div>
      <div class="hero-content">
        <div class="hero-label">🎬 Featured</div>
        <div class="hero-title">${escHtml(featured.title || 'Welcome to NexVision')}</div>
        <div class="hero-meta">
          <span>⭐ ${featured.rating || '8.5'}</span>
          <span>${featured.year || '2024'}</span>
          <span>${featured.genre || 'Entertainment'}</span>
          <span>${featured.runtime || 120} min</span>
        </div>
        <div class="hero-btns">
          <button class="btn-hero btn-hero-primary" onclick="openMovieDetail(${featured.id || 0})">▶ Watch Now</button>
          <button class="btn-hero btn-hero-ghost" onclick="showScreen('vod')">Browse Library</button>
        </div>
      </div>
    </div>`;
  }

  // ── If nothing enabled, show minimal welcome ──────────────────────────
  if (!heroHTML) {
    heroHTML = `<div style="padding:48px 32px;text-align:center">
      <div style="font-family:'Cormorant Garamond',serif;font-size:36px;font-weight:300;color:var(--gold);margin-bottom:8px">${escHtml(hotelName)}</div>
      <div style="color:var(--dimmed);font-size:15px">${escHtml(welcomeText || 'Enjoy your stay!')}</div>
    </div>`;
  }

  el.innerHTML = heroHTML +
  (showChannels ? `
  <div class="home-section">
    <div class="sec-header">
      <div class="sec-title">Live Channels</div>
      <div class="sec-count">${_tvTotal || allChannels.length} channels</div>
      <a class="sec-link" onclick="showScreen('tv')">View all →</a>
    </div>
    <div class="h-scroll-wrap">
      <button class="h-nav-btn left" onclick="scrollHomeRow('home-ch-scroll',-1)" aria-label="Scroll channels left">‹</button>
      <div class="h-scroll" id="home-ch-scroll">
        ${homeChannels.map((c,i) => {
          const logoUrl = usableLogo(c.tvg_logo_url);
          return `
          <div class="ch-card" onclick="quickPlay(${c.id})">
            <div class="ch-img">${logoUrl
              ? `<img src="${logoUrl}" data-logo-src="${logoUrl}" style="width:74px;height:56px;object-fit:contain" onerror="markLogoFailed(this)">`
              : channelEmoji[i % channelEmoji.length]}</div>
            <div class="ch-info">
              <div class="ch-name">${escHtml(c.name)}</div>
              <div class="ch-num">${c.group_title||c.group_name||'Live'}</div>
              ${_epgNowMap[c.id]?`<div class="ch-epg-now"><span class="ch-epg-time-red">${escHtml(_epgNowTimeMap[c.id]||'')}</span>▶ ${escHtml(_epgNowMap[c.id])}</div>`:''}
              ${_epgNextMap[c.id]?`<div class="ch-epg-next"><span class="ch-epg-time-red">${escHtml(_epgNextTimeMap[c.id]||'')}</span>Next: ${escHtml(_epgNextMap[c.id])}</div>`:''}
            </div>
          </div>`;
        }).join('')}
      </div>
      <button class="h-nav-btn right" onclick="scrollHomeRow('home-ch-scroll',1)" aria-label="Scroll channels right">›</button>
    </div>
  </div>` : '') +
  (showVod && allMovies.length > 1 ? `
  <div class="home-section">
    <div class="sec-header">
      <div class="sec-title">Movies</div>
      <div class="sec-count">${allMovies.length}</div>
      <a class="sec-link" onclick="showScreen('vod')">View all →</a>
    </div>
    <div class="h-scroll-wrap">
      <button class="h-nav-btn left" onclick="scrollHomeRow('home-mv-scroll',-1)" aria-label="Scroll movies left">‹</button>
      <div class="h-scroll" id="home-mv-scroll">
        ${allMovies.slice(0,10).map(m => `
          <div class="mv-card" onclick="openMovieDetail(${m.id})">
            <div class="mv-poster"><span style="font-size:32px">🎬</span>
              <div class="mv-badge">★ ${m.rating}</div>
            </div>
            <div class="mv-title">${escHtml(m.title)}</div>
            <div class="mv-sub">${m.year || '—'}</div>
          </div>`).join('')}
      </div>
      <button class="h-nav-btn right" onclick="scrollHomeRow('home-mv-scroll',1)" aria-label="Scroll movies right">›</button>
    </div>
  </div>` : '');

  // Start slide auto-play
  if (showSlides && _promoSlides.length > 1) startSlideshow();
}

function scrollHomeRow(rowId, dir) {
  const row = document.getElementById(rowId);
  if (!row) return;
  const step = Math.max(240, Math.round(row.clientWidth * 0.82));
  row.scrollBy({ left: step * dir, behavior: 'smooth' });
}

// Helper: build promo slide HTML items
function _buildSlideItems() {
  return _promoSlides.map((s, i) => {
    // FIX: only treat as video if media_type is explicitly 'video'
    const isVideo = s.media_type === 'video';
    const clickAttr = s.link_action ? `onclick="promoSlideClick('${escNav(s.link_action)}')"` : '';
    if (isVideo && s.video_url) {
      return `<div class="promo-slide ${i === 0 ? 'active' : ''}" ${clickAttr}>
        <video class="promo-video" autoplay muted loop playsinline
          style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">
          <source src="${s.video_url}" type="video/mp4">
        </video>
        <div class="promo-slide-overlay"></div>
        <div class="promo-slide-content">
          ${s.title ? `<div class="promo-slide-title">${escHtml(s.title)}</div>` : ''}
          ${s.subtitle ? `<div class="promo-slide-sub">${escHtml(s.subtitle)}</div>` : ''}
        </div>
      </div>`;
    }
    // Image slide — use background-image
    const bgStyle = s.image_url ? `style="background-image:url('${s.image_url}')"` : '';
    return `<div class="promo-slide ${i === 0 ? 'active' : ''}" ${bgStyle} ${clickAttr}>
      <div class="promo-slide-overlay"></div>
      <div class="promo-slide-content">
        ${s.title ? `<div class="promo-slide-title">${escHtml(s.title)}</div>` : ''}
        ${s.subtitle ? `<div class="promo-slide-sub">${escHtml(s.subtitle)}</div>` : ''}
      </div>
    </div>`;
  }).join('');
}

// ── Slideshow engine ─────────────────────────────────────────────────────────
let _slideIdx   = 0;
let _slideTimer = null;
let _promoSlides = [];

function startSlideshow() {
  clearInterval(_slideTimer);
  _slideIdx = 0;
  const dur = (_promoSlides[0]?.duration_seconds || 5) * 1000;
  _slideTimer = setInterval(nextSlide, dur);
}

function nextSlide() {
  if (!_promoSlides.length) return;
  _slideIdx = (_slideIdx + 1) % _promoSlides.length;
  goToSlide(_slideIdx);
  // adjust timer for new slide duration
  clearInterval(_slideTimer);
  const dur = (_promoSlides[_slideIdx]?.duration_seconds || 5) * 1000;
  _slideTimer = setInterval(nextSlide, dur);
}

function goToSlide(idx) {
  _slideIdx = idx;
  document.querySelectorAll('.promo-slide').forEach((el, i) => {
    el.classList.toggle('active', i === idx);
  });
  document.querySelectorAll('.promo-dot').forEach((d, i) => {
    d.classList.toggle('active', i === idx);
  });
}

function promoSlideClick(action) {
  if (!action) return;
  if (action.startsWith('http')) window.open(action, '_blank');
  else showScreen(action);
}


async function loadTV() {
  if (!allGroups.length) allGroups = await api('/media-groups') || [];
  await apiChannels();
  // v6: Merge VIP channels this room has access to
  allChannels = mergeVipIntoChannelList(allChannels);
  renderChGroups();
  renderChList(allChannels);
  updateTvPagination();
  // Load EPG "now" data in background and refresh rows when ready
  loadEpgNow();
}

async function loadEpgNow() {
  try {
    const data = await api('/epg?hours=1');
    if (!Array.isArray(data) || !data.length) return;
    const now = Date.now();
    const map = {};
    for (const e of data) {
      const start = parseEpgDate(e.start_time).getTime();
      const end = parseEpgDate(e.end_time).getTime();
      if (Number.isFinite(start) && Number.isFinite(end) && start <= now && end > now) {
        map[e.channel_id] = e.title;
      }
    }
    _epgNowMap = map;
    renderChList(allChannels);  // re-render rows with EPG titles injected
  } catch(_) {}
}

function renderChGroups() {
  const el = document.getElementById('ch-groups');
  if (!el) return;
  el.innerHTML = `<button class="ch-group-btn active" onclick="filterByGroup(null,this)">All</button>`
    + allGroups.map(g=>`<button class="ch-group-btn" onclick="filterByGroup(${g.id},this)">${g.name}</button>`).join('');
  updateChGroupArrows();
  el.addEventListener('scroll', updateChGroupArrows, { passive: true });
}

function scrollChGroups(dir) {
  const el = document.getElementById('ch-groups');
  if (!el) return;
  el.scrollBy({ left: dir * 150, behavior: 'smooth' });
}

function updateChGroupArrows() {
  const el = document.getElementById('ch-groups');
  const lBtn = document.getElementById('ch-grp-left');
  const rBtn = document.getElementById('ch-grp-right');
  if (!el || !lBtn || !rBtn) return;
  const atStart = el.scrollLeft <= 2;
  const atEnd   = el.scrollLeft + el.clientWidth >= el.scrollWidth - 2;
  lBtn.classList.toggle('hidden', atStart);
  rBtn.classList.toggle('hidden', atEnd);
}

function renderChList(channels) {
  const el = document.getElementById('ch-list');
  if (!el) return;

  if (document.body.classList.contains('tv-mode')) {
    // ── TV mode: 3×4 grid of channel cards ──────────────────────────────────
    el.innerHTML = channels.map(c => {
      const mono    = escHtml((c.name||'TV').substring(0,2).toUpperCase());
      const logoUrl = usableLogo(c.tvg_logo_url);
      const logoHTML = logoUrl
        ? `<img src="${logoUrl}" data-logo-src="${logoUrl}"
               style="max-width:100%;max-height:100%;object-fit:contain;display:block"
               onerror="markLogoFailed(this)">
           <span class="ch-mono-lbl" style="display:none">${mono}</span>`
        : `<span class="ch-mono-lbl">${mono}</span>`;
      return `
      <div class="ch-card${c.id===currentChId?' playing':''}" id="card-${c.id}"
           tabindex="0" onclick="playChannel(${c.id})">
        <div class="ch-img">${logoHTML}</div>
        <div class="ch-info">
          <div class="ch-name">${escHtml(c.name||'')}${c._is_vip?'<span class="vip-badge">VIP</span>':''}</div>
          <div class="ch-num">${escHtml(c.group_title||c.group_name||'Live')}</div>
          ${_epgNowMap[c.id]?`<div class="ch-epg-now">▶ ${escHtml(_epgNowMap[c.id])}</div>`:''}
        </div>
        <div class="ch-play">▶</div>
      </div>`;
    }).join('');
    return;
  }

  // ── Normal mode: compact vertical list ──────────────────────────────────
  el.innerHTML = channels.map(c => {
    const mono    = escHtml((c.name||'TV').substring(0,2).toUpperCase());
    const logoUrl = usableLogo(c.tvg_logo_url);
    const logoHTML = logoUrl
      ? `<img src="${logoUrl}" data-logo-src="${logoUrl}"
             style="width:36px;height:36px;object-fit:contain;border-radius:4px;display:block"
             onerror="markLogoFailed(this)"><span class="ch-mono-lbl" style="display:none">${mono}</span>`
      : `<span class="ch-mono-lbl">${mono}</span>`;
    return `
    <div class="ch-row ${c.id===currentChId?'playing':''}" id="row-${c.id}" onclick="playChannel(${c.id})">
      <div class="ch-row-logo">${logoHTML}</div>
      <div class="ch-row-info">
        <div class="ch-row-name">${escHtml(c.name||'')}${c._is_vip?'<span class="vip-badge">VIP</span>':''}</div>
        <div class="ch-row-num">${escHtml(c.group_title||c.group_name||'Live')}</div>
        ${_epgNowMap[c.id]?`<div class="ch-row-epg">▶ ${escHtml(_epgNowMap[c.id])}</div>`:''}
      </div>
      <span class="ch-row-live">LIVE</span>
    </div>`;
  }).join('');
}

async function filterByGroup(groupId, btn) {
  document.querySelectorAll('.ch-group-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  _tvGroupId = groupId;
  _tvPage = 0;
  await apiChannels();
  renderChList(allChannels);
  updateTvPagination();
}

async function tvSearchChannels(q) {
  _tvSearchQ = q;
  _tvPage = 0;
  clearTimeout(_tvSearchTimer);
  _tvSearchTimer = setTimeout(async ()=>{
    await apiChannels();
    allChannels = mergeVipIntoChannelList(allChannels);
    renderChList(allChannels);
    updateTvPagination();
  }, 350);
}

async function tvNextPage() {
  const size = tvPageSize();
  if ((_tvPage+1)*size >= _tvTotal) return;
  _tvPage++;
  await apiChannels();
  renderChList(allChannels);
  updateTvPagination();
  // Scroll the list to top in normal mode (grid mode has no scroll).
  if (!document.body.classList.contains('tv-mode')) {
    document.getElementById('ch-list')?.scrollTo(0, 0);
  }
}
async function tvPrevPage() {
  if (_tvPage <= 0) return;
  _tvPage--;
  await apiChannels();
  renderChList(allChannels);
  updateTvPagination();
}
function updateTvPagination() {
  const size   = tvPageSize();
  const offset = _tvPage * size;
  const shown  = Math.min(offset + allChannels.length, _tvTotal);
  const totalEl = document.getElementById('tv-ch-total');
  const pageEl  = document.getElementById('tv-page-info');
  const prevBtn = document.getElementById('tv-prev-btn');
  const nextBtn = document.getElementById('tv-next-btn');
  if (totalEl) totalEl.textContent = `(${_tvTotal.toLocaleString()})`;
  if (pageEl)  pageEl.textContent  = `${offset+1}–${shown}`;
  if (prevBtn) prevBtn.disabled = _tvPage === 0;
  if (nextBtn) nextBtn.disabled = shown >= _tvTotal;
}

async function playChannel(channelId) {
  const ch = allChannels.find(c=>c.id===channelId);
  if (!ch) return;
  const playSeq = ++_tvPlaySeq;
  currentChId = ch.id;

  // Mirror to Cast receiver if a session is active.
  CastMgr.loadMedia(ch);

  const overlay  = document.getElementById('player-overlay');
  const video    = document.getElementById('player');
  const poIcon   = document.getElementById('po-icon');
  const poName   = document.getElementById('po-name');
  const logoUrl  = usableLogo(ch.tvg_logo_url);

  // Update UI
  if (logoUrl) {
    poIcon.innerHTML = `<img src="${logoUrl}" data-logo-src="${logoUrl}" style="max-width:80px;max-height:60px;object-fit:contain" onerror="markLogoFailed(this);this.outerHTML='📺'">`;
  } else {
    poIcon.textContent = '📺';
  }
  poName.textContent = ch.name;
  document.getElementById('ctrl-name').textContent = ch.name;
  document.getElementById('ctrl-num').textContent  = ch.group_title || ch.group_name || 'Live';
  document.getElementById('play-btn').textContent  = '⏸';
  document.querySelectorAll('.ch-row,.ch-card').forEach(r=>r.classList.remove('playing'));
  document.getElementById('row-'+ch.id)?.classList.add('playing');
  document.getElementById('card-'+ch.id)?.classList.add('playing');

  // Destroy previous HLS instance
  if (hlsInstance) { hlsInstance.destroy(); hlsInstance = null; }
  video.pause();
  video.src = '';
  video.load();

  const url = (ch.stream_url || '').trim();
  const isHTTPCheck = url && (url.startsWith('http://') || url.startsWith('https://'));
  // Show pre-roll ad only for playable HTTP streams, not UDP
  if (isHTTPCheck) await showAdOverlay('live');
  const ctype = ch.channel_type || 'stream_udp';
  // Broad HLS detection: m3u8, common path patterns, or channel_type=m3u
  const isHLS = url && (
    url.includes('.m3u8') || url.includes('/playlist') ||
    url.includes('/index') || url.includes('chunklist') ||
    url.includes('/hls/') || url.includes('/live/') ||
    url.includes('/stream') || ctype === 'm3u'
  );
  const isHTTP = url && (url.startsWith('http://') || url.startsWith('https://'));
  // For UDP multicast — show stream info, can't play in browser
  if (!url) {
    overlay.style.display = '';
    const ps = overlay.querySelector('.player-status');
    if (ps) ps.textContent = '⚠ No stream URL configured for this channel.';
    document.getElementById('play-btn').textContent = '▶';
    return;
  }

  if (ctype === 'stream_udp' || url.startsWith('udp://') || url.startsWith('rtp://')) {
    overlay.style.display = '';
    const ps = overlay.querySelector('.player-status');
    if (ps) ps.textContent = '📡 Multicast stream: ' + url + '\n(UDP/RTP streams require a set-top box or VLC)';
    document.getElementById('play-btn').textContent = '▶';
    return;
  }

  if (isHTTP && isHLS && Hls.isSupported()) {
    overlay.style.display = 'none';
    const hls = new Hls({
      enableWorker: true,
      lowLatencyMode: true,
      maxBufferLength: 30,
    });
    hlsInstance = hls;
    hls.loadSource(url);
    hls.attachMedia(video);
    hls.on(Hls.Events.MANIFEST_PARSED, ()=> {
      if (playSeq !== _tvPlaySeq || hls !== hlsInstance) return;
      video.play().catch(()=>{});
      document.getElementById('play-btn').textContent = '⏸';
    });
    hls.on(Hls.Events.ERROR, (e, data)=> {
      if (playSeq !== _tvPlaySeq || hls !== hlsInstance) return;
      if (!data || !data.fatal) return;

      // Try in-place recovery for transient fatal errors during rapid channel zapping.
      if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
        try { hls.startLoad(); } catch(_) {}
        return;
      }
      if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
        try { hls.recoverMediaError(); } catch(_) {}
        return;
      }

      overlay.style.display = '';
      const ps = overlay.querySelector('.player-status');
      if (ps) ps.textContent = '⚠ Stream error — ' + (data.details||'unknown');
      document.getElementById('play-btn').textContent = '▶';
      try { hls.destroy(); } catch(_) {}
      if (hls === hlsInstance) hlsInstance = null;
    });
  } else if (isHTTP && video.canPlayType('application/vnd.apple.mpegurl')) {
    // Native HLS (Safari/iOS)
    overlay.style.display = 'none';
    video.src = url;
    video.play().catch(()=>{ if (playSeq === _tvPlaySeq) overlay.style.display=''; });
  } else if (isHTTP) {
    // Direct MP4/webm/etc
    overlay.style.display = 'none';
    video.src = url;
    video.play().catch(()=>{ if (playSeq === _tvPlaySeq) overlay.style.display=''; });
  } else {
    // UDP/RTP or unknown — show info
    overlay.style.display = '';
    overlay.querySelector('.player-status').textContent = '📡 Stream: ' + url;
    document.getElementById('play-btn').textContent = '▶';
  }

  // TV mode: enter fullscreen when a channel is selected.
  // Called synchronously inside the user-click handler, so the browser's
  // transient-activation requirement is satisfied.  The container goes
  // fullscreen immediately; the video stream loads inside it.
  // Guarded by isHTTP so UDP/unknown-scheme overlays never fullscreen.
  if (document.body.classList.contains('tv-mode') && isHTTP) {
    const pw = document.getElementById('player-wrap');
    if (pw && !document.fullscreenElement) {
      pw.requestFullscreen().catch(() => {});
      // fullscreenchange will fire and call FsOsd.show(ch) once FS is granted.
    } else if (document.fullscreenElement) {
      // Channel switch while already in fullscreen — fullscreenchange won't
      // re-fire, so update the OSD directly.
      FsOsd.show(ch);
    }
  }

  // EPG panel
  document.getElementById('epg-content').innerHTML = `
    <div style="display:flex;align-items:center;gap:16px;background:var(--bg3);border-radius:10px;padding:18px;border:1px solid var(--border)">
      ${logoUrl ? `<img src="${logoUrl}" data-logo-src="${logoUrl}" style="width:56px;height:56px;object-fit:contain;border-radius:8px;background:#000;flex-shrink:0" onerror="markLogoFailed(this)">` : ''}
      <div>
        <div style="font-size:10px;color:var(--muted);font-family:'DM Mono',monospace;letter-spacing:2px;margin-bottom:4px">NOW PLAYING</div>
        <div style="font-family:'Cormorant Garamond',serif;font-size:20px;font-weight:400">${ch.name}</div>
        <div style="font-size:12px;color:var(--dimmed);margin-top:4px">${ch.group_title||''}${ch.tvg_id?' · '+ch.tvg_id:''}</div>
      </div>
    </div>`;
  // Fetch live EPG programme and append below channel card
  (function(chId) {
    fetch('/api/epg?channel_id=' + chId + '&hours=4')
      .then(r => r.ok ? r.json() : [])
      .then(data => {
        if (currentChId !== chId || !Array.isArray(data) || !data.length) return;
        const now = new Date();
        const cur = data.find(e => parseEpgDate(e.start_time) <= now && parseEpgDate(e.end_time) > now);
        const next = data.find(e => parseEpgDate(e.start_time) > now);
        if (!cur && !next) return;
        // Feed the OSD bar regardless of whether the overlay is currently
        // visible — it will animate correctly the next time show() is called.
        if (cur && document.fullscreenElement) {
          FsOsd.setEpg(
            cur.title,
            parseEpgDate(cur.start_time).getTime(),
            parseEpgDate(cur.end_time).getTime()
          );
        }
        const fmtT = d => d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
        const el = document.getElementById('epg-content');
        if (!el) return;
        let html = '';
        if (cur) {
          const curStart = parseEpgDate(cur.start_time);
          const curEnd = parseEpgDate(cur.end_time);
          const pct = Math.min(100, Math.round((now - curStart) / (curEnd - curStart) * 100));
          html += `<div style="margin-top:10px;background:var(--bg3);border-radius:8px;padding:12px 14px;border:1px solid var(--border)">
            <div style="font-size:10px;color:#c9a86c;font-family:'DM Mono',monospace;letter-spacing:2px;margin-bottom:5px">ON AIR NOW</div>
            <div style="font-size:14px;font-weight:500;margin-bottom:3px">${escHtml(cur.title)}</div>
            <div style="font-size:11px;color:var(--dimmed);margin-bottom:8px">${fmtT(curStart)} – ${fmtT(curEnd)}${cur.category?' · '+escHtml(cur.category):''}</div>
            <div style="height:3px;background:var(--bg2);border-radius:2px;overflow:hidden">
              <div style="height:100%;width:${pct}%;background:#c9a86c;border-radius:2px"></div>
            </div>
          </div>`;
        }
        if (next) {
          const nextStart = parseEpgDate(next.start_time);
          html += `<div style="margin-top:8px;background:var(--bg3);border-radius:8px;padding:10px 14px;border:1px solid var(--border);opacity:0.75">
            <div style="font-size:10px;color:var(--muted);font-family:'DM Mono',monospace;letter-spacing:2px;margin-bottom:4px">UP NEXT · ${fmtT(nextStart)}</div>
            <div style="font-size:13px">${escHtml(next.title)}</div>
          </div>`;
        }
        el.insertAdjacentHTML('beforeend', html);
      })
      .catch(() => {});
  })(ch.id);
  toast('▶ ' + ch.name);
}

async function quickPlay(channelId) {
  await showScreen('tv');
  setTimeout(async ()=>{
    const targetId = parseInt(channelId);
    if (!Number.isFinite(targetId) || targetId <= 0) return;

    // If channel is not in the currently paged TV list, fetch it directly.
    let hasTarget = allChannels.find(c => parseInt(c.id) === targetId);
    if (!hasTarget) {
      try {
        const ch = await api('/channels/' + targetId);
        if (ch && !ch.error && ch.id) {
          const idx = allChannels.findIndex(c => parseInt(c.id) === parseInt(ch.id));
          if (idx >= 0) allChannels[idx] = ch;
          else allChannels.unshift(ch);
          hasTarget = ch;
        }
      } catch (_) {}
    }

    if (!hasTarget) {
      toast('⚠ Channel unavailable');
      return;
    }
    playChannel(targetId);
  }, 400);
}

function togglePlay() {
  const v = document.getElementById('player');
  const btn = document.getElementById('play-btn');
  if (v.paused) { v.play(); btn.textContent='⏸'; }
  else { v.pause(); btn.textContent='▶'; }
}

function toggleMute() {
  const v = document.getElementById('player');
  isMuted = !isMuted;
  v.muted = isMuted;
  toast(isMuted ? '🔇 Muted' : '🔊 Unmuted');
}

function toggleFullscreen() {
  const el = document.getElementById('player-wrap');
  if (!document.fullscreenElement) el.requestFullscreen?.();
  else document.exitFullscreen?.();
}

function prevChannel() {
  const idx = allChannels.findIndex(c=>c.id===currentChId);
  if (idx > 0) playChannel(allChannels[idx-1].id);
}
function nextChannel() {
  const idx = allChannels.findIndex(c=>c.id===currentChId);
  if (idx >= 0 && idx < allChannels.length-1) playChannel(allChannels[idx+1].id);
}

// ── VoD ───────────────────────────────────────────────────────────────────────
async function loadVoD() {
  if (!allMovies.length) allMovies = await api('/vod') || [];
  if (!allSeries.length) allSeries = await api('/vod/series') || [];
  _vodPlaylist = allMovies;
  _vodSearchQ = ''; _vodActiveGenre = null; _vodShowFavs = false;
  _vodTab = 'all'; _vodGenreActive = null;
  renderVoD();
}

function _vodAllGenres() {
  return [...new Set([
    ...allMovies.flatMap(m => m.genre.split('/')),
    ...allSeries.flatMap(s => s.genre.split('/'))
  ].filter(Boolean))].sort();
}

function _movieTile(m) {
  return `
    <div class="movie-tile" onclick="openMovieDetail(${m.id})" tabindex="0">
      <div class="mt-poster">
        ${m.poster ? `<img src="${m.poster}" alt="" loading="lazy" onerror="this.style.display='none'">` : '🎬'}
        <div class="mt-rating">★ ${m.rating}</div>
        <button class="mt-fav-btn${_vodFavs.has(m.id)?' active':''}" onclick="toggleFav(${m.id},event)" title="${_vodFavs.has(m.id)?'Remove from favourites':'Add to favourites'}" aria-label="Favourite">♥</button>
        <div class="mt-overlay"><div class="mt-play-btn">▶</div></div>
      </div>
      <div class="mt-title">${m.title}</div>
      <div class="mt-sub">${m.year} · ${m.genre.split('/')[0]}</div>
      <div class="mt-price">${m.price>0?'$'+m.price:'Free'}</div>
    </div>`;
}

function _seriesTile(s) {
  const seasons  = s.season_count  || 0;
  const episodes = s.episode_count || 0;
  return `
    <div class="movie-tile" onclick="openSeriesDetail(${s.id})" tabindex="0">
      <div class="mt-poster">
        ${s.poster ? `<img src="${s.poster}" alt="" loading="lazy" onerror="this.style.display='none'">` : '📺'}
        <div class="mt-series-badge">📺 Series</div>
        <button class="mt-fav-btn${_seriesFavs.has(s.id)?' active':''}" onclick="toggleSeriesFav(${s.id},event)" title="${_seriesFavs.has(s.id)?'Remove from favourites':'Add to favourites'}" aria-label="Favourite">♥</button>
        <div class="mt-overlay"><div class="mt-play-btn">▶</div></div>
      </div>
      <div class="mt-title">${s.title}</div>
      <div class="mt-sub">${s.year} · ${s.genre.split('/')[0]}</div>
      <div class="mt-ep-count">${seasons} Season${seasons!==1?'s':''} · ${episodes} Ep</div>
    </div>`;
}

function setVodTab(tab) {
  _vodTab = tab;
  _vodGenreActive = null;
  _vodSearchQ = '';
  renderVoD();
}

function renderVoD() {
  const el = document.getElementById('screen-vod');
  if (!el) return;

  const tabs = [
    {id:'all',     label:'All'},
    {id:'movies',  label:'Movies'},
    {id:'tvshows', label:'TV Shows'},
    {id:'genres',  label:'Genres'},
    {id:'search',  label:'Search'},
  ];

  const navHtml = `<div class="vod-top-nav">${tabs.map(t =>
    `<button class="vod-top-tab${_vodTab===t.id?' active':''}" onclick="setVodTab('${t.id}')">${t.label}</button>`
  ).join('')}</div>`;

  let bodyHtml = '';

  if (_vodTab === 'search') {
    const results = _vodSearchResults();
    bodyHtml = `
      <div class="vod-search-bar">
        <svg class="vod-search-icon" viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
        <input class="vod-search-input" id="vod-search-input" placeholder="Search movies &amp; series…"
          value="${_vodSearchQ.replace(/"/g,'&quot;')}"
          oninput="vodSearchType(this.value)" autocomplete="off" autofocus>
        ${_vodSearchQ ? `<button class="vod-search-clear" onclick="vodSearchType('');document.getElementById('vod-search-input').value=''">✕</button>` : ''}
      </div>
      <div class="movie-grid">
        ${results.series.map(s => _seriesTile(s)).join('')}
        ${results.movies.map(m => _movieTile(m)).join('')}
        ${!results.movies.length && !results.series.length && _vodSearchQ
          ? `<div class="vod-empty">No results for "${_vodSearchQ}"</div>` : ''}
        ${!_vodSearchQ ? `<div class="vod-empty vod-search-hint">Start typing to search…</div>` : ''}
      </div>`;

  } else if (_vodTab === 'genres') {
    if (_vodGenreActive) {
      const movies = allMovies.filter(m => m.genre.includes(_vodGenreActive));
      const series = allSeries.filter(s => s.genre.includes(_vodGenreActive));
      bodyHtml = `
        <div class="vod-genre-back">
          <button class="vod-genre-back-btn" onclick="_vodGenreActive=null;renderVoD()">← Genres</button>
          <span class="vod-genre-back-title">${_vodGenreActive}</span>
        </div>
        <div class="movie-grid">
          ${series.map(s => _seriesTile(s)).join('')}
          ${movies.map(m => _movieTile(m)).join('')}
          ${!movies.length && !series.length ? `<div class="vod-empty">No content in this genre</div>` : ''}
        </div>`;
      _vodPlaylist = movies;
    } else {
      const genres = _vodAllGenres();
      bodyHtml = `<div class="vod-genre-grid">${genres.map(g => {
        const count = allMovies.filter(m => m.genre.includes(g)).length
                    + allSeries.filter(s => s.genre.includes(g)).length;
        return `<div class="vod-genre-card" onclick="_vodGenreActive='${g.replace(/'/g,"\\'")}';renderVoD()">
          <div class="vgc-name">${g}</div>
          <div class="vgc-count">${count}</div>
        </div>`;
      }).join('')}${!genres.length ? `<div class="vod-empty">No genres available</div>` : ''}</div>`;
    }

  } else {
    let movies = allMovies;
    let series = allSeries;
    if (_vodTab === 'movies')  { series = []; }
    if (_vodTab === 'tvshows') { movies = []; }
    _vodPlaylist = movies;
    const hasContent = movies.length || series.length;
    bodyHtml = `
      <div class="movie-grid">
        ${series.map(s => _seriesTile(s)).join('')}
        ${movies.map(m => _movieTile(m)).join('')}
        ${!hasContent ? `<div class="vod-empty">No content found</div>` : ''}
      </div>`;
  }

  el.innerHTML = navHtml + bodyHtml;
}

function vodSearchType(q) {
  _vodSearchQ = q.trim().toLowerCase();
  renderVoD();
}

function _vodSearchResults() {
  if (!_vodSearchQ) return {movies: [], series: []};
  const q = _vodSearchQ;
  return {
    movies: allMovies.filter(m =>
      m.title.toLowerCase().includes(q) || (m.description || '').toLowerCase().includes(q)),
    series: allSeries.filter(s =>
      s.title.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q)),
  };
}

function searchVoD(q) {
  _vodSearchQ = q.trim().toLowerCase();
  _vodTab = 'search';
  renderVoD();
}

function showFavourites() {
  _vodTab = 'all';
  _vodShowFavs = true;
  renderVoD();
}

function filterVoD(genre) {
  _vodGenreActive = genre;
  _vodTab = 'genres';
  renderVoD();
}

function toggleFav(id, e) {
  e.stopPropagation();
  if (_vodFavs.has(id)) { _vodFavs.delete(id); toast('Removed from favourites'); }
  else                   { _vodFavs.add(id);    toast('Added to favourites ♥');   }
  localStorage.setItem('nv_fav_movies', JSON.stringify([..._vodFavs]));
  renderVoD();
}

function toggleFavDetail(id) {
  if (_vodFavs.has(id)) { _vodFavs.delete(id); toast('Removed from favourites'); }
  else                   { _vodFavs.add(id);    toast('Added to favourites ♥');   }
  localStorage.setItem('nv_fav_movies', JSON.stringify([..._vodFavs]));
  const btn = document.getElementById('md-fav-btn');
  const isFav = _vodFavs.has(id);
  if (btn) { btn.textContent = isFav ? '♥ Favourited' : '♡ Favourite'; btn.className = `btn-hero ${isFav?'btn-hero-fav':'btn-hero-ghost'}`; }
  renderVoD();
}

function toggleSeriesFav(id, e) {
  e.stopPropagation();
  if (_seriesFavs.has(id)) { _seriesFavs.delete(id); toast('Removed from favourites'); }
  else                      { _seriesFavs.add(id);    toast('Added to favourites ♥');   }
  localStorage.setItem('nv_fav_series', JSON.stringify([..._seriesFavs]));
  renderVoD();
}

function toggleSeriesFavDetail(id) {
  if (_seriesFavs.has(id)) { _seriesFavs.delete(id); toast('Removed from favourites'); }
  else                      { _seriesFavs.add(id);    toast('Added to favourites ♥');   }
  localStorage.setItem('nv_fav_series', JSON.stringify([..._seriesFavs]));
  const btn = document.getElementById('sd-fav-btn');
  const isFav = _seriesFavs.has(id);
  if (btn) { btn.textContent = isFav ? '♥ Favourited' : '♡ Favourite'; btn.className = `btn-hero ${isFav?'btn-hero-fav':'btn-hero-ghost'}`; }
  renderVoD();
}

async function openMovieDetail(id) {
  const m = allMovies.find(x=>x.id===id) || await api(`/vod/${id}`);
  if (!m) return;
  const bd = document.getElementById('md-backdrop');
  if (m.backdrop) { bd.innerHTML = `<img src="${m.backdrop}" alt="" style="width:100%;height:100%;object-fit:cover">`; }
  else if (m.poster) { bd.innerHTML = `<img src="${m.poster}" alt="" style="width:100%;height:100%;object-fit:cover">`; }
  else { bd.textContent = '🎬'; }
  const isFav = _vodFavs.has(m.id);
  document.getElementById('md-body').innerHTML = `
    <div class="md-title">${m.title}</div>
    <div class="md-meta">
      <span>⭐ <b class="hl">${m.rating}</b></span>
      <span>${m.year}</span>
      <span>${m.genre}</span>
      <span>${m.runtime} min</span>
      <span>${m.language}</span>
    </div>
    <div class="md-desc">${m.description}</div>
    <div class="md-actions">
      ${m.stream_url
        ? `<button class="btn-hero btn-hero-primary" onclick="startVoD('${m.stream_url}','${m.title.replace(/'/g,"\\'")}','${(m.poster||'').replace(/'/g,"\\'")}')">▶ Play Now</button>`
        : `<button class="btn-hero btn-hero-primary" onclick="toast('Stream not configured')">▶ Rent — $${m.price}</button>`}
      <button class="btn-hero ${isFav?'btn-hero-fav':'btn-hero-ghost'}" id="md-fav-btn" onclick="toggleFavDetail(${m.id})">${isFav?'♥ Favourited':'♡ Favourite'}</button>
      <button class="btn-hero btn-hero-ghost" onclick="closeMovieDetail()">✕ Close</button>
    </div>`;
  document.getElementById('movie-detail').classList.add('open');
  setTimeout(() => {
    const modal = document.getElementById('movie-detail');
    const btn = modal?.querySelector('.md-actions button, button[onclick*="startVoD"], button[onclick*="openSeries"]');
    if (btn && DPad) DPad.focusEl(btn);
  }, 350);
}

function closeMovieDetail() { document.getElementById('movie-detail').classList.remove('open'); }

// ── Series Detail ─────────────────────────────────────────────────────────────
let _seriesDetailData = null;
let _seriesActiveSeason = 0;

async function openSeriesDetail(id) {
  const data = await api(`/vod/series/${id}`);
  if (!data) return;
  _seriesDetailData = data;
  _seriesActiveSeason = 0;
  const bd = document.getElementById('sd-backdrop');
  if (data.backdrop)     bd.innerHTML = `<img src="${data.backdrop}" alt="" style="width:100%;height:100%;object-fit:cover">`;
  else if (data.poster)  bd.innerHTML = `<img src="${data.poster}"   alt="" style="width:100%;height:100%;object-fit:cover">`;
  else                   bd.textContent = '📺';
  _renderSeriesBody();
  document.getElementById('series-detail').classList.add('open');
  setTimeout(() => {
    const modal = document.getElementById('series-detail');
    const btn = modal?.querySelector('button:not([disabled])');
    if (btn && DPad) DPad.focusEl(btn);
  }, 350);
}

function _renderSeriesBody() {
  const s = _seriesDetailData;
  if (!s) return;
  const seasons = s.seasons || [];
  const activeSeason = seasons[_seriesActiveSeason] || null;
  const episodes = activeSeason ? (activeSeason.episodes || []) : [];

  document.getElementById('sd-body').innerHTML = `
    <div class="md-title">${s.title}</div>
    <div class="md-meta">
      <span>⭐ <b class="hl">${s.rating}</b></span>
      <span>${s.year}</span>
      <span>${s.genre}</span>
      <span>${s.language}</span>
    </div>
    <div class="md-desc">${s.description || ''}</div>
    <div class="md-actions">
      <button class="btn-hero ${_seriesFavs.has(s.id)?'btn-hero-fav':'btn-hero-ghost'}" id="sd-fav-btn" onclick="toggleSeriesFavDetail(${s.id})">${_seriesFavs.has(s.id)?'♥ Favourited':'♡ Favourite'}</button>
      <button class="btn-hero btn-hero-ghost" onclick="closeSeriesDetail()">✕ Close</button>
    </div>
    ${seasons.length ? `
    <div class="sd-seasons">
      ${seasons.map((sn, i) => `
        <button class="sd-season-tab${i===_seriesActiveSeason?' active':''}"
          onclick="_switchSeason(${i})">Season ${sn.season_number}${sn.title?' — '+sn.title:''}</button>
      `).join('')}
    </div>
    <div class="sd-ep-list">
      ${episodes.length ? episodes.map((ep, epIdx) => `
        <div class="ep-row" onclick="_playEpisode(${epIdx})">
          <div class="ep-num">E${ep.episode_number}</div>
          <div class="ep-thumb">
            ${ep.thumbnail ? `<img src="${ep.thumbnail}" alt="" loading="lazy" onerror="this.style.display='none'">` : '🎬'}
          </div>
          <div class="ep-info">
            <div class="ep-title">${ep.title}</div>
            <div class="ep-runtime">${ep.runtime ? ep.runtime+' min' : ''}</div>
          </div>
          <button class="ep-play-btn">▶</button>
        </div>
      `).join('') : `<div style="padding:20px;text-align:center;color:var(--muted)">No episodes yet</div>`}
    </div>` : `<div style="padding:20px;text-align:center;color:var(--muted)">No seasons added yet</div>`}`;
}

function _switchSeason(idx) {
  _seriesActiveSeason = idx;
  _renderSeriesBody();
}

function _playEpisode(epIdx) {
  const s = _seriesDetailData;
  if (!s) return;
  const season   = (s.seasons || [])[_seriesActiveSeason];
  const episodes = season ? (season.episodes || []) : [];
  const ep = episodes[epIdx];
  if (!ep || !ep.stream_url) { toast('No stream URL for this episode'); return; }
  _vodEpisodeCtx = {episodes, idx: epIdx};
  closeSeriesDetail();
  startVoD(ep.stream_url, `${s.title} · S${season.season_number}E${ep.episode_number} · ${ep.title}`);
}

function closeSeriesDetail() { document.getElementById('series-detail').classList.remove('open'); }

// ── VOD Player Modal ──────────────────────────────────────────────────────────
let _vodHls = null;
let _vodCtrlTimer = null;
let _vodPlaylist = [], _vodPlaylistIdx = -1;
let _vodCurrentUrl = '', _vodCurrentTitle = '', _vodCurrentPoster = '';
let _vodEpisodeCtx = null; // {episodes:[...], idx:N} — set when playing a series episode

async function resolveVodHlsUrl(url) {
  const raw = (url || '').trim();
  if (!raw.includes('/vod/hls/')) return raw;

  const m = raw.match(/\/vod\/hls\/([^/]+)\/master\.m3u8(?:[?#].*)?$/);
  if (!m) return raw;

  const id = m[1];
  const base = raw.replace(/\/master\.m3u8(?:[?#].*)?$/, '');
  const candidates = [
    raw,
    `${base}/1080p/index.m3u8`,
    `${base}/720p/index.m3u8`,
    `${base}/480p/index.m3u8`,
    `${base}/360p/index.m3u8`
  ];

  for (const candidate of candidates) {
    try {
      const resp = await fetch(candidate, { cache: 'no-store' });
      if (resp.ok) return candidate;
    } catch (_e) {}
  }

  // Keep original URL so existing error handling can still surface a message.
  return raw;
}

async function startVoD(url, title, posterUrl) {
  closeMovieDetail();

  // Normalize absolute http:// same-origin URLs to relative paths so HTTPS
  // pages don't get blocked by mixed-content policy.
  if (url && /^http:\/\//i.test(url)) {
    try {
      const u = new URL(url);
      if (u.hostname === location.hostname) url = u.pathname + u.search;
    } catch(_) {}
  }

  // ── Native VLC player (Android APK) ─────────────────────────────────────
  if (window.NexVisionAndroid) {
    window.NexVisionAndroid.playVideo(url, title || '');
    return;
  }
  // ────────────────────────────────────────────────────────────────────────

  // If a Cast session is active, send to Cast receiver instead of local player.
  if (CastMgr.isConnected()) {
    CastMgr.loadVod(url, title, posterUrl);
    toast('▶ Casting: ' + (title || 'video'));
    return;
  }

  // Show pre-roll ad before opening VOD player
  await showAdOverlay('vod');

  const modal  = document.getElementById('vod-player-modal');
  const video  = document.getElementById('vod-video');
  const loading = document.getElementById('vod-loading');

  // Clean up any previous session
  if (_vodHls) { _vodHls.destroy(); _vodHls = null; }
  video.pause();
  video.src = '';
  video.load();

  // Remember current VOD for Cast-while-playing support.
  _vodCurrentUrl    = url;
  _vodCurrentTitle  = title || '';
  _vodCurrentPoster = posterUrl || '';

  // Track playlist position (movies) or episode context (series)
  // _vodEpisodeCtx is set by _playEpisode() before calling startVoD;
  // for plain movie calls it's already null (closeVodPlayer clears it).
  _vodPlaylistIdx = _vodEpisodeCtx ? -1 : _vodPlaylist.findIndex(m => m.stream_url === url);
  _vodUpdateNavBtns();

  // Reset UI
  document.getElementById('vod-modal-title').textContent = title || '';
  document.getElementById('vod-play-btn').innerHTML = '&#9654;';
  document.getElementById('vod-seek-fill').style.width  = '0%';
  document.getElementById('vod-seek-buf').style.width   = '0%';
  document.getElementById('vod-seek-thumb').style.left  = '0%';
  document.getElementById('vod-seek-input').value = 0;
  document.getElementById('vod-cur').textContent = '0:00';
  document.getElementById('vod-dur').textContent = '0:00';
  loading.style.display = '';
  modal.classList.add('open');
  document.body.classList.add('vod-active');
  history.pushState({vodPlayer:true}, '');

  const playableUrl = await resolveVodHlsUrl(url);
  const isHLS = playableUrl && (playableUrl.includes('.m3u8') || playableUrl.includes('/hls/'));

  // Common error handler for all paths
  const onVideoError = () => {
    loading.style.display = '';
    loading.textContent = '⚠ Cannot play this video on your device';
  };
  video.onerror = onVideoError;

  // Timeout: if nothing starts within 20s, show error
  const loadTimeout = setTimeout(() => {
    if (loading.style.display !== 'none') onVideoError();
  }, 20000);
  video.addEventListener('canplay', () => clearTimeout(loadTimeout), { once: true });

  if (isHLS && typeof Hls !== 'undefined' && Hls.isSupported()) {
    let recoveringMediaError = false;
    _vodHls = new Hls({
      enableWorker: true,
      capLevelToPlayerSize: true,
      maxBufferLength: 30,
      maxMaxBufferLength: 60,
      backBufferLength: 30
    });
    _vodHls.loadSource(playableUrl);
    _vodHls.attachMedia(video);
    _vodHls.on(Hls.Events.MANIFEST_PARSED, () => {
      loading.style.display = 'none';
      video.play().catch(() => {});
      document.getElementById('vod-play-btn').innerHTML = '&#9646;&#9646;';
    });
    _vodHls.on(Hls.Events.ERROR, (e, data) => {
      if (!data.fatal) return;

      if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
        _vodHls.startLoad();
        return;
      }

      if (data.type === Hls.ErrorTypes.MEDIA_ERROR && !recoveringMediaError) {
        recoveringMediaError = true;
        _vodHls.recoverMediaError();
        setTimeout(() => { recoveringMediaError = false; }, 3000);
        return;
      }

      clearTimeout(loadTimeout);
      onVideoError();
    });
  } else if (isHLS && video.canPlayType('application/vnd.apple.mpegurl')) {
    // Native HLS (iOS Safari)
    video.src = playableUrl;
    video.load();
    video.addEventListener('canplay', () => { loading.style.display = 'none'; }, { once: true });
    video.play().catch(() => {});
    document.getElementById('vod-play-btn').textContent = '⏸';
  } else {
    // Direct file (MP4 etc.)
    video.src = playableUrl;
    video.load();
    video.addEventListener('canplay', () => { loading.style.display = 'none'; }, { once: true });
    video.play().catch(() => {});
    document.getElementById('vod-play-btn').textContent = '⏸';
  }

  // Auto-hide controls after 3s of no interaction
  _vodResetCtrlTimer();
  modal.addEventListener('mousemove', _vodResetCtrlTimer);
  modal.addEventListener('touchstart', _vodResetCtrlTimer);
}

function _vodResetCtrlTimer() {
  const bar  = document.getElementById('vod-ctrl-bar');
  const prev = document.getElementById('vod-prev-btn');
  const next = document.getElementById('vod-next-btn');
  const show = el => { if (el) { el.style.opacity = '1'; el.style.pointerEvents = ''; } };
  const hide = el => { if (el) { el.style.opacity = '0'; el.style.pointerEvents = 'none'; } };
  show(bar); show(prev); show(next);
  clearTimeout(_vodCtrlTimer);
  _vodCtrlTimer = setTimeout(() => { hide(bar); hide(prev); hide(next); }, 3500);
}

function closeVodPlayer() {
  const modal = document.getElementById('vod-player-modal');
  if (!modal.classList.contains('open')) return;
  const video = document.getElementById('vod-video');
  modal.classList.remove('open');
  document.body.classList.remove('vod-active');
  _vodEpisodeCtx = null;
  if (_vodHls) { _vodHls.destroy(); _vodHls = null; }
  video.onerror = null;
  video.pause(); video.src = ''; video.load();
  clearTimeout(_vodCtrlTimer);
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  // If closed via button (not back gesture), remove the history entry
  if (history.state?.vodPlayer) history.back();
}

// Cast the currently-playing VOD item to the active Cast session.
// If no session, opens the device picker.
function vodCast() {
  if (CastMgr.isConnected()) {
    CastMgr.loadVod(_vodCurrentUrl, _vodCurrentTitle, _vodCurrentPoster);
    const video = document.getElementById('vod-video');
    video.pause();
    closeVodPlayer();
    toast('▶ Casting: ' + (_vodCurrentTitle || 'video'));
  } else {
    CastMgr.requestSessionForVod(_vodCurrentUrl, _vodCurrentTitle, _vodCurrentPoster);
  }
}

window.addEventListener('popstate', function(e) {
  if (document.getElementById('vod-player-modal').classList.contains('open')) {
    // Back button pressed while player is open — close player, stay on page
    const modal = document.getElementById('vod-player-modal');
    const video = document.getElementById('vod-video');
    modal.classList.remove('open');
    document.body.classList.remove('vod-active');
    if (_vodHls) { _vodHls.destroy(); _vodHls = null; }
    video.pause(); video.src = ''; video.load();
    clearTimeout(_vodCtrlTimer);
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  }
});

function vodTogglePlay() {
  const video = document.getElementById('vod-video');
  if (video.paused) video.play();
  else video.pause();
}

function vodSeek(delta) {
  const video = document.getElementById('vod-video');
  if (!isFinite(video.duration)) return;
  video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + delta));
  _vodResetCtrlTimer();
}

function vodToggleMute() {
  const video = document.getElementById('vod-video');
  video.muted = !video.muted;
  _vodUpdateVolIcon(video);
}

function vodFullscreen() {
  const modal = document.getElementById('vod-player-modal');
  if (!document.fullscreenElement) modal.requestFullscreen?.();
  else document.exitFullscreen?.();
}

function _vodUpdateNavBtns() {
  const prev = document.getElementById('vod-prev-btn');
  const next = document.getElementById('vod-next-btn');
  if (_vodEpisodeCtx) {
    const {episodes, idx} = _vodEpisodeCtx;
    if (prev) prev.style.visibility = idx > 0 ? '' : 'hidden';
    if (next) next.style.visibility = idx < episodes.length - 1 ? '' : 'hidden';
  } else {
    if (prev) prev.style.visibility = _vodPlaylistIdx > 0 ? '' : 'hidden';
    if (next) next.style.visibility = _vodPlaylistIdx >= 0 && _vodPlaylistIdx < _vodPlaylist.length - 1 ? '' : 'hidden';
  }
}

function vodPlayPrev() {
  if (_vodEpisodeCtx) {
    const {episodes, idx} = _vodEpisodeCtx;
    if (idx > 0) { _vodEpisodeCtx = {episodes, idx: idx-1}; const e = episodes[idx-1]; startVoD(e.stream_url, e.title); }
  } else if (_vodPlaylistIdx > 0) {
    const m = _vodPlaylist[_vodPlaylistIdx - 1];
    startVoD(m.stream_url, m.title);
  }
}

function vodPlayNext() {
  if (_vodEpisodeCtx) {
    const {episodes, idx} = _vodEpisodeCtx;
    if (idx < episodes.length - 1) { _vodEpisodeCtx = {episodes, idx: idx+1}; const e = episodes[idx+1]; startVoD(e.stream_url, e.title); }
  } else if (_vodPlaylistIdx >= 0 && _vodPlaylistIdx < _vodPlaylist.length - 1) {
    const m = _vodPlaylist[_vodPlaylistIdx + 1];
    startVoD(m.stream_url, m.title);
  }
}

function _vodUpdateVolIcon(video) {
  const path = document.getElementById('vod-vol-icon');
  if (!path) return;
  const vol = video.muted || video.volume === 0;
  path.setAttribute('d', vol
    ? 'M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z'
    : video.volume < 0.5
      ? 'M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z'
      : 'M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z'
  );
}

// Wire up seek bar + volume + events
(function() {
  function _init() {
    const input  = document.getElementById('vod-seek-input');
    const volEl  = document.getElementById('vod-vol-slider');
    const video  = document.getElementById('vod-video');
    if (!input || !video) return;

    // Seek bar — update as video plays
    video.addEventListener('timeupdate', () => {
      if (!isFinite(video.duration) || video.duration === 0) return;
      const pct = (video.currentTime / video.duration) * 100;
      document.getElementById('vod-seek-fill').style.width = pct + '%';
      document.getElementById('vod-seek-thumb').style.left = pct + '%';
      input.value = Math.round(pct * 10);
      document.getElementById('vod-cur').textContent = _fmt(video.currentTime);
      document.getElementById('vod-dur').textContent = _fmt(video.duration);
    });

    // Buffered progress
    video.addEventListener('progress', () => {
      if (!video.duration) return;
      let buf = 0;
      for (let i = 0; i < video.buffered.length; i++) {
        if (video.buffered.start(i) <= video.currentTime) buf = video.buffered.end(i);
      }
      document.getElementById('vod-seek-buf').style.width = (buf / video.duration * 100) + '%';
    });

    // Seek drag/click
    input.addEventListener('input', () => {
      if (!isFinite(video.duration)) return;
      const pct = input.value / 1000;
      video.currentTime = pct * video.duration;
      document.getElementById('vod-seek-fill').style.width = (pct * 100) + '%';
      document.getElementById('vod-seek-thumb').style.left = (pct * 100) + '%';
      _vodResetCtrlTimer();
    });

    // Volume slider
    if (volEl) {
      volEl.addEventListener('input', () => {
        video.volume = volEl.value / 100;
        video.muted  = volEl.value == 0;
        _vodUpdateVolIcon(video);
      });
      video.addEventListener('volumechange', () => {
        if (!video.muted) volEl.value = Math.round(video.volume * 100);
        _vodUpdateVolIcon(video);
      });
    }

    // Play/pause state sync — use innerHTML to keep SVG in button intact
    function _syncPlay() {
      const btn = document.getElementById('vod-play-btn');
      if (!btn) return;
      btn.innerHTML = video.paused ? '&#9654;' : '&#9646;&#9646;';
    }
    video.addEventListener('play',  _syncPlay);
    video.addEventListener('pause', _syncPlay);
    video.addEventListener('ended', _syncPlay);

    // Keyboard shortcuts (active only when modal is open)
    document.addEventListener('keydown', e => {
      if (!document.getElementById('vod-player-modal').classList.contains('open')) return;
      if (e.key === ' ' || e.key === 'k')               { e.preventDefault(); vodTogglePlay(); }
      else if (e.key === 'ArrowRight' || e.key === 'l') { e.preventDefault(); vodSeek(10); }
      else if (e.key === 'ArrowLeft'  || e.key === 'j') { e.preventDefault(); vodSeek(-10); }
      else if (e.key === 'ArrowUp')   { video.volume = Math.min(1, video.volume + 0.1); if (volEl) volEl.value = Math.round(video.volume * 100); }
      else if (e.key === 'ArrowDown') { video.volume = Math.max(0, video.volume - 0.1); if (volEl) volEl.value = Math.round(video.volume * 100); }
      else if (e.key === 'f')         vodFullscreen();
      else if (e.key === 'Escape')    closeVodPlayer();
      _vodResetCtrlTimer();
    });

    // Click video area to play/pause
    video.addEventListener('click', vodTogglePlay);
  }

  function _fmt(secs) {
    if (!isFinite(secs)) return '0:00';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    return h > 0
      ? h + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0')
      : m + ':' + String(s).padStart(2,'0');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _init);
  else _init();
})();

// ── Radio ─────────────────────────────────────────────────────────────────────
async function loadRadio() {
  if (!allRadio.length) allRadio = await api('/radio') || [];
  const countries = [...new Set(allRadio.map(s=>s.country))].sort();
  renderRadio(allRadio, countries, null);
}

function renderRadio(stations, countries, activeCountry) {
  const playing = stations.find(s=>s===currentStation);
  document.getElementById('screen-radio').innerHTML = `
    <div class="radio-player">
      <div class="radio-vinyl ${currentStation?'spinning':''}" id="radio-vinyl"></div>
      <div class="radio-now" id="radio-now">${currentStation?.name||'Select a Station'}</div>
      <div class="radio-sub" id="radio-sub">${currentStation?(currentStation.country+' · '+currentStation.genre):'Choose your radio station below'}</div>
      <div class="radio-ctrl">
        <button class="r-btn" onclick="stopRadio()">⏹</button>
        <button class="r-btn play" id="radio-play-btn" onclick="toggleRadio()">${currentStation?'⏸':'▶'}</button>
        <button class="r-btn" onclick="">⋯</button>
      </div>
    </div>
    <div class="country-tabs">
      <button class="country-tab ${!activeCountry?'active':''}" onclick="filterRadio2(null)">All Countries</button>
      ${countries.map(c=>`<button class="country-tab ${activeCountry===c?'active':''}" onclick="filterRadio2('${c}')">${c}</button>`).join('')}
    </div>
    <div class="station-grid">
      ${stations.map(s=>`
        <div class="station-card ${currentStation?.id===s.id?'playing':''}" onclick="playStation(${s.id})">
          <div class="st-icon">📻</div>
          <div>
            <div class="st-name">${s.name}</div>
            <div class="st-meta">${s.country} · ${s.genre}</div>
          </div>
        </div>`).join('')}
    </div>`;
}

function filterRadio2(country) {
  const filtered = country ? allRadio.filter(s=>s.country===country) : allRadio;
  const countries = [...new Set(allRadio.map(s=>s.country))].sort();
  renderRadio(filtered, countries, country);
}

function playStation(id) {
  const s = allRadio.find(x=>x.id===id);
  if (!s) return;
  if (radioAudio) { radioAudio.pause(); radioAudio = null; }
  currentStation = s;
  radioAudio = new Audio();
  radioAudio.crossOrigin = 'anonymous';
  radioAudio.src = s.stream_url;
  radioAudio.play().catch(()=>toast('Stream unavailable (CORS/network)'));
  document.getElementById('radio-now').textContent = s.name;
  document.getElementById('radio-sub').textContent = s.country + ' · ' + s.genre;
  document.getElementById('radio-vinyl').classList.add('spinning');
  document.getElementById('radio-play-btn').textContent = '⏸';
  document.querySelectorAll('.station-card').forEach(c=>c.classList.remove('playing'));
  toast('📻 ' + s.name);
  loadedScreens.delete('radio'); // allow re-render next time
}

function stopRadio() {
  if (radioAudio) { radioAudio.pause(); radioAudio = null; }
  currentStation = null;
  document.getElementById('radio-vinyl')?.classList.remove('spinning');
  document.getElementById('radio-play-btn').textContent = '▶';
  document.getElementById('radio-now').textContent = 'Select a Station';
  loadedScreens.delete('radio');
}

function toggleRadio() {
  if (!radioAudio || !currentStation) return;
  if (radioAudio.paused) { radioAudio.play(); document.getElementById('radio-play-btn').textContent='⏸'; }
  else { radioAudio.pause(); document.getElementById('radio-play-btn').textContent='▶'; }
}

// ── Weather ───────────────────────────────────────────────────────────────────
async function loadWeather() {
  const w = await api('/weather?city=Al+Ain');
  if (!w) return;
  // Update header
  document.getElementById('hdr-w-icon').textContent = w.icon;
  document.getElementById('hdr-w-temp').textContent = w.temperature+'°';
  document.getElementById('hdr-w-city').textContent = w.city;

  document.getElementById('screen-weather').innerHTML = `
    <div class="weather-card">
      <div class="w-current">
        <div class="w-icon-big">${w.icon}</div>
        <div class="w-temp">${w.temperature}<span class="w-deg">°C</span></div>
        <div class="w-desc">${w.condition}</div>
        <div class="w-city">${w.city}</div>
        <div style="font-size:12px;color:var(--muted)">Updated: ${w.last_updated}</div>
        <div class="w-details">
          <div class="w-detail"><div class="w-detail-val">${w.feels_like}°</div><div class="w-detail-lbl">Feels Like</div></div>
          <div class="w-detail"><div class="w-detail-val">${w.humidity}%</div><div class="w-detail-lbl">Humidity</div></div>
          <div class="w-detail"><div class="w-detail-val">${w.wind_speed}<span style="font-size:13px"> km/h</span></div><div class="w-detail-lbl">Wind</div></div>
          <div class="w-detail"><div class="w-detail-val">${w.uv_index}</div><div class="w-detail-lbl">UV Index</div></div>
        </div>
      </div>
      <div class="w-forecast">
        ${w.forecast.map(d=>`
          <div class="w-fc-day">
            <div class="w-fc-name">${d.day}</div>
            <div class="w-fc-icon">${d.icon}</div>
            <div style="font-size:11px;color:var(--muted);margin-bottom:8px">${d.condition}</div>
            <div class="w-fc-temps">
              <span class="w-fc-hi">${d.high}°</span>
              <span class="w-fc-lo">${d.low}°</span>
            </div>
          </div>`).join('')}
      </div>
    </div>`;
}

// ── Info Pages ────────────────────────────────────────────────────────────────
async function loadInfo() {
  // Fetch pages — include items for preview images
  const pages = await api('/content') || [];
  // Fetch first item of each page for thumbnail preview
  const enriched = await Promise.all(pages.map(async p => {
    try {
      const detail = await api(`/content/${p.id}`);
      return detail ? { ...p, items: detail.items || [] } : p;
    } catch(e) { return p; }
  }));
  const groups = [...new Set(enriched.map(p=>p.group_name))];
  let activeGroup = groups[0];
  renderInfo(enriched, groups, activeGroup);
}

function renderInfo(pages, groups, activeGroup) {
  const el = document.getElementById('screen-info');
  const filtered = pages.filter(p=>p.group_name===activeGroup);
  el.innerHTML = `
    <div style="margin-bottom:20px;padding:28px 40px 0">
      <div style="font-family:'Cormorant Garamond',serif;font-size:32px;font-weight:300;margin-bottom:16px">Hotel Information</div>
      <div class="info-groups">
        ${groups.map(g=>`<button class="ig-btn ${g===activeGroup?'active':''}" onclick="filterInfo('${g}')">${escHtml(g)}</button>`).join('')}
      </div>
    </div>
    <div class="info-grid" id="info-grid" style="padding:20px 40px 40px">
      ${filtered.map(p=>{
        const firstItem  = p.items && p.items[0];
        const previewImg = firstItem ? ((firstItem.images&&firstItem.images[0]?.url) || firstItem.photo_url || firstItem.image || '') : '';
        const itemCount  = p.item_count || (p.items&&p.items.length) || 0;
        return `<div class="info-tile" onclick="openInfoPage(${p.id})">
          ${previewImg ? `<div style="height:100px;background:url('${previewImg}') center/cover;border-radius:8px 8px 0 0;margin:-24px -24px 16px -24px;flex-shrink:0" onerror="this.remove()"></div>` : ''}
          <div class="it-label">${escHtml(p.group_name)}</div>
          <div class="it-title">${escHtml(p.name)}</div>
          <div class="it-desc" style="display:flex;align-items:center;gap:6px;font-size:12px;margin-top:8px">
            <span style="color:var(--gold)">▶ View</span>
            ${itemCount>0 ? `<span style="color:var(--muted)">${itemCount} item${itemCount!==1?'s':''}</span>` : ''}
          </div>
        </div>`;
      }).join('')}
    </div>`;
  window._infoPages = pages;
  window._infoGroups = groups;
}

function filterInfo(group) {
  renderInfo(window._infoPages||[], window._infoGroups||[], group);
}

// ── Info page detail overlay ─────────────────────────────────────────────────
let _infoOverlay = null;

function closeInfoOverlay() {
  if (window._infoSlideTimer) { clearInterval(window._infoSlideTimer); window._infoSlideTimer = null; }
  if (_infoOverlay) {
    _infoOverlay.classList.remove('info-overlay-open');
    setTimeout(() => {
      if (_infoOverlay && _infoOverlay.parentNode) {
        _infoOverlay.parentNode.removeChild(_infoOverlay);
      }
      _infoOverlay = null;
    }, 300);
  }
}

function _infoSlide(sliderId, dotsId, dir) {
  const wrap = document.getElementById(sliderId);
  if (!wrap) return;
  const track  = wrap.querySelector('.info-slider-track');
  const dots   = document.getElementById(dotsId);
  if (!track) return;
  const total  = track.children.length;
  let cur = parseInt(track.dataset.cur || '0');
  cur = (cur + dir + total) % total;
  track.dataset.cur = cur;
  track.style.transform = `translateX(-${cur * 100}%)`;
  if (dots) {
    [...dots.children].forEach((d, i) => {
      d.style.background = i === cur ? 'rgba(255,255,255,.95)' : 'rgba(255,255,255,.35)';
    });
  }
}

async function openInfoPage(id) {
  const page = await api(`/content/${id}`);
  if (!page) return;

  closeInfoOverlay();

  const overlay = document.createElement('div');
  overlay.className = 'info-overlay-backdrop info-overlay-open';
  overlay.id = 'info-overlay-el';

  const items = page.items || [];

  function listHTML() {
    if (!items.length) return '<div class="info-empty">No content available yet.</div>';
    return items.map((item, idx) => {
      const galleryFirst = (item.images && item.images.length > 0) ? item.images[0].url : '';
      const imgUrl = galleryFirst || item.photo_url || item.image || '';
      const desc   = (item.description || '').trim();
      return `<div class="info-list-row" onclick="_infoShowDetail(${idx})">
        <div class="info-list-thumb">
          ${imgUrl ? `<img src="${imgUrl}" alt="" onerror="this.parentElement.innerHTML='&#128247;'">` : '&#128247;'}
        </div>
        <div class="info-list-text">
          <div class="info-list-title">${escHtml(item.title)}</div>
          ${desc ? `<div class="info-list-desc">${escHtml(desc.substring(0,120))}${desc.length>120?'…':''}</div>` : ''}
        </div>
        <div class="info-list-arrow">›</div>
      </div>`;
    }).join('');
  }

  function renderList() {
    document.getElementById('info-ov-back').style.display = 'none';
    document.getElementById('info-ov-title-wrap').innerHTML =
      `<div class="info-overlay-group">${escHtml(page.group_name||'')}</div>
       <div class="info-overlay-title">${escHtml(page.name||'')}</div>`;
    document.getElementById('info-ov-body').innerHTML = listHTML();
  }

  window._infoShowDetail = function(idx) {
    const item   = items[idx];
    const hasHtml = item.content_html && item.content_html.trim().length > 3;
    const hasDesc = (item.description || '').trim().length > 0;

    // Build image list: gallery first, then fall back to single photo_url/image
    // Build image list preserving position/fit metadata
    const galleryImgs = (item.images || []).filter(i => i.url);
    const singleImg   = item.photo_url || item.image || '';
    const allImgs     = galleryImgs.length > 0 ? galleryImgs
      : (singleImg ? [{ url: singleImg, position: 'center center', fit: 'cover' }] : []);

    document.getElementById('info-ov-back').style.display = 'flex';
    document.getElementById('info-ov-title-wrap').innerHTML =
      `<div class="info-overlay-group">${escHtml(page.group_name||'')}</div>
       <div class="info-overlay-title">${escHtml(item.title)}</div>`;

    const sliderId = 'info-slider-' + idx;
    const dotsId   = 'info-dots-' + idx;

    const imgTag = (im) => {
      const pos = im.position || 'center center';
      const fit = im.fit || 'cover';
      return `<img src="${escHtml(im.url)}" alt="" style="width:100%;height:100%;display:block;object-fit:${fit};object-position:${pos};max-height:420px" onerror="this.style.display='none'">`;
    };

    let sliderHTML = '';
    if (allImgs.length === 0) {
      sliderHTML = '<div class="info-detail-photo-empty">&#128247;</div>';
    } else if (allImgs.length === 1) {
      sliderHTML = imgTag(allImgs[0]);
    } else {
      sliderHTML = `
        <div id="${sliderId}" style="position:relative;overflow:hidden;border-radius:14px">
          <div class="info-slider-track" style="display:flex;transition:transform .5s ease;will-change:transform">
            ${allImgs.map(im=>`<div style="flex:0 0 100%;min-width:0;height:420px;max-height:420px">${imgTag(im)}</div>`).join('')}
          </div>
          <div id="${dotsId}" style="position:absolute;bottom:8px;left:0;right:0;display:flex;justify-content:center;gap:6px;pointer-events:none">
            ${allImgs.map((_,i)=>`<span class="info-slider-dot${i===0?' active':''}" style="width:7px;height:7px;border-radius:50%;background:${i===0?'rgba(255,255,255,.95)':'rgba(255,255,255,.35)'};display:inline-block;transition:background .3s"></span>`).join('')}
          </div>
          <button onclick="_infoSlide('${sliderId}','${dotsId}',-1)" style="position:absolute;left:8px;top:50%;transform:translateY(-50%);background:rgba(0,0,0,.5);border:none;color:#fff;width:30px;height:30px;border-radius:50%;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center">‹</button>
          <button onclick="_infoSlide('${sliderId}','${dotsId}',1)"  style="position:absolute;right:8px;top:50%;transform:translateY(-50%);background:rgba(0,0,0,.5);border:none;color:#fff;width:30px;height:30px;border-radius:50%;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center">›</button>
        </div>`;
    }

    document.getElementById('info-ov-body').innerHTML = `
      <div class="info-detail-wrap">
        <div class="info-detail-photo">${sliderHTML}</div>
        <div class="info-detail-content">
          <div class="info-detail-title">${escHtml(item.title)}</div>
          ${hasHtml
            ? `<div class="info-detail-html">${item.content_html}</div>`
            : hasDesc ? `<div class="info-detail-desc">${escHtml(item.description)}</div>` : ''}
        </div>
      </div>`;

    // Auto-advance if multiple images
    if (allImgs.length > 1) {
      if (window._infoSlideTimer) clearInterval(window._infoSlideTimer);
      window._infoSlideTimer = setInterval(() => _infoSlide(sliderId, dotsId, 1), 4000);
    }
  };

  overlay.innerHTML = `
    <div class="info-overlay-panel" role="dialog" aria-modal="true">
      <div class="info-overlay-hdr">
        <div class="info-overlay-hdr-left">
          <button class="info-overlay-back" id="info-ov-back" style="display:none" onclick="_infoShowList()" aria-label="Back">‹</button>
          <div id="info-ov-title-wrap">
            <div class="info-overlay-group">${escHtml(page.group_name||'')}</div>
            <div class="info-overlay-title">${escHtml(page.name||'')}</div>
          </div>
        </div>
        <button class="info-overlay-close" onclick="closeInfoOverlay()" aria-label="Close">✕</button>
      </div>
      <div class="info-overlay-body" id="info-ov-body">
        ${listHTML()}
      </div>
    </div>`;

  window._infoShowList = function(){ if(window._infoSlideTimer){clearInterval(window._infoSlideTimer);window._infoSlideTimer=null;} renderList(); };

  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeInfoOverlay(); });

  document.body.appendChild(overlay);
  _infoOverlay = overlay;
  requestAnimationFrame(() => overlay.classList.add('info-overlay-visible'));
}

// ── Init ──────────────────────────────────────────────────────────────────────



// ═══════════════════════════════════════════════════════════════════════════════
// V8 — MESSAGE INBOX
// ═══════════════════════════════════════════════════════════════════════════════
let _inboxMsgs   = [];
let _unreadCount = 0;

async function loadInbox() {
  const data  = await api('/messages/inbox');
  _inboxMsgs  = Array.isArray(data) ? data : [];
  updateMsgBadge();
  if (document.getElementById('screen-messages')?.classList.contains('active')) renderInbox();
}

function updateMsgBadge() {
  const unread = _inboxMsgs.filter(m => !m.is_read).length;
  _unreadCount = unread;
  const badge = document.getElementById('hdr-msg-badge');
  const btn   = document.getElementById('hdr-msg-btn');
  if (badge) { badge.textContent = unread > 9 ? '9+' : String(unread); badge.classList.toggle('on', unread > 0); }
  if (btn && getRoomToken()) btn.style.display = 'flex';
}

function renderInbox() {
  const el = document.getElementById('screen-messages');
  if (!el) return;
  const ICONS = {emergency:'🚨', normal:'📢', birthday:'🎂', room:'📩'};
  function relTime(ts) {
    if (!ts) return '';
    const diff = (Date.now() - new Date(ts + 'Z').getTime()) / 1000;
    if (diff < 60)    return 'Just now';
    if (diff < 3600)  return Math.floor(diff/60) + 'm ago';
    if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
    return Math.floor(diff/86400) + 'd ago';
  }
  if (!_inboxMsgs.length) {
    el.innerHTML = `<div style="padding:48px 32px;text-align:center"><div style="font-size:52px;margin-bottom:14px">✉️</div><div style="font-family:'Cormorant Garamond',serif;font-size:22px;color:var(--silver);margin-bottom:6px">No messages yet</div><div style="color:var(--muted);font-size:14px">Messages from hotel management will appear here</div></div>`;
    return;
  }
  el.innerHTML = `
  <div style="padding:28px 32px;max-width:820px;margin:0 auto">
    <div class="msg-inbox-hdr">
      <div class="msg-inbox-title">✉ Messages <span style="font-size:14px;color:var(--muted);font-family:'DM Mono',monospace">(${_inboxMsgs.length})</span></div>
      ${_unreadCount > 0 ? '<button class="msg-mark-all" onclick="markAllRead()">Mark all as read</button>' : ''}
    </div>
    <div id="inbox-list">
      ${_inboxMsgs.map(m => {
        const isUnread = !m.is_read;
        const tc = m.type || 'normal';
        return `<div class="msg-card-inbox ${tc}${isUnread?' unread':''}" id="mci-${m.id}" onclick="openMsgDetail(${m.id})">
          ${isUnread ? '<div class="mci-unread-dot"></div>' : ''}
          <div class="mci-header">
            <div class="mci-icon">${ICONS[m.type]||'📢'}</div>
            <div class="mci-title">${escHtml(m.title)}</div>
            <span class="mci-type ${tc}">${tc}</span>
            <div class="mci-time">${relTime(m.sent_at)}</div>
          </div>
          <div class="mci-body">${escHtml(m.body)}</div>
        </div>`;
      }).join('')}
    </div>
  </div>`;
}

async function openMsgDetail(id) {
  const m = _inboxMsgs.find(x => x.id === id);
  if (!m) return;
  if (!m.is_read) {
    await api('/messages/' + id + '/read', {method:'POST'});
    m.is_read = 1; updateMsgBadge();
    const card = document.getElementById('mci-' + id);
    if (card) { card.classList.remove('unread'); card.querySelector('.mci-unread-dot')?.remove(); }
  }
  const ICONS = {emergency:'🚨', normal:'📢', birthday:'🎂', room:'📩'};
  const modal = document.getElementById('movie-detail');
  const body  = document.getElementById('md-body');
  const bd    = document.getElementById('md-backdrop');
  if (!modal || !body) return;
  body.innerHTML = `
    <div style="text-align:center;margin-bottom:14px;font-size:44px">${ICONS[m.type]||'📢'}</div>
    <div style="font-family:'Cormorant Garamond',serif;font-size:24px;text-align:center;margin-bottom:8px;color:var(--white)">${escHtml(m.title)}</div>
    <div style="font-size:11px;color:var(--muted);text-align:center;font-family:'DM Mono',monospace;letter-spacing:1px;margin-bottom:18px">
      ${m.sent_at ? new Date(m.sent_at+'Z').toLocaleString() : ''} · Hotel Management
    </div>
    <div style="background:var(--bg3);border-radius:10px;padding:18px;font-size:15px;color:var(--dimmed);line-height:1.7;margin-bottom:18px">${escHtml(m.body)}</div>
    <button onclick="closeMsgDetail()" style="display:block;width:100%;background:var(--gold);color:#000;border:none;border-radius:10px;padding:13px;cursor:pointer;font-family:'Cormorant Garamond',serif;font-size:16px;font-weight:600">Close</button>`;
  modal.classList.add('open');
  if (bd) bd.style.display = 'block';
}
function closeMsgDetail() {
  const modal = document.getElementById('movie-detail');
  const bd    = document.getElementById('md-backdrop');
  if (modal) modal.classList.remove('open');
  if (bd) bd.style.display = 'none';
}
async function markAllRead() {
  await api('/messages/mark-all-read', {method:'POST'});
  _inboxMsgs.forEach(m => m.is_read = 1);
  updateMsgBadge(); renderInbox(); toast('All messages marked as read');
}


// ═══════════════════════════════════════════════════════════════════════════════
// V8 — PRAYER TIMES
// ═══════════════════════════════════════════════════════════════════════════════
let _prayerData      = null;
let _prayerCountdown = null;
let _notifiedPrayers = new Set();

const PRAYER_ARABIC = {Fajr:'الفجر',Sunrise:'الشروق',Dhuhr:'الظهر',Asr:'العصر',Maghrib:'المغرب',Isha:'العشاء'};
const PRAYER_ORDER  = ['Fajr','Sunrise','Dhuhr','Asr','Maghrib','Isha'];

async function loadPrayerTimes() {
  const data = await api('/prayer');
  if (!data || !data.enabled) { _prayerData = null; return; }
  _prayerData = data;
  const navBtn = document.getElementById('nav-prayers');
  if (navBtn) navBtn.style.display = 'inline-block';
  startPrayerCountdown();
  injectPrayerWidget();
}

function parsePrayerTime(timeStr) {
  const clean = (timeStr||'').split(' ')[0];
  const [h,m] = clean.split(':').map(Number);
  const d = new Date(); d.setHours(h,m,0,0); return d;
}

function getNextPrayer() {
  if (!_prayerData?.timings) return null;
  const now = new Date();
  for (const name of PRAYER_ORDER) {
    const t = _prayerData.timings[name]; if (!t) continue;
    const dt = parsePrayerTime(t);
    if (dt > now) return {name, time:dt, timeStr:t.split(' ')[0]};
  }
  const fajr = parsePrayerTime(_prayerData.timings.Fajr);
  fajr.setDate(fajr.getDate()+1);
  return {name:'Fajr', time:fajr, timeStr:_prayerData.timings.Fajr?.split(' ')[0]};
}

function startPrayerCountdown() {
  if (_prayerCountdown) clearInterval(_prayerCountdown);
  _prayerCountdown = setInterval(() => { updatePrayerCountdowns(); checkPrayerNotification(); }, 1000);
}

function updatePrayerCountdowns() {
  const next = getNextPrayer(); if (!next) return;
  const diff = next.time - new Date(); if (diff <= 0) return;
  const h=Math.floor(diff/3600000),m=Math.floor((diff%3600000)/60000),s=Math.floor((diff%60000)/1000);
  const str = h>0 ? h+'h '+m.toString().padStart(2,'0')+'m' : m+':'+s.toString().padStart(2,'0');
  const cd=document.getElementById('prayer-countdown'); if(cd) cd.textContent=str;
  const nn=document.getElementById('prayer-next-name'); if(nn) nn.textContent=next.name;
  const wn=document.getElementById('pw-next-name');     if(wn) wn.textContent=next.name;
  const wt=document.getElementById('pw-next-time');     if(wt) wt.textContent=next.timeStr+' · '+str;
}

function checkPrayerNotification() {
  if (!_prayerData?.timings || _settings.prayer_notify==='0') return;
  const now=new Date();
  const nowStr=now.getHours().toString().padStart(2,'0')+':'+now.getMinutes().toString().padStart(2,'0');
  for (const name of PRAYER_ORDER) {
    if (name==='Sunrise'||name==='Midnight') continue;
    const t=(_prayerData.timings[name]||'').split(' ')[0];
    const key=nowStr+name;
    if (t===nowStr && !_notifiedPrayers.has(key)) {
      _notifiedPrayers.add(key);
      showPrayerNotification(name,t); break;
    }
  }
}

function showPrayerNotification(name, timeStr) {
  const el=document.getElementById('prayer-notify');
  const nm=document.getElementById('pn-name');
  const ar=document.getElementById('pn-arabic');
  const tm=document.getElementById('pn-time');
  if(!el) return;
  if(nm) nm.textContent=name+' Prayer';
  if(ar) ar.textContent='حان وقت '+(PRAYER_ARABIC[name]||'الصلاة');
  if(tm) tm.textContent=timeStr;
  el.classList.add('on');
  setTimeout(()=>dismissPrayerNotify(), 180000);
}
function dismissPrayerNotify() {
  const el=document.getElementById('prayer-notify'); if(el) el.classList.remove('on');
}

function renderPrayerScreen() {
  const el=document.getElementById('screen-prayers'); if(!el) return;
  if (!_prayerData) {
    el.innerHTML='<div style="padding:48px;text-align:center;color:var(--muted)">Prayer times not enabled. Contact hotel management.</div>';
    return;
  }
  const now=new Date(), next=getNextPrayer();
  const days=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const months=['January','February','March','April','May','June','July','August','September','October','November','December'];
  const dateStr=days[now.getDay()]+', '+now.getDate()+' '+months[now.getMonth()]+' '+now.getFullYear();

  const tiles=PRAYER_ORDER.map(name=>{
    const t=_prayerData.timings[name]; if(!t) return '';
    const dt=parsePrayerTime(t);
    const isN=next?.name===name, isP=dt<now;
    return `<div class="prayer-tile${isN?' next':isP?' past':''}">
      <div class="pt-name">${name}</div>
      <div class="pt-time">${t.split(' ')[0]}</div>
      <div class="pt-arabic">${PRAYER_ARABIC[name]||''}</div>
    </div>`;
  }).join('');

  el.innerHTML=`
  <div class="prayer-hero">
    <div class="prayer-city">🕌 ${escHtml(_prayerData.city||'')}</div>
    <div class="prayer-date-greg">${dateStr}</div>
    ${_prayerData.hijri?'<div class="prayer-date-hijri">📅 '+escHtml(_prayerData.hijri)+' '+escHtml(_prayerData.hijri_month||'')+'</div>':''}
    ${next?`<div class="prayer-next-lbl">Next Prayer</div>
    <div class="prayer-next-name" id="prayer-next-name">${next.name}</div>
    <div class="prayer-countdown" id="prayer-countdown">—</div>`:''}
    ${_prayerData.offline?'<div style="font-size:11px;color:rgba(255,255,255,0.3);margin-top:8px;font-family:\'DM Mono\',monospace">⚠ Offline — approximate times</div>':''}
  </div>
  <div class="prayer-grid">${tiles}</div>`;
  updatePrayerCountdowns();
}

function injectPrayerWidget() {
  if (!_prayerData) return;
  const homeEl=document.getElementById('screen-home');
  if (!homeEl||document.getElementById('prayer-widget-home')) return;
  const next=getNextPrayer();
  const widget=document.createElement('div');
  widget.id='prayer-widget-home';
  widget.className='prayer-widget';
  widget.style.cssText='margin:0 32px 16px;cursor:pointer';
  widget.onclick=()=>showScreen('prayers');
  const allTimes=PRAYER_ORDER.filter(n=>n!=='Sunrise'&&_prayerData.timings[n]).map(n=>{
    const isN=getNextPrayer()?.name===n;
    return `<div class="pw-item${isN?' next':''}"><div class="pw-item-name">${n}</div><div class="pw-item-time">${(_prayerData.timings[n]||'').split(' ')[0]}</div></div>`;
  }).join('');
  widget.innerHTML=`
    <div class="pw-icon">🕌</div>
    <div><div class="pw-next-lbl">Next Prayer</div><div class="pw-next-name" id="pw-next-name">${next?.name||'—'}</div><div class="pw-next-time" id="pw-next-time">${next?.timeStr||'—'}</div></div>
    <div class="pw-all">${allTimes}</div>`;
  homeEl.insertBefore(widget, homeEl.firstChild);
}



// ═══════════════════════════════════════════════════════════════════════════════
// V8 — DYNAMIC NAVIGATION SYSTEM
// ═══════════════════════════════════════════════════════════════════════════════

let _navConfig   = { items: [], position: 'top', style: 'pill' };
let _activeScreen = 'home';

async function loadNavConfig() {
  const data = await api('/nav');
  if (!data) return;
  _navConfig = data;
  buildNav();
}

// Nav keys that are hotel-specific — hidden in commercial mode
const HOTEL_ONLY_NAV = ['services', 'prayer', 'birthdays'];

function buildNav() {
  const { items, position, style } = _navConfig;
  const isHotel = (window._deployMode || 'hotel') !== 'commercial';
  const enabled = items.filter(it => it.enabled && (isHotel || !HOTEL_ONLY_NAV.includes(it.key)));

  // On mobile phones, always use bottom nav for usability.
  // Also treat landscape phones (short viewport) as mobile so the
  // bottom nav is built even when width > 640px after rotation.
  const isLandscapePhone = window.innerHeight <= 480 && window.innerWidth > window.innerHeight;
  const isMobile = window.innerWidth <= 640 || isLandscapePhone;
  const effectivePosition = isMobile ? 'bottom' : position;

  if (effectivePosition === 'bottom') {
    buildBottomNav(enabled);
    document.body.classList.add('nav-bottom');
    document.body.classList.remove('nav-top');
  } else {
    buildTopNav(enabled, style);
    document.body.classList.add('nav-top');
    document.body.classList.remove('nav-bottom');
  }

  // Mark current active screen
  setNavActive(_activeScreen);
}

// Rebuild nav on orientation change / resize
window.addEventListener('resize', () => {
  if (_navConfig && _navConfig.items && _navConfig.items.length) buildNav();
});

function buildTopNav(items, style) {
  const nav = document.getElementById('top-nav');
  if (!nav) return;
  // Set style class
  nav.className = 'style-' + (style || 'pill');
  nav.innerHTML = items.map(it => {
    const label = style === 'icon' ? it.icon + ' ' + it.label : it.label;
    return `<button class="nav-btn" onclick="navItemClick('${escNav(it.key)}','${escNav(it.target_url||'')}')">${label}</button>`;
  }).join('');

  // Hide bottom nav
  const bn = document.getElementById('bottom-nav');
  if (bn) bn.classList.remove('visible');
}

function buildBottomNav(items) {
  const bn = document.getElementById('bottom-nav');
  if (!bn) return;
  bn.innerHTML = items.map(it => `
    <button class="bn-item" data-key="${escNav(it.key)}" onclick="navItemClick('${escNav(it.key)}','${escNav(it.target_url||'')}')">
      <span class="bn-icon">${it.icon || '📄'}</span>
      <span class="bn-label">${it.label}</span>
    </button>`).join('');
  bn.classList.add('visible');

  // Hide top nav
  const topNav = document.getElementById('top-nav');
  if (topNav) topNav.innerHTML = '';
}

function escNav(s) {
  return String(s || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function navItemClick(key, targetUrl) {
  if (targetUrl && targetUrl.startsWith('http')) {
    window.open(targetUrl, '_blank');
    return;
  }
  const screen = targetUrl || key;
  showScreen(screen);
}

function setNavActive(name) {
  _activeScreen = name;
  // Top nav
  document.querySelectorAll('#top-nav .nav-btn').forEach((btn, i) => {
    const enabled = (_navConfig.items || []).filter(it => it.enabled);
    const it = enabled[i];
    btn.classList.toggle('active', it && (it.key === name || (it.target_url || '') === name));
  });
  // Bottom nav
  document.querySelectorAll('#bottom-nav .bn-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.key === name);
  });
}


// ═══════════════════════════════════════════════════════════════════════════════
// V7 — SETTINGS & HOTEL IDENTITY
// ═══════════════════════════════════════════════════════════════════════════════
let _settings = {};

function applyClientBranding(s) {
  const cfg = s || _settings || {};
  const logoUrl = String(cfg.hotel_logo || cfg.admin_logo_url || '').trim();
  const brandName = String(cfg.hotel_name || cfg.admin_brand_name || 'NexVision').trim() || 'NexVision';
  const initials = brandName.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase() || 'NV';

  const logoEl = document.getElementById('hdr-logo');
  if (logoEl) {
    if (logoUrl) {
      logoEl.innerHTML = `<img src="${logoUrl}" style="height:36px;max-width:100px;object-fit:contain">`;
      const img = logoEl.querySelector('img');
      if (img) img.onerror = () => { logoEl.textContent = initials; };
    } else {
      logoEl.textContent = initials;
    }
  }

  const ssHotel = document.getElementById('ss-hotel');
  if (ssHotel) ssHotel.textContent = brandName;
}

async function loadSettings() {
  const s = await api('/settings');
  if (!s) return;
  _settings = s;
  // Re-apply deployment mode if it changed since init
  if (s.deployment_mode && s.deployment_mode !== window._deployMode) {
    window._deployMode = s.deployment_mode;
    applyDeployMode();
  }
  applyClientBranding(s);
  // Start screensaver with configured delay
  const delay = parseInt(s.screensaver_delay ?? 600) * 1000;
  resetScreensaverTimer(delay);
  initCastQR();
  initAlarmChecker();
}

// ═══════════════════════════════════════════════════════════════════════════════
// V7 — SCREENSAVER
// ═══════════════════════════════════════════════════════════════════════════════
let _ssTimer   = null;
let _ssActive  = false;
let _ssDelay   = 600000; // default 10 min
let _ssPaused  = { tv: false, vod: false, radio: false };

function resetScreensaverTimer(delay) {
  if (delay !== undefined) _ssDelay = delay;
  clearTimeout(_ssTimer);
  if (_ssDelay > 0) _ssTimer = setTimeout(activateScreensaver, _ssDelay);
}

function _ssPauseMedia() {
  // Live TV
  const tvVideo = document.getElementById('player');
  if (tvVideo && !tvVideo.paused && tvVideo.src) {
    tvVideo.pause();
    _ssPaused.tv = true;
  } else {
    _ssPaused.tv = false;
  }
  // VOD
  const vodVideo = document.getElementById('vod-video');
  if (vodVideo && !vodVideo.paused && vodVideo.src) {
    vodVideo.pause();
    _ssPaused.vod = true;
  } else {
    _ssPaused.vod = false;
  }
  // Radio
  if (radioAudio && !radioAudio.paused) {
    radioAudio.pause();
    _ssPaused.radio = true;
  } else {
    _ssPaused.radio = false;
  }
}

function _ssResumeMedia() {
  if (_ssPaused.tv) {
    document.getElementById('player')?.play().catch(()=>{});
  }
  if (_ssPaused.vod) {
    document.getElementById('vod-video')?.play().catch(()=>{});
  }
  if (_ssPaused.radio && radioAudio) {
    radioAudio.play().catch(()=>{});
    document.getElementById('radio-play-btn') && (document.getElementById('radio-play-btn').textContent = '⏸');
  }
  _ssPaused = { tv: false, vod: false, radio: false };
}

function activateScreensaver() {
  if (_ssActive) return;
  const type = _settings.screensaver_type || 'clock';
  if (type === 'off') return;
  _ssActive = true;
  _ssPauseMedia();
  const ss = document.getElementById('screensaver');
  if (!ss) return;
  ss.classList.add('on');
  updateScreensaverClock();
  spawnParticles();
}

function wakeFromScreensaver() {
  _ssActive = false;
  const ss = document.getElementById('screensaver');
  if (ss) ss.classList.remove('on');
  ss?.querySelectorAll('.ss-particle').forEach(p => p.remove());
  _ssResumeMedia();
  resetScreensaverTimer();
}

function updateScreensaverClock() {
  if (!_ssActive) return;
  const now  = new Date();
  const h    = now.getHours().toString().padStart(2,'0');
  const m    = now.getMinutes().toString().padStart(2,'0');
  const days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  const dateStr = `${days[now.getDay()]}, ${now.getDate()} ${months[now.getMonth()]}`;

  const te = document.getElementById('ss-time');
  const de = document.getElementById('ss-date');
  if (te) te.textContent = h + ':' + m;
  if (de) de.textContent = dateStr;
  setTimeout(updateScreensaverClock, 1000);
}

function spawnParticles() {
  const ss = document.getElementById('screensaver');
  if (!ss) return;
  for (let i = 0; i < 18; i++) {
    const p = document.createElement('div');
    p.className = 'ss-particle';
    const size   = Math.random() * 6 + 2;
    const left   = Math.random() * 100;
    const dur    = Math.random() * 15 + 10;
    const delay  = Math.random() * 20;
    const dx     = (Math.random() - 0.5) * 200;
    const colors = ['rgba(212,168,67,0.3)','rgba(255,255,255,0.1)','rgba(74,158,255,0.15)','rgba(155,123,255,0.15)'];
    const color  = colors[Math.floor(Math.random() * colors.length)];
    p.style.cssText = `width:${size}px;height:${size}px;left:${left}%;background:${color};animation-duration:${dur}s;animation-delay:-${delay}s;--dx:${dx}px`;
    ss.appendChild(p);
  }
}

// Reset screensaver on any user interaction
['mousemove','mousedown','keydown','touchstart','click'].forEach(evt => {
  document.addEventListener(evt, () => {
    if (_ssActive) { wakeFromScreensaver(); return; }
    resetScreensaverTimer();
  }, {passive:true});
});


// ═══════════════════════════════════════════════════════════════════════════════
// V7 — EPG OVERLAY
// ═══════════════════════════════════════════════════════════════════════════════
async function openEpgOverlay() {
  const chId = currentChId;
  if (!Number.isInteger(chId) || chId <= 0) {
    toast('Select a channel first');
    return;
  }
  const data = await api('/epg?channel_id=' + chId + '&hours=8');
  const ch   = (allChannels || []).find(c => c.id === chId);
  const el   = document.getElementById('epg-ch-name');
  if (el && ch) el.textContent = ch.name;

  const list = document.getElementById('epg-list');
  if (!list) return;

  const now = Date.now();
  if (!data || !data.length) {
    list.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:10px 0">No programme guide available for this channel.</div>';
  } else {
    list.innerHTML = data.map(e => {
      const start  = parseEpgDate(e.start_time);
      const end    = parseEpgDate(e.end_time);
      const isNow  = start <= new Date() && end > new Date();
      const pct    = isNow ? Math.round((now - start.getTime()) / (end.getTime() - start.getTime()) * 100) : 0;
      const fmtT   = d => d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
      return `<div class="epg-card ${isNow?'now':''}">
        <div class="epg-time">${fmtT(start)} – ${fmtT(end)}${isNow?'<span class="epg-now-badge">NOW</span>':''}</div>
        <div class="epg-title">${escHtml(e.title)}</div>
        ${e.category ? `<div class="epg-cat">${escHtml(e.category)}</div>` : ''}
        ${isNow ? `<div class="epg-progress"><div class="epg-prog-fill" style="width:${pct}%"></div></div>` : ''}
      </div>`;
    }).join('');
  }
  document.getElementById('epg-overlay').classList.add('on');
}

function closeEpg() {
  document.getElementById('epg-overlay').classList.remove('on');
}


// ═══════════════════════════════════════════════════════════════════════════════
// V7 — GUEST SERVICES SCREEN
// ═══════════════════════════════════════════════════════════════════════════════
let _services = [];

async function loadServices() {
  const data = await api('/services');
  _services = Array.isArray(data) ? data : [];
}

async function renderServicesScreen() {
  if (!_services.length) await loadServices();
  const el = document.getElementById('screen-services');
  if (!el) return;

  // Group by category
  const cats = {};
  _services.forEach(s => {
    if (!cats[s.category]) cats[s.category] = [];
    cats[s.category].push(s);
  });

  el.innerHTML = `
  <div style="padding:28px 32px">
    <div style="margin-bottom:24px">
      <div style="font-family:'Cormorant Garamond',serif;font-size:28px;font-weight:300;color:var(--white);margin-bottom:4px">Guest Services</div>
      <div style="font-size:13px;color:var(--muted)">Contact our team for any assistance during your stay</div>
    </div>
    ${_settings.wifi_name ? `
    <div class="wifi-card" style="margin-bottom:24px">
      <span style="font-size:24px">📶</span>
      <div>
        <div style="font-size:11px;color:var(--muted);font-family:'DM Mono',monospace;letter-spacing:1px;margin-bottom:4px">WI-FI</div>
        <div class="wifi-ssid">${escHtml(_settings.wifi_name)}</div>
        ${_settings.wifi_password ? `<div class="wifi-pass">Password: ${escHtml(_settings.wifi_password)}</div>` : ''}
      </div>
    </div>` : ''}
    ${Object.entries(cats).map(([cat, svcs]) => `
      <div style="margin-bottom:24px">
        <div style="font-family:'DM Mono',monospace;font-size:10px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px">${escHtml(cat)}</div>
        <div class="svc-grid">
          ${svcs.map(s => `
            <div class="svc-tile" onclick="openServiceDetail(${s.id})">
              <div class="svc-icon">${s.icon}</div>
              <div class="svc-name">${escHtml(s.name)}</div>
              ${s.phone ? `<div class="svc-phone">📞 ${escHtml(s.phone)}</div>` : ''}
            </div>`).join('')}
        </div>
      </div>`).join('')}
    ${_settings.checkout_time ? `
    <div style="margin-top:8px;padding:14px 18px;background:var(--bg2);border:1px solid var(--border);border-radius:10px;font-size:13px;color:var(--muted)">
      🕐 <b style="color:var(--text)">Checkout Time:</b> ${escHtml(_settings.checkout_time)} &nbsp;&nbsp;
      ${_settings.support_phone ? '📞 <b style="color:var(--text)">Front Desk:</b> ' + escHtml(_settings.support_phone) : ''}
    </div>` : ''}
  </div>`;
}

function openServiceDetail(id) {
  const s = _services.find(x => x.id === id);
  if (!s) return;

  // Detect if icon field is an image URL
  const iconIsUrl = s.icon && (s.icon.startsWith('http') || s.icon.startsWith('/'));
  const iconHTML = iconIsUrl
    ? `<img src="${s.icon}" style="width:80px;height:80px;object-fit:cover;border-radius:14px;margin:0 auto 12px;display:block" onerror="this.outerHTML='<div style=\"font-size:52px;text-align:center;margin-bottom:12px\">${escHtml(s.icon)}</div>'">`
    : `<div class="svc-modal-icon">${s.icon||'🛎'}</div>`;

  const modal    = document.getElementById('movie-detail');
  const backdrop = document.getElementById('md-backdrop');
  const body     = document.getElementById('md-body');
  if (!modal || !body) return;

  body.innerHTML = `
    ${iconHTML}
    <div class="svc-modal-name">${escHtml(s.name)}</div>
    <div style="font-size:11px;color:var(--muted);font-family:'DM Mono',monospace;letter-spacing:1px;text-transform:uppercase;margin-bottom:14px;text-align:center">${escHtml(s.category)}</div>
    ${s.description ? `<div class="svc-modal-desc" style="white-space:pre-line">${escHtml(s.description)}</div>` : ''}
    ${s.phone ? `
    <div style="margin:16px 0 12px;text-align:center;background:var(--bg3);border-radius:12px;padding:16px">
      <div style="font-size:11px;color:var(--muted);font-family:'DM Mono',monospace;letter-spacing:1px;margin-bottom:6px">PHONE NUMBER</div>
      <div style="font-size:28px;font-family:'Cormorant Garamond',serif;color:var(--gold);letter-spacing:3px">${escHtml(s.phone)}</div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px">Dial from your room phone</div>
    </div>
    <button class="svc-call-btn">📞 Call ${escHtml(s.name)}</button>` :
    '<div style="color:var(--muted);text-align:center;padding:12px 0">Contact the front desk for assistance</div>'}
    <button onclick="closeSvcDetail()" style="display:block;width:100%;margin-top:12px;background:transparent;border:1px solid var(--border2);color:var(--dimmed);border-radius:8px;padding:10px;cursor:pointer;font-size:13px">✕ Close</button>`;

  modal.classList.add('open');
  if (backdrop) backdrop.style.display = 'block';
}

function closeSvcDetail() {
  const modal = document.getElementById('movie-detail');
  const backdrop = document.getElementById('md-backdrop');
  if (modal) modal.classList.remove('open');
  if (backdrop) backdrop.style.display='none';
}


// ═══════════════════════════════════════════════════════════════════════════════
// V6 — RSS TICKERS
// ═══════════════════════════════════════════════════════════════════════════════
let _rssFeeds = [];
let _rssTimers = [];

async function loadRssFeeds() {
  const data = await api('/rss/public');
  if (!data || !Array.isArray(data)) return;
  _rssFeeds = data;
  renderEmergencyTicker(data.filter(f => f.type === 'emergency'));
  renderNewsTicker(data.filter(f => f.type === 'normal'));
  // Schedule per-feed refresh timeouts (fastest feed interval wins)
  _rssTimers.forEach(t => clearTimeout(t));
  _rssTimers = [];
  if (data.length > 0) {
    const minMs = Math.min(...data.map(f => (f.refresh_minutes || 15) * 60 * 1000));
    _rssTimers.push(setTimeout(loadRssFeeds, minMs));
  }
}

function renderEmergencyTicker(feeds) {
  const ticker = document.getElementById('emergency-ticker');
  const inner  = document.getElementById('et-inner');
  if (!ticker || !inner) return;
  const items = feeds.flatMap(f => (f.items || []).map(i => ({ title: i.title, feed: f.title })));
  if (!items.length) {
    ticker.classList.remove('on');
    document.body.classList.remove('emergency-active');
    return;
  }
  // Duplicate items for seamless loop
  const html = [...items, ...items].map(i =>
    `<span class="et-item">⚠ ${escHtml(i.title)}</span>`
  ).join('');
  inner.innerHTML = '<span class="et-label">🚨 EMERGENCY</span>' + html;
  ticker.classList.add('on');
  document.body.classList.add('emergency-active');
}

function renderNewsTicker(feeds) {
  const ticker = document.getElementById('news-ticker');
  const inner  = document.getElementById('nt-inner');
  if (!ticker || !inner) return;
  const items = feeds.flatMap(f => (f.items || []).map(i => ({ title: i.title, feed: f.title })));
  // Include custom hotel ticker messages from settings
  const customRaw = (_settings.ticker_custom || '').trim();
  const customItems = customRaw
    ? customRaw.split('\n').map(t => t.trim()).filter(Boolean).map(t => ({ title: t, feed: _settings.hotel_name || 'Hotel' }))
    : [];
  const allItems = [...customItems, ...items];
  if (!allItems.length) {
    ticker.classList.remove('on');
    document.body.classList.remove('news-ticker-active');
    return;
  }
  // Apply global ticker appearance from settings
  const txtCol = _settings.ticker_text_color || '#ffffff';
  const bgCol  = _settings.ticker_bg_color   || '#09090f';
  const op     = parseInt(_settings.ticker_bg_opacity ?? 92) / 100;
  const _r = parseInt(bgCol.slice(1,3),16), _g = parseInt(bgCol.slice(3,5),16), _b = parseInt(bgCol.slice(5,7),16);
  ticker.style.background = `rgba(${_r},${_g},${_b},${op})`;

  const html = [...allItems, ...allItems].map(i =>
    `<span class="nt-item" style="color:${escHtml(txtCol)}"><b>${escHtml(i.feed)}:</b> ${escHtml(i.title)}</span>`
  ).join('');
  const tickerLabel = (_settings.ticker_label || 'NEWS').trim() || 'NEWS';
  inner.innerHTML = `<span class="nt-label">📰 ${escHtml(tickerLabel)}</span>` + html;
  ticker.classList.add('on');
  document.body.classList.add('news-ticker-active');
}

function escHtml(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ═══════════════════════════════════════════════════════════════════════════════
// V6 — MESSAGES
// ═══════════════════════════════════════════════════════════════════════════════
let _shownMsgIds = new Set();
let _msgQueue    = [];
let _showingMsg  = false;

async function pollMessages() {
  const msgs = await api('/messages/active');
  if (!msgs || !Array.isArray(msgs)) return;
  let inboxUpdated = false;
  msgs.forEach(m => {
    // Queue for popup if not yet seen
    if (!_shownMsgIds.has(m.id)) {
      _shownMsgIds.add(m.id);
      _msgQueue.push(m);
    }
    // Also land in inbox if not already there
    if (!_inboxMsgs.find(i => i.id === m.id)) {
      _inboxMsgs.unshift({ ...m, is_read: 0 });
      inboxUpdated = true;
    }
  });
  if (inboxUpdated) {
    updateMsgBadge();
    // Refresh inbox view if currently open
    if (document.getElementById('screen-messages')?.classList.contains('active')) renderInbox();
  }
  if (!_showingMsg && _msgQueue.length) showNextMessage();
}

function showNextMessage() {
  if (!_msgQueue.length) { _showingMsg = false; return; }
  _showingMsg = true;
  const m = _msgQueue.shift();
  if (m.type === 'emergency') {
    showMsgOverlay(m);
  } else {
    showMsgBanner(m);
    // Auto-dismiss non-emergency after 12 seconds, then show next
    setTimeout(() => {
      dismissMsgBanner();
      setTimeout(showNextMessage, 600);
    }, 12000);
  }
}

function showMsgOverlay(m) {
  const icons = { emergency: '🚨', normal: '📢', birthday: '🎂', room: '📩' };
  const card  = document.getElementById('msg-card');
  if (card) {
    card.className = 'msg-card ' + (m.type || 'normal');
  }
  document.getElementById('msg-icon').textContent  = icons[m.type] || '📢';
  document.getElementById('msg-title').textContent = m.title;
  document.getElementById('msg-body-txt').textContent = m.body;
  document.getElementById('msg-from').textContent  = 'From Hotel Management';
  document.getElementById('msg-overlay').classList.add('on');
  window._currentMsgId = m.id;
}

function dismissMsgOverlay() {
  document.getElementById('msg-overlay').classList.remove('on');
  if (window._currentMsgId) {
    api('/messages/' + window._currentMsgId + '/dismiss', { method: 'POST' });
    window._currentMsgId = null;
  }
  setTimeout(showNextMessage, 400);
}

function showMsgBanner(m) {
  const icons = { normal: '📢', room: '📩', birthday: '🎂' };
  document.getElementById('mb-icon').textContent    = icons[m.type] || '📢';
  document.getElementById('mb-title').textContent   = m.title;
  document.getElementById('mb-body-txt').textContent = m.body;
  const banner = document.getElementById('msg-banner');
  banner.className = 'on ' + (m.type || 'normal');
  window._currentBannerMsgId = m.id;
}

function dismissMsgBanner() {
  const banner = document.getElementById('msg-banner');
  if (banner) banner.classList.remove('on');
  window._currentBannerMsgId = null;
}

// ═══════════════════════════════════════════════════════════════════════════════
// V6 — BIRTHDAYS
// ═══════════════════════════════════════════════════════════════════════════════
async function checkBirthdays() {
  const data = await api('/birthdays/today');
  if (!data || !data.length) return;
  // Check if already shown this session
  if (sessionStorage.getItem('bday_shown_' + data[0].id)) return;

  const b = data[0]; // Show first birthday of the day
  const roomInfo = getRoomInfo();

  // Only show if this is the room's birthday OR it's a general birthday
  const isMyRoom = !b.room_number || (roomInfo && roomInfo.room_number === b.room_number);
  if (!isMyRoom) return;

  sessionStorage.setItem('bday_shown_' + b.id, '1');

  document.getElementById('bday-name').textContent = b.guest_name;
  document.getElementById('bday-room').textContent = b.room_number ? 'Room ' + b.room_number : '';
  document.getElementById('bday-msg').textContent  = b.message || 'Happy Birthday! Wishing you a wonderful and joyful day!';
  document.getElementById('bday-banner').classList.add('on');
}

function closeBdayBanner() {
  document.getElementById('bday-banner').classList.remove('on');
  setTimeout(showNextMessage, 400);
}

// ═══════════════════════════════════════════════════════════════════════════════
// V6 — VIP CHANNELS
// ═══════════════════════════════════════════════════════════════════════════════
let _vipChannels = [];

async function loadVipChannels() {
  const data = await api('/vip/my-channels');
  _vipChannels = Array.isArray(data) ? data : [];
}

function mergeVipIntoChannelList(channels) {
  // Add VIP channels to channel list with a VIP badge, if not already present
  const existing = new Set(channels.map(c => c.id));
  const vipExtra = _vipChannels.filter(c => !existing.has(c.id));
  // Mark VIP channels
  vipExtra.forEach(c => c._is_vip = true);
  channels.forEach(c => {
    if (_vipChannels.find(v => v.id === c.id)) c._is_vip = true;
  });
  return [...channels, ...vipExtra];
}


async function loadApp() {
  // Load weather for header
  const w = await api('/weather');
  if (w && w.enabled) {
    document.getElementById('hdr-w-icon').textContent = w.icon;
    document.getElementById('hdr-w-temp').textContent = w.temperature + '°';
    document.getElementById('hdr-w-city').textContent = w.city;
  }
  // v6: Load RSS, messages, birthdays, VIP channels
  // Load settings, skin + nav first (home screen depends on them)
  await Promise.all([loadSettings(), loadSkin(), loadNavConfig()]);
  // Then load everything else in parallel
  await Promise.all([
    loadRssFeeds(),
    loadVipChannels(),
    loadPrayerTimes(),
    pollMessages(),
    checkBirthdays(),
    loadServices(),
    loadInbox(),
    loadAdsCache()
  ]);
  // v6: Poll messages every 30s, RSS every feed's own interval
  setInterval(pollMessages, 30000);
  setInterval(() => loadInbox(), 60000);
  // Auto-refresh RSS every 5 minutes as a safety net (feeds also schedule themselves)
  setInterval(loadRssFeeds, 5 * 60 * 1000);
  // v8.2: Poll for admin config changes every 30s → auto-refresh TV client
  _lastConfigStamp = _settings.config_stamp || '';
  setInterval(pollConfigChanges, 30000);
  // Show the app
  document.getElementById('root').classList.add('visible');
  showScreen('home');
  // Show PMS guest welcome overlay if enabled and not yet shown this session
  showGuestWelcome();
}

// ── PMS Guest Welcome Screen ──────────────────────────────────────────────────
function showGuestWelcome() {
  if (_settings.pms_enabled !== '1') return;
  if (sessionStorage.getItem('nv_welcome_shown')) return;

  const roomInfo   = getRoomInfo();
  const guestName  = roomInfo?.guest_name || '';
  if (!guestName) return;

  const overlay    = document.getElementById('guest-welcome');
  if (!overlay) return;

  // Populate content
  const hotelName  = _settings.hotel_name || 'NexVision';
  const checkin    = roomInfo.checkin_time  || '';
  const checkout   = roomInfo.checkout_time || '';

  const gwHotel    = document.getElementById('gw-hotel');
  const gwGreeting = document.getElementById('gw-greeting');
  const gwTimes    = document.getElementById('gw-times');

  if (gwHotel)    gwHotel.textContent    = hotelName;
  if (gwGreeting) gwGreeting.textContent = 'Welcome, ' + guestName;
  if (gwTimes) {
    let timeLines = '';
    if (checkin)  timeLines += `<div>Check-in: <b>${_fmtDT(checkin)}</b></div>`;
    if (checkout) timeLines += `<div>Check-out: <b>${_fmtDT(checkout)}</b></div>`;
    gwTimes.innerHTML = timeLines;
  }

  overlay.style.display = 'flex';
  sessionStorage.setItem('nv_welcome_shown', '1');

  // Welcome music
  let _welcomeAudio = null;
  if (_settings.welcome_music_enabled === '1' && _settings.welcome_music_url) {
    _welcomeAudio = new Audio(_settings.welcome_music_url);
    _welcomeAudio.volume = 0.7;
    _welcomeAudio.play().catch(() => {});
  }

  function _dismissWelcome() {
    overlay.style.display = 'none';
    if (_welcomeAudio) { _welcomeAudio.pause(); _welcomeAudio = null; }
    showScreen('home');
    document.removeEventListener('keydown', _dismissWelcome);
    overlay.removeEventListener('click', _dismissWelcome);
  }

  // Auto-dismiss after 12 seconds
  setTimeout(_dismissWelcome, 12000);
  document.addEventListener('keydown', _dismissWelcome, { once: true });
  overlay.addEventListener('click', _dismissWelcome, { once: true });
}

function _fmtDT(dt) {
  if (!dt) return '';
  try {
    const d = new Date(dt.includes('T') ? dt : dt.replace(' ', 'T'));
    if (isNaN(d)) return dt;
    return d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
  } catch (_) { return dt; }
}

// ── Auto-sync: detect admin changes and refresh content ───────────────────────
let _lastConfigStamp = '';

async function pollConfigChanges() {
  try {
    // Lightweight check first — only fetch full settings if something changed
    const stampData = await api('/settings/stamp');
    if (!stampData) return;
    const stamp = stampData.stamp || '';
    if (!_lastConfigStamp) { _lastConfigStamp = stamp; return; } // first run, just record
    if (stamp === _lastConfigStamp) return; // no change

    // Something changed — fetch full settings and refresh
    _lastConfigStamp = stamp;
    const s = await api('/settings');
    if (!s) return;
    _settings = s;

    // Reload slides
    const slides = await api('/slides');
    if (slides) { _promoSlides = slides; }

    // Reload ads cache
    await loadAdsCache();

    // Reload nav
    await loadNavConfig();

    // Reload RSS / custom ticker
    await loadRssFeeds();

    // Force home to re-render with fresh data
    loadedScreens.delete('home');
    loadedScreens.delete('tv');
    loadedScreens.delete('info');
    if (activeScreen === 'home') {
      await loadHome();
    }
    // Reload services so guest services screen is always fresh
    await loadServices();
    if (activeScreen === 'services') {
      await renderServicesScreen();
    }
    // Reload content pages
    loadedScreens.delete('info');

    applyClientBranding(s);
    initCastQR();
    initAlarmChecker();
    loadedScreens.delete('clock');

    // Reload skin (admin may have changed background image)
    await loadSkin();

    console.log('[NexVision] Config updated (stamp=' + stamp + ') — content refreshed');
  } catch(e) {}
}

async function loadSkin() {
  const skin = await api('/skin');
  if (!skin) return;
  const bg = (skin.background_image || '').trim();
  const root = document.getElementById('root') || document.body;
  if (bg) {
    root.style.backgroundImage    = `url('${bg}')`;
    root.style.backgroundSize     = 'cover';
    root.style.backgroundPosition = 'center center';
    root.style.backgroundRepeat   = 'no-repeat';
    root.style.backgroundAttachment = 'fixed';
  } else {
    root.style.backgroundImage    = '';
    root.style.backgroundSize     = '';
    root.style.backgroundPosition = '';
    root.style.backgroundRepeat   = '';
    root.style.backgroundAttachment = '';
  }
}

async function init() {
  // Fetch deployment mode early (before registration screen) so labels are correct
  try {
    const _ms = await fetch(API + '/settings').then(r=>r.json()).catch(()=>null);
    if (_ms) { _settings = _ms; window._deployMode = _ms.deployment_mode || 'hotel'; }
  } catch(e) {}
  applyDeployMode();

  // After splash animation, decide: show registration or load app
  setTimeout(async () => {
    document.getElementById('splash').classList.add('hide');

    await new Promise(r => setTimeout(r, 400)); // wait for fade

    // v8: Admin live preview can inject a room token via URL param
    const pvToken = new URLSearchParams(window.location.search).get('preview_token');
    if (pvToken) {
      localStorage.setItem(ROOM_TOKEN_KEY, pvToken);
      const rInfo = await fetch(API + '/rooms/setup/' + pvToken).then(r=>r.json()).catch(()=>null);
      if (rInfo) localStorage.setItem(ROOM_INFO_KEY, JSON.stringify(rInfo));
    }

    if (!isRegistered()) {
      // ── Not registered: show registration input ────────────────────────────
      showRegisterScreen();
      // App will continue inside doRegister() on success
    } else {
      // ── Already registered: go straight to app ─────────────────────────────
      updateRoomBadge();
      await loadApp();
      // v8: Navigate to hash screen if provided
      const hash = window.location.hash.replace('#','');
      if (hash && typeof showScreen === 'function') setTimeout(()=>showScreen(hash), 800);
    }
  }, 1600);
}

// ═══════════════════════════════════════════════════════════════════════════
// D-PAD NAVIGATION  (TV mode only — body.tv-mode present)
//
// Spatial algorithm: for each arrow direction, scores every visible focusable
// element by (primary-axis distance) + (cross-axis offset × 2.5).  The ×2.5
// weight makes alignment dominate over raw closeness, so pressing Down in a
// grid column lands on the tile directly below, not a diagonal neighbour.
//
// Registered with {capture:true} so it runs before the bubble-phase handler
// below that calls nextChannel/prevChannel — those are superseded in TV mode
// by focus-driven navigation (Enter on a .ch-row triggers playChannel).
// ═══════════════════════════════════════════════════════════════════════════
const DPad = (() => {
  if (!document.body.classList.contains('tv-mode')) return null;

  // ── Selectors ─────────────────────────────────────────────────────────────
  // Tiles: non-native interactive elements that need tabindex=0 to be focusable.
  const TILE_SEL =
    '.ch-card,.ch-row,.mv-card,.movie-tile,.station-card,' +
    '.svc-tile,.info-tile,.prayer-tile,.msg-card-inbox,.info-list-row';

  // Full set: tiles + every native focusable in the UI.
  const ALL_SEL =
    TILE_SEL +
    ',.nav-btn,.ch-group-btn,.filter-chip,.country-tab' +
    ',.ctrl-btn,.epg-btn,.btn-hero,.reg-btn,.h-nav-btn' +
    ',.vlc-btn,.vlc-play,.vlc-skip,.r-btn,.sec-link' +
    ',.msg-mark-all,.mb-close,.bday-close,.epg-close' +
    ',.hdr-msg-btn,.svc-call-btn,.ig-btn,.info-overlay-back,.info-overlay-close' +
    ',button:not([disabled]),a[href]';

  // ── Helpers ───────────────────────────────────────────────────────────────
  // Returns every element that matches ALL_SEL and is actually visible on screen.
  function visibleFocusables() {
    return Array.from(document.querySelectorAll(ALL_SEL)).filter(el => {
      if (el.offsetParent === null) return false;   // display:none ancestor
      const r = el.getBoundingClientRect();
      // Must have size and overlap the viewport
      return r.width > 0 && r.height > 0 &&
             r.bottom > 0 && r.right > 0 &&
             r.top < window.innerHeight && r.left < window.innerWidth;
    });
  }

  // Centre-point of an element's bounding rect.
  function centre(el) {
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }

  // ── Spatial move ──────────────────────────────────────────────────────────
  // Finds the best candidate in `dir` from `current` using a weighted score:
  //   score = primaryDist + crossDist * 2.5
  // Low score wins.  The cross-axis weight ensures column/row alignment is
  // preferred over raw Euclidean distance (critical for grid layouts).
  function spatialMove(current, dir) {
    const all = visibleFocusables();
    const { x: cx, y: cy } = centre(current);

    let best = null;
    let bestScore = Infinity;

    for (const el of all) {
      if (el === current) continue;
      const { x: ex, y: ey } = centre(el);
      const dx = ex - cx;
      const dy = ey - cy;

      let primary, cross, inDir;
      if (dir === 'right') { inDir = dx >  2; primary =  dx; cross = Math.abs(dy); }
      if (dir === 'left')  { inDir = dx < -2; primary = -dx; cross = Math.abs(dy); }
      if (dir === 'down')  { inDir = dy >  2; primary =  dy; cross = Math.abs(dx); }
      if (dir === 'up')    { inDir = dy < -2; primary = -dy; cross = Math.abs(dx); }

      if (!inDir) continue;

      const score = primary + cross * 2.5;
      if (score < bestScore) { bestScore = score; best = el; }
    }

    return best;
  }

  // ── Focus + scroll ────────────────────────────────────────────────────────
  function focusEl(el) {
    if (!el) return;
    el.focus({ preventScroll: true });
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
  }

  // Focus the first tile in the active screen, falling back to first nav-btn.
  function focusFirst() {
    const screen = document.querySelector('.screen.active');
    const tile   = screen && screen.querySelector(TILE_SEL);
    if (tile) { focusEl(tile); return; }
    const nav = document.querySelector('#top-nav .nav-btn, #bottom-nav .nav-btn');
    if (nav) focusEl(nav);
  }

  // ── Screen history for Backspace ──────────────────────────────────────────
  const _history = [];
  const _origShowScreen = window.showScreen;

  window.showScreen = async function (name, ...args) {
    // Record departing screen so Backspace can return to it.
    // `activeScreen` is the existing global tracking variable.
    if (typeof activeScreen !== 'undefined' && activeScreen !== name) {
      _history.push(activeScreen);
      if (_history.length > 20) _history.shift();
    }
    const result = await _origShowScreen.call(this, name, ...args);
    // Transition is 300 ms (opacity); give a small buffer before focusing.
    setTimeout(focusFirst, 360);
    return result;
  };

  // ── Key handler ───────────────────────────────────────────────────────────
  function onKey(e) {
    // Hands off when a text field is active — let normal typing through.
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    // Hands off when the VOD player modal owns the keyboard.
    if (document.getElementById('vod-player-modal')?.classList.contains('open')) return;

    // ── Arrow keys ───────────────────────────────────────────────────────────
    const DIR = { ArrowUp:'up', ArrowDown:'down', ArrowLeft:'left', ArrowRight:'right' };
    const dir = DIR[e.key];

    if (dir) {
      e.preventDefault();
      // stopImmediatePropagation prevents the bubble-phase handler below from
      // also firing nextChannel/prevChannel on the same keystroke.
      e.stopImmediatePropagation();
      // Any arrow key while fullscreen wakes the OSD (or resets its timer).
      if (document.fullscreenElement) FsOsd.show();

      const cur = document.activeElement;
      if (!cur || cur === document.body || cur === document.documentElement) {
        focusFirst();
        return;
      }
      const next = spatialMove(cur, dir);

      // Grid edge → flip page instead of wrapping or stopping.
      // Triggered when there is no focusable candidate in the pressed direction
      // and the focused element lives inside the channel grid (#ch-list).
      if (!next && (dir === 'left' || dir === 'right') && cur.closest('#ch-list')) {
        if (dir === 'right') {
          tvNextPage().then(() => {
            const first = document.querySelector('#ch-list .ch-card, #ch-list .ch-row');
            if (first) focusEl(first);
          });
        } else {
          tvPrevPage().then(() => {
            const tiles = document.querySelectorAll('#ch-list .ch-card, #ch-list .ch-row');
            if (tiles.length) focusEl(tiles[tiles.length - 1]);
          });
        }
        return;
      }

      if (next) focusEl(next);
      return;
    }

    // ── Enter → click ────────────────────────────────────────────────────────
    if (e.key === 'Enter') {
      // Wake OSD on Enter while fullscreen (e.g. pressing play/mute ctrl-btn).
      if (document.fullscreenElement) FsOsd.show();
      const cur = document.activeElement;
      if (cur && cur !== document.body) {
        e.preventDefault();
        cur.click();
      }
      return;
    }

    // ── Backspace → exit fullscreen first, then go back ─────────────────────
    if (e.key === 'Backspace') {
      e.preventDefault();
      if (document.fullscreenElement) {
        // Let fullscreenchange handle focus restoration after the exit animates.
        document.exitFullscreen().catch(() => {});
        return;
      }
      const prev = _history.pop();
      // Call the original directly to avoid re-recording this navigation.
      if (typeof _origShowScreen === 'function') {
        _origShowScreen.call(window, prev || 'home');
        setTimeout(focusFirst, 360);
      }
    }
  }

  // Capture phase: runs before all bubble-phase handlers on document.
  document.addEventListener('keydown', onKey, { capture: true });

  // ── Initial auto-focus ────────────────────────────────────────────────────
  // Content loads asynchronously from the API after init().  Watch for the
  // first batch of tiles to appear, then focus once.
  let _initialFocusDone = false;
  new MutationObserver((_, obs) => {
    if (_initialFocusDone) return;
    const screen = document.querySelector('.screen.active');
    if (screen && screen.querySelector(TILE_SEL)) {
      _initialFocusDone = true;
      obs.disconnect();
      setTimeout(focusFirst, 120);
    }
  }).observe(document.body, { childList: true, subtree: true });

  return { focusFirst, spatialMove, focusEl };
})();

// Restore D-pad focus when fullscreen exits in TV mode.
// Fires whether the user pressed Backspace (our handler), Escape (browser
// native), or the browser chrome's own exit button.
document.addEventListener('fullscreenchange', () => {
  if (!document.body.classList.contains('tv-mode')) return;

  if (document.fullscreenElement) {
    // Entering fullscreen — show OSD immediately with current channel data.
    const ch = allChannels.find(c => c.id === currentChId);
    FsOsd.show(ch || null);
    return;
  }

  // Exiting fullscreen — dismiss OSD, then restore D-pad focus.
  FsOsd.hide();
  // Small delay: let the browser finish the fullscreen-exit transition before
  // re-focusing, otherwise the focus call lands on an element still animating
  // out of the fullscreen layer and the outline ring appears in the wrong place.
  setTimeout(() => {
    const playingRow = document.querySelector('.ch-row.playing, .ch-card.playing');
    if (playingRow) {
      playingRow.focus({ preventScroll: true });
      // ch-card is in a non-scrolling grid; ch-row still needs scrollIntoView.
      if (playingRow.classList.contains('ch-row')) {
        playingRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    } else if (DPad) {
      DPad.focusFirst();
    }
  }, 120);
});

// Keyboard nav
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeMovieDetail();
    closeInfoOverlay();
    document.querySelectorAll('div[style*="position:fixed"]').forEach(d=>{ if(d.id!=='splash') d.remove(); });
  }
  // Arrow-key channel switching is superseded in tv-mode by DPad above.
  // Kept here for non-tv-mode browser use (mouse/keyboard desktop users).
  if (!document.body.classList.contains('tv-mode')) {
    if (e.key === 'ArrowRight' && activeScreen==='tv') nextChannel();
    if (e.key === 'ArrowLeft'  && activeScreen==='tv') prevChannel();
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// ADS — pre-roll overlay for Live TV and VOD players
// ═══════════════════════════════════════════════════════════════════════════════
let _adsCache = null;

async function loadAdsCache() {
  try {
    const data = await fetch(API + '/ads').then(r => r.json()).catch(() => []);
    _adsCache = Array.isArray(data) ? data : [];
  } catch(e) { _adsCache = []; }
}

let _adResolve = null;

function showAdOverlay(placement) {
  if (!_adsCache || !_adsCache.length) return Promise.resolve();
  const eligible = _adsCache.filter(a => a.active && (a.placement === placement || a.placement === 'both'));
  if (!eligible.length) return Promise.resolve();
  const ad = eligible[Math.floor(Math.random() * eligible.length)];

  return new Promise(resolve => {
    _adResolve = resolve;
    const overlay = document.getElementById('ad-overlay');
    const imgEl   = document.getElementById('ad-img-el');
    const vidEl   = document.getElementById('ad-video-el');
    const timerEl = document.getElementById('ad-timer');
    const skipBtn = document.getElementById('ad-skip-btn');

    imgEl.style.display = 'none';
    vidEl.style.display = 'none';
    skipBtn.style.display = 'none';
    overlay.style.display = 'flex';

    let adAutoTimer, skipCountTimer;

    function finishAd() {
      clearTimeout(adAutoTimer);
      clearInterval(skipCountTimer);
      overlay.style.display = 'none';
      vidEl.pause();
      vidEl.src = '';
      if (_adResolve) { _adResolve(); _adResolve = null; }
    }
    window._finishAd = finishAd;

    if (ad.skip_after > 0) {
      let remaining = ad.skip_after;
      skipBtn.textContent = `Skip in ${remaining}s`;
      skipBtn.style.display = 'block';
      skipBtn.style.opacity = '0.5';
      skipBtn.disabled = true;
      skipCountTimer = setInterval(() => {
        remaining--;
        if (remaining <= 0) {
          clearInterval(skipCountTimer);
          skipBtn.textContent = 'Skip Ad ›';
          skipBtn.style.opacity = '1';
          skipBtn.disabled = false;
        } else {
          skipBtn.textContent = `Skip in ${remaining}s`;
        }
      }, 1000);
    }

    if (ad.media_type === 'video') {
      vidEl.style.display = 'block';
      vidEl.src = ad.media_url;
      vidEl.muted = false;
      vidEl.play().catch(() => { vidEl.muted = true; vidEl.play().catch(() => {}); });
      vidEl.onended = finishAd;
      timerEl.textContent = '📢 Advertisement';
    } else {
      imgEl.style.display = 'block';
      imgEl.src = ad.media_url;
      const dur = Math.max((ad.duration_seconds || 10), 3) * 1000;
      let secsLeft = Math.round(dur / 1000);
      timerEl.textContent = `Advertisement · ${secsLeft}s`;
      skipCountTimer = skipCountTimer || setInterval(() => {
        secsLeft--;
        timerEl.textContent = secsLeft > 0 ? `Advertisement · ${secsLeft}s` : 'Advertisement';
        if (secsLeft <= 0) clearInterval(skipCountTimer);
      }, 1000);
      adAutoTimer = setTimeout(finishAd, dur);
    }
  });
}

function skipAd() {
  if (window._finishAd) window._finishAd();
}

// ═══════════════════════════════════════════════════════════════════════════════
// CAST FULL PAGE
// ═══════════════════════════════════════════════════════════════════════════════
async function loadCast() {
  const el = document.getElementById('screen-cast');
  if (!el) return;

  const enabled   = _settings.cast_qr_enabled === '1';
  const serverUrl = (_settings.cast_server_url || '').trim().replace(/\/$/, '');
  const roomInfo  = getRoomInfo();
  const roomNum   = roomInfo?.room_number;

  if (!enabled || !serverUrl) {
    el.innerHTML = `
      <div class="cast-pg-empty">
        <div class="cpe-icon">📡</div>
        <div class="cpe-title">Cast Not Available</div>
        <div class="cpe-sub">Casting has not been configured on this property.<br>Please contact the front desk for assistance.</div>
      </div>`;
    return;
  }

  if (!roomNum) {
    el.innerHTML = `
      <div class="cast-pg-empty">
        <div class="cpe-icon">📡</div>
        <div class="cpe-title">Room Not Registered</div>
        <div class="cpe-sub">This TV has not been assigned to a room.<br>Please register this TV to enable casting.</div>
      </div>`;
    return;
  }

  const castUrl = serverUrl + '/room/' + encodeURIComponent(roomNum);

  el.innerHTML = `
    <div class="cast-pg">
      <div class="cast-pg-hdr">
        <div class="cpg-title">Cast to This TV</div>
        <div class="cpg-room">Room ${escHtml(String(roomNum))}</div>
      </div>
      <div class="cast-pg-body">
        <div class="cpg-qr-wrap">
          <div class="cpg-qr-box">
            <canvas id="cast-page-canvas"></canvas>
          </div>
          <div class="cpg-scan-hint">Scan with your phone</div>
        </div>
        <div class="cpg-info">
          <div class="cpg-steps-title">How to Cast</div>
          <div class="cpg-steps">
            <div class="cpg-step"><span class="cpg-step-n">1</span><span>Scan the QR code with your phone</span></div>
            <div class="cpg-step"><span class="cpg-step-n">2</span><span>Open Netflix, YouTube or any streaming app</span></div>
            <div class="cpg-step"><span class="cpg-step-n">3</span><span>Tap the Cast icon and select this TV</span></div>
          </div>
          <div class="cpg-divider"></div>
          <div class="cpg-url-label">Or visit on your browser</div>
          <div class="cpg-url">${escHtml(castUrl)}</div>
        </div>
      </div>
    </div>`;

  requestAnimationFrame(() => { _renderQR('cast-page-canvas', castUrl, 200); });
}

// ═══════════════════════════════════════════════════════════════════════════════
// CAST QR BADGE
// ═══════════════════════════════════════════════════════════════════════════════
function _renderQR(canvasId, text, size) {
  if (typeof QRCode === 'undefined') return;
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  QRCode.toCanvas(canvas, text, { width: size, margin: 1, color: { dark: '#000000', light: '#ffffff' } }, () => {});
}

function initCastQR() {
  const enabled   = _settings.cast_qr_enabled === '1';
  const serverUrl = (_settings.cast_server_url || '').trim().replace(/\/$/, '');
  const position  = _settings.cast_qr_position || 'bottom-right';
  const display   = _settings.cast_qr_display  || 'both';

  const badge   = document.getElementById('cast-qr-badge');
  const ssBadge = document.getElementById('ss-cast-qr');

  if (!enabled || !serverUrl) {
    if (badge)   badge.style.display = 'none';
    if (ssBadge) ssBadge.style.display = 'none';
    return;
  }

  const roomInfo = getRoomInfo();
  const roomNum  = roomInfo?.room_number;
  if (!roomNum) {
    if (badge)   badge.style.display = 'none';
    if (ssBadge) ssBadge.style.display = 'none';
    return;
  }

  const castUrl  = serverUrl + '/room/' + encodeURIComponent(roomNum);
  const showHome = display === 'home' || display === 'both';
  const showSS   = display === 'screensaver' || display === 'both';

  if (badge) {
    badge.className = 'cast-qr-badge cqr-pos-' + position;
    badge.style.display = showHome ? 'flex' : 'none';
    _renderQR('cast-qr-canvas', castUrl, 96);
  }

  if (ssBadge) {
    ssBadge.style.display = showSS ? 'flex' : 'none';
    _renderQR('ss-cast-qr-canvas', castUrl, 140);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// WORLD CLOCK SCREEN
// ═══════════════════════════════════════════════════════════════════════════════

let _wcTickTimer = null;

async function loadWorldClock() {
  const el = document.getElementById('screen-clock');
  if (!el) return;

  let zones = [];
  try { zones = JSON.parse(_settings.worldclock_zones || '[]'); } catch(e) {}

  if (!zones.length) {
    el.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:16px;color:var(--muted);text-align:center;padding:40px">
      <div style="font-size:56px">🌍</div>
      <div style="font-size:18px">No timezones configured</div>
      <div style="font-size:14px">Ask your admin to add timezones in the Clock &amp; Alarm settings.</div>
    </div>`;
    return;
  }

  _renderWorldClockScreen(zones);
  clearInterval(_wcTickTimer);
  _wcTickTimer = setInterval(() => {
    if (activeScreen !== 'clock') { clearInterval(_wcTickTimer); return; }
    _tickWorldClockCards();
  }, 1000);
}

function _wcFmt(tz, opts) {
  try { return new Intl.DateTimeFormat('en-US', {timeZone: tz, ...opts}).format(new Date()); }
  catch(e) { return '—'; }
}

function _wcCityName(tz) {
  return tz.split('/').pop().replace(/_/g, ' ');
}

function _wcTzAbbr(tz) {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {timeZone:tz, timeZoneName:'short'}).formatToParts(new Date());
    return (parts.find(p=>p.type==='timeZoneName')||{}).value || '';
  } catch(e) { return ''; }
}

function _wcIsNight(tz) {
  try {
    const h = parseInt(new Intl.DateTimeFormat('en-US', {timeZone:tz, hour:'numeric', hour12:false}).format(new Date()));
    return h < 6 || h >= 20;
  } catch(e) { return false; }
}

function _renderWorldClockScreen(zones) {
  const el = document.getElementById('screen-clock');
  if (!el) return;

  const now = new Date();
  const serverTime = now.toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit', hour12:false});
  const serverDate = now.toLocaleDateString('en-US', {weekday:'long', year:'numeric', month:'long', day:'numeric'});

  const cards = zones.map((tz, i) => {
    const time    = _wcFmt(tz, {hour:'2-digit', minute:'2-digit', hour12:false});
    const secs    = _wcFmt(tz, {second:'2-digit'});
    const date    = _wcFmt(tz, {month:'short', day:'numeric'});
    const day     = _wcFmt(tz, {weekday:'long'});
    const abbr    = _wcTzAbbr(tz);
    const city    = _wcCityName(tz);
    const night   = _wcIsNight(tz);

    return `<div class="wc-card ${night?'wc-night':'wc-day'}" id="wc-card-${i}" data-tz="${escHtml(tz)}">
      <div class="wc-city">${escHtml(city)}</div>
      <div class="wc-time-wrap">
        <span class="wc-time" id="wc-time-${i}">${escHtml(time)}</span><span class="wc-secs" id="wc-secs-${i}">${escHtml(secs)}</span>
      </div>
      <div class="wc-day-name" id="wc-day-${i}">${escHtml(day)}</div>
      <div class="wc-date" id="wc-date-${i}">${escHtml(date)}</div>
      <div class="wc-abbr">${escHtml(abbr)}</div>
      <div class="wc-icon">${night?'🌙':'☀️'}</div>
    </div>`;
  }).join('');

  el.innerHTML = `
  <div class="wc-screen">
    <div class="wc-header">
      <div class="wc-header-title">🌍 World Clock</div>
      <div class="wc-header-sub">${escHtml(serverDate)}</div>
    </div>
    <div class="wc-grid">${cards}</div>
  </div>`;
}

function _tickWorldClockCards() {
  const el = document.getElementById('screen-clock');
  if (!el) return;
  const cards = el.querySelectorAll('.wc-card');
  cards.forEach((card, i) => {
    const tz = card.dataset.tz;
    if (!tz) return;
    const timeEl = document.getElementById('wc-time-'+i);
    const secsEl = document.getElementById('wc-secs-'+i);
    const dayEl  = document.getElementById('wc-day-'+i);
    const dateEl = document.getElementById('wc-date-'+i);
    if (timeEl) timeEl.textContent = _wcFmt(tz, {hour:'2-digit', minute:'2-digit', hour12:false});
    if (secsEl) secsEl.textContent = _wcFmt(tz, {second:'2-digit'});
    if (dayEl)  dayEl.textContent  = _wcFmt(tz, {weekday:'long'});
    if (dateEl) dateEl.textContent = _wcFmt(tz, {month:'short', day:'numeric'});
    const night = _wcIsNight(tz);
    card.classList.toggle('wc-night', night);
    card.classList.toggle('wc-day', !night);
    const icon = card.querySelector('.wc-icon');
    if (icon) icon.textContent = night ? '🌙' : '☀️';
  });
}


// ═══════════════════════════════════════════════════════════════════════════════
// ALARM SYSTEM
// ═══════════════════════════════════════════════════════════════════════════════

let _alarmCtx        = null;
let _alarmRinging    = false;
let _alarmCheckTimer = null;

// Fired alarm keys persist in localStorage so a page reload within the same
// minute doesn't re-fire the same alarm. Key format: "alarmId:HH:MM:YYYY-MM-DD"
const _ALARM_FIRED_KEY = 'nv_alarm_fired';

function _alarmFiredMark(key) {
  try {
    const map = JSON.parse(localStorage.getItem(_ALARM_FIRED_KEY) || '{}');
    map[key] = Date.now();
    localStorage.setItem(_ALARM_FIRED_KEY, JSON.stringify(map));
  } catch(e) {}
}

function _alarmAlreadyFired(key) {
  try {
    const map = JSON.parse(localStorage.getItem(_ALARM_FIRED_KEY) || '{}');
    const t = map[key];
    return t && (Date.now() - t) < 120000; // 2-minute window
  } catch(e) { return false; }
}

function _alarmPruneFired() {
  try {
    const map = JSON.parse(localStorage.getItem(_ALARM_FIRED_KEY) || '{}');
    const now = Date.now();
    let pruned = false;
    for (const k in map) { if (now - map[k] > 120000) { delete map[k]; pruned = true; } }
    if (pruned) localStorage.setItem(_ALARM_FIRED_KEY, JSON.stringify(map));
  } catch(e) {}
}

function initAlarmChecker() {
  clearInterval(_alarmCheckTimer);
  clearInterval(_alarmCacheTimer);
  _cachedAlarms = [];

  if (_settings.alarm_enabled !== '1') return;

  // Fetch alarm list now and refresh every 5 min (picks up newly added alarms)
  _refreshAlarmCache();
  _alarmCacheTimer = setInterval(_refreshAlarmCache, 300000);

  // Check local time every minute — aligned to the top of the next minute
  const msToNextMinute = (60 - new Date().getSeconds()) * 1000 - new Date().getMilliseconds();
  setTimeout(() => {
    _checkAlarms();
    _alarmCheckTimer = setInterval(_checkAlarms, 60000);
  }, msToNextMinute);
}

let _cachedAlarms = [];
let _alarmCacheTimer = null;

async function _refreshAlarmCache() {
  try {
    const r = await fetch(API + '/alarms/active');
    if (r.ok) _cachedAlarms = await r.json();
  } catch(e) {}
}

async function _checkAlarms() {
  if (_settings.alarm_enabled !== '1') return;
  _alarmPruneFired();

  // Use client local time — server time is irrelevant (could be different timezone)
  const now      = new Date();
  const localHH  = now.getHours().toString().padStart(2, '0');
  const localMM  = now.getMinutes().toString().padStart(2, '0');
  const localTime = localHH + ':' + localMM;
  const localDay  = now.getDay(); // 0=Sun … 6=Sat, matches JS convention

  if (!Array.isArray(_cachedAlarms)) return;
  for (const alarm of _cachedAlarms) {
    if (alarm.time !== localTime) continue;

    const days = alarm.days;
    let dayMatch = false;
    if (days === 'daily') {
      dayMatch = true;
    } else if (Array.isArray(days)) {
      dayMatch = days.includes(localDay);
    } else {
      dayMatch = true; // fallback: fire anyway
    }
    if (!dayMatch) continue;

    const fireKey = alarm.id + ':' + localTime + ':' + now.toDateString();
    if (_alarmAlreadyFired(fireKey)) continue;
    _alarmFiredMark(fireKey);
    _fireAlarm(alarm);
  }
}

function _fireAlarm(alarm) {
  _showAlarmOverlay(alarm);
  _playAlarmSound(alarm.sound || 'bell');
}

function _showAlarmOverlay(alarm) {
  const overlay = document.getElementById('alarm-overlay');
  if (!overlay) return;
  const labelEl = document.getElementById('alarm-label');
  const clockEl = document.getElementById('alarm-clock');
  if (labelEl) labelEl.textContent = alarm.label || 'Alarm';
  if (clockEl) clockEl.textContent = alarm.time  || '--:--';
  overlay.classList.add('on');
  _alarmRinging = true;
  if (_ssActive) wakeFromScreensaver();
}

function dismissAlarm() {
  const overlay = document.getElementById('alarm-overlay');
  if (overlay) overlay.classList.remove('on');
  _alarmRinging = false;
  if (_alarmCtx) {
    try { _alarmCtx.close(); } catch(e) {}
    _alarmCtx = null;
  }
}

function _playAlarmSound(type) {
  try {
    if (_alarmCtx) { try { _alarmCtx.close(); } catch(e) {} }
    _alarmCtx = new (window.AudioContext || window.webkitAudioContext)();
    const ctx  = _alarmCtx;

    const patterns = {
      bell: [
        { freq: 880, start: 0,    dur: 0.8, type: 'sine',     gain: 0.6 },
        { freq: 659, start: 0.9,  dur: 0.8, type: 'sine',     gain: 0.5 },
        { freq: 880, start: 1.8,  dur: 0.8, type: 'sine',     gain: 0.6 },
        { freq: 659, start: 2.7,  dur: 0.8, type: 'sine',     gain: 0.5 },
      ],
      digital: [
        { freq: 1200, start: 0,    dur: 0.12, type: 'square', gain: 0.3 },
        { freq: 1200, start: 0.18, dur: 0.12, type: 'square', gain: 0.3 },
        { freq: 1200, start: 0.36, dur: 0.12, type: 'square', gain: 0.3 },
        { freq: 900,  start: 0.6,  dur: 0.25, type: 'square', gain: 0.3 },
        { freq: 1200, start: 1.0,  dur: 0.12, type: 'square', gain: 0.3 },
        { freq: 1200, start: 1.18, dur: 0.12, type: 'square', gain: 0.3 },
        { freq: 1200, start: 1.36, dur: 0.12, type: 'square', gain: 0.3 },
        { freq: 900,  start: 1.6,  dur: 0.25, type: 'square', gain: 0.3 },
      ],
      gentle: [
        { freq: 528, start: 0,   dur: 1.5, type: 'sine', gain: 0.35 },
        { freq: 594, start: 1.6, dur: 1.5, type: 'sine', gain: 0.35 },
        { freq: 660, start: 3.2, dur: 1.5, type: 'sine', gain: 0.35 },
        { freq: 528, start: 4.8, dur: 1.5, type: 'sine', gain: 0.35 },
      ],
      loud: [
        { freq: 1500, start: 0,    dur: 0.1, type: 'sawtooth', gain: 0.7 },
        { freq: 800,  start: 0.15, dur: 0.1, type: 'sawtooth', gain: 0.7 },
        { freq: 1500, start: 0.3,  dur: 0.1, type: 'sawtooth', gain: 0.7 },
        { freq: 800,  start: 0.45, dur: 0.1, type: 'sawtooth', gain: 0.7 },
        { freq: 1500, start: 0.6,  dur: 0.1, type: 'sawtooth', gain: 0.7 },
        { freq: 800,  start: 0.75, dur: 0.1, type: 'sawtooth', gain: 0.7 },
        { freq: 1500, start: 0.9,  dur: 0.1, type: 'sawtooth', gain: 0.7 },
        { freq: 800,  start: 1.05, dur: 0.1, type: 'sawtooth', gain: 0.7 },
      ],
    };

    const notes = patterns[type] || patterns.bell;
    for (const note of notes) {
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = note.type;
      osc.frequency.setValueAtTime(note.freq, ctx.currentTime + note.start);
      gain.gain.setValueAtTime(0, ctx.currentTime + note.start);
      gain.gain.linearRampToValueAtTime(note.gain, ctx.currentTime + note.start + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + note.start + note.dur);
      osc.start(ctx.currentTime + note.start);
      osc.stop(ctx.currentTime + note.start + note.dur + 0.05);
    }
  } catch(e) {}
}

init();

// Remove any old service worker so admin routes are never shadowed by stale app-shell cache.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations()
    .then(registrations => Promise.all(registrations.map(registration => registration.unregister())))
    .catch(() => {});
}
