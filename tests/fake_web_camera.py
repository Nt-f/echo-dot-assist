#!/usr/bin/env python3
"""The camera (camera.c, web.c GET /api/camera/stream; docs/camera.md) against build/hassmic-host with the PC's stand-in
camera (tests/fake_camera.py), read by the Echo Local integration's own client (custom_components/echo_local/api.py)
and muxed by its tsmux.py: off by default and refused then; switched on, records sealed per stream that decrypt and
mux into an MPEG-TS ffprobe reads at the camera's own rate; one viewer at a time; unsigned, forged and replayed
requests refused; the camera process gone when the viewer goes, the lens is covered or the setting goes off; not in
an export; a camera that does not open ends the stream at once; the page answers meanwhile."""
import asyncio, http.client, json, os, re, shutil, subprocess, sys, tempfile, time
import aiohttp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from webclient import wait_port, Browser, req

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "custom_components", "echo_local"))
import api, tsmux                                               # noqa: E402  (the integration's modules, no Home Assistant needed)

PORT, WEB = 16991, 16992


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: check.failed = True
check.failed = False


async def until(cond, secs=5):
    end = time.monotonic() + secs
    while not cond() and time.monotonic() < end: await asyncio.sleep(0.05)
    return cond()


def status_only(headers):
    """a stream request's status alone, the connection closed right after (req() would read an endless body)"""
    c = http.client.HTTPConnection("127.0.0.1", WEB, timeout=15)
    c.request("GET", "/api/camera/stream", headers=headers)
    st = c.getresponse().status; c.close()
    return st


async def take(echo, secs=None, n=None):
    """records of one stream: for secs, or n of them; (records, error)"""
    out, end = [], time.monotonic() + (secs or 30)
    try:
        async for r in echo.camera_stream():
            out.append(r)
            if (n and len(out) >= n) or time.monotonic() > end: break
    except api.EchoError as e:
        return out, str(e)
    return out, None


# The face's eyes (camera.c face_thread, setting eyes_follow): build/hassmic-host-screen with a stand-in UI that says
# "faceview" when a file says so and logs what it is sent
UI = r"""
import os, re, sys, threading, time
d = sys.argv[1]
log = open(os.path.join(d, "ui.log"), "ab", buffering=0)
out = threading.Lock()
def tell(b):
    with out: sys.stdout.buffer.write(b); sys.stdout.buffer.flush()
tell(b"ready 960 470\n")
def faceview():
    was = None
    while True:
        try: v = open(os.path.join(d, "faceview")).read().strip()
        except OSError: v = "0"
        if v != was: tell(b"faceview " + v.encode() + b"\n"); was = v
        time.sleep(0.1)
threading.Thread(target=faceview, daemon=True).start()
carry = b""
while True:
    b = sys.stdin.buffer.read1(65536)
    if not b: break
    log.write(b); buf = carry + b
    for m in re.finditer(rb"ping (\d+)\n", buf): tell(b"pong " + m.group(1) + b"\n")
    carry = buf[-24:]
"""


