// hassmic's wall panel (wall.html), in the manner of Apple's HomeView: square glass widgets over a wallpaper, a page
// Home (clock, date and weather, the thermostat's big number, what plays, a camera, scenes, locks, the kiosk's other
// screens) and a page per room (Home Assistant's areas: a tile per light, switch, fan, cover, lock, speaker, door or
// motion sensor, a thermostat as a big one), swiped sideways; a tap toggles, a long press opens the controls; left
// alone, the ambient clock.  URL: ?theme=amber|dusk|light, ?ambient=<s>, ?favorites=<ids> (Home's tiles),
// ?thermostat=, ?camera=, ?weather=.  Only Home Assistant's websocket: subscribe_entities (compressed states, as the frontend gets them), the
// area, device and entity registries for display, call_service.
//
// The login: the kiosk app puts the Echo's token into this origin's localStorage as the frontend keeps its own
// ("hassTokens"), so a browser logged into Home Assistant here ("Keep me logged in") opens this page as well.
// window.HassmicKiosk (the kiosk app's, Kiosk.java Bridge): the other screens, to switch to.
'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  const params = new URLSearchParams(location.search);

  // ---------------------------------------------------------------- icons (drawn for this page, 24 x 24)
  const P = {
    bulb: 'M12 2a7 7 0 0 0-4 12.7V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.3A7 7 0 0 0 12 2zm-3 18h6v1a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1z',
    power: 'M11 3h2v9h-2zM7.05 5.64l1.41 1.41A6 6 0 1 0 15.54 7.05l1.41-1.41A8 8 0 1 1 7.05 5.64z',
    plug: 'M8 2h2v5H8zm6 0h2v5h-2zM6 8h12v3a6 6 0 0 1-5 5.9V22h-2v-5.1A6 6 0 0 1 6 11z',
    fan: 'M12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2zm.5-9C17 2 17 7 13.6 10c3-1.8 8.4-1.6 8.4 2.5 0 4.5-5 4.5-8 1.1 1.8 3 1.6 8.4-2.5 8.4C7 22 7 17 10.4 14c-3 1.8-8.4 1.6-8.4-2.5C2 7 7 7 10 10.4 8.2 7.4 8.4 2 12.5 2z',
    blinds: 'M3 3h18v2h-1v14h1v2H3v-2h1V5H3zm3 2v2h12V5zm0 4v2h12V9zm0 4v2h12v-2zm0 4v2h12v-2z',
    thermo: 'M12 2a3 3 0 0 0-3 3v8.3a5 5 0 1 0 6 0V5a3 3 0 0 0-3-3zm0 2a1 1 0 0 1 1 1v9.4l.4.3a3 3 0 1 1-2.8 0l.4-.3V5a1 1 0 0 1 1-1z',
    music: 'M9 3v10.6A4 4 0 1 0 11 17V7h8V3z',
    lock: 'M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5zm-3 8V7a3 3 0 0 1 6 0v3z',
    unlock: 'M12 2a5 5 0 0 0-5 5h2a3 3 0 0 1 6 0v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5z',
    sparkle: 'M12 2l1.8 5.2L19 9l-5.2 1.8L12 16l-1.8-5.2L5 9l5.2-1.8zm7 11l.9 2.1L22 16l-2.1.9L19 19l-.9-2.1L16 16l2.1-.9z',
    door: 'M6 2h12v20h-2V4H8v18H6zm8 9a1 1 0 1 0 0 2 1 1 0 0 0 0-2z',
    window: 'M4 3h16v18H4zm2 2v6h5V5zm7 0v6h5V5zm-7 8v6h5v-6zm7 0v6h5v-6z',
    motion: 'M13.5 5.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM9.8 8.9L7 23h2.1l1.8-8 2.1 2v6h2v-7.5l-2.1-2 .6-3A7.3 7.3 0 0 0 19 13v-2a5.1 5.1 0 0 1-4.4-2.4l-1-1.6a2 2 0 0 0-2.5-.8L6 8.3V13h2V9.6z',
    toggle: 'M7 7h10a5 5 0 0 1 0 10H7A5 5 0 0 1 7 7zm10 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
    home: 'M12 3l9 8h-3v9h-5v-6h-2v6H6v-9H3z',
    play: 'M8 5v14l11-7z', pause: 'M6 5h4v14H6zm8 0h4v14h-4z', next: 'M6 6l8.5 6L6 18zm10 0h2v12h-2z', prev: 'M18 6l-8.5 6L18 18zM6 6h2v12H6z',
    sun: 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM11 1h2v3h-2zm0 19h2v3h-2zM1 11h3v2H1zm19 0h3v2h-3zM4.2 2.8l2.1 2.1-1.4 1.4-2.1-2.1zm14.9 14.9 2.1 2.1-1.4 1.4-2.1-2.1zM2.8 19.8l2.1-2.1 1.4 1.4-2.1 2.1zM17.7 4.9l2.1-2.1 1.4 1.4-2.1 2.1z',
    cloud: 'M6.5 19a4.5 4.5 0 0 1-.4-9A6 6 0 0 1 17.6 9 5 5 0 0 1 18 19z',
    rain: 'M6.5 15a4.5 4.5 0 0 1-.4-9A6 6 0 0 1 17.6 5 5 5 0 0 1 18 15zM8 17h2l-1 4H7zm5 0h2l-1 4h-2z',
    moon: 'M14 2a9 9 0 1 0 8 13A8 8 0 0 1 14 2z',
    screen: 'M3 4h18v12H3zm2 2v8h14V6zm3 12h8v2H8z',
    up: 'M7.4 15.4L12 10.8l4.6 4.6L18 14l-6-6-6 6z', down: 'M7.4 8.6L12 13.2l4.6-4.6L18 10l-6 6-6-6z',
  };
  const svg = (name) => `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${P[name] || P.power}"/></svg>`;

  // ---------------------------------------------------------------- the login and the websocket
  function tokens() {
    try { return JSON.parse(localStorage.getItem('hassTokens') || 'null'); } catch (e) { return null; }
  }
  async function refresh(t) {
    // a browser's own login (a 30 min access token with a refresh token); the kiosk's never expires
    if (!t || !t.refresh_token) return null;
    const body = new URLSearchParams({ grant_type: 'refresh_token', client_id: t.clientId || location.origin + '/', refresh_token: t.refresh_token });
    const r = await fetch('/auth/token', { method: 'POST', body });
    if (!r.ok) return null;
    const j = await r.json();
    const n = Object.assign({}, t, j, { expires: Date.now() + j.expires_in * 1000 });
    try { localStorage.setItem('hassTokens', JSON.stringify(n)); } catch (e) { /* private window */ }
    return n;
  }

  let ws, nextId = 1;
  const pending = new Map(), subs = new Map();
  function send(msg) {
    return new Promise((res, rej) => {
      const id = nextId++; pending.set(id, { res, rej });
      ws.send(JSON.stringify(Object.assign({ id }, msg)));
    });
  }
  function subscribe(msg, cb) {
    const id = nextId++; subs.set(id, cb);
    const p = new Promise((res, rej) => pending.set(id, { res, rej }));
    ws.send(JSON.stringify(Object.assign({ id }, msg)));
    p.catch(() => subs.delete(id));
    return p;
  }
  const call = (domain, service, entity_id, data) => send({ type: 'call_service', domain, service, service_data: data || {}, target: { entity_id } }).catch((e) => console.warn(service, e));

  async function connect() {
    let t = tokens();
    if (!t || !t.access_token) { message('Not logged in', 'Set the kiosk up from the hassmic integration, or log into Home Assistant in this browser with "Keep me logged in".'); return; }
    if (t.expires && Date.now() > t.expires - 60000 && t.refresh_token) t = (await refresh(t).catch(() => null)) || t;
    ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/api/websocket');
    ws.onmessage = async (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === 'auth_required') ws.send(JSON.stringify({ type: 'auth', access_token: t.access_token }));
      else if (m.type === 'auth_invalid') {
        const n = await refresh(t).catch(() => null);
        if (n) { ws.close(); return; }     // onclose connects again with it
        message('Login refused', 'Home Assistant no longer takes this login: set the kiosk up again from the hassmic integration.');
        ws.onclose = null; ws.close();
      } else if (m.type === 'auth_ok') started();
      else if (m.type === 'result') { const p = pending.get(m.id); if (p) { pending.delete(m.id); m.success ? p.res(m.result) : p.rej(m.error); } }
      else if (m.type === 'event') { const cb = subs.get(m.id); if (cb) cb(m.event); }
    };
    ws.onclose = () => { pending.clear(); subs.clear(); setTimeout(connect, 5000); };
  }

  // ---------------------------------------------------------------- state
  const states = {};                    // entity_id -> { s, a }
  let areas = [], devices = {}, entities = {};
  let built = false;

  function onEntities(ev) {
    let changed = new Set(), rebuild = false;
    if (ev.a) for (const [id, v] of Object.entries(ev.a)) { if (!states[id]) rebuild = true; states[id] = { s: v.s, a: v.a || {} }; changed.add(id); }
    if (ev.c) for (const [id, d] of Object.entries(ev.c)) {
      const st = states[id]; if (!st) continue;
      if (d['+']) { if ('s' in d['+']) st.s = d['+'].s; if (d['+'].a) Object.assign(st.a, d['+'].a); }
      if (d['-'] && d['-'].a) for (const k of d['-'].a) delete st.a[k];
      changed.add(id);
    }
    if (ev.r) for (const id of ev.r) { delete states[id]; rebuild = true; }
    if (!built || rebuild) render(); else changed.forEach(update);
  }

  async function registries() {
    const [ar, dv, en] = await Promise.all([
      send({ type: 'config/area_registry/list' }),
      send({ type: 'config/device_registry/list' }).catch(() => []),
      send({ type: 'config/entity_registry/list_for_display' }),
    ]);
    areas = ar.sort((x, y) => x.name.localeCompare(y.name));
    devices = {}; for (const d of dv) devices[d.id] = d;
    entities = {}; for (const e of en.entities) entities[e.ei] = e;
    render();
  }

  async function started() {
    // the layout (custom_components/hassmic wall.py): this Echo's, followed live; without the integration, this
    // browser's own (localStorage)
    subscribe({ type: 'hassmic/wall/subscribe', echo: ECHO }, (ev) => { layout = ev.layout || {}; local = false; applyLayout(); })
      .catch(() => { local = true; try { layout = JSON.parse(localStorage.getItem('hassmicWall') || '{}'); } catch (e) { layout = {}; } applyLayout(); });
    subscribe({ type: 'subscribe_entities' }, onEntities);
    await registries().catch((e) => message('No rooms', 'Home Assistant did not give the areas: ' + (e && e.message || e)));
    // areas and entities renamed or moved: read again
    for (const t of ['area_registry_updated', 'entity_registry_updated', 'device_registry_updated'])
      subscribe({ type: 'subscribe_events', event_type: t }, debounce(() => registries().catch(() => {}), 1500));
  }
  function debounce(f, ms) { let t; return () => { clearTimeout(t); t = setTimeout(f, ms); }; }

  // ---------------------------------------------------------------- what is shown
  const TILES = ['light', 'switch', 'fan', 'cover', 'climate', 'media_player', 'lock', 'input_boolean', 'humidifier', 'vacuum', 'binary_sensor'];
  const SENSORS = ['door', 'window', 'garage_door', 'opening', 'motion', 'occupancy', 'presence'];
  const domain = (id) => id.slice(0, id.indexOf('.'));

  function areaOf(id) {
    const e = entities[id];
    if (!e) return null;
    if (e.ai) return e.ai;
    const d = e.di && devices[e.di];
    return (d && d.area_id) || null;
  }
  function shown(id) {
    if (hidden().has(id)) return false;
    const e = entities[id], st = states[id], dm = domain(id);
    if (e && (e.hb || e.ec != null)) return false;          // hidden, or a config/diagnostic entity
    if (!st) return false;
    if (dm === 'binary_sensor') return SENSORS.includes(st.a.device_class);
    if (dm === 'switch' && st.a.device_class === undefined && e && e.ec != null) return false;
    return TILES.includes(dm) || dm === 'scene' || dm === 'script';
  }
  function nameOf(id, areaName) {
    const st = states[id];
    let n = (st && st.a.friendly_name) || id;
    // "Kitchen Ceiling" in Kitchen is "Ceiling", as Apple's Home shows it
    if (areaName && n.toLowerCase().startsWith(areaName.toLowerCase() + ' ') && n.length > areaName.length + 2) n = n.slice(areaName.length + 1);
    return n;
  }

  function look(id) {
    const st = states[id], dm = domain(id), s = st.s, a = st.a;
    const r = { on: false, icon: 'power', c: 'var(--amber)', text: s, bar: null };
    if (s === 'unavailable' || s === 'unknown') { r.text = s === 'unknown' ? '—' : 'No response'; r.unavail = true; }
    switch (dm) {
      case 'light':
        r.icon = 'bulb'; r.on = s === 'on';
        if (r.on) {
          const pct = a.brightness != null ? Math.round(a.brightness / 2.55) : null;
          r.text = pct != null ? pct + '%' : 'On'; r.bar = pct;
          if (a.rgb_color && a.color_mode && !/color_temp|brightness|onoff/.test(a.color_mode)) r.c = `rgb(${a.rgb_color.join(',')})`;
        } else if (!r.unavail) r.text = 'Off';
        break;
      case 'switch': case 'input_boolean':
        r.icon = a.device_class === 'outlet' ? 'plug' : 'toggle'; r.on = s === 'on'; r.c = 'var(--green)'; if (!r.unavail) r.text = r.on ? 'On' : 'Off'; break;
      case 'fan':
        r.icon = 'fan'; r.on = s === 'on'; r.c = 'var(--blue)'; if (!r.unavail) r.text = r.on ? (a.percentage != null ? a.percentage + '%' : 'On') : 'Off'; break;
      case 'cover': {
        r.icon = 'blinds'; r.c = 'var(--blue)'; r.on = s === 'open' || s === 'opening';
        const pos = a.current_position;
        if (!r.unavail) r.text = { open: pos != null && pos < 100 ? pos + '% open' : 'Open', closed: 'Closed', opening: 'Opening…', closing: 'Closing…' }[s] || s;
        r.bar = r.on ? pos : null; break;
      }
      case 'climate':
        r.icon = 'thermo'; r.on = s !== 'off' && !r.unavail; r.c = s === 'cool' ? 'var(--blue)' : 'var(--orange)';
        if (!r.unavail) r.text = (a.current_temperature != null ? a.current_temperature + '°' : '') + (s === 'off' ? ' · Off' : a.temperature != null ? ' → ' + a.temperature + '°' : ' · ' + s);
        break;
      case 'media_player':
        r.icon = 'music'; r.on = s === 'playing'; r.c = 'var(--red)';
        if (!r.unavail) r.text = s === 'playing' || s === 'paused' ? (a.media_title || s) + (a.media_artist ? ' · ' + a.media_artist : '') : s === 'off' ? 'Off' : 'Idle';
        break;
      case 'lock':
        r.icon = s === 'locked' ? 'lock' : 'unlock'; r.on = s !== 'locked' && !r.unavail; r.c = 'var(--orange)';
        if (!r.unavail) r.text = { locked: 'Locked', unlocked: 'Unlocked', locking: 'Locking…', unlocking: 'Unlocking…', jammed: 'Jammed', open: 'Open' }[s] || s;
        break;
      case 'humidifier': r.icon = 'fan'; r.on = s === 'on'; r.c = 'var(--blue)'; if (!r.unavail) r.text = r.on ? (a.humidity != null ? a.humidity + '%' : 'On') : 'Off'; break;
      case 'vacuum': r.icon = 'home'; r.on = s === 'cleaning'; r.c = 'var(--green)'; break;
      case 'binary_sensor': {
        const dc = a.device_class; r.on = s === 'on'; r.c = 'var(--orange)';
        r.icon = dc === 'motion' || dc === 'occupancy' || dc === 'presence' ? 'motion' : dc === 'window' ? 'window' : 'door';
        if (!r.unavail) r.text = r.icon === 'motion' ? (r.on ? 'Motion' : 'Clear') : (r.on ? 'Open' : 'Closed');
        break;
      }
    }
    return r;
  }

  // ---------------------------------------------------------------- the grid: pages of square glass widgets
  const painters = new Map();           // entity_id -> [repaint functions]
  const bind = (id, f) => { if (!painters.has(id)) painters.set(id, []); painters.get(id).push(f); f(); };
  let pageNames = [], pageIndex = 0, playing = '';

  function message(title, text) {
    let m = document.querySelector('.msg');
    if (!m) { m = el('div', 'msg'); document.body.append(m); }
    m.textContent = ''; const d = el('div'); d.append(el('b', null, title), el('span', null, text)); m.append(d);
    built = false;
  }

  function rooms() {
    const ids = Object.keys(states).filter(shown), by = new Map();
    for (const id of ids) { const a = areaOf(id) || ''; if (!by.has(a)) by.set(a, []); by.get(a).push(id); }
    const list = areas.filter((a) => by.has(a.area_id)).map((a) => ({ id: a.area_id, name: a.name, ids: by.get(a.area_id) }));
    if (by.has('')) list.push({ id: '', name: 'Other', ids: by.get('') });
    return list;
  }
  const roomName = (id) => { const a = areas.find((x) => x.area_id === areaOf(id)); return a ? a.name : ''; };

  function summary(r) {
    // the room's temperature and humidity, as Apple's Home writes under a room's name
    const sens = Object.keys(states).filter((id) => domain(id) === 'sensor' && areaOf(id) === r.id && !(entities[id] && (entities[id].hb || entities[id].ec != null)));
    const pick = (dc) => { const id = sens.find((x) => states[x].a.device_class === dc && !isNaN(parseFloat(states[x].s))); return id && states[id]; };
    const t = pick('temperature'), h = pick('humidity'), out = [];
    if (t) out.push(Math.round(parseFloat(t.s) * 10) / 10 + (t.a.unit_of_measurement || '°'));
    if (h) out.push(Math.round(parseFloat(h.s)) + '%');
    return out.join(' · ');
  }

  // as many square cells as fit: the Show 5's 960 x 470 takes 6 x 3
  function grid() {
    const W = innerWidth, H = innerHeight, gap = 10, pad = 12, bottom = 22;
    const rows = H < 600 ? 3 : H < 900 ? 4 : 5;
    const cell = (H - pad - bottom - gap * (rows - 1)) / rows;
    const cols = Math.max(2, Math.floor((W - 2 * pad + gap) / (cell + gap)));
    document.documentElement.style.setProperty('--cell', cell + 'px');
    document.documentElement.style.setProperty('--rows', rows);
    document.documentElement.style.setProperty('--cols', cols);
    return { rows, cols };
  }

  // items into pages: a 2x2 widget takes four cells; what does not fit starts the page's next one
  function pack(name, items, g, keepOrder) {
    const cap = g.rows * g.cols, bigMax = Math.floor(g.rows / 2) * Math.floor(g.cols / 2), pages = [];
    let cur = null, used = 0, bigs = 0;
    const open = () => { cur = { name: pages.length && pages[pages.length - 1].name.startsWith(name) ? name : name, items: [] }; pages.push(cur); used = 0; bigs = 0; };
    if (!keepOrder) items.sort((a, b) => (b.big ? 1 : 0) - (a.big ? 1 : 0));   // the big ones first: dense flow fills around them
    for (const it of items) {
      const area = it.big ? 4 : 1;
      if (!cur || used + area > cap || (it.big && bigs >= bigMax)) open();
      cur.items.push(it); used += area; if (it.big) bigs++;
    }
    return pages;
  }

  function render() {
    built = true; painters.clear();
    const m = document.querySelector('.msg'); if (m) m.remove();
    const g = grid(), list = rooms();
    const keep = pageNames[pageIndex];
    const pages = [];
    // Home: the clock, the date and weather, then the favourites (the layout's, else a thermostat, a camera, scenes,
    // locks), what plays, the kiosk's other screens
    const home = [{ k: 'clock' }, { k: 'date' }];
    playing = Object.keys(states).find((x) => domain(x) === 'media_player' && states[x].s === 'playing' && states[x].a.media_title && !hidden().has(x)) || '';
    const fav = favorites();
    for (const id of fav) {
      const dm = domain(id);
      if (dm === 'climate' && states[id].a.temperature != null) home.push({ k: 'thermo', id, big: true });
      else if (dm === 'camera') home.push({ k: 'cam', id });
      else if (dm === 'media_player' && id === playing) home.push({ k: 'np', id, big: true });
      else home.push({ k: 'tile', id, home: true });
    }
    if (playing && layout.nowplaying !== false && !fav.includes(playing)) home.push({ k: 'np', id: playing, big: true, auto: true });
    const k = window.HassmicKiosk;
    if (k && !editing) { try { JSON.parse(k.screens()).forEach((n, i) => { if (i !== k.current()) home.push({ k: 'screen', n, i }); }); } catch (e) { /* an older app */ } }
    pages.push(...pack('Home', home, g, true));
    const order = (id) => TILES.indexOf(domain(id));
    for (const r of list) {
      const own = (layout.order || {})[r.id || '-'] || [];
      const at = (id) => { const i = own.indexOf(id); return i < 0 ? 1e6 : i; };
      const kind = (x) => domain(x) === 'scene' || domain(x) === 'script' ? -1 : order(x);
      const ids = r.ids.filter((x) => TILES.includes(domain(x)) || domain(x) === 'scene' || domain(x) === 'script')
        .sort((x, y) => at(x) - at(y) || kind(x) - kind(y) || nameOf(x, r.name).localeCompare(nameOf(y, r.name)));
      if (!ids.length) continue;
      const items = ids.map((id) => domain(id) === 'climate' && states[id].a.temperature != null ? { k: 'thermo', id, big: true, room: r.name } : { k: 'tile', id, room: r.name });
      const ps = pack(r.name, items, g, own.length > 0);
      ps.forEach((p) => { p.sub = summary(r); p.area = r.id || '-'; });
      pages.push(...ps);
    }
    const box = $('pages'); box.textContent = '';
    pageNames = pages.map((p) => p.name);
    pages.forEach((p) => {
      const pg = el('div', 'page'); pg.dataset.name = p.name; pg.dataset.sub = p.sub || ''; pg.dataset.area = p.area || '';
      for (const it of p.items) { const w = widget(it); if (it.id && !it.auto) w.dataset.id = it.id; pg.append(w); if (editing) badges(w, p); }
      box.append(pg);
    });
    if (!list.length && pages.length === 1) message('Nothing in your rooms yet', 'Give your devices areas in Home Assistant: the wall panel shows them room by room.');
    const back = Math.max(0, pageNames.indexOf(keep));
    box.scrollLeft = back * innerWidth; pageIndex = back;
    dots();
  }

  function dots() {
    const d = $('dots'); d.textContent = '';
    const pg = $('pages').children[pageIndex];
    if (pg) d.append(el('span', null, pg.dataset.name + (pg.dataset.sub ? ' · ' + pg.dataset.sub : '')));
    pageNames.forEach((_, i) => { const b = el('i'); if (i === pageIndex) b.className = 'sel'; d.append(b); });
  }

  function widget(it) {
    switch (it.k) {
      case 'clock': { const w = el('div', 'w clockw'); clocks.push(w); drawClock(w); return w; }
      case 'date': { const w = el('div', 'w datew'); dates.push(w); drawDate(w); return w; }
      case 'thermo': return thermo(it.id, it.room);
      case 'np': return nowPlaying(it.id);
      case 'cam': return camera(it.id);
      case 'screen': {
        const w = el('div', 'w tile');
        w.innerHTML = `<div class="ic">${svg(/music/i.test(it.n) ? 'music' : /assistant/i.test(it.n) ? 'home' : 'screen')}</div>`;
        w.append(el('div', 'nm', it.n), el('div', 'st', 'Open'));
        w.onclick = () => window.HassmicKiosk.go(it.i);
        return w;
      }
      default: return tile(it.id, it.room, it.home);
    }
  }

  function tile(id, areaName, onHome) {
    const t = el('div', 'w tile');
    t.innerHTML = '<div class="ic"></div><div class="nm"></div><div class="st"></div>';
    const dm = domain(id);
    t.querySelector('.nm').textContent = onHome ? nameOf(id, roomName(id)) : nameOf(id, areaName);
    if (dm === 'scene' || dm === 'script') {
      t.querySelector('.ic').innerHTML = svg('sparkle');
      t.querySelector('.st').textContent = onHome && roomName(id) ? roomName(id) : dm === 'scene' ? 'Scene' : 'Shortcut';
      t.onclick = () => { call(dm, 'turn_on', id); t.classList.add('on'); setTimeout(() => t.classList.remove('on'), 700); };
      return t;
    }
    press(t, () => tap(id), () => sheet(id, areaName));
    bind(id, () => {
      if (!states[id]) return;
      const r = look(id);
      t.classList.toggle('on', r.on); t.classList.toggle('unavail', !!r.unavail);
      t.style.setProperty('--c', r.c);
      const ic = t.querySelector('.ic'); if (ic.dataset.i !== r.icon) { ic.innerHTML = svg(r.icon); ic.dataset.i = r.icon; }
      // on Home, Apple's way: the name and the room; in a room, its state
      t.querySelector('.st').textContent = onHome && roomName(id) && !r.unavail ? roomName(id) : r.text;
      let lvl = t.querySelector('.lvl');
      if (r.bar != null && r.on) { if (!lvl) { lvl = el('div', 'lvl'); lvl.append(el('b')); t.append(lvl); } lvl.firstChild.style.width = r.bar + '%'; }
      else if (lvl) lvl.remove();
    });
    return t;
  }

  function thermo(id, room) {
    const w = el('div', 'w big thermo');
    w.innerHTML = `<div class="t"></div><div class="lb"></div><div class="sub"></div><button class="dn">${svg('down')}</button><button class="up">${svg('up')}</button>`;
    let want = null, timer;
    const step = () => states[id].a.target_temp_step || (states[id].a.temperature_unit === '°F' ? 1 : 0.5);
    const show = (v) => { const s = String(v).split('.'); w.querySelector('.t').innerHTML = s[0] + (s[1] ? `<small>.${s[1]}</small>` : ''); };
    const nudge = (d) => {
      const st = states[id]; if (!st) return;
      want = Math.round(((want ?? st.a.temperature) + d * step()) / step()) * step();
      want = Math.max(st.a.min_temp ?? -100, Math.min(st.a.max_temp ?? 100, want)); show(want);
      clearTimeout(timer); timer = setTimeout(() => { call('climate', 'set_temperature', id, { temperature: want }); want = null; }, 800);
    };
    w.querySelector('.dn').onclick = (e) => { e.stopPropagation(); nudge(-1); };
    w.querySelector('.up').onclick = (e) => { e.stopPropagation(); nudge(1); };
    press(w, () => sheet(id, room), () => sheet(id, room));
    bind(id, () => {
      const st = states[id]; if (!st || want != null) return;
      show(st.a.temperature ?? '—');
      w.querySelector('.lb').textContent = room ? nameOf(id, room) : (st.a.friendly_name || 'Thermostat');
      const where = room || roomName(id);
      w.querySelector('.sub').textContent = [where, st.a.current_temperature != null ? st.a.current_temperature + '°' : '', st.s === 'off' ? 'Off' : ''].filter(Boolean).join(' • ');
    });
    return w;
  }

  function nowPlaying(id) {
    const w = el('div', 'w big np');
    w.innerHTML = `<div class="ti"></div><div class="ar"></div><div class="ctl"><button class="pv">${svg('prev')}</button><button class="pp"></button><button class="nx">${svg('next')}</button></div>`;
    w.querySelector('.pv').onclick = (e) => { e.stopPropagation(); call('media_player', 'media_previous_track', id); };
    w.querySelector('.pp').onclick = (e) => { e.stopPropagation(); call('media_player', 'media_play_pause', id); };
    w.querySelector('.nx').onclick = (e) => { e.stopPropagation(); call('media_player', 'media_next_track', id); };
    press(w, () => sheet(id, null), () => sheet(id, null));
    let pic = '';
    bind(id, () => {
      const st = states[id]; if (!st) return;
      w.querySelector('.ti').textContent = st.a.media_title || st.a.friendly_name || '';
      w.querySelector('.ar').textContent = st.a.media_artist || st.a.media_album_name || '';
      w.querySelector('.pp').innerHTML = svg(st.s === 'playing' ? 'pause' : 'play');
      if (st.a.entity_picture && st.a.entity_picture !== pic) { pic = st.a.entity_picture; w.style.backgroundImage = `url("${pic.replace(/"/g, '%22')}")`; }
      if (!pic) w.style.background = 'linear-gradient(135deg, #3a3f55, #1c1f2c)';
    });
    return w;
  }

  function camera(id) {
    const w = el('div', 'w cam');
    w.append(el('div', 'lb', nameOf(id, roomName(id))));
    const load = () => { const st = states[id]; if (st && st.a.entity_picture) w.style.backgroundImage = `url("${st.a.entity_picture}&t=${Date.now()}")`; };
    load(); cams.push(load);
    w.onclick = () => { const st = states[id]; if (st) sheetImage(st.a.friendly_name || id, st.a.entity_picture); };
    return w;
  }
  function sheetImage(title, url) {
    closeSheet();
    const veil = el('div', 'veil'), box = el('div', 'sheet'); veil.append(box); document.body.append(veil);
    box.append(el('h3', null, title)); const img = el('img'); img.src = url + '&t=' + Date.now(); img.style.cssText = 'width:100%;border-radius:18px;margin-top:8px';
    box.append(img); veil.onclick = closeSheet; openSheet = { id: '', veil, refresh() {} };
  }

  function update(id) {
    (painters.get(id) || []).forEach((f) => f());
    if (openSheet && openSheet.id === id) openSheet.refresh();
    // music starting or stopping: Home's "now playing" comes and goes
    if (domain(id) === 'media_player') {
      const now = Object.keys(states).find((x) => domain(x) === 'media_player' && states[x].s === 'playing' && states[x].a.media_title) || '';
      if (now !== playing) render();
    }
  }

  // a tap and a long press (500 ms) on one element; a swipe (paging) is neither
  function press(e, onTap, onHold) {
    let timer, x, y, held, moved;
    e.addEventListener('pointerdown', (ev) => { if (editing) return; x = ev.clientX; y = ev.clientY; held = moved = false; timer = setTimeout(() => { held = true; onHold(); }, 500); });
    e.addEventListener('pointermove', (ev) => { if (Math.abs(ev.clientX - x) + Math.abs(ev.clientY - y) > 12) { moved = true; clearTimeout(timer); } });
    e.addEventListener('pointerup', () => { clearTimeout(timer); if (!held && !moved && !editing) onTap(); });
    e.addEventListener('pointercancel', () => { moved = true; clearTimeout(timer); });
    e.addEventListener('contextmenu', (ev) => ev.preventDefault());
  }

  function tap(id) {
    const dm = domain(id), st = states[id];
    if (!st || st.s === 'unavailable') return;
    switch (dm) {
      case 'light': case 'switch': case 'fan': case 'input_boolean': case 'humidifier': call(dm, 'toggle', id); break;
      case 'cover': call(dm, st.s === 'open' || st.s === 'opening' ? 'close_cover' : 'open_cover', id); break;
      case 'media_player': call(dm, 'media_play_pause', id); break;
      case 'vacuum': call(dm, st.s === 'cleaning' ? 'return_to_base' : 'start', id); break;
      default: sheet(id, null);       // climate, lock (no lock opens by a stray tap), sensors
    }
  }

  // ---------------------------------------------------------------- the sheet: a device's controls
  let openSheet = null;
  function sheet(id, areaName) {
    closeSheet();
    const veil = el('div', 'veil'), box = el('div', 'sheet');
    veil.append(box); document.body.append(veil);
    veil.addEventListener('click', (ev) => { if (ev.target === veil) closeSheet(); });
    const dm = domain(id);
    const head = () => { box.textContent = ''; const st = states[id]; box.append(el('h3', null, nameOf(id, areaName))); box.append(el('div', 'sub', look(id).text)); return st; };
    const refresh = () => {
      const st = head(); if (!st) return;
      const row = el('div', 'row'); box.append(row);
      const btn = (label, f, primary) => { const b = el('button', 'btn' + (primary ? ' primary' : '')); b.innerHTML = label; b.onclick = f; return b; };
      if (dm === 'light' || (dm === 'cover' && st.a.current_position != null) || (dm === 'fan' && st.a.percentage != null) || dm === 'media_player') {
        const val = dm === 'light' ? (st.s === 'on' ? Math.round((st.a.brightness || 255) / 2.55) : 0)
          : dm === 'cover' ? st.a.current_position : dm === 'fan' ? (st.s === 'on' ? st.a.percentage : 0) : Math.round((st.a.volume_level || 0) * 100);
        row.append(slider(val, look(id).c, (v) => {
          if (dm === 'light') v ? call('light', 'turn_on', id, { brightness_pct: v }) : call('light', 'turn_off', id);
          else if (dm === 'cover') call('cover', 'set_cover_position', id, { position: v });
          else if (dm === 'fan') v ? call('fan', 'set_percentage', id, { percentage: v }) : call('fan', 'turn_off', id);
          else call('media_player', 'volume_set', id, { volume_level: v / 100 });
        }));
      }
      const col = el('div', 'btns'); row.append(col);
      if (dm === 'light' || dm === 'switch' || dm === 'fan' || dm === 'input_boolean' || dm === 'humidifier')
        col.append(btn(st.s === 'on' ? 'Turn off' : 'Turn on', () => call(dm, 'toggle', id), st.s !== 'on'));
      if (dm === 'cover') { col.append(btn('Open', () => call(dm, 'open_cover', id))); col.append(btn('Stop', () => call(dm, 'stop_cover', id))); col.append(btn('Close', () => call(dm, 'close_cover', id))); }
      if (dm === 'media_player') {
        const r = el('div', 'row');
        r.append(btn(svg('prev'), () => call(dm, 'media_previous_track', id)), btn(svg(st.s === 'playing' ? 'pause' : 'play'), () => call(dm, 'media_play_pause', id), true), btn(svg('next'), () => call(dm, 'media_next_track', id)));
        col.append(r);
      }
      if (dm === 'lock') col.append(btn(st.s === 'locked' ? 'Unlock' : 'Lock', () => call(dm, st.s === 'locked' ? 'unlock' : 'lock', id), true));
      if (dm === 'climate') {
        const t = st.a.temperature, step = st.a.target_temp_step || (st.a.temperature_unit === '°F' ? 1 : 0.5);
        if (t != null) {
          const r = el('div', 'row'), dn = el('button', 'round', '−'), up = el('button', 'round', '+'), v = el('div', 'temp', t + '°');
          let want = t, timer;
          const set = (d) => { want = Math.round((want + d) / step) * step; v.textContent = want + '°'; clearTimeout(timer); timer = setTimeout(() => call('climate', 'set_temperature', id, { temperature: want }), 700); };
          dn.onclick = () => set(-step); up.onclick = () => set(step);
          r.append(dn, v, up); col.append(r);
        }
        const modes = st.a.hvac_modes || [];
        if (modes.length) { const r = el('div', 'row'); for (const md of modes.slice(0, 4)) r.append(btn(md, () => call('climate', 'set_hvac_mode', id, { hvac_mode: md }), md === st.s)); col.append(r); }
      }
      col.append(btn('Done', closeSheet));
    };
    openSheet = { id, veil, refresh };
    refresh();
  }
  function closeSheet() { if (openSheet) { openSheet.veil.remove(); openSheet = null; } }

  // Apple's tall pill slider: drag anywhere on it, sent once let go
  function slider(val, color, onSet) {
    const p = el('div', 'pill'), f = el('div', 'fill'), v = el('div', 'val');
    p.style.setProperty('--c', color && color.startsWith('rgb') ? color : '#f6f5f1');
    p.append(f, v);
    let cur = val || 0;
    const show = () => { f.style.height = cur + '%'; v.textContent = cur + '%'; };
    const at = (ev) => { const r = p.getBoundingClientRect(); cur = Math.max(0, Math.min(100, Math.round((r.bottom - ev.clientY) / r.height * 100))); show(); };
    p.addEventListener('pointerdown', (ev) => { p.setPointerCapture(ev.pointerId); at(ev); });
    p.addEventListener('pointermove', (ev) => { if (p.hasPointerCapture(ev.pointerId)) at(ev); });
    p.addEventListener('pointerup', () => onSet(cur));
    show();
    return p;
  }

  // ---------------------------------------------------------------- the clock, the date and weather, the ambient clock
  const clocks = [], dates = [], cams = [];
  function drawClock(w) {
    const d = new Date(), h = d.getHours() % 12 + d.getMinutes() / 60, mi = d.getMinutes();
    let ticks = '';
    for (let i = 0; i < 12; i++) { const a = i * Math.PI / 6, r1 = i % 3 ? 40 : 37; ticks += `<line x1="${50 + r1 * Math.sin(a)}" y1="${50 - r1 * Math.cos(a)}" x2="${50 + 44 * Math.sin(a)}" y2="${50 - 44 * Math.cos(a)}" stroke="currentColor" stroke-width="${i % 3 ? 1.6 : 2.6}" stroke-linecap="round" opacity=".85"/>`; }
    const hand = (deg, len, wd) => `<line x1="50" y1="50" x2="${50 + len * Math.sin(deg * Math.PI / 180)}" y2="${50 - len * Math.cos(deg * Math.PI / 180)}" stroke="currentColor" stroke-width="${wd}" stroke-linecap="round"/>`;
    w.innerHTML = `<svg viewBox="0 0 100 100">${ticks}${hand(h * 30, 24, 4)}${hand(mi * 6, 35, 2.6)}<circle cx="50" cy="50" r="2.6" fill="currentColor"/></svg>`;
  }
  const WICON = { sunny: 'sun', 'clear-night': 'moon', cloudy: 'cloud', partlycloudy: 'cloud', rainy: 'rain', pouring: 'rain', lightning: 'rain', 'lightning-rainy': 'rain', snowy: 'cloud', fog: 'cloud', windy: 'cloud' };
  function wx() {
    const want = params.get('weather') || layout.weather || '';
    if (want === 'none') return null;
    const id = want || Object.keys(states).find((x) => domain(x) === 'weather');
    return id && states[id];
  }
  function drawDate(w) {
    const d = new Date(), st = wx();
    w.innerHTML = '';
    // Apple's order whatever the locale's: "Wed Apr", then the day
    w.append(el('div', 'day', d.toLocaleDateString([], { weekday: 'short' }) + ' ' + d.toLocaleDateString([], { month: 'short' })), el('div', 'num', String(d.getDate())));
    if (st) {
      const r = el('div', 'wx'); r.innerHTML = svg(WICON[st.s] || 'cloud');
      r.append(el('span', null, st.a.temperature != null ? Math.round(st.a.temperature) + '°' : '')); w.append(r);
      w.append(el('div', 'cond', (st.s || '').replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase())));
    }
  }
  function tick() {
    clocks.splice(0, clocks.length, ...clocks.filter((w) => w.isConnected)); clocks.forEach(drawClock);
    dates.splice(0, dates.length, ...dates.filter((w) => w.isConnected)); dates.forEach(drawDate);
    if ($('ambient').classList.contains('show')) ambientDraw();
  }

  // left alone, the ambient clock (?ambient=<s>, 0 never; 120 s by default); a touch brings the widgets back
  const ambientS = () => params.has('ambient') ? +params.get('ambient') : layout.ambient ?? 120;
  let lastTouch = Date.now();
  function ambientDraw() {
    const d = new Date(), st = wx();
    let h = d.getHours(); const h12 = new Intl.DateTimeFormat([], { hour: 'numeric' }).resolvedOptions().hour12;
    if (h12) h = h % 12 || 12;
    $('adigits').textContent = `${h}:${String(d.getMinutes()).padStart(2, '0')}`;
    $('aunder').textContent = d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }) + (st && st.a.temperature != null ? ` · ${Math.round(st.a.temperature)}°` : '');
  }
  document.addEventListener('pointerdown', () => {
    lastTouch = Date.now();
    if ($('ambient').classList.contains('show')) { $('ambient').classList.remove('show'); $('pages').scrollLeft = 0; pageIndex = 0; dots(); }
  }, true);
  setInterval(() => {
    if (ambientS() > 0 && built && !openSheet && !editing && Date.now() - lastTouch > ambientS() * 1000 && !$('ambient').classList.contains('show')) {
      ambientDraw(); $('ambient').classList.add('show');
    }
  }, 5000);

  $('pages').addEventListener('scroll', debounce(() => { const i = Math.round($('pages').scrollLeft / innerWidth); if (i !== pageIndex) { pageIndex = i; dots(); } }, 80));
  addEventListener('resize', debounce(() => built && render(), 300));
  // ---------------------------------------------------------------- the layout and its edit mode
  const ECHO = params.get('echo') || '';
  let layout = {}, local = false, editing = false;
  const hidden = () => new Set(layout.hidden || []);
  // Home's ids: the layout's favourites, else what the panel picks (the URL's ?favorites= first)
  function favorites() {
    const ok = (x) => states[x] && !hidden().has(x);
    if (params.get('favorites')) return params.get('favorites').split(',').filter(ok);
    if (Array.isArray(layout.favorites)) return layout.favorites.filter(ok);
    const out = [];
    const climate = params.get('thermostat') || Object.keys(states).find((x) => domain(x) === 'climate' && states[x].a.temperature != null && shown(x));
    if (climate && states[climate]) out.push(climate);
    const cam = params.get('camera') || Object.keys(states).find((x) => domain(x) === 'camera' && states[x].s !== 'unavailable' && !hidden().has(x));
    if (cam && states[cam]) out.push(cam);
    out.push(...Object.keys(states).filter((x) => domain(x) === 'scene' && shown(x)).slice(0, 3));
    out.push(...Object.keys(states).filter((x) => domain(x) === 'lock' && shown(x)));
    return out;
  }
  function applyLayout() {
    const t = params.get('theme') || layout.theme;
    if (['dusk', 'light', 'amber'].includes(t)) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
    if (built) render();
    if (editing) editBar();
  }
  let saveTimer;
  function save(patch) {
    layout = Object.assign({}, layout, patch);
    applyLayout();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      if (local) { try { localStorage.setItem('hassmicWall', JSON.stringify(layout)); } catch (e) { /* private window */ } return; }
      send({ type: 'hassmic/wall/set', echo: ECHO, layout }).catch((e) => toast('Not saved: ' + (e && e.message || e)));
    }, 500);
  }
  function toast(t) {
    const d = el('div', 'toast', t); document.body.append(d); setTimeout(() => d.remove(), 3500);
  }

  // hold the page dots: edit
  (() => {
    let timer;
    $('dots').addEventListener('pointerdown', () => { timer = setTimeout(() => edit(true), 700); });
    for (const e of ['pointerup', 'pointercancel', 'pointerleave']) $('dots').addEventListener(e, () => clearTimeout(timer));
  })();
  function edit(on) {
    editing = on;
    document.body.classList.toggle('editing', on);
    const b = $('editbar'); if (b) b.remove();
    if (on) editBar();
    closeSheet();
    render();
  }
  window.hassmicWallEdit = edit;              // tests
  // nothing of a widget's own while editing: its buttons, a scene's run
  document.addEventListener('click', (ev) => {
    if (editing && !ev.target.closest('.badge, #editbar, .sheet, #dots')) { ev.stopPropagation(); ev.preventDefault(); }
  }, true);

  function editBar() {
    let b = $('editbar'); if (b) b.remove();
    b = el('div'); b.id = 'editbar';
    const cur = params.get('theme') || layout.theme || 'amber';
    for (const t of ['amber', 'dusk', 'light']) {
      const s = el('button', 'swatch ' + t + (t === cur ? ' sel' : '')); s.title = t; s.onclick = () => save({ theme: t }); b.append(s);
    }
    const n = (layout.hidden || []).length;
    const h = el('button', 'eb', n ? `Hidden (${n})` : 'Hidden'); h.onclick = hiddenSheet; b.append(h);
    const r = el('button', 'eb', 'Reset'); r.onclick = () => save({ favorites: null, order: {}, hidden: [] }); b.append(r);
    const d = el('button', 'eb done', 'Done'); d.onclick = () => edit(false); b.append(d);
    if (local) b.append(el('span', 'note', 'this browser only'));
    document.body.append(b);
  }

  function hiddenSheet() {
    closeSheet();
    const veil = el('div', 'veil'), box = el('div', 'sheet'); veil.append(box); document.body.append(veil);
    veil.addEventListener('click', (ev) => { if (ev.target === veil) closeSheet(); });
    box.append(el('h3', null, 'Hidden'), el('div', 'sub', 'Shown nowhere on the wall panel. Tap to show again.'));
    const list = layout.hidden || [];
    if (!list.length) box.append(el('div', 'sub', 'Nothing hidden: tap ⊖ on a tile to hide it.'));
    for (const id of list) {
      const b = el('button', 'btn', (states[id] && states[id].a.friendly_name) || id);
      b.style.cssText = 'display:block;width:100%;margin:6px 0;text-align:left';
      b.onclick = () => { save({ hidden: list.filter((x) => x !== id) }); hiddenSheet(); };
      box.append(b);
    }
    const d = el('button', 'btn primary', 'Done'); d.onclick = closeSheet; d.style.marginTop = '10px'; box.append(d);
    openSheet = { id: '', veil, refresh() {} };
  }

  // a widget's badges: ★ on Home or off it, ⊖ hidden (on Home: off Home); a drag moves it
  function badges(w, page) {
    const id = w.dataset.id; if (!id) return;
    const onHome = page.name === 'Home';
    const fav = favorites();
    const star = el('button', 'badge fav' + (fav.includes(id) ? '' : ' off'), '★');
    star.onclick = () => save({ favorites: fav.includes(id) ? fav.filter((x) => x !== id) : [...fav, id] });
    const minus = el('button', 'badge hide', '−');
    minus.onclick = () => onHome ? save({ favorites: fav.filter((x) => x !== id) }) : save({ hidden: [...(layout.hidden || []), id], favorites: Array.isArray(layout.favorites) ? fav.filter((x) => x !== id) : layout.favorites });
    if (!onHome) w.append(star);
    w.append(minus);
    drag(w, page);
  }

  // the drag follows the pointer on the window: moving the tile in the grid (insertBefore) takes its pointer capture away
  function drag(w, page) {
    w.addEventListener('pointerdown', (ev) => {
      if (!editing || ev.target.closest('.badge')) return;
      let sx = ev.clientX, sy = ev.clientY, on = false;
      const pid = ev.pointerId;
      const move = (e) => {
        if (e.pointerId !== pid) return;
        const dx = e.clientX - sx, dy = e.clientY - sy;
        if (!on && Math.abs(dx) + Math.abs(dy) < 8) return;
        if (!on) { on = true; w.classList.add('dragging'); $('pages').style.overflowX = 'hidden'; }
        w.style.transform = `translate(${dx}px, ${dy}px) scale(1.05)`;
        const under = document.elementFromPoint(e.clientX, e.clientY);
        const t = under && under.closest('.w[data-id]');
        if (t && t !== w && t.parentNode === w.parentNode) {
          const kids = [...w.parentNode.children], a = kids.indexOf(w), b = kids.indexOf(t);
          const r0 = w.getBoundingClientRect();
          t.parentNode.insertBefore(w, a < b ? t.nextSibling : t);
          const r1 = w.getBoundingClientRect();                // the grid moved it: under the finger it stays
          sx += r1.left - r0.left; sy += r1.top - r0.top;
          w.style.transform = `translate(${e.clientX - sx}px, ${e.clientY - sy}px) scale(1.05)`;
        }
      };
      const end = (e) => {
        if (e.pointerId !== pid) return;
        removeEventListener('pointermove', move); removeEventListener('pointerup', end); removeEventListener('pointercancel', end);
        if (!on) return;
        w.classList.remove('dragging'); w.style.transform = ''; $('pages').style.overflowX = '';
        const ids = [...w.parentNode.querySelectorAll('.w[data-id]')].map((x) => x.dataset.id);
        if (page.name === 'Home') save({ favorites: ids.concat(favorites().filter((x) => !ids.includes(x))) });
        else save({ order: Object.assign({}, layout.order, { [page.area]: ids }) });
      };
      addEventListener('pointermove', move); addEventListener('pointerup', end); addEventListener('pointercancel', end);
    });
  }

  setInterval(tick, 10000);
  setInterval(() => { cams.splice(0, cams.length, ...cams.filter(() => true)); cams.forEach((f) => f()); }, 10000);
  connect();
})();
