#!/usr/bin/env python3
"""Home screens (custom_components/echo_local home.py, frontend/panel.js; docs/home-screens.md) in a real Home Assistant
against build/hassmic-host: the wall panel's store of before (version 1) migrated; the sidebar panel registered for
administrators; the slots per Echo and app over the websocket, checked by each app's descriptor (Echo-Wall's own keys
kept, a wrong value refused, the size cap); the Echo's kiosk user only at its own Echo's slots, whatever it names; an
app's own descriptor; the screen's options set from the panel's command and sent on to the Echo; then the panel in
headless Chrome as an administrator: the Echo listed, the wall panel's preview drawn from the draft, an import from
another app by what both share, Save, the layout in Home Assistant; an edit made in the preview's own edit mode reaching
the draft.  build/test-logs/panel.png shows the panel for the eye.

Same isolation and Home Assistant as tests/ha_real_kiosk.py.  Chrome: google-chrome or chromium on PATH (else that
part is skipped)."""
import asyncio, base64, json, os, shutil, signal, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ha_real_dropin as hr
import ha_real_alarms as ra
import ha_real_kiosk as rk
from ha_real_dropin import check

NODE = "echo-show-5-a1b2c3"
EW = "io.github.nt_f.echowall"


def write_config(conf):
    rk.write_config(conf)
    # the wall panel's layouts as wall.py kept them (store version 1)
    json.dump({"version": 1, "minor_version": 1, "key": "echo_local.wall", "data": {"layouts": {
        NODE: {"theme": "dusk", "favorites": ["light.bed_light"], "ambient": 30}, "default": {"theme": "light"}}}},
        open(os.path.join(conf, ".storage", "echo_local.wall"), "w"))


async def as_user(session, token):
    c = hr.Client(session, token)
    c.sock = await session.ws_connect(f"{hr.HA}/api/websocket")
    await c.sock.receive_json(); await c.sock.send_json({"type": "auth", "access_token": token})
    check((await c.sock.receive_json()).get("type") == "auth_ok", "the kiosk's token on the websocket")
    return c


async def fails(coro):
    try:
        await coro
        return ""
    except RuntimeError as e:
        return str(e)


