import faulthandler
faulthandler.enable()

import os, sys, math, json, random
import numpy as np
import config, news_fetcher, script_writer, llm_writer, voice_engine, audio_engine
import story_engine, seo_engine, style, youtube_uploader, image_fetcher

SR, FPS = config.SR, config.FPS


def skip(msg):
    print("SKIP:", msg)
    (config.BUILD / "skip").write_text(msg)
    sys.exit(0)


def run():
    print("MODE:", config.MODE, f"{config.W}x{config.H}", "| DRY RUN" if config.DRY else "", "| RSS images:", config.RSS_IMAGES, flush=True)
    extra = []
    if not config.DRY:
        miss = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not os.getenv(k)]
        if miss:
            sys.exit("Missing secrets: " + ", ".join(miss))
        try:
            youtube_uploader.check_auth()
        except Exception as e:
            sys.exit(f"YouTube auth check failed (fix secrets/scopes first): {e}")
        extra = youtube_uploader.recent_titles(40)
    try:
        topic = news_fetcher.pick_topic(extra)
    except news_fetcher.NoFreshTopic as e:
        skip(str(e))
    head = script_writer.clean_head(topic["headline"])
    profile = style.pick(news_fetcher.load_history(), random.SystemRandom().randint(0, 2 ** 31))
    print("style profile:", profile)
    if not config.DRY:
        news_fetcher.reserve(topic, profile)

    beats = script_writer.plan_short(topic, profile) if config.IS_SHORT else script_writer.plan(topic, profile)
    if config.DRY:
        beats = beats[:3]
    try:
        llm_writer.load()
    except llm_writer.LLMUnavailable as e:
        sys.exit(f"LLM unavailable: {e}")
    facts = llm_writer.Facts(topic)
    voice_engine.load()
    maxw = 18 if config.IS_SHORT else 42
    kept, total = [], 0.0

    def add_beat(b):
        nonlocal total
        text = llm_writer.write(facts, b)
        print(f"beat {b['order']} {b['name']}: {len(text.split())} words", flush=True)
        if not text:
            return
        for s in script_writer.to_scenes(b, text, head, maxw):
            try:
                s["audio"] = voice_engine.synth(s["text"], s["emotion"])
            except Exception as e:
                print("TTS failed:", e)
                continue
            d = len(s["audio"]) / SR + 0.5
            if total + d > config.MAX_SEC:
                continue
            kept.append(s)
            total += d

    try:
        for b in beats:
            if not b["optional"]:
                add_beat(b)
        for b in beats:
            if b["optional"] and total < config.TARGET_SEC and not config.DRY:
                add_beat(b)
    except llm_writer.LLMUnavailable as e:
        sys.exit(f"LLM unavailable: {e}")
    finally:
        llm_writer.unload()

    kept.sort(key=lambda s: s["seq"])
    print(f"duration estimate: {total / 60:.1f} min, scenes: {len(kept)}")
    floor_sec = 8 if config.DRY else (20 if config.IS_SHORT else 8 * 60)
    if total < floor_sec or not kept:
        sys.exit(f"Script far too short ({total:.0f}s) - stopping")
    if not config.IS_SHORT and total < config.MIN_SEC and not config.DRY:
        print("WARNING: shorter than 20 minutes")

    cum = 0
    for i, s in enumerate(kept):
        nxt = kept[i + 1]["sec"] if i + 1 < len(kept) else None
        pause = 0.35 if nxt == s["sec"] else (1.0 if nxt is not None else 2.5)
        s["adur"] = len(s["audio"]) / SR
        s["frames"] = math.ceil((s["adur"] + 0.15 + pause) * FPS)
        s["start_f"] = cum
        cum += s["frames"]
    total_samples = round(cum * SR / FPS)
    voice = np.zeros(total_samples, np.float32)
    for s in kept:
        st = round(s["start_f"] * SR / FPS) + int(0.15 * SR)
        a = s.pop("audio")
        m = min(len(a), total_samples - st)
        voice[st:st + m] += a[:m]

    story_engine.annotate(kept, topic, profile)
    imgs = []
    try:
        imgs = image_fetcher.fetch(topic, kept, limit=7 if config.DRY else None)
    except Exception as e:
        print("image fetch failed (video continues without photos):", repr(e)[:200])
    try:
        image_fetcher.fetch_geo()
    except Exception as e:
        print("geo fetch failed:", repr(e)[:100])

    shots = story_engine.plan(kept, topic, profile, imgs)
    if config.DRY:
        shots = shots[:8]
        cur = 0
        for s in shots:
            s["frames"] = min(s["frames"], 72)
            s["start_f"] = cur
            cur += s["frames"]

    used_ids = {s["photo"] for s in shots if s.get("photo")} | {i for s in shots for i in s.get("photos", [])}
    thumb_photo = shots[0].get("photo") or (imgs[0]["id"] if imgs else None)
    if thumb_photo:
        used_ids.add(thumb_photo)
    metas = image_fetcher.pack(used_ids)
    image_fetcher.reserve_images([m["id"] for m in metas])

    secs, events = {}, []
    for s in kept:
        a, b = s["start_f"] / FPS, (s["start_f"] + s["frames"]) / FPS
        lo, hi = secs.get(s["sec"], (a, b))
        secs[s["sec"]] = (min(lo, a), max(hi, b))
    for k, (a, b) in secs.items():
        events += [(a, "impact"), (a, "whoosh")]
        if k == 0:
            events.append((max(0, b - 2.6), "riser"))
    for sh in shots:
        for off, name in sh["sfx"]:
            events.append((sh["start_f"] / FPS + off, name))
    sections = [(a, b, script_writer.MOODS[k]) for k, (a, b) in sorted(secs.items())]
    audio_engine.mix(voice, sections, events, config.BUILD / "mix.flac")
    del voice

    meta = seo_engine.make_meta(topic, kept, profile, metas)
    seo_engine.write_srt(kept, config.BUILD / "captions.srt")

    total_frames = shots[-1]["start_f"] + shots[-1]["frames"]
    n = max(1, min(config.MAX_SHARDS, math.ceil(total_frames / float(config.FRAMES_PER_SHARD))))
    per = math.ceil(total_frames / float(n))
    ranges = [[i * per, min(total_frames, (i + 1) * per)] for i in range(n) if i * per < total_frames]
    print(f"frames: {total_frames} | shards: {len(ranges)} | photos used: {len(metas)}")
    (config.BUILD / "plan.json").write_text(json.dumps({"mode": config.MODE, "shards": len(ranges), "ranges": ranges, "profile": profile,
                                                        "thumb_photo": thumb_photo, "shots": shots}, default=str))
    (config.BUILD / "shards.json").write_text(json.dumps(list(range(len(ranges)))))
    (config.BUILD / "meta.json").write_text(json.dumps(meta))
    (config.BUILD / "topic.json").write_text(json.dumps({"headline": topic["headline"], "link": topic["link"], "keywords": topic["keywords"],
                                                         "date": topic.get("date", "")}))
    print("prepare done")


if __name__ == "__main__":
    run()
