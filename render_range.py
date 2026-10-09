import sys, json, bisect, subprocess
import cairo
import config
import shots as SH

# ---- সুরক্ষা-প্যাচ: শূন্য সাইজ থেকে "invalid matrix" এরর আটকায় ----
_font0, _ell0, _icon0 = SH.font, SH._ell, SH.icon


def _font(c, st, size):
    _font0(c, st, max(float(size), 0.5))


def _ell(c, x, y, rx, ry):
    _ell0(c, x, y, max(float(rx), 1e-3), max(float(ry), 1e-3))


def _icon(c, name, cx, cy, z, th, a=1.0, t=0.0):
    if z >= 1.0:
        _icon0(c, name, cx, cy, z, th, a, t)


SH.font, SH._ell, SH.icon = _font, _ell, _icon
ERRS = [0]


def draw(surf, s, t):
    """প্রতি ফ্রেমে নতুন কনটেক্সট: একবার এরর হলে Cairo কনটেক্সট আর কাজ করে না"""
    for kind in (s["kind"], "ripple", None):
        c = cairo.Context(surf)
        try:
            c.scale(config.S, config.S)
            if kind is None:
                c.identity_matrix()
                c.set_source_rgb(0.9, 0.9, 0.9)
                c.paint()
                return
            SH.KINDS.get(kind, SH.k_ripple)(c, s, t)
            return
        except Exception as e:
            ERRS[0] += 1
            if ERRS[0] <= 8:
                print("shot failed:", kind, repr(e)[:120], flush=True)


def main():
    a, b, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    shots = json.load(open(config.BUILD / "plan.json"))["shots"]
    SH.set_dir(config.BUILD / "images")
    starts = [s["start_f"] for s in shots]
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{config.W}x{config.H}",
                           "-r", str(config.FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-maxrate", "22M",
                           "-bufsize", "44M", "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", "48", "-keyint_min", "48",
                           "-sc_threshold", "0", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                           "-threads", "2", out], stdin=subprocess.PIPE)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, config.W, config.H)
    for g in range(a, b):
        s = shots[max(0, bisect.bisect_right(starts, g) - 1)]
        t = (g - s["start_f"]) / float(max(1, s["frames"] - 1))
        draw(surf, s, min(1.0, max(0.0, t)))
        surf.flush()
        ff.stdin.write(surf.get_data())
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("ffmpeg failed in render_range")
    print(f"range {a}..{b} done, shot errors: {ERRS[0]}", flush=True)


if __name__ == "__main__":
    main()
