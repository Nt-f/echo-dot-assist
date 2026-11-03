#!/usr/bin/env python3
"""Home screens (custom_components/echo_local home.py, frontend/panel.js; docs/home-screens.md) in a real Home Assistant
against build/hassmic-host: the web wall panel's layouts of before (store version 1) migrated into Echo-Wall's; the
sidebar panel registered for administrators; the slots per Echo and app over the websocket, checked by each app's
descriptor (Echo-Wall's own keys kept, a wrong value refused, the size cap); the Echo's kiosk user only at its own
Echo's slots, whatever it names; an app's own descriptor, for its Echo; the screen's options set from the panel's
command and sent on to the Echo; then the panel in headless Chrome as an administrator: the Echo listed, Echo-Wall's
own WallView as the preview (frontend/echowall/, its lib/preview.dart built for the web) logged in with the panel's
token and drawing this Home Assistant's devices, the draft drawn there, an import from another app by what both
share, Save, the layout in Home Assistant, the preview's edit mode switched from the panel and its edit (a tile hidden)
reaching the draft, not Home Assistant; Export.  The Echo Show's apps (apps.py; the Echo's apps.c with root's
scripts/device/apps.sh and fake_web_apps.py's stand-in pm): the list, internet per app, an APK uploaded by an
administrator and installed, one refused by Android, one from a path, a path outside the allowed folders, removal,
the panel's Apps tab; a replaced entry adopting the screen the Echo shows (kiosk.adopt).  build/test-logs/panel*.png
show it for the eye.

Same isolation and Home Assistant as tests/ha_real_kiosk.py.  Chrome: google-chrome or chromium on PATH (else that
part is skipped)."""
import asyncio, base64, hashlib, json, os, shutil, signal, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ha_real_dropin as hr
import ha_real_alarms as ra
import ha_real_kiosk as rk
from ha_real_dropin import check

