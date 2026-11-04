#!/usr/bin/env python3
"""The PC's stand-in for src/cam/cam.c's play mode (HASSMIC_FAKE_VIDEO): reads its records on stdin until it ends, as
the player shows them on an Echo Show's screen.  FAKE_VIDEO_LOG: a file it appends "start <pid>", "rec <type> <bytes>"
per record and "stop" to (hassmic kills it at a call's end: then no "stop", its pid gone: gone()); like cam.c it ends
by itself after 3 s without a record (PLAY_IDLE_MS).  FAKE_VIDEO_DUMP: a file the records themselves are appended to
(to play what a browser sent on an Echo Show's player by hand)."""
import os, select, struct, sys


def gone(log_path):
    """every player the log names has ended (exited, or killed by hassmic's video.c): no picture left on a screen"""
    if not os.path.exists(log_path): return True
    for l in open(log_path).read().splitlines():
        if l.startswith("start "):
            try: os.kill(int(l.split()[1]), 0); return False
            except ProcessLookupError: pass
    return True


def main():
    log = open(os.environ["FAKE_VIDEO_LOG"], "a", buffering=1) if os.environ.get("FAKE_VIDEO_LOG") else None
    say = (lambda s: log.write(s + "\n")) if log else (lambda s: None)
    say(f"start {os.getpid()}")
    dump = open(os.environ["FAKE_VIDEO_DUMP"], "ab") if os.environ.get("FAKE_VIDEO_DUMP") else None
    inp = sys.stdin.buffer

    def read(n):
        b = b""
        while len(b) < n:
            if not select.select([inp], [], [], 3.0)[0]: return None      # idle: hidden, as cam.c
            c = os.read(inp.fileno(), n - len(b))
            if not c: return None
            b += c
        return b

    while True:
        h = read(20)
        if not h or h[:4] != b"HMCV": break
        n = struct.unpack_from("<I", h, 8)[0]
        d = read(n)
        if d is None: break
        say(f"rec {h[4]} {n}")
        if dump: dump.write(h + d); dump.flush()
    say("stop")


if __name__ == "__main__":
    main()
