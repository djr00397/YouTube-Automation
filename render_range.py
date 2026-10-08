import sys, json, bisect, subprocess
import cairo
import config
import shots as SH


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
    c = cairo.Context(surf)
    for g in range(a, b):
        s = shots[max(0, bisect.bisect_right(starts, g) - 1)]
        t = (g - s["start_f"]) / float(max(1, s["frames"] - 1))
        c.save()
        c.scale(config.S, config.S)
        SH.render_frame(c, s, min(1.0, max(0.0, t)))
        c.restore()
        surf.flush()
        ff.stdin.write(surf.get_data())
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("ffmpeg failed in render_range")


if __name__ == "__main__":
    main()