NODE = "echo-show-5-a1b2c3"
EW = "io.github.nt_f.echowall"
ICON = "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAEElEQVR4nGN4YGAARwzEcQATUhQB4NTEHgAAAABJRU5ErkJggg=="                    # a 4x4 PNG, as an app's icon


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
        console = []
        async def cdp(method, **params):
            n[0] += 1; i = n[0]
            await ws.send_json({"id": i, "method": method, "params": params})
            while True:
                m = await ws.receive_json()
                if m.get("id") == i: return m.get("result", m.get("error"))
                if m.get("method") == "Runtime.consoleAPICalled":
                    console.append(" ".join(str(a.get("value", a.get("description", ""))) for a in m["params"].get("args", []))[:300])
                elif m.get("method") == "Runtime.exceptionThrown":
                    console.append("exception: " + json.dumps(m["params"]["exceptionDetails"])[:400])
        async def js(expr):
            r = await cdp("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
            if r and r.get("exceptionDetails"): return {"error": json.dumps(r["exceptionDetails"])[:400]}
            return (r.get("result") or {}).get("value")
        await cdp("Page.enable"); await cdp("Runtime.enable")
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
        # the preview's accessibility nodes (lib/preview.dart turns them on): what Echo-Wall drew, by name
        labels = f"""(() => {{ const f = {find}.shadowRoot.querySelector('iframe'); const d = f && f.contentDocument; if (!d) return [];
            return [...d.querySelectorAll('flt-semantics')].map(e => (e.getAttribute('aria-label') || e.textContent || '').trim()).filter(Boolean); }})()"""
        out = {}
        for _ in range(120):
            await asyncio.sleep(0.5)
            out = await js(f"""(() => {{ const p = {find}; if (!p) return {{}}; const r = p.shadowRoot;
                const f = r.querySelector('iframe'); const d = f && f.contentDocument;
                return {{ echos: [...r.querySelectorAll('.echo .t')].map(e => e.textContent), apps: [...r.querySelectorAll('.chip')].map(e => e.textContent),
                         fields: r.querySelectorAll('.card .row').length, flutter: !!(d && d.querySelector('flutter-view')) }}; }})()""") or {}
            out["labels"] = await js(labels) or []
            if out.get("flutter") and len(out["labels"]) > 3: break
        await asyncio.sleep(2)
        out["labels"] = await js(labels) or []
        async def shot(name, clip=None):
            r = await cdp("Page.captureScreenshot", format="png", **({"clip": clip} if clip else {}))
            if r and r.get("data"):
                os.makedirs(os.path.dirname(png), exist_ok=True); open(png.replace(".png", name + ".png"), "wb").write(base64.b64decode(r["data"]))
                return base64.b64decode(r["data"])
        await shot("")
        # the draft drawn: the wallpaper as the form sets it, seen in the iframe's pixels (Flutter draws on a canvas)
        rect = await js(f"(() => {{ const b = {find}.shadowRoot.querySelector('iframe').getBoundingClientRect(); return {{x: b.x, y: b.y, width: b.width, height: b.height, scale: b.width / 960}}; }})()")
        clip = {"x": rect["x"], "y": rect["y"], "width": rect["width"], "height": rect["height"], "scale": 1}
        out["bright"] = {}
        for wp in ("dusk", "light"):
            await js(f"(() => {{ const p = {find}; p.cur().draft.wallpaper = '{wp}'; p.changed(true); }})()")
            await asyncio.sleep(2.5)
            png_ = await shot("-" + wp, clip)
            try:
                from PIL import Image, ImageStat
                import io as _io
                out["bright"][wp] = round(ImageStat.Stat(Image.open(_io.BytesIO(png_)).convert("L")).mean[0])
            except Exception as e:
                out["bright"][wp] = str(e)
        # a dashboard after Home (the form's "Dashboard after Home"): its section a page of its own, drawn natively; a
        # swipe (touch: Flutter pages by touch, not by a mouse's drag) to it
        out["dash_field"] = await js(f"""(async () => {{ const p = {find}; await new Promise(r => setTimeout(r, 300));
            const s = [...p.shadowRoot.querySelectorAll('.card select')].find(x => [...x.options].some(o => o.value === 'dash-test'));
            if (!s) return null; s.value = 'dash-test'; s.dispatchEvent(new Event('change')); return [...s.options].map(o => o.value); }})()""")
        await asyncio.sleep(3)
        async def swipe():
            y = rect["y"] + rect["height"] * .55
            pts = [rect["x"] + rect["width"] * f for f in (.85, .7, .55, .4, .25, .15)]
            await cdp("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": pts[0], "y": y}])
            for x in pts[1:]:
                await asyncio.sleep(.03); await cdp("Input.dispatchTouchEvent", type="touchMove", touchPoints=[{"x": x, "y": y}])
            await cdp("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
            await asyncio.sleep(1.5)
        out["seen"] = list(out["labels"])            # every page swiped past (Home's later pages: the Echo's apps' tiles)
        for _ in range(3):
            await swipe()
            out["dash_labels"] = await js(labels) or []
            out["seen"] += out["dash_labels"]
            if any("Living Room" in l for l in out["dash_labels"]): break
        await shot("-dashboard")
        # the form's Pages after Home (the preview lists them): a page added, a room taken off and shown, the page deleted
        out["pages"] = await js(f"""(async () => {{ const p = {find}; const r = p.shadowRoot; const wait = (ms) => new Promise(x => setTimeout(x, ms));
            const rows = () => [...r.querySelectorAll('.pagesrow .item.page')].map(e => e.textContent);
            const until = async (f) => {{ for (let i = 0; i < 40 && !f(); i++) await wait(250); return f(); }};
            await until(() => rows().length > 0); const at = {{ first: rows() }};
            const nm = r.querySelector('.addpage .pagename'); nm.value = 'Test page'; r.querySelector('.addpage button').click();
            await until(() => (p.pages || []).some(x => x.title === 'Test page' && x.kind === 'own'));
            at.added = {{ pages: p.pages.map(x => x.title), draft: (p.cur().draft.custom_pages || []).map(x => x.name) }};
            const room = p.pages.find(x => x.kind !== 'own'); at.room = room && room.title;
            if (room) {{ [...r.querySelectorAll('.pagesrow .item.page')].find(e => e.textContent.startsWith(room.title)).querySelector('.danger').click();
              await until(() => (p.pages.find(x => x.group === room.group) || {{}}).hidden);
              at.hidden = [...(p.cur().draft.hidden_pages || [])];
              [...r.querySelectorAll('.pagesrow .item.page')].find(e => e.textContent.startsWith(room.title)).querySelector('button:last-child').click();
              await until(() => !(p.pages.find(x => x.group === room.group) || {{}}).hidden); at.shown = [...(p.cur().draft.hidden_pages || [])]; }}
            window.confirm = () => true;
            [...r.querySelectorAll('.pagesrow .item.page')].find(e => e.querySelector('input') && e.querySelector('input').value === 'Test page').querySelector('.danger').click();
            await until(() => !(p.pages || []).some(x => x.title === 'Test page'));
            at.deleted = {{ pages: p.pages.map(x => x.title), draft: (p.cur().draft.custom_pages || []).map(x => x.name) }};
            return at; }})()""")
        await shot("-pages")
        # another app's Home into Echo-Wall's, by what both share (its descriptor: tint = theme, favs = favorites)
        out["import"] = await js(f"""(async () => {{ const p = {find};
            p.take('org.example.screen', {{ tint: 'light', favs: ['light.kitchen_lights', 'light.ceiling_lights'] }}, null, 'a test');
            await new Promise(r => setTimeout(r, 800));
            return {{ dirty: p.dirty(), draft: p.cur().draft, save: !p.shadowRoot.querySelector('.bar .primary').disabled }}; }})()""")
        await shot("-import")
        out["saved"] = await js(f"""(async () => {{ const p = {find}; p.shadowRoot.querySelector('.bar .primary').click();
            await new Promise(r => setTimeout(r, 1500)); return {{ dirty: p.dirty(), status: p.shadowRoot.querySelector('.bar .status').textContent }}; }})()""")
        # the panel's switch: the preview's edit mode; then a − in it (a real click on the canvas, where its node is)
        await js(f"(() => {{ const i = {find}.shadowRoot.querySelector('.pbar .switch input'); i.click(); }})()")
        await asyncio.sleep(1.5)
        minus = await js(f"""(() => {{ const f = {find}.shadowRoot.querySelector('iframe'); const d = f.contentDocument;
            const m = [...d.querySelectorAll('flt-semantics')].find(e => (e.getAttribute('aria-label') || e.textContent || '').trim() === '−');
            if (!m) return null; const b = m.getBoundingClientRect(); return {{ x: b.x + b.width / 2, y: b.y + b.height / 2 }}; }})()""")
        out["edit"] = {"editing": bool(minus)}
        if minus:
            x, y = rect["x"] + minus["x"] * rect["scale"], rect["y"] + minus["y"] * rect["scale"]
            for t in ("mousePressed", "mouseReleased"):
                await cdp("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)
                await asyncio.sleep(0.05)
            await asyncio.sleep(1.5)
            out["edit"].update(await js(f"""(() => {{ const p = {find}; const c = p.cur();
                const changed = Object.keys(Object.assign({{}}, c.draft, c.saved)).filter(k => JSON.stringify(c.draft[k]) !== JSON.stringify(c.saved[k]));
                return {{ dirty: p.dirty(), changed, hidden: changed }}; }})()""") or {})
        await shot("-edit")
        # every card at every size, with this Home Assistant's devices (the preview's gallery)
        out["gallery"] = await js(f"""(async () => {{ const p = {find}; const i = [...p.shadowRoot.querySelectorAll('.pbar .switch input')][1];
            if (!i) return null; i.click(); await new Promise(r => setTimeout(r, 2500)); return true; }})()""")
        out["gallery_labels"] = await js(labels) or []
        await shot("-gallery")
        await js(f"(() => {{ const i = [...{find}.shadowRoot.querySelectorAll('.pbar .switch input')][1]; if (i) i.click(); }})()")
        out["export"] = await js(f"""(() => {{ const p = {find}; const o = URL.createObjectURL;
            URL.createObjectURL = (b) => {{ b.text().then(t => window.__exp = t); return 'blob:x'; }};
            p.exportFile(); URL.createObjectURL = o; return true; }})()""")
        await asyncio.sleep(0.5)
        out["exported"] = json.loads(await js("window.__exp || '{}'") or "{}")
        out["screen"] = await js(f"""(async () => {{ const p = {find}; p.tab = 'screen'; await p.loadKiosk();
            await new Promise(r => setTimeout(r, 300)); return {{ rows: [...p.shadowRoot.querySelectorAll('.card .row .name')].map(e => e.textContent),
              push: (p.shadowRoot.querySelector('.pushst') || {{}}).textContent || '' }}; }})()""")
        await asyncio.sleep(0.5); await shot("-screen")
        out["appstab"] = await js(f"""(async () => {{ const p = {find}; p.tab = 'apps'; p.render(); await p.loadApps();
            await new Promise(r => setTimeout(r, 500)); const r = p.shadowRoot;
            return {{ tabs: [...r.querySelectorAll('.tab')].map(e => e.textContent), apps: [...r.querySelectorAll('.item.app .nm div:first-child')].map(e => e.textContent), icons: r.querySelectorAll('.item.app img.appicon').length,
                     screenApp: [...r.querySelectorAll('.item.app')].filter(e => e.textContent.includes('the screen app')).map(e => e.querySelector('.danger').disabled),
                     status: (r.querySelector('.inst') || {{}}).textContent || '' }}; }})()""")
        await asyncio.sleep(0.3); await shot("-apps")
        out["console"] = console
        open(png.replace(".png", "-console.txt"), "w").write("\n".join(console))
        return out
    finally:
        proc.terminate()
        try: proc.wait(10)
        except subprocess.TimeoutExpired: proc.kill()
        shutil.rmtree(prof, ignore_errors=True)


# the Echo Show's apps: a packages.xml as PackageManager keeps it, and a stand-in pm that installs an "APK" whose first
# line names its package and refuses one starting "bad" as Android refuses a 64-bit only one (fake_web_apps.py's)
PKG = '<package name="{n}" codePath="{c}" publicFlags="{f}" privateFlags="0" ft="1" it="1" ut="{ut}" version="{v}" userId="{u}">\n'
def apps_xml(apps):
    return "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<packages>\n" + "".join(PKG.format(**a) for a in apps) + "</packages>\n"
APPS_PM = r'''#!/bin/sh
X=$PACKAGES_XML
case "$1" in
install) f=$3; head -c 3 "$f" | grep -q bad && { echo "Failure [INSTALL_FAILED_NO_MATCHING_ABIS: no native code]"; exit 1; }
    n=$(head -1 "$f" | sed -n 's/^PK pkg //p')
    grep -v "name=\"$n\"" $X > $X.new
    sed -i '$d' $X.new
    echo "<package name=\"$n\" codePath=\"/data/app/$n-1\" publicFlags=\"0\" privateFlags=\"0\" ft=\"1\" it=\"1\" ut=\"$(date +%s%N)\" version=\"7\" userId=\"10050\">" >> $X.new
    echo "</packages>" >> $X.new; mv $X.new $X; echo Success;;
uninstall) grep -v "name=\"$2\"" $X > $X.new; mv $X.new $X; echo Success;;
esac
'''


async def apps_part(c, session, cfg, conf, root):
    rooter = asyncio.ensure_future(root())
    r = await c.ws(type="echo_local/apps/list", echo=NODE)
    pk = {a["package"]: a for a in r.get("apps", [])}
    check("org.schabi.newpipe" in pk and EW in pk and "com.amazon.webview.chromium" not in pk and not r.get("none"),
          f"the owner's apps, not the system's ({sorted(pk)})")
    await c.ws(type="echo_local/apps/net", echo=NODE, package="org.schabi.newpipe", on=True)
    r = await c.ws(type="echo_local/apps/list", echo=NODE)
    check(any(a["package"] == "org.schabi.newpipe" and a["net"] for a in r["apps"]), "internet for NewPipe switched on")
    e = await fails(k2.ws(type="echo_local/apps/list", echo=NODE)) if (k2 := await as_user(session, cfg.get("token", ""))) else "x"
    check("unauthorized" in e.lower(), "the apps: administrators only")
    async def until_done(want):
        for _ in range(120):
            r = await c.ws(type="echo_local/apps/list", echo=NODE)
            st = (r.get("install") or {}).get("state")
            if (r.get("send") or {}).get("state") != "sending" and st in ("ok", "failed") and want(r): return r
            await asyncio.sleep(0.5)
        return r
    apk = b"PK pkg org.example.app\n" + os.urandom(17 << 20)         # past aiohttp's 16 MB body limit; 69 pieces
    async with session.post(f"{hr.HA}/api/echo_local/apk/{NODE}", data=apk, headers=c.h) as r:
        up = (r.status, await r.json())
    r = await until_done(lambda r: any(a["package"] == "org.example.app" for a in r["apps"]))
    check(up[0] == 200 and up[1].get("size") == len(apk) and r["install"]["state"] == "ok" and r["install"]["package"] == "org.example.app"
          and any(a["package"] == "org.example.app" and not a["net"] for a in r["apps"]),
          f"an APK uploaded, sent in pieces, installed, off the internet ({up}, {r.get('install')}, {r.get('send')})")
    async with session.post(f"{hr.HA}/api/echo_local/apk/{NODE}", data=apk, headers={"Authorization": "Bearer " + cfg.get("token", "")}) as r:
        check(r.status in (401, 403), f"an upload by the kiosk's user: refused ({r.status})")
    bad = os.path.join(conf, "www"); os.makedirs(bad, exist_ok=True); bad = os.path.join(bad, "bad.apk")
    open(bad, "wb").write(b"bad" + os.urandom(1000))
    await c.ws(type="echo_local/apps/install", echo=NODE, path=bad)
    r = await until_done(lambda r: True)
    check(r["install"]["state"] == "failed" and "NO_MATCHING_ABIS" in r["install"].get("error", ""),
          f"one from a path under /config, refused by Android: its reason ({r.get('install')})")
    e = await fails(c.ws(type="echo_local/apps/install", echo=NODE, path="/etc/passwd"))
    check("may read" in e, "a path outside the folders Home Assistant may read: refused")
    await c.ws(type="echo_local/apps/uninstall", echo=NODE, package="org.example.app")
    r = await until_done(lambda r: not any(a["package"] == "org.example.app" for a in r["apps"]))
    check(not any(a["package"] == "org.example.app" for a in r["apps"]), f"removed ({r.get('install')})")
    rooter.cancel()


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
    # the Echo Show's apps: packages.xml, root's apps.sh with the stand-in pm (as fake_web_apps.py has them)
    fwa = type("fwa", (), {"xml": staticmethod(apps_xml), "PM": APPS_PM})
    px, adir, fake = os.path.join(tmp, "packages.xml"), os.path.join(tmp, "appsroot"), os.path.join(tmp, "bin")
    os.makedirs(fake)
    open(px, "w").write(fwa.xml([
        dict(n="org.schabi.newpipe", c="/data/app/org.schabi.newpipe-1", f=671628868, ut="a1", v=1015, u=10005),
        dict(n="io.github.nt_f.echowall", c="/data/app/io.github.nt_f.echowall-1", f=0, ut="a2", v=1, u=10008),
        dict(n="com.amazon.webview.chromium", c="/system/app/AmazonWebView", f=-1207386555, ut="a3", v=60807432, u=10001)]))
    open(os.path.join(fake, "pm"), "w").write(fwa.PM); os.chmod(os.path.join(fake, "pm"), 0o755)
    os.environ.update(HASSMIC_PACKAGES_XML=px, HASSMIC_APPS_RESULT=os.path.join(adir, "result"))
    renv = dict(os.environ, PATH=f"{fake}:{os.environ['PATH']}", APPS_STATE=echo.state, APPS_DIR=adir, PACKAGES_XML=px, READ_AS="env")
    async def root():
        while True:                     # root's watcher (main.sh ota_watch runs apps.sh take on a request)
            await asyncio.get_running_loop().run_in_executor(None, lambda: subprocess.run(
                ["sh", f"{hr.ROOT}/scripts/device/apps.sh", "take"], env=renv, capture_output=True, timeout=60))
            await asyncio.sleep(0.3)
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

            # the store of before, migrated: the web wall panel's layouts became Echo-Wall's
            lay = await c.ws(type="echo_local/home/get", echo=NODE, app=EW)
            check(lay == {"wallpaper": "dusk", "favorites": ["light.bed_light"], "ambient": 30}, f"version 1's wall layout migrated into Echo-Wall's ({lay})")
            e = await fails(c.ws(type="echo_local/wall/get", echo=NODE))
            check("unknown" in e.lower(), "the web wall panel's commands are gone")
            e = await fails(c.ws(type="echo_local/home/get", echo=NODE, app="wall"))
            check(e != "", "... and its app id")
            async with session.get(f"{hr.HA}/echo_local/wall.html") as r:
                check(r.status == 404, f"wall.html is gone ({r.status})")
            async with session.get(f"{hr.HA}/echo_local/echowall/index.html") as r:
                t = await r.text()
            async with session.get(f"{hr.HA}/echo_local/echowall/main.dart.js") as r2:
                n = len(await r2.read())
            check(r.status == 200 and "flutter_bootstrap.js" in t and r2.status == 200 and n > 500000,
                  f"Echo-Wall's preview served ({r.status}, main.dart.js {n} bytes)")
            panels = await c.ws(type="get_panels")
            p = panels.get("echo-local") or {}
            check(p.get("component_name") == "custom" and p.get("require_admin") and p.get("title") == "Echo Local"
                  and (p.get("config") or {}).get("_panel_custom", {}).get("module_url") == "/echo_local/panel.js",
                  f"the sidebar panel, administrators only ({ {k: p.get(k) for k in ('component_name', 'require_admin', 'title')} })")
            async with session.get(f"{hr.HA}/echo_local/panel.js") as r:
                check(r.status == 200 and "echo-local-panel" in await r.text(), f"panel.js served ({r.status})")
            lst = await c.ws(type="echo_local/home/list")
            check([e["echo"] for e in lst["echos"]] == [NODE] and EW in lst["echos"][0]["slots"] and EW in lst["descriptors"]
                  and "wall" not in lst["descriptors"] and lst["descriptors"][EW].get("preview") == "/echo_local/echowall/index.html",
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
                                                                            "kiosk_return": 60, "kiosk_app": EW})
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
            check(cfg.get("return") == 60 and [(s["name"], s["url"][:13]) for s in cfg.get("screens", [])] == [("Home", "hassmic:home"), ("Home Assistant", hr.HA[:13])],
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
                           descriptor={"name": "Example", "fields": [{"key": "tint", "type": "select", "label": "Tint", "options": [["a", "A"], ["light", "B"]], "common": "theme"},
                                                                      {"key": "favs", "type": "entities", "label": "Tiles", "common": "favorites"}]})
            check(d == {"builtin": False}, "an app describes its own layout")
            d = await k.ws(type="echo_local/home/describe", app=EW, descriptor={"name": "Mine", "fields": []})
            check(d == {"builtin": True}, "... but not the built-in ones")
            e = await fails(k.ws(type="echo_local/home/set", app="org.example.screen", layout={"tint": "c"}))
            check("one of" in e, "its descriptor checks its layout")
            lst = await c.ws(type="echo_local/home/list")
            check(lst["echos"][0]["descriptors"]["org.example.screen"]["name"] == "Example" and "org.example.screen" not in lst["descriptors"]
                  and lst["descriptors"][EW]["name"] == "Echo-Wall" and lst["echos"][0]["slots"][EW]["by"] == "app",
                  f"the list: the app's descriptor with its Echo, who saved ({lst['echos'][0]['slots'].get(EW)})")
            got = await c.ws(type="echo_local/home/set", echo="another-echo", app="org.example.screen", layout={"tint": "c"})
            check(got == {"tint": "c"}, "... and for its Echo only: another Echo's layouts of that app are not checked by it")
            # live: the app's subscription (Echo-Wall's layout_sync.dart) gets the panel's save
            await k.sock.send_json({"id": 900, "type": "echo_local/home/subscribe", "app": EW})
            first = []
            while len(first) < 2:
                m = await k.sock.receive_json()
                if m.get("id") == 900: first.append(m)
            await c.ws(type="echo_local/home/set", echo=NODE, app=EW, layout={"wallpaper": "dusk", "favorites": None, "place": ew["place"]})
            ev = None
            for _ in range(10):
                m = await asyncio.wait_for(k.sock.receive_json(), 5)
                if m.get("id") == 900 and m.get("type") == "event": ev = m["event"]; break
            check(ev and ev["layout"] == {"wallpaper": "dusk", "favorites": None, "place": ew["place"]} and ev["echo"] == NODE, f"a subscriber gets the save at once ({ev})")
            await k.sock.close()
            # the Echo's Android apps as Echo-Wall lists them (layout_sync.dart publishApps): for the preview's tiles
            k = await as_user(session, cfg.get("token", ""))
            await k.ws(type="echo_local/home/apps/set", echo="another-echo", apps=[{"package": "org.schabi.newpipe", "label": "NewPipe", "icon": ICON}])
            la = await c.ws(type="echo_local/home/apps/get", echo=NODE)
            check([a["label"] for a in la.get("apps", [])] == ["NewPipe"] and la["apps"][0]["icon"] == ICON
                  and (await c.ws(type="echo_local/home/apps/get", echo="another-echo"))["apps"] == [],
                  f"the kiosk's user sends its Echo's apps, for its own Echo only ({[a['label'] for a in la.get('apps', [])]})")
            e = await fails(k.ws(type="echo_local/home/apps/set", apps=[{"package": "not a package", "label": "x"}]))
            check("invalid" in e.lower() or "match" in e.lower(), f"... checked ({e[:80]})")
            await k.sock.close()

            # ---- the Echo Show's apps (where the Echo side, apps.c and root's apps.sh, is in this tree)
            if not os.path.exists(f"{hr.ROOT}/scripts/device/apps.sh"):
                print("note: no scripts/device/apps.sh here: the apps part is skipped")
            else:
                await apps_part(c, session, cfg, conf, root)

            # a replaced entry: the screen the Echo shows taken over (kiosk.adopt, Home Assistant's own Python)
            code = ("import json, sys; sys.path.insert(0, sys.argv[1]); from echo_local import kiosk; print(json.dumps(kiosk.adopt(None, json.loads(sys.argv[2]))))")
            old = {"enabled": True, "ha": "http://192.168.1.211:8123", "app": EW, "default": 0, "return": 90,
                   "screens": [{"name": "Home", "url": "http://192.168.1.211:8123/hassmic/wall.html?echo=x"},
                               {"name": "Music", "url": "http://192.168.1.211:8123/d5369777_music_assistant"},
                               {"name": "Home Assistant", "url": "http://192.168.1.211:8123/dashboard-wall"}]}
            o = subprocess.run([hr.HA_PY, "-c", code, os.path.join(conf, "custom_components"), json.dumps(old)], capture_output=True, text=True)
            ad = json.loads(o.stdout or "null") if o.returncode == 0 else o.stderr[-300:]
            check(isinstance(ad, dict) and ad.get("kiosk") and ad.get("kiosk_screens") == ["wall", "music", "dashboard"] and ad.get("kiosk_app") == EW
                  and ad.get("kiosk_music") == "d5369777_music_assistant" and ad.get("kiosk_dashboard") == "dashboard-wall" and ad.get("kiosk_return") == 90,
                  f"the Echo's screen adopted by a new entry ({ad})")
            o = subprocess.run([hr.HA_PY, "-c", code, os.path.join(conf, "custom_components"), json.dumps({**old, "enabled": False})], capture_output=True, text=True)
            check(o.stdout.strip() == "null", "... none while the Echo's screen is off")
            kg = await c.ws(type="echo_local/kiosk/get", echo=NODE)
            check((kg.get("push") or {}).get("ok") and kg["push"].get("kiosk"), f"the last push's outcome for the panel ({kg.get('push')})")
            r = await c.ws(type="echo_local/kiosk/push", echo=NODE)
            check((r.get("push") or {}).get("ok"), f"Send to the Echo again ({r})")

            # a sections dashboard for the preview to draw natively (as Home Assistant's editor saves one)
            await c.ws(type="lovelace/dashboards/create", url_path="dash-test", title="Test dashboard", mode="storage", show_in_sidebar=False, require_admin=False)
            await c.ws(type="lovelace/config/save", url_path="dash-test", config={"views": [{"title": "Home", "type": "sections", "sections": [
                {"type": "grid", "cards": [{"type": "heading", "heading": "Living Room"}, {"type": "tile", "entity": "light.ceiling_lights"},
                                           {"type": "thermostat", "entity": "climate.ecobee"}, {"type": "custom:mushroom-chips-card"}]}]}]})

            # the frontend's onboarding's last step (hr.onboard leaves it: the other tests use no browser as an administrator)
            async with session.post(f"{hr.HA}/api/onboarding/integration", headers=c.h,
                                    json={"client_id": f"{hr.HA}/", "redirect_uri": f"{hr.HA}/?auth_callback=1"}) as r: pass
            out = await browser(session, admin_tok, os.path.join(hr.ROOT, "build", "test-logs", "panel.png"))
            if out is not None:
                check(out.get("echos") == ["Echo Show 5 a1b2c3"] and any("Echo-Wall" in a and "on the screen" in a for a in out.get("apps", [])),
                      f"the panel: the Echo, Echo-Wall on its screen ({out.get('echos')}, {out.get('apps')})")
                check(out.get("flutter") and out.get("fields", 0) >= 9, f"Echo-Wall's own preview started, the form from its descriptor ({out.get('fields')} rows)")
                check("NewPipe" in " ".join(out.get("seen", [])), f"the preview draws the Echo's Android apps as Echo-Wall sent them ({[l for l in out.get('seen', []) if len(l) < 40][:24]})")
                check(any(n in " ".join(out.get("labels", [])) for n in ("Kitchen", "Living Room", "Ceiling Lights")),
                      f"the preview logged in with the panel's token: this Home Assistant's rooms and devices drawn ({out.get('labels', [])[:12]})")
                check(out.get("bright", {}).get("light", 0) > out.get("bright", {}).get("dusk", 255) + 30,
                      f"the draft drawn in the preview: the light wallpaper lighter than dusk ({out.get('bright')})")
                im = out.get("import") or {}
                check(im.get("dirty") and (im.get("draft") or {}).get("wallpaper") == "light"
                      and im["draft"].get("favorites") == ["light.kitchen_lights", "light.ceiling_lights"] and "tint" not in im["draft"]
                      and (im["draft"].get("place") or {}) == ew["place"] and im.get("save"),
                      f"an import from another app by what both share, Echo-Wall's own keys kept, Save offered ({im})")
                lay = await c.ws(type="echo_local/home/get", echo=NODE, app=EW)
                check(not (out.get("saved") or {}).get("dirty") and lay.get("wallpaper") == "light" and lay.get("favorites") == ["light.kitchen_lights", "light.ceiling_lights"]
                      and lay.get("dashboard") == "dash-test",
                      f"Save: in Home Assistant ({out.get('saved')}, {lay})")
                ed = out.get("edit") or {}
                lay2 = await c.ws(type="echo_local/home/get", echo=NODE, app=EW)
                check(ed.get("editing") and ed.get("changed") and ed.get("dirty") and lay2 == lay,
                      f"the panel's switch: the preview's edit mode; a tile hidden there reaches the draft, not Home Assistant ({ed})")
                check(out.get("dash_field") and "dash-test" in out["dash_field"] and "lovelace" in out["dash_field"],
                      f"the form's dashboard field: Home Assistant's dashboards ({out.get('dash_field')})")
                dl = " ".join(out.get("dash_labels") or [])
                check("Living Room" in dl and "Ceiling Lights" in dl and "Ecobee" in dl and "Mushroom chips card" in dl,
                      f"the dashboard's section a page after Home, drawn natively: a tile, a thermostat, a card it cannot draw ({dl[:200]})")
                gl = " ".join(out.get("gallery_labels") or [])
                check(out.get("gallery") and "Analog clock" in gl and "Large · 2x2" in gl and "Thermostat" in gl,
                      f"Card sizes: every card at every size in the preview ({gl[:160]})")
                x = out.get("exported") or {}
                check(x.get("format") == "echo-local-home" and x.get("app") == EW and x.get("echo") == NODE
                      and (x.get("common") or {}).get("theme") == "light" and x.get("layout", {}).get("wallpaper") == "light",
                      f"Export: the file ({ {k: x.get(k) for k in ('format', 'app', 'echo', 'common')} })")
                scr = out.get("screen") or {}
                check("Show Home Assistant on the screen" in scr.get("rows", []) and "Sent to the Echo" in scr.get("push", ""),
                      f"the Screen tab: the kiosk's options, the last push ({scr.get('rows', [])[:2]}, {scr.get('push')!r})")
                pg = out.get("pages") or {}
                check(pg.get("first") and "Test page" in (pg.get("added") or {}).get("pages", []) and (pg.get("added") or {}).get("draft") == ["Test page"]
                      and pg.get("room") and len(pg.get("hidden") or []) == 1 and pg.get("shown") == []
                      and "Test page" not in (pg.get("deleted") or {}).get("pages", ["Test page"]) and (pg.get("deleted") or {}).get("draft") == [],
                      f"Pages after Home in the form: added (the preview has it), a room taken off and shown, deleted ({pg})")
                ap = out.get("appstab") or {}
                check("Apps" in ap.get("tabs", []) and "NewPipe" in ap.get("apps", []) and ap.get("icons", 0) >= 1 and ap.get("screenApp") == [True]
                      and ap.get("status", "").startswith("Removed org.example.app"),
                      f"the Apps tab: the apps by the names and icons Echo-Wall sent, Remove off for the screen app ({ap})")
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
