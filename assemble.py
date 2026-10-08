import os, sys, json, time, random, shutil, subprocess, datetime as dt
T0 = time.time()
import config, seo_engine, youtube_uploader


def wait_for_slot():
    if os.getenv("WAIT_FOR_SLOT") != "1" or config.DRY:
        return
    now = dt.datetime.utcnow() + dt.timedelta(hours=config.LOCAL_UTC_OFFSET)
    cands = []
    for day in (0, 1):
        base = (now + dt.timedelta(days=day)).replace(minute=0, second=0, microsecond=0)
        cands += [base.replace(hour=h) for h in config.SLOT_HOURS_LOCAL]
    slot = sorted(c for c in cands if c + dt.timedelta(minutes=25) > now)[0]
    target = slot + dt.timedelta(minutes=random.randint(-20, 25))
    wait = (target - now).total_seconds()
    left = config.JOB_BUDGET_SEC - (time.time() - T0) - 600
    if 0 < wait < 5.6 * 3600:
        wait = min(wait, max(0, left))
        print(f"waiting {int(wait // 60)} min for slot {target}")
        time.sleep(wait)
    else:
        print("slot already passed or too far; uploading now")


def run():
    b = config.BUILD
    plan = json.load(open(b / "plan.json"))
    segs = [b / f"seg_{i:03d}.mp4" for i in range(plan["shards"])]
    missing = [p.name for p in segs if not p.exists()]
    if missing:
        sys.exit("Missing render segments: " + ", ".join(missing) + " -> use 'Re-run failed jobs' in the Actions UI")
    lst = b / "list.txt"
    lst.write_text("\n".join(f"file '{p}'" for p in segs))
    out = config.OUT / "video.mp4"
    print(f"assembling {len(segs)} segments -> {config.W}x{config.H}")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(b / "mix.flac"),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    print(f"video ready: {out.stat().st_size / 1e9:.2f} GB")
    meta = json.load(open(b / "meta.json"))
    topic = json.load(open(b / "topic.json"))
    thumb = None
    if not config.IS_SHORT:
        try:
            thumb = seo_engine.thumbnail(topic, plan, b / "images", config.OUT / "thumb.jpg")
        except Exception as e:
            print("thumbnail failed (upload continues without custom thumbnail):", repr(e)[:200])
    srt = b / "captions.srt"
    if config.DRY:
        print("DRY RUN finished: video saved as artifact, nothing uploaded")
        return
    wait_for_slot()
    youtube_uploader.upload(out, thumb, meta, srt if srt.exists() else None)
    shutil.rmtree(config.WORK, ignore_errors=True)


if __name__ == "__main__":
    run()