async def eyes(state0, env0, b0):
    state = tempfile.mkdtemp(); camlog = os.path.join(state, "camera.log"); lens = os.path.join(state, "lens")
    open(lens, "w").write("0\n"); open(os.path.join(state, "faceview"), "w").write("0")
    face = os.path.join(state, "face"); open(face, "w").write("-400 -200 -200 100 98")    # left of the picture, high
    ui = os.path.join(state, "ui.py"); open(ui, "w").write(UI)
    runner = os.path.join(state, "ui.sh"); open(runner, "w").write(f"#!/bin/sh\nexec {sys.executable} {ui} {state}\n"); os.chmod(runner, 0o755)
    open(os.path.join(state, "config"), "w").write("eyes_follow=on\n")
    env = dict(env0, HASSMIC_STATE=state, HASSMIC_FAKE_LENS=lens, FAKE_CAMERA_LOG=camlog, FAKE_CAMERA_FACE=face, HASSMIC_SCREEN=runner,
               HASSMIC_MUSIC=os.path.join(state, "music.raw"))
    env.pop("FAKE_CAMERA_FAIL", None)
    log = os.path.join(state, "log")
    proc = subprocess.Popen([f"{ROOT}/build/hassmic-host-screen", "-P", "esphome", "-p", str(PORT), "-n", "Echo Eyes", "-z", "0", "-o", "0",
                             "-a", "16993", "-W", str(WEB)], env=env, stderr=open(log, "w"))
    txt = lambda f: open(f, errors="replace").read() if os.path.exists(f) else ""      # (the UI log has the band's rows)
    looks = lambda: re.findall(r"look (-?\d+) (-?\d+)\n", txt(os.path.join(state, "ui.log")))   # (after a band row's bytes, maybe)
    try:
        wait_port(PORT, WEB)
        await asyncio.sleep(1.5)
        check("face" not in txt(camlog), "eyes_follow on, the face not shown: no camera")
        open(os.path.join(state, "faceview"), "w").write("1")
        check(await until(lambda: "face 0" in txt(camlog), 5), "the face shown: the camera in face mode, without the dot (HMCAM_DOT=0)")
        check(await until(lambda: len(looks()) > 0, 5) and looks()[0] == ("300", "-50"),
              f"the nearest face to the UI, x turned round for the viewer: {looks()[:2]}")
        open(face, "w").write("-400 -200 -200 100 98 100 100 500 500 90")   # a second, larger face: that one
        check(await until(lambda: ("-300", "300") in looks(), 3), f"two faces: the larger one ({looks()[-1:]})")
        open(face, "w").write("")
        n = len(looks()); await asyncio.sleep(1)
        check(len(looks()) == n, "nobody there: no looks (the UI's own glances again after 1.5 s)")
        open(face, "w").write("-400 -200 -200 100 98")
        # a stream from Home Assistant takes the camera from the eyes, and gives it back
        b = b0.at(WEB)
        check(b.login_with_button(proc), "logged in")
        async with aiohttp.ClientSession() as s:
            echo = api.Echo(s, "127.0.0.1", WEB, b.sk.private_bytes_raw().hex())
            await echo.set("camera=on\n")
            recs, err = await take(echo, secs=2)
            c = txt(camlog)
            check(err is None and recs and c.index("face stop") < c.index("start\n", c.index("face 0")),
                  f"a stream: the eyes let the camera go first ({len(recs)} records)")
        check(await until(lambda: txt(camlog).count("face 0") == 2, 5), "the stream over: the eyes again")
        open(os.path.join(state, "faceview"), "w").write("0")
        check(await until(lambda: txt(camlog).count("face stop") == 2, 4), "the face not shown: the camera off")
        open(os.path.join(state, "faceview"), "w").write("1")
        await until(lambda: txt(camlog).count("face 0") == 3, 5)
        open(lens, "w").write("1\n")
        check(await until(lambda: txt(camlog).count("face stop") == 3, 4), "the lens covered: the eyes' camera off")
        st = json.loads(b.call("GET", "/api/state")[2])
        check(any(x["name"] == "eyes_follow" for x in st["settings"]), "the page has the setting")
        check("eyes_follow=" not in b.call("GET", "/api/export")[2].decode(), "not in an export")
    finally:
        proc.terminate()
        try: proc.wait(5)
        except subprocess.TimeoutExpired: proc.kill()
        if check.failed: print(open(log).read()[-3000:])