async def browser(session, token, png):
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        print("note: no Chrome here, the panel is not drawn"); return None
    prof = tempfile.mkdtemp(prefix="panel-chrome-")
    proc = subprocess.Popen([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=9334",
                             f"--user-data-dir={prof}", "--window-size=1500,1000", "--force-device-scale-factor=1", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                async with session.get("http://127.0.0.1:9334/json") as r:
                    tabs = await r.json(); break
            except Exception: await asyncio.sleep(0.2)
        page = next(t for t in tabs if t.get("type") == "page")
        ws = await session.ws_connect(page["webSocketDebuggerUrl"], max_msg_size=0)
        n = [0]
        async def cdp(method, **params):
            n[0] += 1; i = n[0]
            await ws.send_json({"id": i, "method": method, "params": params})
            while True:
                m = await ws.receive_json()
                if m.get("id") == i: return m.get("result", m.get("error"))
        async def js(expr):
            r = await cdp("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
            if r and r.get("exceptionDetails"): return {"error": json.dumps(r["exceptionDetails"])[:400]}
            return (r.get("result") or {}).get("value")
        await cdp("Page.enable")
        await cdp("Emulation.setDeviceMetricsOverride", width=1500, height=1000, deviceScaleFactor=1, mobile=False)
        await cdp("Page.navigate", url=f"{hr.HA}/echo_local/panel-test-404")
        await asyncio.sleep(1)
        tokens = {"access_token": token, "token_type": "Bearer", "expires_in": 1800, "hassUrl": hr.HA,
                  "clientId": hr.HA + "/", "expires": 4102444800000, "refresh_token": ""}
        await js(f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(tokens))})")
        await cdp("Page.navigate", url=f"{hr.HA}/echo-local")
        # Home Assistant's frontend, down to our element in its shadow roots
        find = """(() => { const walk = (r) => { if (!r) return null; const p = r.querySelector('echo-local-panel'); if (p) return p;
            for (const e of r.querySelectorAll('*')) { if (e.shadowRoot) { const f = walk(e.shadowRoot); if (f) return f; } } return null; };
            return walk(document); })()"""
        out = {}
        for _ in range(80):
            await asyncio.sleep(0.5)
            out = await js(f"""(() => {{ const p = {find}; if (!p) return {{}}; const r = p.shadowRoot;
                const f = r.querySelector('iframe'); let tiles = 0; try {{ tiles = f.contentDocument.querySelectorAll('.w').length; }} catch (e) {{}}
                return {{ echos: [...r.querySelectorAll('.echo .t')].map(e => e.textContent), apps: [...r.querySelectorAll('.chip')].map(e => e.textContent),
                         fields: r.querySelectorAll('.card .row').length, iframe: !!f, tiles,
                         theme: f && f.contentDocument ? f.contentDocument.documentElement.dataset.theme || '' : '' }}; }})()""") or {}
            if out.get("tiles", 0) > 2: break
        async def shot(name):
            r = await cdp("Page.captureScreenshot", format="png")
            if r and r.get("data"):
                os.makedirs(os.path.dirname(png), exist_ok=True); open(png.replace(".png", name + ".png"), "wb").write(base64.b64decode(r["data"]))
        await shot("")
        # another app's Home into the wall panel's, by what both share (Echo-Wall's "light" wallpaper = the wall's theme)
        out["import"] = await js(f"""(async () => {{ const p = {find};
            p.take('{EW}', {{ wallpaper: 'light', now_playing: false, favorites: ['light.kitchen_lights', 'light.ceiling_lights'], place: {{}} }}, null, 'a test');
            await new Promise(r => setTimeout(r, 1200));
            const f = p.shadowRoot.querySelector('iframe');
            return {{ dirty: p.dirty(), draft: p.cur().draft, theme: f.contentDocument.documentElement.dataset.theme || '',
                     save: !p.shadowRoot.querySelector('.bar .primary').disabled }}; }})()""")
        await shot("-import")
        out["saved"] = await js(f"""(async () => {{ const p = {find}; p.shadowRoot.querySelector('.bar .primary').click();
            await new Promise(r => setTimeout(r, 1500)); return {{ dirty: p.dirty(), status: p.shadowRoot.querySelector('.bar .status').textContent }}; }})()""")
        # the preview's own edit mode: a hide (⊖ on a room's tile) comes back as the draft, not saved
        out["edit"] = await js(f"""(async () => {{ const p = {find}; const f = p.shadowRoot.querySelector('iframe');
            f.contentWindow.echoLocalWallEdit(true); await new Promise(r => setTimeout(r, 500));
            const d = f.contentDocument; const t = [...d.querySelectorAll('.page')].find(x => x.dataset.name !== 'Home');
            const b = t && t.querySelector('.w[data-id] .badge.hide'); const id = b && b.closest('.w').dataset.id; if (b) b.click();
            await new Promise(r => setTimeout(r, 500));
            return {{ id, hidden: (p.cur().draft.hidden || []), dirty: p.dirty() }}; }})()""")
        out["export"] = await js(f"""(() => {{ const p = {find}; let doc; const o = URL.createObjectURL;
            URL.createObjectURL = (b) => {{ b.text().then(t => window.__exp = t); return 'blob:x'; }};
            p.exportFile(); URL.createObjectURL = o; return true; }})()""")
        await asyncio.sleep(0.5)
        out["exported"] = json.loads(await js("window.__exp || '{}'") or "{}")
        out["screen"] = await js(f"""(async () => {{ const p = {find}; p.tab = 'screen'; await p.loadKiosk();
            await new Promise(r => setTimeout(r, 300)); return [...p.shadowRoot.querySelectorAll('.card .row .name')].map(e => e.textContent); }})()""")
        await asyncio.sleep(0.5); await shot("-screen")
        return out
    finally:
        proc.terminate()
        try: proc.wait(10)
        except subprocess.TimeoutExpired: proc.kill()
        shutil.rmtree(prof, ignore_errors=True)


async def run(tmp):
    import aiohttp
    conf = os.path.join(tmp, "ha")
    write_config(conf)
    net = f"{int.from_bytes(os.urandom(8), 'little') | 1:016x} " + base64.b64encode(os.urandom(32)).decode()
    echo = hr.Echo(tmp, "Echo Show 5 a1b2c3", "02:00:00:a1:b2:c3", 26190, net, os.path.join(hr.ROOT, "build", "hassmic-host"))
    halog = open(os.path.join(tmp, "ha.log"), "w")
    hass = subprocess.Popen([hr.HA_PY, "-m", "homeassistant", "-c", conf, "--skip-pip"], stdout=halog, stderr=subprocess.STDOUT, cwd=conf)
    apps = os.path.join(tmp, "apps"); os.makedirs(os.path.join(apps, "io.github.gamer92000.echodotassist.kiosk"))
    os.environ["HASSMIC_APP_DATA"] = apps
    echo.start()
    web = f"http://127.0.0.1:{echo.port + 10}"
    try:
        async with aiohttp.ClientSession() as session:
            for _ in range(240):
                try:
                    async with session.get(f"{hr.HA}/api/onboarding") as r:
                        if r.status == 200: break
                except aiohttp.ClientError: pass
                if hass.poll() is not None: raise RuntimeError("Home Assistant ended")
                await asyncio.sleep(0.5)
            admin_tok = await hr.onboard(session)
            c = hr.Client(session, admin_tok); await c.ws_open()
            f = await ra.add_echo_local(c, echo)
            check(f.get("type") == "create_entry", f"Echo Local added ({f.get('type')})")
            await asyncio.sleep(2)
            areas = {a["name"]: a["area_id"] for a in await c.ws(type="config/area_registry/list")}
            for n in ("Kitchen", "Living Room"):
                if n not in areas: areas[n] = (await c.ws(type="config/area_registry/create", name=n))["area_id"]
            reg = {e["entity_id"]: e for e in await c.ws(type="config/entity_registry/list")}
            for eid, a in {"light.ceiling_lights": "Living Room", "light.kitchen_lights": "Kitchen", "light.bed_light": "Living Room",
                           "switch.decorative_lights": "Living Room"}.items():
                if eid not in reg: continue
                if reg[eid].get("device_id"): await c.ws(type="config/device_registry/update", device_id=reg[eid]["device_id"], area_id=areas[a])
                else: await c.ws(type="config/entity_registry/update", entity_id=eid, area_id=areas[a])

            # the store of before, migrated: the wall panel's layouts under app "wall"
            lay = await c.ws(type="echo_local/home/get", echo=NODE, app="wall")
            check(lay == {"theme": "dusk", "favorites": ["light.bed_light"], "ambient": 30}, f"version 1's layout migrated ({lay})")
            old = await c.ws(type="echo_local/wall/get", echo="another-echo")
            check(old == {"theme": "light"}, f"the old command name, the default for an Echo without one ({old})")
            panels = await c.ws(type="get_panels")
            p = panels.get("echo-local") or {}
            check(p.get("component_name") == "custom" and p.get("require_admin") and p.get("title") == "Echo Local"
                  and (p.get("config") or {}).get("_panel_custom", {}).get("module_url") == "/echo_local/panel.js",
                  f"the sidebar panel, administrators only ({ {k: p.get(k) for k in ('component_name', 'require_admin', 'title')} })")
            async with session.get(f"{hr.HA}/echo_local/panel.js") as r:
                check(r.status == 200 and "echo-local-panel" in await r.text(), f"panel.js served ({r.status})")
            lst = await c.ws(type="echo_local/home/list")
            check([e["echo"] for e in lst["echos"]] == [NODE] and "wall" in lst["echos"][0]["slots"] and EW in lst["descriptors"],
                  f"the list: the Echo, its slot, the descriptors ({[e['echo'] for e in lst['echos']]}, {sorted(lst['descriptors'])})")

            # descriptors check what they name, and keep what they do not
            ew = {"wallpaper": "photo", "favorites": None, "hidden": ["switch.decorative_lights"], "place": {"home": {"clock": [0, 0, 0]}},
                  "home_order": ["clock", "date"], "player": "media_player.living_room", "ambient": 90, "analog_clock": False}
            got = await c.ws(type="echo_local/home/set", echo=NODE, app=EW, layout=ew)
            check(got == ew, f"Echo-Wall's layout as it is, its own keys kept ({got})")
            e = await fails(c.ws(type="echo_local/home/set", echo=NODE, app=EW, layout={**ew, "wallpaper": "neon"}))
            check("one of" in e, f"a wallpaper Echo-Wall has not: refused ({e[-80:]})")
            e = await fails(c.ws(type="echo_local/home/set", echo=NODE, app="org.example.big", layout={"x": "y" * 70000}))
            check("KB at most" in e, f"over the size cap: refused ({e[-60:]})")
            e = await fails(c.ws(type="echo_local/home/set", echo=NODE, app="../etc", layout={}))
            check(e != "", "an app id that is no package: refused")

            # the kiosk on: its user and token, as the Echo has them
            r = await c.ws(type="echo_local/kiosk/set", echo=NODE, options={"kiosk": True, "kiosk_screens": ["wall", "dashboard"], "kiosk_default": "wall",
                                                                            "kiosk_return": 60, "kiosk_app": ""})
            check(r["options"].get("kiosk") and r["options"].get("kiosk_return") == 60, f"the screen's options from the panel's command ({r['options']})")
            e = await fails(c.ws(type="echo_local/kiosk/set", echo=NODE, options={"kiosk_screens": ["nonsense"]}))
            check("nonsense" in e or "value" in e, "a screen kind there is none of: refused")
            cfg = {}
            for _ in range(60):
                try:
                    async with session.get(f"{web}/kiosk/config/front") as r:
                        cfg = await r.json()
                    if cfg.get("token") and cfg.get("return") == 60: break
                except aiohttp.ClientError: pass
                await asyncio.sleep(0.5)
            check(cfg.get("return") == 60 and [s["name"] for s in cfg.get("screens", [])] == ["Home", "Home Assistant"],
                  f"... and the entry reloaded: the Echo has them ({cfg.get('return')}, {[s['name'] for s in cfg.get('screens', [])]})")
            k = await as_user(session, cfg.get("token", ""))
            got = await k.ws(type="echo_local/home/get", app=EW)
            check(got.get("place") == ew["place"], "the kiosk's user reads its own Echo's slot without naming it")
            await k.ws(type="echo_local/home/set", echo="another-echo", app=EW, layout={**ew, "ambient": 45})
            mine = await c.ws(type="echo_local/home/get", echo=NODE, app=EW)
            other = await c.ws(type="echo_local/home/get", echo="another-echo", app=EW)
            check(mine.get("ambient") == 45 and other == {}, f"the kiosk's user writes its own Echo's, whatever it names ({mine.get('ambient')}, {other})")
            e = await fails(k.ws(type="echo_local/home/list"))
            check("unauthorized" in e.lower(), "the list: administrators only")
            e = await fails(k.ws(type="echo_local/kiosk/set", echo=NODE, options={"kiosk_admin": True}))
            check("unauthorized" in e.lower(), "the screen's options: administrators only (the kiosk does not make itself one)")
            d = await k.ws(type="echo_local/home/describe", app="org.example.screen",
                           descriptor={"name": "Example", "fields": [{"key": "tint", "type": "select", "label": "Tint", "options": [["a", "A"], ["b", "B"]], "common": "theme"}]})
            check(d == {"builtin": False}, "an app describes its own layout")
            d = await k.ws(type="echo_local/home/describe", app="wall", descriptor={"name": "Mine", "fields": []})
            check(d == {"builtin": True}, "... but not the built-in ones")
            e = await fails(k.ws(type="echo_local/home/set", app="org.example.screen", layout={"tint": "c"}))
            check("one of" in e, "its descriptor checks its layout")
            lst = await c.ws(type="echo_local/home/list")
            check(lst["echos"][0]["descriptors"]["org.example.screen"]["name"] == "Example" and "org.example.screen" not in lst["descriptors"]
                  and lst["descriptors"]["wall"]["name"] == "Wall panel" and lst["echos"][0]["slots"][EW]["by"] == "app",
                  f"the list: the app's descriptor with its Echo, who saved ({lst['echos'][0]['slots'].get(EW)})")
            got = await c.ws(type="echo_local/home/set", echo="another-echo", app="org.example.screen", layout={"tint": "c"})
            check(got == {"tint": "c"}, "... and for its Echo only: another Echo's layouts of that app are not checked by it")
            # live: the wall panel's subscription gets the panel's save
            await k.sock.send_json({"id": 900, "type": "echo_local/home/subscribe", "app": "wall"})
            first = []
            while len(first) < 2:
                m = await k.sock.receive_json()
                if m.get("id") == 900: first.append(m)
            await c.ws(type="echo_local/home/set", echo=NODE, app="wall", layout={"theme": "amber", "favorites": None})
            ev = None
            for _ in range(10):
                m = await asyncio.wait_for(k.sock.receive_json(), 5)
                if m.get("id") == 900 and m.get("type") == "event": ev = m["event"]; break
            check(ev and ev["layout"] == {"theme": "amber", "favorites": None} and ev["echo"] == NODE, f"a subscriber gets the save at once ({ev})")
            await k.sock.close()

            # the frontend's onboarding's last step (hr.onboard leaves it: the other tests use no browser as an administrator)
            async with session.post(f"{hr.HA}/api/onboarding/integration", headers=c.h,
                                    json={"client_id": f"{hr.HA}/", "redirect_uri": f"{hr.HA}/?auth_callback=1"}) as r: pass
            out = await browser(session, admin_tok, os.path.join(hr.ROOT, "build", "test-logs", "panel.png"))
            if out is not None:
                check(out.get("echos", [None])[0] == "Echo Show 5 a1b2c3" and any("Wall panel" in a for a in out.get("apps", []))
                      and any("Echo-Wall" in a for a in out.get("apps", [])), f"the panel: the Echo, its apps ({out.get('echos')}, {out.get('apps')})")
                check(out.get("iframe") and out.get("tiles", 0) > 2 and out.get("fields", 0) >= 7,
                      f"the wall panel's preview drawn, the form from its descriptor ({out.get('tiles')} widgets, {out.get('fields')} rows)")
                im = out.get("import") or {}
                check(im.get("dirty") and (im.get("draft") or {}).get("theme") == "light" and im["draft"].get("nowplaying") is False
                      and im["draft"].get("favorites") == ["light.kitchen_lights", "light.ceiling_lights"] and "place" not in im["draft"]
                      and im.get("theme") == "light" and im.get("save"),
                      f"an import from Echo-Wall by what both share: the draft, the preview following, Save offered ({im})")
                lay = await c.ws(type="echo_local/home/get", echo=NODE, app="wall")
                check(not (out.get("saved") or {}).get("dirty") and lay.get("theme") == "light" and lay.get("favorites") == ["light.kitchen_lights", "light.ceiling_lights"],
                      f"Save: in Home Assistant ({out.get('saved')}, {lay})")
                ed = out.get("edit") or {}
                check(ed.get("id") and ed["id"] in ed.get("hidden", []) and ed.get("dirty") and ed["id"] not in (lay.get("hidden") or []),
                      f"the preview's edit mode edits the draft, not Home Assistant ({ed})")
                x = out.get("exported") or {}
                check(x.get("format") == "echo-local-home" and x.get("app") == "wall" and x.get("echo") == NODE
                      and (x.get("common") or {}).get("theme") == "light" and x.get("layout", {}).get("theme") == "light",
                      f"Export: the file ({ {k: x.get(k) for k in ('format', 'app', 'echo', 'common')} })")
                check("Show Home Assistant on the screen" in (out.get("screen") or []), f"the Screen tab: the kiosk's options ({list(out.get('screen') or [])[:3]})")
    finally:
        echo.stop()
        hass.send_signal(signal.SIGTERM)
        try: hass.wait(30)
        except subprocess.TimeoutExpired: hass.kill()
        log = open(os.path.join(tmp, "ha.log")).read()
        bad = [l for l in log.splitlines() if "echo_local" in l and ("Traceback" in l or "ERROR" in l)]
        check(not bad, f"no errors of echo_local in Home Assistant's log ({bad[:3]})")
        if check.failed:
            print(log[-6000:])


def main():
    if os.environ.get("HASSMIC_IN_NETNS") != "1":
        if not os.path.exists(hr.HA_PY):
            hr.skip(f"no Home Assistant at {hr.HA_PY} (.venv/bin/python tests/ha_real_dropin.py --setup makes one)")
        if not os.path.exists(os.path.join(hr.ROOT, "build", "hassmic-host")): sys.exit("make host first")
        if subprocess.run(["unshare", "-rn", "true"], capture_output=True).returncode:
            hr.skip("unshare -rn is not allowed here (user namespaces)")
        env = dict(os.environ, HASSMIC_IN_NETNS="1")
        sys.exit(subprocess.run(["unshare", "-rn", sys.executable, os.path.abspath(__file__), *sys.argv[1:]], env=env).returncode)
    hr.loopback_up()
    tmp = tempfile.mkdtemp(prefix="ha-home-")
    try: asyncio.run(run(tmp))
    finally: shutil.rmtree(tmp, ignore_errors=True)
    print("FAILED" if check.failed else "all good")
    sys.exit(1 if check.failed else 0)


if __name__ == "__main__":
    main()
