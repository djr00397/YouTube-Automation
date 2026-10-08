import re, random
import config, style
from script_writer import CHAPTERS, clean_head

SHORT_STOP = set("a an the of to in on for and or at by with from as is are was were be been this that it its has have had not but will new says say after over into out up about more than".split())
BADGES = ["EXPLAINED", "THE FACTS", "FULL STORY", "BREAKDOWN", "ANALYSIS"]
TITLE_PATTERNS = ["{h}: What It Means and Why It Matters", "{h} Explained: Background, Evidence and Impact", "{h} — The Full Story in {m} Minutes",
                  "What {h} Means for Your Money", "Behind the Headline: {h}", "{h}: Who Wins, Who Pays?", "The Real Impact of {h}",
                  "{h} — Facts, Both Sides, and What Happens Next", "Understanding {h} in {m} Minutes", "{h}: The Numbers Behind the News",
                  "Why {h} Is Bigger Than It Looks", "{h}: What the Evidence Shows"]


def _ts(sec):
    return f"{int(sec) // 60:02d}:{int(sec) % 60:02d}"


def _srt_ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _shorten(h, n):
    return h if len(h) <= n else h[:n].rsplit(" ", 1)[0]


def make_title(topic, profile, minutes):
    h0 = clean_head(topic["headline"])
    if config.IS_SHORT:
        return (_shorten(h0, 84) + " #Shorts")[:100]
    pat = TITLE_PATTERNS[profile["title_pat"] % len(TITLE_PATTERNS)]
    for n in (70, 58, 46, 36):
        t = pat.format(h=_shorten(h0, n), m=minutes)
        if len(t) <= 100:
            return t
    return _shorten(h0, 90)


def credits_block(credits):
    if not credits:
        return ""
    lines = [f'- "{c["title"][:70]}" — {c["author"]} ({c["license"]}) via {c["source"]}: {c["page"]}' for c in credits[:20]]
    return "\nImage credits:\n" + "\n".join(lines)[:1800] + "\n"


def make_meta(topic, scenes, profile, credits=None):
    minutes = max(1, int(round(sum(s["frames"] for s in scenes) / float(config.FPS) / 60)))
    title = make_title(topic, profile, minutes)
    srcs = "\n".join(f"- {a['source']}: {a['title']} ({a['link']})" for a in topic["articles"][:8])
    wiki = topic.get("wiki")
    wnote = f"\nBackground information drawn from Wikipedia (CC BY-SA 4.0): {wiki['url']}" if wiki else ""
    cr = credits_block(credits)
    disclose = ("Disclosure: This video was produced with automation and AI tools. The script is machine-written from the sources above, "
                "the narration is a synthetic voice, and the animations are illustrative. Photos are credited to their sources; "
                "map data: Natural Earth (public domain).\nDisclaimer: Educational and informational content only, not financial advice.")
    head = clean_head(topic["headline"])
    kw_tags = " ".join("#" + re.sub(r"[^A-Za-z0-9]", "", k).title() for k in topic["keywords"][:2] if k)
    if config.IS_SHORT:
        summ = " ".join(s["text"] for s in scenes if s["sec"] in (4, 6))[:400]
        desc = f"{head}\n\n{summ}\n\nSources:\n{srcs}{wnote}\n{cr}\n{disclose}\n\n#Shorts #Finance #Business {kw_tags}"
        base = ["shorts", "finance", "business news", "economy", "money", "investing", "stock market", "news explained"]
    else:
        summ = " ".join(s["text"] for s in scenes if s["sec"] == 1)[:600]
        firsts = {}
        for s in scenes:
            firsts.setdefault(s["sec"], s["start_f"] / float(config.FPS))
        chapters = "\n".join(f"{_ts(firsts[k])} {CHAPTERS[k]}" for k in sorted(firsts))
        if not chapters.startswith("00:00"):
            chapters = "00:00 Intro\n" + chapters
        desc = (f"{head} — an evidence-based explainer covering the background, the data, both sides of the argument and the real-world impact."
                f"\n\n{summ}\n\nChapters:\n{chapters}\n\nSources and further reading:\n{srcs}{wnote}\n{cr}\n{disclose}\n\n#Finance #Business #Economy {kw_tags}")
        base = ["finance", "business news", "economy", "investing", "stock market", "money", "personal finance", "financial education",
                "business explained", "global economy"]
    desc = desc.replace("<", "").replace(">", "")[:4900]
    tags, total = [], 0
    for t in list(topic["keywords"]) + base:
        t = t[:30]
        if t not in tags and total + len(t) + 1 < 450:
            tags.append(t)
            total += len(t) + 1
    return {"title": title, "description": desc, "tags": tags, "categoryId": "25"}


def write_srt(scenes, path):
    lines, k = [], 1
    for s in scenes:
        sents = [x for x in re.split(r"(?<=[.!?])\s+", s["text"].strip()) if x]
        tot = sum(len(x.split()) for x in sents) or 1
        t = s["start_f"] / float(config.FPS) + 0.15
        for x in sents:
            dur = s["adur"] * len(x.split()) / tot
            parts = re.findall(r".{1,42}(?:\s|$)", x)
            lines.append(f"{k}\n{_srt_ts(t)} --> {_srt_ts(t + dur)}\n" + "\n".join(p.strip() for p in parts[:3] if p.strip()) + "\n")
            k += 1
            t += dur
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def thumbnail(topic, plan, img_dir, out_path):
    """ডকুমেন্টারি থাম্বনেইল: Cairo-তে আঁকা, ৫ ধরনের লেআউট ঘোরে"""
    import cairo
    from PIL import Image
    import shots as SH
    SH.set_dir(img_dir)
    profile = plan["profile"]
    words = [w for w in re.findall(r"[A-Za-z0-9\$%']+", clean_head(topic["headline"])) if w.lower() not in SHORT_STOP and len(w) > 1][:5]
    sp = {"th": style.THEMES[profile["theme"] % len(style.THEMES)], "layout": profile["thumb"], "seed": profile["seed"] % 100000,
          "title": " ".join(words) or "BUSINESS", "photo": plan.get("thumb_photo"), "date": topic.get("date", ""),
          "badge": BADGES[profile["seed"] % len(BADGES)]}
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1280, 720)
    c = cairo.Context(surf)
    SH.thumb(c, sp)
    surf.flush()
    im = Image.frombuffer("RGBA", (1280, 720), bytes(surf.get_data()), "raw", "BGRA", 0, 1).convert("RGB")
    im.save(out_path, "JPEG", quality=90)
    return out_path
