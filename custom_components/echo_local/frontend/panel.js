// Echo Local's sidebar panel (/echo-local, registered in __init__.py; docs/home-screens.md has the design): every Echo
// Show's screen and the Home of each app that draws one, edited graphically.
//
//   - left: the Echos (config entries of echo_local)
//   - "Home screen": the apps that have a Home on that Echo (Echo-Wall always; the screen app the Echo runs; any app
//     that saved one), a form drawn from the app's descriptor (home.py BUILTIN, or the app's own from
//     echo_local/home/describe), beside a preview: Echo-Wall's own WallView built for the web (frontend/echowall/,
//     its lib/preview.dart) in an iframe, whose edit mode (drag, star, hide) edits the draft here; an app without a
//     preview page gets a sketch of its Home's tiles
//   - Export (a .echohome.json file), Import (a file, another app on this Echo, the same app on another Echo), Copy to
//     other Echos, Reset (the slot gone: the app's own defaults)
//   - "Screen": the kiosk's options (kiosk.py), which the options flow also sets
//
// Only Home Assistant's websocket (this.hass.connection), as the rest of Home Assistant's own panels.  Nothing of the
// layout is saved until Save: a draft per Echo and app, and the Echo's own changes meanwhile are offered, not forced.
// Plain custom element, no build step (the integration's frontend files are served as they are).
'use strict';

const FORMAT = 'echo-local-home';
// the screen app's window in Flutter's logical pixels (the Show 5: 960 x 480 at density 160, the light band's rows off)
const SIZES = { 'Echo Show 5': [960, 470], 'Echo Show 8': [1280, 790], 'Echo Show': [1024, 590] };
const ECHOWALL = 'io.github.nt_f.echowall';
const KIND_LABEL = { wall: 'Home (Echo-Wall draws it)', clock: 'Clock', dashboard: "Home Assistant's own UI", music: 'Music Assistant', custom: 'A page of your own' };
const KIND_NAME = { dashboard: 'Home Assistant', music: 'Music' };           // kiosk.py's names for the switcher
const KNOWN_APPS = [[ECHOWALL, 'Echo-Wall'], ['io.github.nt_f.echoscreen', 'Echo-Screen'], ['', "hassmic's kiosk (web pages only, no Home)"]];

const h = (tag, props, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'style') e.style.cssText = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k in e && typeof v !== 'string') e[k] = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
};
const clone = (x) => JSON.parse(JSON.stringify(x == null ? {} : x));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const ago = (t) => {
  if (!t) return '';
  const s = Math.round(Date.now() / 1000 - t);
  return s < 60 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : new Date(t * 1000).toLocaleDateString();
};
const domainOf = (id) => String(id).split('.')[0];

const CSS = `
:host { display: block; height: 100%; background: var(--primary-background-color); color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, Roboto, sans-serif); --r: var(--ha-card-border-radius, 12px);
  --line: var(--divider-color, rgba(127,127,127,.25)); --soft: var(--secondary-background-color, rgba(127,127,127,.08));
  --accent: var(--primary-color, #03a9f4); --muted: var(--secondary-text-color, #888); }
* { box-sizing: border-box; }
header { height: var(--header-height, 56px); display: flex; align-items: center; gap: 8px; padding: 0 12px;
  background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff);
  border-bottom: var(--app-header-border-bottom, none); position: sticky; top: 0; z-index: 3; }
header h1 { font-size: 20px; font-weight: 400; margin: 0 0 0 4px; flex: 1; }
header .menu { display: none; }
:host([narrow]) header .menu { display: inline-flex; }
.iconbtn { background: none; border: 0; color: inherit; width: 40px; height: 40px; border-radius: 50%; cursor: pointer; font-size: 22px; }
.iconbtn:hover { background: rgba(127,127,127,.15); }
.wrap { display: grid; grid-template-columns: 260px 1fr; min-height: calc(100% - var(--header-height, 56px)); }
:host([narrow]) .wrap { grid-template-columns: 1fr; }
nav { border-right: 1px solid var(--line); padding: 12px 8px; background: var(--card-background-color); }
:host([narrow]) nav { border-right: 0; border-bottom: 1px solid var(--line); display: flex; overflow-x: auto; gap: 6px; padding: 8px; }
nav .lbl { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 6px 10px 8px; }
:host([narrow]) nav .lbl { display: none; }
.echo { display: flex; gap: 10px; align-items: center; width: 100%; text-align: left; padding: 10px; border-radius: 10px; border: 0;
  background: none; color: inherit; cursor: pointer; font: inherit; }
:host([narrow]) .echo { width: auto; flex: none; border: 1px solid var(--line); }
.echo:hover { background: var(--soft); }
.echo.sel { background: color-mix(in srgb, var(--accent) 16%, transparent); }
.echo .dev { width: 36px; height: 24px; border-radius: 5px; border: 2px solid currentColor; opacity: .7; flex: none; position: relative; }
.echo .dev.on::after { content: ''; position: absolute; inset: 3px; border-radius: 2px; background: var(--accent); opacity: .7; }
.echo .t { font-weight: 500; } .echo .s { font-size: 12px; color: var(--muted); }
main { padding: 16px 20px 40px; min-width: 0; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); margin-bottom: 16px; }
.tab { background: none; border: 0; border-bottom: 2px solid transparent; padding: 10px 14px; font: inherit; color: var(--muted); cursor: pointer; }
.tab.sel { color: var(--accent); border-bottom-color: var(--accent); }
.apps { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.chip { border: 1px solid var(--line); background: var(--card-background-color); color: inherit; border-radius: 18px; padding: 6px 14px;
  font: inherit; font-size: 14px; cursor: pointer; display: inline-flex; gap: 6px; align-items: center; }
.chip.sel { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent); }
.chip .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success-color, #4caf50); }
.chip .dot.none { background: var(--line); }
.bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
.bar .grow { flex: 1; }
.status { font-size: 13px; color: var(--muted); }
.status.dirty { color: var(--warning-color, #ff9800); }
.btn { border: 1px solid var(--line); background: var(--card-background-color); color: inherit; border-radius: 8px; padding: 8px 14px;
  font: inherit; font-size: 14px; cursor: pointer; }
.btn:hover:not(:disabled) { background: var(--soft); }
.btn:disabled { opacity: .45; cursor: default; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--text-primary-color, #fff); }
.btn.danger { color: var(--error-color, #db4437); }
.btn.small { padding: 4px 10px; font-size: 13px; }
.grid { display: grid; grid-template-columns: minmax(320px, 1fr) minmax(320px, 1.25fr); gap: 16px; align-items: start; }
@media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }
.card { background: var(--card-background-color); border-radius: var(--r); border: 1px solid var(--line); padding: 4px 16px 12px;
  box-shadow: var(--ha-card-box-shadow, none); }
.card h2 { font-size: 16px; font-weight: 500; margin: 14px 0 4px; }
.card .about { font-size: 13px; color: var(--muted); margin-bottom: 6px; }
.row { padding: 12px 0; border-top: 1px solid var(--line); }
.row:first-of-type { border-top: 0; }
.row .head { display: flex; align-items: center; gap: 10px; }
.row .name { flex: 1; font-size: 15px; }
.row .help { font-size: 12px; color: var(--muted); margin-top: 3px; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.seg button { border: 0; background: none; color: inherit; padding: 6px 12px; font: inherit; font-size: 13px; cursor: pointer; }
.seg button + button { border-left: 1px solid var(--line); }
.seg button.sel { background: var(--accent); color: var(--text-primary-color, #fff); }
input[type=text], input[type=number], input[type=url], select, textarea { font: inherit; font-size: 14px; color: inherit;
  background: var(--soft); border: 1px solid var(--line); border-radius: 8px; padding: 7px 10px; }
input[type=number] { width: 110px; }
textarea { width: 100%; min-height: 90px; font-family: var(--code-font-family, monospace); font-size: 13px; }
.switch { position: relative; width: 40px; height: 22px; flex: none; }
.switch input { opacity: 0; width: 0; height: 0; }
.switch span { position: absolute; inset: 0; border-radius: 11px; background: var(--line); cursor: pointer; transition: .15s; }
.switch span::after { content: ''; position: absolute; width: 16px; height: 16px; left: 3px; top: 3px; border-radius: 50%; background: #fff; transition: .15s; }
.switch input:checked + span { background: var(--accent); }
.switch input:checked + span::after { transform: translateX(18px); }
.list { margin-top: 8px; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: var(--card-background-color); border-top: 1px solid var(--line); }
.item:first-child { border-top: 0; }
.item.drag { opacity: .4; }
.item.over { box-shadow: inset 0 2px 0 var(--accent); }
.item .grip { cursor: grab; color: var(--muted); user-select: none; padding: 0 4px; }
.item .nm { flex: 1; min-width: 0; }
.item.page.off .nm { opacity: .55; }
.pagename { font: inherit; border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; background: transparent; color: inherit; width: 100%; box-sizing: border-box; }
.addpage { display: flex; gap: 8px; margin-top: 8px; }
.addpage .pagename { flex: 1; }
.appicon { width: 36px; height: 36px; border-radius: 9px; flex: none; }
.appicon.none { background: var(--secondary-background-color, #e6e6e6); }
.item .nm div { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item .id { font-size: 12px; color: var(--muted); }
.item.unknown .nm div:first-child { color: var(--warning-color, #ff9800); }
.mini { background: none; border: 0; color: var(--muted); cursor: pointer; font-size: 16px; width: 28px; height: 28px; border-radius: 6px; }
.mini:hover { background: var(--soft); color: inherit; }
.mini:disabled { opacity: .3; }
.add { display: flex; gap: 6px; margin-top: 8px; }
.add input { flex: 1; }
.empty { padding: 10px; font-size: 13px; color: var(--muted); }
details.room { border: 1px solid var(--line); border-radius: 10px; margin-top: 8px; }
details.room summary { padding: 8px 12px; cursor: pointer; display: flex; gap: 8px; align-items: center; }
details.room summary .n { flex: 1; } details.room .list { margin: 0 8px 8px; }
.preview { position: sticky; top: calc(var(--header-height, 56px) + 12px); }
.screen { position: relative; border-radius: 14px; background: #111; padding: 10px; box-shadow: 0 6px 24px rgba(0,0,0,.25); }
.screen .vp { position: relative; overflow: hidden; border-radius: 4px; background: #000; }
.screen iframe { border: 0; transform-origin: 0 0; position: absolute; left: 0; top: 0; }
.screen .band { height: 4px; margin: 6px 30% 0; border-radius: 2px; background: color-mix(in srgb, var(--accent) 60%, #000); opacity: .6; }
.sketch { position: absolute; inset: 0; padding: 4%; display: grid; grid-template-columns: repeat(4, 1fr); grid-auto-rows: 22%; gap: 3%;
  background: linear-gradient(135deg, #3a2a1a, #120d08); }
.sketch.dusk { background: linear-gradient(135deg, #2a2848, #0b0a18); } .sketch.light { background: linear-gradient(135deg, #f2eee8, #cfc8bd); }
.sketch.photo { background: linear-gradient(135deg, #4a6a7a, #1b2a33 60%, #2f3a24); }
.sketch .w { border-radius: 12px; background: rgba(255,255,255,.14); backdrop-filter: blur(4px); color: #fff; font-size: 11px; padding: 8px;
  overflow: hidden; display: flex; flex-direction: column; justify-content: flex-end; }
.sketch.light .w { background: rgba(255,255,255,.6); color: #222; }
.sketch .w.big { grid-column: span 2; grid-row: span 2; font-size: 14px; }
.sketch .w .k { opacity: .7; font-size: 10px; }
.pbar { display: flex; gap: 8px; align-items: center; margin-top: 10px; flex-wrap: wrap; }
.note { font-size: 12px; color: var(--muted); }
.banner { border: 1px solid var(--warning-color, #ff9800); background: color-mix(in srgb, var(--warning-color, #ff9800) 12%, transparent);
  border-radius: 10px; padding: 10px 12px; display: flex; gap: 10px; align-items: center; margin-bottom: 12px; font-size: 14px; }
.banner .grow { flex: 1; }
.menuwrap { position: relative; display: inline-block; }
.pop { position: absolute; top: calc(100% + 4px); left: 0; z-index: 5; min-width: 260px; background: var(--card-background-color);
  border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,.2); padding: 6px; }
.pop button { display: block; width: 100%; text-align: left; border: 0; background: none; color: inherit; font: inherit; font-size: 14px;
  padding: 8px 10px; border-radius: 6px; cursor: pointer; }
.pop button:hover { background: var(--soft); }
.pop .sep { height: 1px; background: var(--line); margin: 4px 0; }
.pop .h { font-size: 12px; color: var(--muted); padding: 6px 10px 2px; }
.toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: var(--primary-text-color); color: var(--card-background-color, #fff);
  padding: 10px 16px; border-radius: 8px; z-index: 10; font-size: 14px; max-width: 90vw; }
.screens .item .nm { display: flex; align-items: center; gap: 8px; }
.kv { display: grid; grid-template-columns: 1fr; gap: 6px; margin-top: 8px; }
.kv input { width: 100%; }
.pushst { font-size: 13px; padding: 10px 12px; border-radius: 10px; margin-bottom: 12px; display: flex; gap: 10px; align-items: center;
  background: var(--soft); }
.pushst.bad { background: color-mix(in srgb, var(--error-color, #db4437) 12%, transparent); color: var(--error-color, #db4437); }
.pushst .grow { flex: 1; }
.app .nm div:first-child { font-family: var(--code-font-family, monospace); font-size: 14px; }
.prog { height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; margin-top: 8px; }
.prog > div { height: 100%; background: var(--accent); transition: width .2s; }
.inst { margin-top: 10px; font-size: 14px; }
.inst.bad { color: var(--error-color, #db4437); }
.inst.good { color: var(--success-color, #4caf50); }
`;

class EchoLocalPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.state = { echos: [], descriptors: {}, loaded: false, error: '' };
    this.echo = null;                 // the Echo's node
    this.app = ECHOWALL;
    this.tab = 'home';
    this.drafts = new Map();          // "echo|app" -> { saved, draft, incoming, sub }
    this.kiosk = null;                // { saved, draft } of the selected Echo
    this.size = null;
    this.editOnScreen = false;
    this.launcher = {};               // echo -> its Android apps as Echo-Wall lists them (echo_local/home/apps/get)
    // the preview (Echo-Wall's lib/preview.dart) asks the login, the draft and what the Echo's app would know from here
    window.echoLocalPreview = {
      token: async () => { const a = this._hass.auth; if (a.expired) await a.refreshAccessToken(); return a.accessToken; },
      layout: () => (this.cur() || {}).draft,
      info: () => this.previewInfo(),
    };
    this.pages = null;                // the pages after Home, as Echo-Wall's preview last made them (echo-local-pages)
    this.onMessage = (ev) => {
      if (ev.origin !== location.origin || !ev.data) return;
      if (ev.data.type === 'echo-local-pages') {
        if (JSON.stringify(ev.data.pages) === JSON.stringify(this.pages)) return;
        this.pages = ev.data.pages;
        const r = this.shadowRoot.querySelector('.pagesrow'); const c = this.cur();
        if (r && c) r.replaceWith(this.pagesRow(c));
        return;
      }
      if (ev.data.type !== 'echo-local-edit') return;
      const c = this.cur(); if (!c) return;
      c.draft = clone(ev.data.layout); this.refresh();      // not sent back: the preview has it
    };
  }

  // what the screen app gets beside the layout: the clock's format, the other screens' names (their tiles on Home)
  previewInfo() {
    const loc = this._hass.locale || {};
    const h24 = loc.time_format === '24' ? true : loc.time_format === '12' ? false
      : new Intl.DateTimeFormat(loc.language || undefined, { hour: 'numeric' }).resolvedOptions().hour12 === false;
    const info = this.echoInfo() || {};
    const screens = (info.screens || []).filter((k) => KIND_NAME[k]).map((k) => KIND_NAME[k]);
    return { h24, screens, settings: {}, editing: this.editOnScreen, gallery: this.gallery, apps: this.launcher[this.echo] || [] };
  }

  set hass(h) { const first = !this._hass; this._hass = h; if (first) this.load(); }
  get hass() { return this._hass; }
  set narrow(n) { this.toggleAttribute('narrow', !!n); }

  connectedCallback() { addEventListener('message', this.onMessage); this.render(); }
  disconnectedCallback() {
    removeEventListener('message', this.onMessage);
    for (const d of this.drafts.values()) if (d.sub) d.sub.then((u) => u()).catch(() => {});
    this.drafts.clear();
  }

  ws(msg) { return this._hass.connection.sendMessagePromise(msg); }
  key(echo = this.echo, app = this.app) { return echo + '|' + app; }
  cur() { return this.drafts.get(this.key()); }
  // built in, else the one the app sent from this Echo, else an administrator's (home.py descriptor())
  desc(app = this.app, echo = this.echo) {
    const own = (this.echoInfo(echo) || {}).descriptors || {};
    return ((this.state.builtin || []).includes(app) ? null : own[app]) || this.state.descriptors[app] || null;
  }
  echoInfo(node = this.echo) { return this.state.echos.find((e) => e.echo === node); }
  toast(t) { const d = h('div', { class: 'toast' }, t); this.shadowRoot.append(d); setTimeout(() => d.remove(), 3500); }

  async load() {
    try {
      const r = await this.ws({ type: 'echo_local/home/list' });
      this.state = { echos: r.echos, descriptors: r.descriptors, builtin: r.builtin, limits: r.limits, loaded: true, error: '' };
      if (!this.echo) this.echo = (r.echos[0] || {}).echo || null;
    } catch (e) {
      this.state = { ...this.state, loaded: true, error: (e && e.message) || String(e) };
    }
    this.render();
    if (this.echo) this.select(this.echo, this.app);
  }

  // the apps with a Home on an Echo: Echo-Wall, the screen app it runs, those with a slot
  appsOf(node) {
    const info = this.echoInfo(node);
    const slots = info ? info.slots : {};
    const out = [ECHOWALL];
    if (info && info.app && !out.includes(info.app)) out.push(info.app);
    for (const a of Object.keys(slots || {})) if (!out.includes(a)) out.push(a);
    return out.map((a) => ({ app: a, desc: this.desc(a), slot: (slots || {})[a] }));
  }

  async select(node, app) {
    this.echo = node;
    const apps = this.appsOf(node).map((x) => x.app);
    const running = (this.echoInfo(node) || {}).app;
    this.app = apps.includes(app) ? app : running && this.desc(running) ? running : ECHOWALL;
    const info = this.echoInfo(node);
    this.size = SIZES[Object.keys(SIZES).find((k) => info && info.title.startsWith(k)) || 'Echo Show 5'];
    this.kiosk = null;
    this.pages = null;                      // the new preview tells its own
    await this.open(node, this.app);
    if (info && this.tab === 'screen') this.loadKiosk();
    this.apps = null;
    if (info) this.loadApps();              // whether it has apps at all (an Echo Dot has none): the tab follows
    this.loadLauncher(node);
    this.render();
  }

  // a slot followed live: the saved layout from Home Assistant, a draft of our own
  async open(node, app) {
    const k = this.key(node, app);
    if (this.drafts.has(k)) return;
    const d = { saved: null, draft: null, incoming: null, sub: null };
    this.drafts.set(k, d);
    await new Promise((res) => {
      d.sub = this._hass.connection.subscribeMessage((ev) => {
        const lay = ev.layout || {};
        if (d.saved == null || same(d.saved, d.draft)) { d.saved = clone(lay); d.draft = clone(lay); d.incoming = null; }
        else if (!same(lay, d.saved)) d.incoming = clone(lay);   // the Echo changed it while we edit: offered
        res();
        if (this.key() === k) { this.refresh(); this.pushPreview(); }
      }, { type: 'echo_local/home/subscribe', echo: node, app });
      d.sub.catch((e) => { d.saved = {}; d.draft = {}; this.toast('Not readable: ' + ((e && e.message) || e)); res(); });
    });
  }

  dirty(c = this.cur()) { return !!c && c.saved != null && !same(c.saved, c.draft); }

  // a field changed: the toolbar and the preview follow; the form is left as it is (focus stays where it is)
  changed(rebuild) {
    if (rebuild) this.refresh(); else this.renderBar();
    this.pushPreview();
  }

  // the draft changed or came anew: the form, the banner and the bar drawn again, the preview left alone (an iframe
  // rebuilt or moved loads again: Flutter would start over)
  refresh() {
    const grid = this.shadowRoot.querySelector('.grid');
    const c = this.cur();
    if (!grid || grid.dataset.key !== this.key() + '|' + this.size || !c || c.draft == null) { this.render(); return; }
    grid.firstChild.replaceWith(this.form(c, this.desc()));
    this.shadowRoot.querySelector('.incoming').replaceWith(this.banner(c));
    this.renderBar();
  }

  // the Echo's Android apps with their labels and icons, as Echo-Wall on it sent them: its Home's tiles in the preview,
  // the icons in the Apps tab (hassmic's /api/apps knows packages and versions only)
  async loadLauncher(echo) {
    try {
      const r = await this.ws({ type: 'echo_local/home/apps/get', echo });
      this.launcher[echo] = r.apps || [];
    } catch (e) { return; }                 // an older integration: none
    if (echo !== this.echo) return;
    const f = this.shadowRoot.querySelector('iframe');
    if (f && f.contentWindow) f.contentWindow.postMessage({ type: 'echo-local-apps', apps: this.launcher[echo] }, location.origin);
    if (this.tab === 'apps') { const t = this.shadowRoot.querySelector('.appstab'); if (t) t.replaceWith(this.appsTab()); }
  }

  pushPreview() {
    const f = this.shadowRoot.querySelector('iframe');
    const c = this.cur();
    if (f && f.contentWindow && c) f.contentWindow.postMessage({ type: 'echo-local-layout', layout: c.draft }, location.origin);
    const sk = this.shadowRoot.querySelector('.sketch');
    if (sk) sk.replaceWith(this.sketch());
  }

  async save() {
    const c = this.cur(); if (!c) return;
    try {
      const lay = await this.ws({ type: 'echo_local/home/set', echo: this.echo, app: this.app, layout: c.draft });
      c.saved = clone(lay); c.draft = clone(lay); c.incoming = null;
      this.toast('Saved: the Echo shows it now');
      this.refreshList();
    } catch (e) { this.toast('Not saved: ' + ((e && e.message) || e)); }
    this.refresh();
  }

  async refreshList() {
    try {
      const r = await this.ws({ type: 'echo_local/home/list' });
      Object.assign(this.state, { echos: r.echos, descriptors: r.descriptors });
      this.renderNav();
      if (this.tab === 'home') this.renderBar();
    } catch (e) { /* the next save tells */ }
  }

  // ---------------------------------------------------------------- import and export

  exportFile() {
    const c = this.cur(); if (!c) return;
    const d = this.desc() || { fields: [] };
    const common = {};
    for (const f of d.fields) if (f.common && f.key in c.draft) common[f.common] = c.draft[f.key];
    const info = this.echoInfo();
    const doc = { format: FORMAT, version: 1, app: this.app, app_name: d.name || this.app, echo: this.echo, echo_name: info ? info.title : this.echo,
      exported: new Date().toISOString(), layout: c.draft, common };
    const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' });
    const a = h('a', { href: URL.createObjectURL(blob), download: `${(info ? info.title : this.echo).replace(/[^\w-]+/g, '-')}-${(d.name || this.app).replace(/[^\w-]+/g, '-')}.echohome.json` });
    this.shadowRoot.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  pickFile() {
    const i = h('input', { type: 'file', accept: '.json,application/json', style: 'display:none' });
    i.onchange = async () => {
      const f = i.files[0]; i.remove(); if (!f) return;
      try {
        if (f.size > 256 * 1024) throw new Error('larger than a home screen can be');
        const doc = JSON.parse(await f.text());
        if (doc.format !== FORMAT || typeof doc.layout !== 'object') throw new Error('not an Echo Local home screen file');
        this.take(doc.app, doc.layout, doc.common, `${doc.app_name || doc.app} from ${doc.echo_name || 'a file'}`);
      } catch (e) { this.toast('Not imported: ' + e.message); }
    };
    this.shadowRoot.append(i); i.click();
  }

  // another app's Home into this one's: the same app as it is, another by what both have (descriptor "common")
  take(app, layout, common, what) {
    const c = this.cur(); if (!c) return;
    let next;
    if (app === this.app) next = clone(layout);
    else {
      const src = this.desc(app, this._from || this.echo);
      const shared = Object.assign({}, common || {});
      if (src) for (const f of src.fields) if (f.common && f.key in layout && !(f.common in shared)) shared[f.common] = layout[f.key];
      next = Object.assign(clone(c.draft), this.fromCommon(shared));
      if (!Object.keys(shared).length) { this.toast(`Nothing ${what} shares with ${(this.desc() || {}).name || this.app}`); return; }
    }
    c.draft = next;
    const unknown = this.ids(next).filter((x) => !this._hass.states[x]);
    this.toast(`Imported ${what}: Save to send it to the Echo` + (unknown.length ? ` (${unknown.length} entities not in this Home Assistant, kept)` : ''));
    this.changed(true);
  }

  fromCommon(shared) {
    const out = {};
    for (const f of (this.desc() || { fields: [] }).fields) {
      if (!f.common || !(f.common in shared)) continue;
      const v = shared[f.common];
      if (f.type === 'select' && !(f.options || []).some((o) => o[0] === v)) continue;
      out[f.key] = clone(v);
    }
    return out;
  }

  ids(lay) {
    const out = [];
    for (const f of (this.desc() || { fields: [] }).fields) {
      const v = lay[f.key];
      if (f.type === 'entities' && Array.isArray(v)) out.push(...v);
      else if (f.type === 'entity' && v && v !== f.none) out.push(v);
      else if (f.type === 'area_order' && v) for (const l of Object.values(v)) out.push(...l);
    }
    return [...new Set(out)];
  }

  async fromSlot(node, app) {
    try {
      const lay = await this.ws({ type: 'echo_local/home/get', echo: node, app });
      this._from = node;
      const name = (this.echoInfo(node) || {}).title || node;
      this.take(app, lay, null, `${(this.desc(app, node) || {}).name || app} of ${name}`);
      this._from = null;
    } catch (e) { this.toast('Not read: ' + ((e && e.message) || e)); }
  }

  async copyTo(nodes) {
    const c = this.cur(); if (!c || !nodes.length) return;
    let n = 0;
    for (const node of nodes) {
      try { await this.ws({ type: 'echo_local/home/set', echo: node, app: this.app, layout: c.draft }); n++; }
      catch (e) { this.toast(`${node}: ${(e && e.message) || e}`); }
    }
    this.toast(`Copied to ${n} Echo${n === 1 ? '' : 's'}`);
    this.refreshList();
  }

  async reset() {
    const d = this.desc();
    if (!confirm(`Forget this Echo's ${d ? d.name : this.app} layout? It starts again from the app's own choice.`)) return;
    await this.ws({ type: 'echo_local/home/delete', echo: this.echo, app: this.app }).catch((e) => this.toast(String(e && e.message || e)));
    const c = this.cur(); if (c) { c.saved = null; c.draft = null; }
    this.refreshList();
  }

  // ---------------------------------------------------------------- the screen's options

  async loadKiosk() {
    try {
      const r = await this.ws({ type: 'echo_local/kiosk/get', echo: this.echo });
      this.kiosk = { saved: clone(r.options), draft: clone(r.options), kinds: r.kinds, music: r.music_panel, url: r.ha_url, push: r.push };
    } catch (e) { this.kiosk = { error: (e && e.message) || String(e) }; }
    this.render();
  }

  async saveKiosk() {
    const k = this.kiosk;
    const pick = ['kiosk', 'kiosk_screens', 'kiosk_default', 'kiosk_dashboard', 'kiosk_music', 'kiosk_custom_name', 'kiosk_custom_url',
      'kiosk_return', 'kiosk_admin', 'kiosk_ha_url', 'kiosk_app', 'kiosk_app_settings'];
    const opts = {}; for (const p of pick) if (p in k.draft) opts[p] = k.draft[p];
    try {
      const r = await this.ws({ type: 'echo_local/kiosk/set', echo: this.echo, options: opts });
      k.saved = clone(r.options); k.draft = clone(r.options);
      this.toast('Saved: the Echo gets it in a moment');
      setTimeout(() => { if (this.tab === 'screen') this.loadKiosk(); }, 4000);   // the entry reloads, then pushes: its outcome
      this.refreshList();
    } catch (e) { this.toast('Not saved: ' + ((e && e.message) || e)); }
    this.render();
  }

  // ---------------------------------------------------------------- drawing

  render() {
    const root = this.shadowRoot;
    root.textContent = '';
    root.append(h('style', null, CSS));
    root.append(h('header', null,
      h('button', { class: 'iconbtn menu', title: 'Menu', onclick: () => this.dispatchEvent(new Event('hass-toggle-menu', { bubbles: true, composed: true })) }, '☰'),
      h('h1', null, 'Echo Local')));
    if (!this.state.loaded) { root.append(h('main', null, h('div', { class: 'empty' }, 'Loading…'))); return; }
    if (this.state.error) { root.append(h('main', null, h('div', { class: 'banner' }, 'Echo Local did not answer: ' + this.state.error))); return; }
    const wrap = h('div', { class: 'wrap' }, h('nav'), h('main'));
    root.append(wrap);
    this.renderNav();
    this.renderMain();
  }

  renderNav() {
    const nav = this.shadowRoot.querySelector('nav'); if (!nav) return;
    nav.textContent = '';
    nav.append(h('div', { class: 'lbl' }, 'Echos'));
    for (const e of this.state.echos) {
      const apps = this.appsOf(e.echo).filter((a) => a.slot).map((a) => (a.desc && a.desc.name) || a.app);
      nav.append(h('button', { class: 'echo' + (e.echo === this.echo ? ' sel' : ''), onclick: () => this.select(e.echo, this.app) },
        h('span', { class: 'dev' + (e.kiosk ? ' on' : '') }),
        h('span', null, h('div', { class: 't' }, e.title), h('div', { class: 's' }, (e.kiosk ? 'Screen on' : 'Screen off') + (apps.length ? ' · ' + apps.join(', ') : '')))));
    }
    if (!this.state.echos.length) nav.append(h('div', { class: 'empty' }, 'No Echo added yet: Settings › Devices & services › Add integration › Echo Local.'));
  }

  renderMain() {
    const main = this.shadowRoot.querySelector('main'); if (!main) return;
    main.textContent = '';
    const isEcho = !!this.echoInfo();
    if (!isEcho) { main.append(h('div', { class: 'empty' }, 'Add an Echo Show to Echo Local first.')); return; }
    main.append(h('div', { class: 'tabs' },
      h('button', { class: 'tab' + (this.tab === 'home' ? ' sel' : ''), onclick: () => { this.tab = 'home'; this.render(); } }, 'Home screen'),
      isEcho && h('button', { class: 'tab' + (this.tab === 'screen' ? ' sel' : ''), onclick: () => { this.tab = 'screen'; if (!this.kiosk) this.loadKiosk(); this.render(); } }, 'Screen'),
      isEcho && !(this.apps && this.apps.none) && h('button', { class: 'tab' + (this.tab === 'apps' ? ' sel' : ''), onclick: () => { this.tab = 'apps'; this.loadApps(); this.render(); } }, 'Apps')));
    if (this.tab === 'screen' && isEcho) { main.append(this.screenTab()); return; }
    if (this.tab === 'apps' && isEcho) { main.append(this.appsTab()); return; }
    main.append(this.homeTab());
  }

  // ---- Home screen

  homeTab() {
    const box = h('div');
    const apps = h('div', { class: 'apps' });
    const info = this.echoInfo();
    for (const a of this.appsOf(this.echo)) {
      const running = info && (info.app || '') === a.app;
      apps.append(h('button', { class: 'chip' + (a.app === this.app ? ' sel' : ''), title: a.app, onclick: async () => { this.app = a.app; await this.open(this.echo, a.app); this.render(); } },
        h('span', { class: 'dot' + (a.slot ? '' : ' none') }), (a.desc && a.desc.name) || a.app, running ? ' · on the screen' : ''));
    }
    box.append(apps);
    const c = this.cur();
    if (!c || c.draft == null) {         // being read (a reset: until the subscription brings the empty one)
      if (!c) this.open(this.echo, this.app).then(() => this.render());
      box.append(h('div', { class: 'empty' }, 'Loading…'));
      return box;
    }
    box.append(this.banner(c));
    box.append(h('div', { class: 'bar' }));
    const d = this.desc();
    const grid = h('div', { class: 'grid' }, this.form(c, d), this.previewPane(c, d));
    grid.dataset.key = this.key() + '|' + this.size;
    box.append(grid);
    queueMicrotask(() => this.renderBar());
    return box;
  }

  banner(c) {
    const b = h('div', { class: 'incoming' });
    if (c.incoming) b.append(h('div', { class: 'banner' },
      h('span', { class: 'grow' }, 'The Echo saved a change of its own while you edit (someone arranged it on the screen).'),
      h('button', { class: 'btn small', onclick: () => { c.saved = c.incoming; c.draft = clone(c.incoming); c.incoming = null; this.changed(true); } }, 'Take the Echo’s'),
      h('button', { class: 'btn small', onclick: () => { c.saved = c.incoming; c.incoming = null; this.changed(true); } }, 'Keep mine')));
    return b;
  }

  renderBar() {
    const bar = this.shadowRoot.querySelector('.bar'); if (!bar) return;
    const c = this.cur(); if (!c) return;
    bar.textContent = '';
    const dirty = this.dirty(c);
    const slot = this.appsOf(this.echo).find((a) => a.app === this.app);
    const st = slot && slot.slot ? `Saved ${ago(slot.slot.updated)}${slot.slot.by === 'app' ? ' by the Echo' : slot.slot.by === 'panel' ? ' here' : slot.slot.by ? ' by ' + slot.slot.by : ''}` : 'Nothing saved yet: the app’s own choice';
    bar.append(...[
      h('button', { class: 'btn primary', disabled: !dirty, onclick: () => this.save() }, 'Save'),
      h('button', { class: 'btn', disabled: !dirty, onclick: () => { c.draft = clone(c.saved); this.changed(true); } }, 'Revert'),
      h('span', { class: 'status' + (dirty ? ' dirty' : '') }, dirty ? 'Unsaved changes' : st),
      h('span', { class: 'grow' }),
      this.menu('Import', () => {
        const items = [h('button', { onclick: () => this.pickFile() }, 'From a file…')];
        const others = this.appsOf(this.echo).filter((a) => a.app !== this.app && a.slot);
        if (others.length) items.push(h('div', { class: 'sep' }), h('div', { class: 'h' }, 'Another app on this Echo'),
          ...others.map((a) => h('button', { onclick: () => this.fromSlot(this.echo, a.app) }, (a.desc && a.desc.name) || a.app)));
        const echos = this.state.echos.filter((e) => e.echo !== this.echo && Object.keys(e.slots).length);
        if (echos.length) items.push(h('div', { class: 'sep' }), h('div', { class: 'h' }, 'Another Echo'),
          ...echos.flatMap((e) => Object.keys(e.slots).map((a) => h('button', { onclick: () => this.fromSlot(e.echo, a) }, `${e.title} · ${(this.desc(a) || {}).name || a}`))));
        return items;
      }),
      h('button', { class: 'btn', onclick: () => this.exportFile() }, 'Export'),
      this.state.echos.some((e) => e.echo !== this.echo) ? this.menu('Copy to', () => {
        const rest = this.state.echos.filter((e) => e.echo !== this.echo);
        return [h('div', { class: 'h' }, 'Saves this draft there as it is'),
          ...rest.map((e) => h('button', { onclick: () => this.copyTo([e.echo]) }, e.title)),
          rest.length > 1 && h('button', { onclick: () => this.copyTo(rest.map((e) => e.echo)) }, 'Every other Echo')];
      }) : null,
      h('button', { class: 'btn danger', disabled: !(slot && slot.slot), onclick: () => this.reset() }, 'Reset')].filter(Boolean));
  }

  menu(label, items) {
    const w = h('span', { class: 'menuwrap' });
    const b = h('button', { class: 'btn', onclick: (ev) => {
      ev.stopPropagation();
      const open = w.querySelector('.pop'); if (open) { open.remove(); return; }
      const pop = h('div', { class: 'pop' }, items());
      pop.addEventListener('click', () => pop.remove());
      w.append(pop);
      const close = (e) => { if (!e.composedPath().includes(w)) { pop.remove(); removeEventListener('click', close, true); } };
      addEventListener('click', close, true);
    } }, label + ' ▾');
    w.append(b);
    return w;
  }

  form(c, d) {
    const card = h('div', { class: 'card' });
    if (!d) {
      card.append(h('h2', null, this.app),
        h('div', { class: 'about' }, 'This app has not described its layout (echo_local/home/describe, docs/home-screens.md): it can be exported, imported and copied, and edited as JSON.'),
        this.jsonRow(c));
      return card;
    }
    card.append(h('h2', null, d.name), d.about && h('div', { class: 'about' }, d.about));
    for (const f of d.fields) {
      card.append(this.field(c, f));
      if (this.app === ECHOWALL && f.key === 'dashboard') card.append(this.pagesRow(c));
    }
    card.append(h('details', { class: 'room', style: 'margin-top:12px' }, h('summary', null, h('span', { class: 'n' }, 'All of it, as JSON')), h('div', { style: 'padding:0 12px 12px' }, this.jsonRow(c))));
    return card;
  }

  // Echo-Wall's pages after Home (the preview tells which there are: rooms, a dashboard's sections, the owner's own):
  // in their order, moved up and down (page_order), the owner's renamed or deleted (custom_pages), the others taken
  // off and shown again (hidden_pages), a new one added.  All of it in the draft: Save sends it to the Echo
  pagesRow(c) {
    const lay = c.draft;
    const row = h('div', { class: 'row pagesrow' }, h('div', { class: 'head' }, h('span', { class: 'name' }, 'Pages after Home')));
    const pages = this.pages;
    if (!pages) { row.append(h('div', { class: 'help' }, 'The preview lists them once it has started.')); return row; }
    const done = () => this.changed(true);
    const order = () => pages.map((p) => p.group);
    const own = (g) => (lay.custom_pages || []).find((p) => 'page:' + p.id === g);
    const list = h('div', { class: 'list' });
    if (!pages.length) list.append(h('div', { class: 'empty' }, 'None: Home only.'));
    pages.forEach((p, i) => {
      const move = (d) => { const o = order(); [o[i], o[i + d]] = [o[i + d], o[i]]; lay.page_order = o; this.pages = o.map((g) => pages.find((x) => x.group === g)); done(); };
      const name = p.kind === 'own'
        ? h('input', { class: 'pagename', value: p.title, 'aria-label': 'Page name', onchange: (e) => { const cp = own(p.group); if (cp && e.target.value.trim()) { cp.name = e.target.value.trim(); done(); } } })
        : h('div', null, p.title);
      list.append(h('div', { class: 'item page' + (p.hidden ? ' off' : '') },
        h('div', { class: 'nm' }, name, h('div', { class: 'id' }, (p.kind === 'own' ? 'Your page' : p.kind === 'dashboard' ? 'Dashboard section' : 'Room') + (p.hidden ? ' · taken off' : ''))),
        h('button', { class: 'btn small', disabled: i === 0, title: 'Earlier', 'aria-label': 'Move up', onclick: () => move(-1) }, '↑'),
        h('button', { class: 'btn small', disabled: i === pages.length - 1, title: 'Later', 'aria-label': 'Move down', onclick: () => move(1) }, '↓'),
        p.kind === 'own'
          ? h('button', { class: 'btn small danger', onclick: () => {
              if (!confirm(`Delete the page “${p.title}”? Its cards go with it.`)) return;
              lay.custom_pages = (lay.custom_pages || []).filter((x) => 'page:' + x.id !== p.group);
              for (const k of ['cards', 'place', 'sizes', 'exclude']) if (lay[k]) delete lay[k][p.group];
              lay.page_order = (lay.page_order || []).filter((g) => g !== p.group);
              this.pages = pages.filter((x) => x.group !== p.group); done(); } }, 'Delete')
          : h('button', { class: 'btn small' + (p.hidden ? '' : ' danger'), onclick: () => {
              const hp = new Set(lay.hidden_pages || []); p.hidden ? hp.delete(p.group) : hp.add(p.group);
              lay.hidden_pages = [...hp]; p.hidden = !p.hidden; done(); } }, p.hidden ? 'Show' : 'Remove')));
    });
    const nm = h('input', { class: 'pagename', placeholder: 'New page’s name' });
    const add = () => {
      const n = nm.value.trim() || `Page ${(lay.custom_pages || []).length + 1}`;
      const id = Date.now().toString(36);
      lay.custom_pages = [...(lay.custom_pages || []), { id, name: n }];
      lay.page_order = [...order(), 'page:' + id];
      this.pages = [...pages, { group: 'page:' + id, title: n, kind: 'own', hidden: false }];
      done();
    };
    nm.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); });
    row.append(list, h('div', { class: 'addpage' }, nm, h('button', { class: 'btn small', onclick: add }, '+ Add page')),
      h('div', { class: 'help' }, 'A page of your own starts empty: add cards to it in the preview’s edit mode (+ Add) or on the Echo. A room or a dashboard section taken off stays off until shown again.'));
    return row;
  }

  jsonRow(c) {
    const t = h('textarea', { spellcheck: false });
    t.value = JSON.stringify(c.draft, null, 2);
    const msg = h('div', { class: 'help' });
    t.addEventListener('input', () => {
      try { c.draft = JSON.parse(t.value); msg.textContent = ''; this.changed(false); } catch (e) { msg.textContent = 'Not JSON yet: ' + e.message; }
    });
    t.addEventListener('change', () => this.changed(true));
    return h('div', { class: 'row' }, t, msg);
  }

  field(c, f) {
    const lay = c.draft;
    const has = f.key in lay && lay[f.key] !== undefined;
    const val = has ? lay[f.key] : f.default;
    const set = (v, rebuild) => { if (v === undefined) delete lay[f.key]; else lay[f.key] = v; this.changed(rebuild); };
    const row = h('div', { class: 'row' });
    const head = h('div', { class: 'head' }, h('span', { class: 'name' }, f.label || f.key));
    row.append(head);
    if (f.type === 'select') {
      const opts = f.options || [];
      if (opts.length <= 4) {
        const seg = h('div', { class: 'seg' });
        for (const [v, l] of opts) seg.append(h('button', { class: v === val ? 'sel' : '', onclick: () => { set(v); [...seg.children].forEach((b) => b.classList.toggle('sel', b.textContent === l)); } }, l));
        head.append(seg);
      } else {
        const s = h('select', { onchange: () => set(s.value) }, opts.map(([v, l]) => h('option', { value: v, selected: v === val }, l)));
        head.append(s);
      }
    } else if (f.type === 'number') {
      const i = h('input', { type: 'number', min: f.min, max: f.max, step: f.step || 1 });
      i.value = val == null ? '' : val;
      i.addEventListener('input', () => { if (i.value === '') set(undefined); else if (i.checkValidity()) set(+i.value); });
      head.append(i, f.unit ? h('span', { class: 'note' }, f.unit) : null);
    } else if (f.type === 'bool') {
      head.append(this.switch(!!val, (on) => set(on)));
    } else if (f.type === 'dashboard') {
      // the Home Assistant dashboards (lovelace/dashboards/list) and Overview; the field's value is the url path
      const s = h('select', { onchange: () => set(s.value || undefined) }, h('option', { value: '' }, 'None: a page per room'));
      const add = (v, l) => s.append(h('option', { value: v, selected: v === (val || '') }, l));
      add('lovelace', 'Overview');
      this.ws({ type: 'lovelace/dashboards/list' }).then((ds) => {
        for (const d of ds) add(d.url_path, d.title || d.url_path);
        if (val && ![...s.options].some((o) => o.value === val)) add(val, val + ' (not found)');
        s.value = val || '';
      }).catch(() => { if (val && val !== 'lovelace') add(val, val); s.value = val || ''; });
      head.append(s);
    } else if (f.type === 'text') {
      const i = h('input', { type: 'text' }); i.value = val || '';
      i.addEventListener('input', () => set(i.value));
      head.append(i);
    } else if (f.type === 'entity') {
      head.append(this.entityInput(val && val !== f.none ? val : '', f.domain, (v) => set(v || (f.none != null ? f.none : undefined)), f.none != null ? 'None' : 'The app picks'));
    } else if (f.type === 'entities') {
      const auto = f.nullable && !Array.isArray(val);
      if (f.nullable) head.append(h('span', { class: 'note' }, 'The app picks'), this.switch(auto, (on) => set(on ? null : this.autoPick(), true)));
      if (!auto) row.append(this.entityList(Array.isArray(val) ? val : [], f.ordered !== false, (list, rebuild) => set(list, rebuild)));
    } else if (f.type === 'strings') {
      row.append(this.stringList(Array.isArray(val) ? val : [], (list) => set(list, true)));
    } else if (f.type === 'area_order') {
      row.append(this.areaOrder(val || {}, (v, rebuild) => set(v, rebuild)));
    }
    if (f.help) row.append(h('div', { class: 'help' }, f.help));
    return row;
  }

  switch(on, cb) {
    const i = h('input', { type: 'checkbox', checked: on });
    i.addEventListener('change', () => cb(i.checked));
    return h('label', { class: 'switch' }, i, h('span'));
  }

  // what Echo-Wall picks itself (a thermostat, a camera, scenes, locks): a start for a list of one's own
  autoPick() {
    const s = this._hass.states, ids = Object.keys(s);
    const out = [];
    const cl = ids.find((x) => domainOf(x) === 'climate' && s[x].attributes.temperature != null); if (cl) out.push(cl);
    const cam = ids.find((x) => domainOf(x) === 'camera' && s[x].state !== 'unavailable'); if (cam) out.push(cam);
    out.push(...ids.filter((x) => domainOf(x) === 'scene').slice(0, 3), ...ids.filter((x) => domainOf(x) === 'lock'));
    return out;
  }

  name(id) { const s = this._hass.states[id]; return (s && s.attributes.friendly_name) || id; }

  entityInput(val, domain, cb, placeholder) {
    const listId = 'el-' + Math.random().toString(36).slice(2);
    const i = h('input', { type: 'text', list: listId, placeholder: placeholder || 'entity id or name', style: 'min-width:220px' });
    i.value = val || '';
    const dl = h('datalist', { id: listId });
    for (const id of Object.keys(this._hass.states).filter((x) => !domain || domainOf(x) === domain).sort())
      dl.append(h('option', { value: id }, this.name(id)));
    i.addEventListener('change', () => {
      const v = i.value.trim();
      const id = v === '' || this._hass.states[v] ? v : Object.keys(this._hass.states).find((x) => this.name(x).toLowerCase() === v.toLowerCase()) || v;
      i.value = id; cb(id);
    });
    return h('span', null, i, dl);
  }

  // a list of entities: drag (or the arrows) to order, × to remove, a picker to add
  entityList(list, ordered, cb) {
    const wrap = h('div');
    const draw = () => {
      wrap.textContent = '';
      const box = h('div', { class: 'list' });
      if (!list.length) box.append(h('div', { class: 'empty' }, 'None yet.'));
      list.forEach((id, i) => {
        const known = !!this._hass.states[id];
        const it = h('div', { class: 'item' + (known ? '' : ' unknown'), draggable: ordered ? 'true' : null },
          ordered && h('span', { class: 'grip', title: 'Drag' }, '⠿'),
          h('div', { class: 'nm' }, h('div', null, this.name(id)), h('div', { class: 'id' }, known ? id : id + ' · not in this Home Assistant')),
          ordered && h('button', { class: 'mini', title: 'Up', disabled: i === 0, onclick: () => { list.splice(i - 1, 0, list.splice(i, 1)[0]); cb(list); draw(); } }, '↑'),
          ordered && h('button', { class: 'mini', title: 'Down', disabled: i === list.length - 1, onclick: () => { list.splice(i + 1, 0, list.splice(i, 1)[0]); cb(list); draw(); } }, '↓'),
          h('button', { class: 'mini', title: 'Remove', onclick: () => { list.splice(i, 1); cb(list); draw(); } }, '×'));
        if (ordered) this.dnd(it, i, list, () => { cb(list); draw(); });
        box.append(it);
      });
      wrap.append(box);
      const add = h('div', { class: 'add' });
      add.append(this.entityInput('', null, (v) => { if (v && !list.includes(v)) { list.push(v); cb(list); draw(); } }, 'Add: entity id or name'));
      wrap.append(add);
    };
    list = list.slice(); draw();
    return wrap;
  }

  dnd(it, i, list, done) {
    it.addEventListener('dragstart', (ev) => { this._drag = { list, i }; it.classList.add('drag'); ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', String(i)); });
    it.addEventListener('dragend', () => { it.classList.remove('drag'); this._drag = null; });
    it.addEventListener('dragover', (ev) => { if (this._drag && this._drag.list === list) { ev.preventDefault(); it.classList.add('over'); } });
    it.addEventListener('dragleave', () => it.classList.remove('over'));
    it.addEventListener('drop', (ev) => {
      ev.preventDefault(); it.classList.remove('over');
      const g = this._drag; if (!g || g.list !== list || g.i === i) return;
      const [x] = list.splice(g.i, 1); list.splice(i, 0, x); done();
    });
  }

  stringList(list, cb) {
    list = list.slice();
    const wrap = h('div', { class: 'apps', style: 'margin-top:8px' });
    const draw = () => {
      wrap.textContent = '';
      list.forEach((s, i) => wrap.append(h('span', { class: 'chip' }, s, h('button', { class: 'mini', onclick: () => { list.splice(i, 1); cb(list); draw(); } }, '×'))));
      const i = h('input', { type: 'text', placeholder: 'Add…', style: 'width:140px' });
      i.addEventListener('change', () => { const v = i.value.trim(); if (v && !list.includes(v)) { list.push(v); cb(list); draw(); } });
      wrap.append(i);
    };
    draw();
    return wrap;
  }

  // each room's tiles in order: Home Assistant's areas, their entities (by entity or device area), the saved order first
  areaOrder(order, cb) {
    order = clone(order);
    const H = this._hass;
    const areas = Object.values(H.areas || {}).sort((a, b) => a.name.localeCompare(b.name));
    const areaOf = (id) => { const e = (H.entities || {})[id]; if (!e) return null; return e.area_id || (e.device_id && (H.devices || {})[e.device_id] ? H.devices[e.device_id].area_id : null); };
    const TILE = ['light', 'switch', 'fan', 'cover', 'lock', 'media_player', 'climate', 'binary_sensor', 'scene', 'script', 'camera'];
    const wrap = h('div');
    if (!areas.length) { wrap.append(h('div', { class: 'empty' }, 'No areas in Home Assistant: rooms come from them.')); return wrap; }
    for (const a of areas) {
      const ids = Object.keys(H.states).filter((x) => areaOf(x) === a.area_id && TILE.includes(domainOf(x)) && !(H.entities[x] || {}).hidden);
      const own = order[a.area_id] || [];
      const list = [...own.filter((x) => ids.includes(x) || !H.states[x]), ...ids.filter((x) => !own.includes(x)).sort((x, y) => this.name(x).localeCompare(this.name(y)))];
      const d = h('details', { class: 'room' }, h('summary', null, h('span', { class: 'n' }, a.name), h('span', { class: 'note' }, own.length ? 'own order' : 'the app’s order'),
        own.length ? h('button', { class: 'btn small', onclick: (ev) => { ev.preventDefault(); delete order[a.area_id]; cb(clone(order), true); } }, 'Reset') : null));
      const box = h('div', { class: 'list' });
      const draw = () => {
        box.textContent = '';
        list.forEach((id, i) => {
          const it = h('div', { class: 'item', draggable: 'true' }, h('span', { class: 'grip' }, '⠿'),
            h('div', { class: 'nm' }, h('div', null, this.name(id)), h('div', { class: 'id' }, id)),
            h('button', { class: 'mini', disabled: i === 0, onclick: () => { list.splice(i - 1, 0, list.splice(i, 1)[0]); commit(); } }, '↑'),
            h('button', { class: 'mini', disabled: i === list.length - 1, onclick: () => { list.splice(i + 1, 0, list.splice(i, 1)[0]); commit(); } }, '↓'));
          this.dnd(it, i, list, commit);
          box.append(it);
        });
        if (!list.length) box.append(h('div', { class: 'empty' }, 'Nothing for the screen in this room.'));
      };
      const commit = () => { order[a.area_id] = list.slice(); cb(clone(order)); draw(); };
      draw();
      d.append(box);
      wrap.append(d);
    }
    return wrap;
  }

  previewPane(c, d) {
    const [w, hgt] = this.size || SIZES['Echo Show 5'];
    const pane = h('div', { class: 'preview' });
    const vp = h('div', { class: 'vp' });
    const screen = h('div', { class: 'screen' }, vp, h('div', { class: 'band' }));
    pane.append(screen);
    const fit = () => { const cw = vp.clientWidth || 560; vp.style.height = (cw * hgt / w) + 'px'; const f = vp.querySelector('iframe'); if (f) f.style.transform = `scale(${cw / w})`; };
    if (d && d.preview && this.echo !== null) {
      const src = `${d.preview}?echo=${encodeURIComponent(this.echo)}`;
      const f = h('iframe', { src, title: 'Preview', style: `width:${w}px;height:${hgt}px` });
      f.dataset.key = this.key();
      f.addEventListener('load', () => { this.pushPreview(); if (this.editOnScreen) f.contentWindow.postMessage({ type: 'echo-local-editmode', on: true }, location.origin); });
      vp.append(f);
    } else {
      vp.append(this.sketch());
    }
    new ResizeObserver(fit).observe(vp);
    requestAnimationFrame(fit);
    const sizeSel = h('select', { onchange: () => { this.size = SIZES[sizeSel.value]; this.render(); } },
      Object.entries(SIZES).map(([k, v]) => h('option', { value: k, selected: same(v, this.size) }, `${k} (${v[0]}×${v[1]})`)));
    const bar = h('div', { class: 'pbar' }, sizeSel);
    if (d && d.preview) {
      bar.append(h('label', { class: 'note', style: 'display:flex;gap:6px;align-items:center' },
        this.switch(this.editOnScreen, (on) => { this.editOnScreen = on; const f = vp.querySelector('iframe'); if (f) f.contentWindow.postMessage({ type: 'echo-local-editmode', on }, location.origin); }),
        'Edit on the screen: drag tiles, ★ for Home, − to hide'));
      bar.append(h('label', { class: 'note', style: 'display:flex;gap:6px;align-items:center' },
        this.switch(!!this.gallery, (on) => { this.gallery = on; const f = vp.querySelector('iframe'); if (f) f.contentWindow.postMessage({ type: 'echo-local-gallery', on }, location.origin); }),
        'Card sizes: every card at every size, with your devices'));
      bar.append(h('span', { class: 'note' }, 'The app itself, live with this Home Assistant’s states. Swipe sideways for the pages; hold a card for its menu.'));
    } else {
      bar.append(h('span', { class: 'note' }, 'A sketch of Home’s tiles: the app draws them its own way.'));
    }
    pane.append(bar);
    return pane;
  }

  // other apps: their Home's order from the descriptor's common fields, as tiles
  sketch() {
    const c = this.cur(), d = this.desc();
    const lay = (c && c.draft) || {};
    let theme = 'amber', fav = null;
    for (const f of (d || { fields: [] }).fields) {
      if (f.common === 'theme') theme = lay[f.key] || f.default || theme;
      if (f.common === 'favorites') fav = lay[f.key];
    }
    const box = h('div', { class: 'sketch ' + theme });
    const big = (id) => ['climate', 'camera', 'media_player'].includes(domainOf(id));
    box.append(h('div', { class: 'w big' }, h('span', { class: 'k' }, 'Clock'), new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })));
    for (const id of (Array.isArray(fav) ? fav : this.autoPick()).slice(0, 12))
      box.append(h('div', { class: 'w' + (big(id) ? ' big' : '') }, h('span', { class: 'k' }, domainOf(id)), this.name(id)));
    if (!Array.isArray(fav)) box.append(h('div', { class: 'w', style: 'opacity:.6' }, h('span', { class: 'k' }, 'auto'), 'The app picks'));
    return box;
  }

  // ---- Screen (kiosk.py's options)

  // ---- Apps (apps.py; the Echo's apps.c): the owner's Android apps beside the screen app

  async loadApps() {
    const echo = this.echo;
    try {
      const r = await this.ws({ type: 'echo_local/apps/list', echo });
      if (echo !== this.echo) return;
      this.apps = r;
      if (this.tab === 'apps') { const t = this.shadowRoot.querySelector('.appstab'); if (t) t.replaceWith(this.appsTab()); else this.render(); }
      else if (r.none) {               // no Apps tab on an Echo Dot; nothing else redrawn (the preview would load again)
        const b = [...this.shadowRoot.querySelectorAll('.tab')].find((x) => x.textContent === 'Apps'); if (b) b.remove();
      }
    } catch (e) {
      if (echo === this.echo) { this.apps = { error: (e && e.message) || String(e), apps: [] }; if (this.tab === 'apps') this.render(); }
    }
    // an install or removal under way: asked again every second until it is done
    const busy = this.apps && ((this.apps.send || {}).state === 'sending' || ['receiving', 'installing', 'removing'].includes((this.apps.install || {}).state)
      || this.uploading);
    clearTimeout(this._appsPoll);
    if (busy && echo === this.echo) this._appsPoll = setTimeout(() => this.loadApps(), 1000);
  }

  appsTab() {
    const a = this.apps;
    const box = h('div', { class: 'appstab' });
    if (!a) { box.append(h('div', { class: 'empty' }, 'Loading…')); return box; }
    if (a.error) { box.append(h('div', { class: 'banner' }, 'The Echo did not answer: ' + a.error)); return box; }
    if (a.none) { box.append(h('div', { class: 'empty' }, 'This Echo has no Android apps.')); return box; }
    const screenApp = (this.echoInfo() || {}).app || '';
    const st = a.install || {}, send = a.send || {};
    const busy = send.state === 'sending' || ['receiving', 'installing', 'removing'].includes(st.state) || this.uploading;

    const list = h('div', { class: 'list' });
    if (!a.apps.length) list.append(h('div', { class: 'empty' }, 'None yet: add one below.'));
    for (const app of a.apps.slice().sort((x, y) => x.package.localeCompare(y.package))) {
      const isScreen = app.package === screenApp;
      const l = (this.launcher[this.echo] || []).find((x) => x.package === app.package);
      list.append(h('div', { class: 'item app' },
        l && l.icon ? h('img', { class: 'appicon', src: 'data:image/png;base64,' + l.icon, alt: '' }) : h('div', { class: 'appicon none' }),
        h('div', { class: 'nm' }, h('div', null, l ? l.label : app.package),
          h('div', { class: 'id' }, (l ? app.package + ' · ' : '') + `version ${app.version}` + (isScreen ? ' · the screen app' : ''))),
        h('span', { class: 'note' }, 'Internet'),
        this.switch(!!app.net, async (on) => {
          try { await this.ws({ type: 'echo_local/apps/net', echo: this.echo, package: app.package, on }); app.net = on; this.toast(`${app.package}: ${on ? 'may reach the internet' : 'kept off the internet'}`); }
          catch (e) { this.toast('Not changed: ' + ((e && e.message) || e)); this.loadApps(); }
        }),
        h('button', { class: 'btn small danger', disabled: isScreen || busy, title: isScreen ? 'The screen app: pick another one under Screen first' : '', onclick: async () => {
          if (!confirm(`Remove ${app.package} from the Echo? Its data goes with it.`)) return;
          try { await this.ws({ type: 'echo_local/apps/uninstall', echo: this.echo, package: app.package }); this.loadApps(); }
          catch (e) { this.toast('Not removed: ' + ((e && e.message) || e)); }
        } }, 'Remove')));
    }

    // add: an APK from this computer (uploaded to Home Assistant, then sent on) or from a folder Home Assistant reads
    const file = h('input', { type: 'file', accept: '.apk,application/vnd.android.package-archive' });
    const path = h('input', { type: 'text', placeholder: '/config/www/app.apk', style: 'min-width:260px' });
    const status = h('div');
    let pct = null, msg = '', cls = '';
    if (this.uploading) { pct = this.uploading.pct; msg = `Uploading to Home Assistant… ${Math.round(this.uploading.pct)} %`; }
    else if (send.state === 'sending') { pct = send.size ? 100 * send.sent / send.size : 0; msg = `Sending ${send.name || 'the APK'} to the Echo… ${Math.round(pct)} %`; }
    else if (send.state === 'failed') { msg = 'Not sent to the Echo: ' + send.error; cls = 'bad'; }
    else if (send.op === 'uninstall' && (st.state === 'installing' || st.state === 'receiving')) { msg = `Removing ${send.package}…`; }
    else if (send.op === 'uninstall' && st.state === 'ok') { msg = `Removed ${send.package}.`; cls = 'good'; }
    else if (st.state === 'receiving' || st.state === 'installing') { msg = 'Installing on the Echo…'; }
    else if (st.state === 'ok' && st.package) { msg = `Installed ${st.package}. It is off the internet until you switch it on above.`; cls = 'good'; }
    else if (st.state === 'failed') {
      msg = (send.op === 'uninstall' ? `${send.package} not removed: ` : 'Android refused it: ') + (st.error || 'no reason given');
      if (/NO_MATCHING_ABIS/.test(st.error || '')) msg += ' (the Echo Show runs 32-bit ARM apps: armeabi-v7a)';
      if (/OLDER_SDK|MIN_SDK/.test(st.error || '')) msg += ' (the app needs a newer Android than the Echo has: 7.1 on the Show 5)';
      if (/UPDATE_INCOMPATIBLE/.test(st.error || '')) msg += ' (signed by someone else than the installed one: remove it first)';
      cls = 'bad';
    }
    if (msg) status.append(h('div', { class: 'inst ' + cls }, msg));
    if (pct != null) status.append(h('div', { class: 'prog' }, h('div', { style: `width:${Math.max(2, pct)}%` })));

    const upload = () => {
      const f = file.files[0]; if (!f) { this.toast('Pick an APK first'); return; }
      if (f.size > 200 * 1024 * 1024) { this.toast('An APK is 200 MB at most'); return; }
      const xhr = new XMLHttpRequest();
      const echo = this.echo;
      this.uploading = { pct: 0 };
      xhr.upload.onprogress = (ev) => { if (ev.lengthComputable && this.uploading) { this.uploading.pct = 100 * ev.loaded / ev.total; const t = this.shadowRoot.querySelector('.appstab'); if (t && this.tab === 'apps') t.replaceWith(this.appsTab()); } };
      xhr.onloadend = () => {
        this.uploading = null;
        if (xhr.status !== 200) { let m = xhr.statusText; try { m = JSON.parse(xhr.responseText).message || m; } catch (e) { /* not JSON */ } this.toast('Not uploaded: ' + (m || 'no answer')); }
        if (echo === this.echo) this.loadApps();
      };
      (async () => {
        const auth = this._hass.auth; if (auth.expired) await auth.refreshAccessToken();
        xhr.open('POST', `/api/echo_local/apk/${encodeURIComponent(echo)}`);
        xhr.setRequestHeader('Authorization', 'Bearer ' + auth.accessToken);
        xhr.setRequestHeader('Content-Type', 'application/vnd.android.package-archive');
        xhr.send(f);
        this.loadApps();
      })();
    };
    const fromPath = async () => {
      const v = path.value.trim(); if (!v) return;
      try { await this.ws({ type: 'echo_local/apps/install', echo: this.echo, path: v }); this.loadApps(); }
      catch (e) { this.toast('Not installed: ' + ((e && e.message) || e)); }
    };

    box.append(h('div', { class: 'grid' },
      h('div', { class: 'card' }, h('h2', null, 'Apps on this Echo'),
        h('div', { class: 'about' }, 'The apps you installed beside the screen app (not Amazon’s or Android’s own). Each shows on Echo-Wall’s Home and in its switcher. The Echo keeps every app off the internet until you switch it on here.'),
        list, h('div', { style: 'height:12px' })),
      h('div', { class: 'card' }, h('h2', null, 'Add an app'),
        h('div', { class: 'about' }, 'An APK built for 32-bit ARM (armeabi-v7a) and Android 7.1 (the Echo Show 5); up to 200 MB. Installing an app that is there already updates it (same signature).'),
        h('div', { class: 'row' }, h('div', { class: 'head' }, h('span', { class: 'name' }, 'From this computer')),
          h('div', { class: 'add' }, file, h('button', { class: 'btn primary', disabled: busy, onclick: upload }, 'Install'))),
        h('div', { class: 'row' }, h('div', { class: 'head' }, h('span', { class: 'name' }, 'From a file on Home Assistant')),
          h('div', { class: 'help' }, 'A path in a folder Home Assistant may read (allowlist_external_dirs: /config, /media).'),
          h('div', { class: 'add' }, path, h('button', { class: 'btn', disabled: busy, onclick: fromPath }, 'Install'))),
        status)));
    return box;
  }

  screenTab() {
    const k = this.kiosk;
    if (!k) return h('div', { class: 'empty' }, 'Loading…');
    if (k.error) return h('div', { class: 'banner' }, k.error);
    const o = k.draft;
    const dirty = !same(k.saved, k.draft);
    const touch = () => { bar.querySelector('.primary').disabled = same(k.saved, k.draft); bar.querySelector('.status').textContent = same(k.saved, k.draft) ? 'Saved' : 'Unsaved changes'; };
    const bar = h('div', { class: 'bar' },
      h('button', { class: 'btn primary', disabled: !dirty, onclick: () => this.saveKiosk() }, 'Save'),
      h('button', { class: 'btn', onclick: () => { k.draft = clone(k.saved); this.render(); } }, 'Revert'),
      h('span', { class: 'status' + (dirty ? ' dirty' : '') }, dirty ? 'Unsaved changes' : 'Saved'),
      h('span', { class: 'grow' }), h('span', { class: 'note' }, 'The Echo reaches Home Assistant at ' + k.url));
    const p = k.push || {};
    const pst = h('div', { class: 'pushst' + (p.at && !p.ok ? ' bad' : '') },
      h('span', { class: 'grow' }, !p.at ? 'Not sent to the Echo since Home Assistant started (it keeps what it had).'
        : p.ok ? `Sent to the Echo ${ago(p.at)}` + (p.kiosk ? `: ${p.screens} screen${p.screens === 1 ? '' : 's'} and a fresh login.` : ': the screen off.')
        : `Not sent to the Echo (${ago(p.at)}): ${p.error}`),
      h('button', { class: 'btn small', onclick: async (ev) => {
        ev.target.disabled = true;
        try { const r = await this.ws({ type: 'echo_local/kiosk/push', echo: this.echo }); k.push = r.push; this.toast('Sent to the Echo'); }
        catch (e) { this.toast('Not sent: ' + ((e && e.message) || e)); await this.loadKiosk(); return; }
        this.render();
      } }, 'Send to the Echo again'));
    const row = (name, ctl, help) => h('div', { class: 'row' }, h('div', { class: 'head' }, h('span', { class: 'name' }, name), ctl), help && h('div', { class: 'help' }, help));
    const text = (key, ph, type) => { const i = h('input', { type: type || 'text', placeholder: ph || '', style: 'min-width:240px' }); i.value = o[key] || ''; i.addEventListener('input', () => { o[key] = i.value; touch(); }); return i; };
    const sw = (key) => this.switch(!!o[key], (on) => { o[key] = on; touch(); });

    const scr = (o.kiosk_screens || ['wall', 'dashboard']).slice();
    const screens = h('div', { class: 'list screens' });
    const drawScreens = () => {
      screens.textContent = '';
      const order = [...scr, ...k.kinds.filter((x) => !scr.includes(x))];
      order.forEach((kind) => {
        const on = scr.includes(kind), i = scr.indexOf(kind);
        const it = h('div', { class: 'item' },
          h('div', { class: 'nm' }, this.switch(on, (v) => { if (v) scr.push(kind); else scr.splice(scr.indexOf(kind), 1); o.kiosk_screens = scr.slice(); touch(); drawScreens(); }),
            h('span', null, KIND_LABEL[kind] || kind)),
          on && h('button', { class: 'mini', disabled: i === 0, onclick: () => { scr.splice(i - 1, 0, scr.splice(i, 1)[0]); o.kiosk_screens = scr.slice(); touch(); drawScreens(); } }, '↑'),
          on && h('button', { class: 'mini', disabled: i === scr.length - 1, onclick: () => { scr.splice(i + 1, 0, scr.splice(i, 1)[0]); o.kiosk_screens = scr.slice(); touch(); drawScreens(); } }, '↓'));
        screens.append(it);
      });
    };
    drawScreens();
    const def = h('select', { onchange: () => { o.kiosk_default = def.value; touch(); } }, k.kinds.map((x) => h('option', { value: x, selected: (o.kiosk_default || 'wall') === x }, KIND_LABEL[x] || x)));
    const ret = h('input', { type: 'number', min: 0, max: 3600, step: 10 }); ret.value = o.kiosk_return ?? 120;
    ret.addEventListener('input', () => { if (ret.checkValidity() && ret.value !== '') { o.kiosk_return = +ret.value; touch(); } });
    const appSel = h('select', { onchange: () => { o.kiosk_app = appSel.value === '*' ? (o.kiosk_app || '') : appSel.value; appOwn.style.display = appSel.value === '*' ? '' : 'none'; touch(); } },
      KNOWN_APPS.map(([v, l]) => h('option', { value: v, selected: (o.kiosk_app || '') === v }, l)),
      h('option', { value: '*', selected: !KNOWN_APPS.some(([v]) => v === (o.kiosk_app || '')) }, 'Another app (its package)…'));
    const appOwn = text('kiosk_app', 'org.example.screen');
    appOwn.style.display = KNOWN_APPS.some(([v]) => v === (o.kiosk_app || '')) ? 'none' : '';
    const settings = h('textarea', { spellcheck: false, placeholder: 'immich.url=http://192.168.1.9:2283\nimmich.key=…' });
    settings.value = o.kiosk_app_settings || '';
    settings.addEventListener('input', () => { o.kiosk_app_settings = settings.value; touch(); });

    return h('div', null, bar, pst, h('div', { class: 'grid' },
      h('div', { class: 'card' }, h('h2', null, 'On the screen'),
        row('Show Home Assistant on the screen', sw('kiosk')),
        h('div', { class: 'row' }, h('div', { class: 'head' }, h('span', { class: 'name' }, 'Screens')), h('div', { class: 'help' }, 'On, in the order the switcher offers them.'), screens),
        row('Start on, and go back to', def),
        row('Back to it after untouched for', h('span', null, ret, ' ', h('span', { class: 'note' }, 's')), '0: never.'),
        row("Dashboard (Home Assistant's own UI)", text('kiosk_dashboard', 'lovelace'), 'Its path: lovelace is Overview.'),
        row('Music Assistant', text('kiosk_music', k.music || 'its panel’s path or an address')),
        row('Your page’s name', text('kiosk_custom_name', 'Page')),
        row('Your page’s address', text('kiosk_custom_url', 'http://…', 'url'))),
      h('div', { class: 'card' }, h('h2', null, 'The screen app'),
        h('div', { class: 'about' }, 'The Android app that shows the screens (docs/screen-apps.md). Its Home, if it draws one, is under Home screen.'),
        row('App', h('span', null, appSel, ' ', appOwn)),
        h('div', { class: 'row' }, h('div', { class: 'head' }, h('span', { class: 'name' }, 'Its settings')), h('div', { class: 'help' }, 'One key=value a line; sent sealed with the Echo’s login.'), settings),
        row('The Echo’s user is an administrator', sw('kiosk_admin'), 'Home Assistant’s settings on the Echo.'),
        row('Home Assistant’s address for the Echo', text('kiosk_ha_url', k.url), 'Empty: the one found. The Echo reaches local addresses only.'))));
  }
}

customElements.get('echo-local-panel') || customElements.define('echo-local-panel', EchoLocalPanel);