async def main():
    state = tempfile.mkdtemp(); lens = os.path.join(state, "lens"); camlog = os.path.join(state, "camera.log")
    open(lens, "w").write("0\n")
    env = dict(os.environ, HASSMIC_STATE=state, HASSMIC_CAP=f"{ROOT}/testdata/alexa_espeak.raw", HASSMIC_PLAY=os.path.join(state, "play.raw"),
               HASSMIC_MDNS_FILE=os.path.join(state, "none"), HASSMIC_ARB_ADDR="127.255.255.255",
               HASSMIC_FAKE_CAMERA=os.path.join(ROOT, "tests", "fake_camera.py"), HASSMIC_FAKE_LENS=lens, FAKE_CAMERA_LOG=camlog)
    log = os.path.join(state, "log")
    proc = subprocess.Popen([f"{ROOT}/build/hassmic-host", "-P", "esphome", "-p", str(PORT), "-n", "Echo Cam", "-z", "0", "-o", "0",
                             "-a", "16993", "-W", str(WEB)], env=env, stderr=open(log, "w"))
    starts = lambda: open(camlog).read().count("start") if os.path.exists(camlog) else 0
    stops = lambda: open(camlog).read().count("stop") if os.path.exists(camlog) else 0
    try:
        wait_port(PORT, WEB)
        b = Browser(WEB)
        check(b.login_with_button(proc), "logged in (the action button)")
        async with aiohttp.ClientSession() as s:
            echo = api.Echo(s, "127.0.0.1", WEB, b.sk.private_bytes_raw().hex())
            await echo.get_hello()
            cam = await echo.camera()
            check(cam == {"present": 1, "on": 0, "covered": 0, "streaming": 0}, f"GET /api/camera: there, off by default: {cam}")
            st = json.loads(b.call("GET", "/api/state")[2])
            check(st.get("camera", {}).get("present") == 1 and any(x["name"] == "camera" for x in st["settings"]),
                  "the page's state has the camera and its setting")
            recs, err = await take(echo, n=1)
            check(err == "off" and not recs and starts() == 0, f"off: refused, no camera process started ({err})")

            await echo.set("camera=on\n")
            check((await echo.camera())["on"] == 1, "switched on")
            t0 = time.monotonic()
            task = asyncio.ensure_future(take(echo, secs=3))
            await until(lambda: starts() == 1, 5)
            await asyncio.sleep(0.8)
            # a second viewer meanwhile: refused, the first keeps the camera
            busy, err2 = await take(api.Echo(s, "127.0.0.1", WEB, b.sk.private_bytes_raw().hex()), n=1)
            check(err2 == "busy" and starts() == 1, f"a second stream at once: busy ({err2})")
            stp, _, _ = req(WEB, "GET", "/api/hello")
            check(stp == 200, "the page answers while a stream runs")
            check((await echo.camera())["streaming"] == 1, "GET /api/camera: streaming")
            recs, err = await task
            types = [r[0] for r in recs]
            check(err is None and types[:1] == [api.CAM_CONFIG] and api.CAM_KEY in types and types.count(api.CAM_FRAME) > 20,
                  f"records decrypted: config first, key frames, frames ({len(recs)} in {time.monotonic() - t0:.1f} s)")
            pts = [r[1] for r in recs if r[0] != api.CAM_CONFIG]
            check(all(b2 - a == 66666 for a, b2 in zip(pts, pts[1:])), "the camera's pts kept, 15 fps")
            check(await until(lambda: stops() == 1, 4) and (await echo.camera())["streaming"] == 0,
                  "the viewer went: the camera process stopped")
            # the integration's mux of it: what Home Assistant's stream and go2rtc read
            mux, ts, cfg, base = tsmux.TsMuxer(), bytearray(), b"", None
            for t, p, d in recs:
                if t == api.CAM_CONFIG: cfg = d; continue
                base = p if base is None else base
                ts += mux.frame((p - base) * 9 // 100 + 90000, d, t == api.CAM_KEY, cfg)
            f = os.path.join(state, "t.ts"); open(f, "wb").write(ts)
            nframes = len(pts)
            if shutil.which("ffprobe"):
                pr = subprocess.run(["ffprobe", "-v", "warning", "-count_frames", "-of", "json", "-show_entries",
                                     "stream=codec_name,width,height,nb_read_frames,avg_frame_rate:format=duration", f], capture_output=True, text=True)
                j = json.loads(pr.stdout or "{}"); sv = (j.get("streams") or [{}])[0]
                dur = float(j.get("format", {}).get("duration", 0))
                check(pr.returncode == 0 and not pr.stderr.strip() and sv.get("codec_name") == "h264" and int(sv.get("nb_read_frames", 0)) == nframes
                      and abs(dur - nframes / 15) < 0.2, f"MPEG-TS: ffprobe reads every frame at 15 fps, no warnings ({sv}, {dur:.2f} s; {pr.stderr.strip()[:200]})")
            else:                                       # CI: no ffmpeg; the packets and the PES timing, read here
                pk = [ts[i:i + 188] for i in range(0, len(ts), 188)]
                pes = [p for p in pk if p[1] & 0x40 and ((p[1] & 0x1F) << 8 | p[2]) == tsmux.VIDEO_PID]
                def pts_of(p):
                    o = 4 + (1 + p[4] if p[3] & 0x20 else 0); h = p[o:o + 14]
                    return (h[9] >> 1 & 7) << 30 | h[10] << 22 | (h[11] >> 1) << 15 | h[12] << 7 | h[13] >> 1
                got = [pts_of(p) for p in pes]
                check(len(ts) % 188 == 0 and all(p[0] == 0x47 for p in pk) and len(pes) == nframes and all(b2 - a == 5999 or b2 - a == 6000 for a, b2 in zip(got, got[1:])),
                      f"MPEG-TS (no ffprobe here): whole packets, a PES per frame at 15 fps ({len(pes)} of {nframes})")

            # what the Echo refuses
            check(req(WEB, "GET", "/api/camera/stream")[0] == 401, "unsigned: 401")
            forged = dict(b.headers("GET", "/api/camera/stream", b""), **{"X-HM-Mac": "00" * 16})
            check(req(WEB, "GET", "/api/camera/stream", b"", forged)[0] == 401, "forged: 401")
            hd = b.headers("GET", "/api/camera/stream", b"")
            n0 = starts()
            check(status_only(hd) == 200, "a stream opened and closed at once")
            check(await until(lambda: starts() == n0 + 1 and stops() == n0 + 1, 6), "and its camera process gone with it")
            check(status_only(hd) == 401, "the same request again (a counter taken once): 401")

            # the lens covered while it streams: the stream ends, the next one is refused
            n0 = starts()
            task = asyncio.ensure_future(take(echo, secs=20))
            await until(lambda: starts() == n0 + 1, 5); await asyncio.sleep(1)
            open(lens, "w").write("1\n")
            recs, err = await asyncio.wait_for(task, 6)
            check(recs and err is None, f"the lens covered: the stream ended ({len(recs)} records, {err})")
            check(await until(lambda: stops() == n0 + 1, 4), "and the camera process stopped")
            check((await echo.camera())["covered"] == 1 and (await take(echo, n=1))[1] == "covered", "covered: GET /api/camera says so, a stream is refused")
            open(lens, "w").write("0\n")

            # switched off while it streams
            n0 = starts()
            task = asyncio.ensure_future(take(echo, secs=20))
            await until(lambda: starts() == n0 + 1, 5); await asyncio.sleep(1)
            await echo.set("camera=off\n")
            recs, err = await asyncio.wait_for(task, 6)
            check(recs and err is None and await until(lambda: stops() == n0 + 1, 4), "switched off: the stream ended, the camera process stopped")
            ex = b.call("GET", "/api/export")[2].decode()
            check("camera=" not in ex, "not in an export (make like this Echo never switches a camera on)")
            check("camera=" in open(os.path.join(state, "config")).read(), "kept in state/config")
        # a camera that does not open: the stream ends at once (cam.c's log line in hassmic's)
        proc.terminate(); proc.wait(5)
        env["FAKE_CAMERA_FAIL"] = "1"
        proc = subprocess.Popen([f"{ROOT}/build/hassmic-host", "-P", "esphome", "-p", str(PORT), "-n", "Echo Cam", "-z", "0", "-o", "0",
                                 "-a", "16993", "-W", str(WEB)], env=env, stderr=open(log, "a"))
        wait_port(PORT, WEB)
        async with aiohttp.ClientSession() as s:
            echo = api.Echo(s, "127.0.0.1", WEB, b.sk.private_bytes_raw().hex())
            check((await echo.camera())["on"] == 0, "after a restart: off again (it was switched off)")
            await echo.set("camera=on\n")
            t0 = time.monotonic(); recs, err = await take(echo, secs=10)
            check(not recs and err is None and time.monotonic() - t0 < 3 and "the camera did not open" in open(log).read(),
                  f"a camera that does not open: the stream ends at once, the log says why ({time.monotonic() - t0:.1f} s)")
        proc.terminate(); proc.wait(5)
        await eyes(state, env, b)
    finally:
        proc.terminate()
        try: proc.wait(5)
        except subprocess.TimeoutExpired: proc.kill()
    if check.failed:
        print(open(log).read()[-4000:])
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
