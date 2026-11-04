#!/usr/bin/env python3
"""Video in a Drop In between Echo Shows (dropin.c's "HMV1" over the call's UDP, video.c on the screen; the PC's
stand-ins: tests/fake_camera.py for cam.c's camera, tests/fake_video.py for its player) under a fake Home Assistant,
with tests/fake_ha_dropin.py's Echos.  The kitchen Show has its camera on; the hall Show shows pictures, its camera off;
the bedroom Echo is a Dot (no camera, no screen).  The hall gets the kitchen's picture from a key frame on, none goes
back; hung up, the hall's player goes; the Dot is never sent one (the kitchen's camera does not even start); with
every 7th fragment lost on the way, the picture comes back at each key frame and nothing broken reaches the player."""
import asyncio, base64, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_ha_dropin as fd
import fake_video
from fake_ha_dropin import Echo, check, until

ROOT = fd.ROOT
CAM, VID = os.path.join(ROOT, "tests", "fake_camera.py"), os.path.join(ROOT, "tests", "fake_video.py")


def show(e, camera):
    """an Echo Show: the stand-in player, and the stand-in camera with the setting on or off"""
    e.vlog, e.camlog = os.path.join(e.state, "video.log"), os.path.join(e.state, "camera.log")
    e.env.update(HASSMIC_FAKE_VIDEO=VID, FAKE_VIDEO_LOG=e.vlog, HASSMIC_FAKE_CAMERA=CAM, FAKE_CAMERA_LOG=e.camlog)
    with open(os.path.join(e.state, "config"), "a") as f: f.write(f"camera={'on' if camera else 'off'}\n")
    return e


def recs(e): return [l.split() for l in open(e.vlog).read().splitlines() if l.startswith("rec")] if os.path.exists(e.vlog) else []
def vtext(e): return open(e.vlog).read() if os.path.exists(e.vlog) else ""
def camtext(e): return open(e.camlog).read() if os.path.exists(e.camlog) else ""


async def main():
    net = f"{int.from_bytes(os.urandom(8), 'little') | 1:016x} " + base64.b64encode(os.urandom(32)).decode()
    a = show(Echo("Kitchen Show", 26280, net, speech=True), camera=True)
    b = show(Echo("Hall Show", 26281, net), camera=False)
    d = Echo("Bedroom Dot", 26282, net)
    for e in (a, b, d): e.start()
    try:
        await asyncio.sleep(1.5)
        for e in (a, b, d): await e.connect()
        await asyncio.sleep(2)

        # 1. the kitchen drops in on the hall: its picture on the hall's screen
        await a.call(b.name)
        check(await until(lambda: a.dropin()[0] == "connected" and b.dropin()[0] == "connected", 4), f"connected ({a.dropin()}, {b.dropin()})")
        check(await until(lambda: len(recs(b)) >= 25, 6), f"the kitchen's picture reaches the hall's player ({len(recs(b))} records)")
        r = recs(b)
        check(r[:1] and r[0][1] == "2", f"  from a key frame on, the codec's config inside it ({r[:1]})")
        check("the camera's picture to the other Echo" in a.text() and "start" in camtext(a), "  the kitchen's camera runs for it (its red dot on a Show)")
        check(not recs(a) and "start" not in camtext(b), "nothing goes back: the hall's camera is off")
        b.press("end_drop_in")
        check(await until(lambda: a.dropin()[0] == "idle" and fake_video.gone(b.vlog), 4), "hung up: the hall's player goes, and the picture with it")
        check(await until(lambda: camtext(a).rstrip().endswith("stop"), 4), "  the kitchen's camera stops")
        check(await until(lambda: "pictures:" in a.text() and "pictures:" in b.text(), 2), "  both logs count the pictures")
        await asyncio.sleep(1)

        # 2. a Dot shows no pictures: the kitchen never starts its camera for it
        starts = camtext(a).count("start")
        await a.call(d.name)
        check(await until(lambda: a.dropin()[0] == "connected" and d.dropin()[0] == "connected", 4), "the kitchen drops in on the Dot")
        await asyncio.sleep(3)
        check(camtext(a).count("start") == starts, "  no picture for a Dot: the camera stays off")
        d.press("end_drop_in")
        check(await until(lambda: a.dropin()[0] == "idle", 3), "  hung up")
    finally:
        for e in (a, b, d): e.proc.terminate()
    # 3. lost fragments: a hall that loses every 7th
    b2 = show(Echo("Hall Show 2", 26283, net), camera=False); b2.env["HASSMIC_DROPIN_VIDEO_LOSS"] = "7"
    a2 = show(Echo("Kitchen Show 2", 26284, net, speech=True), camera=True)
    for e in (a2, b2): e.start()
    try:
        await asyncio.sleep(1.5)
        for e in (a2, b2): await e.connect()
        await asyncio.sleep(2)
        await a2.call(b2.name)
        check(await until(lambda: b2.dropin()[0] == "connected", 4), "connected, with a lossy way")
        await asyncio.sleep(6)
        r = recs(b2)
        a2.press("end_drop_in")
        await until(lambda: "pictures:" in b2.text(), 4)
        import re
        m = re.search(r"pictures: (\d+) sent, (\d+) shown, (\d+) lost", b2.text())
        check(m and int(m.group(3)) > 0, f"  frames lost on the way are counted ({m.group(0) if m else None})")
        check(r and r[0][1] == "2" and len(r) >= 5, f"  the picture still comes, from key frames after each loss ({len(r)} records)")
    finally:
        for e in (a2, b2): e.proc.terminate()
    if fd.check.failed: sys.exit(1)
    print("all good")


if __name__ == "__main__":
    asyncio.run(main())
