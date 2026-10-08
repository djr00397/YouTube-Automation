import os, sys, json, subprocess
import config


def start(a, b, out):
    return subprocess.Popen([sys.executable, "-X", "faulthandler", str(config.BASE / "render_range.py"), str(a), str(b), str(out)])


def main():
    shard = int(sys.argv[1])
    a, b = json.load(open(config.BUILD / "plan.json"))["ranges"][shard]
    P = max(1, min(4, os.cpu_count() or 2))
    step = (b - a + P - 1) // P
    parts = [(a + i * step, min(b, a + (i + 1) * step)) for i in range(P) if a + i * step < b]
    outs = [config.WORK / f"part_{shard}_{i}.mp4" for i in range(len(parts))]
    print(f"shard {shard}: frames {a}..{b} in {len(parts)} workers", flush=True)
    procs = [start(x, y, o) for (x, y), o in zip(parts, outs)]
    for i, p in enumerate(procs):
        if p.wait() != 0:
            print("worker", i, "failed -> retry once", flush=True)
            if start(parts[i][0], parts[i][1], outs[i]).wait() != 0:
                sys.exit("render worker failed twice")
    lst = config.WORK / f"list_{shard}.txt"
    lst.write_text("\n".join(f"file '{o}'" for o in outs))
    out = config.BUILD / f"seg_{shard:03d}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True)
    print("segment ready:", out, f"{out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
