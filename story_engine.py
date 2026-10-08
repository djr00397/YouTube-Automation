import re, random, datetime
from collections import Counter
import config, style, image_fetcher
from script_writer import NAMES, CHAPTERS

FPS = config.FPS
ENVS = [("candles", ["stock", "shares", "nasdaq", "dow", "s&p", "market", "index", "earnings", "rally", "investor", "trading", "wall street"]),
        ("barrels", ["oil", "energy", "gas", "crude", "opec", "fuel", "petrol", "electricity"]),
        ("containers", ["trade", "tariff", "shipping", "export", "import", "port", "supply chain", "freight", "logistics", "factory", "manufacturing"]),
        ("bank", ["bank", "central bank", "interest", "rate", "rates", "fed", "debt", "bond", "treasury", "loan", "credit", "lender"]),
        ("houses", ["housing", "mortgage", "real estate", "property", "rent", "homes", "home prices"]),
        ("chip", ["chip", "chips", "semiconductor", "ai", "artificial intelligence", "tech", "software", "nvidia", "data center", "cloud"]),
        ("coins", ["bitcoin", "crypto", "coin", "token", "blockchain", "dollar", "currency", "inflation", "prices", "cost", "cash", "money", "wage", "salary"]),
        ("crowd", ["jobs", "workers", "labor", "hiring", "layoff", "layoffs", "unemployment", "employees", "consumers", "households", "families", "people"]),
        ("globe", ["global", "world", "international", "countries", "economy", "gdp", "growth", "recession", "europe", "asia", "china", "india"]),
        ("skyline", ["company", "companies", "corporate", "business", "firm", "ceo", "industry", "merger", "acquisition"])]
ENV_ICON = {"candles": "chart", "barrels": "barrel", "containers": "container", "bank": "bank", "houses": "house", "chip": "chip",
            "coins": "coins", "crowd": "person", "globe": "globe", "skyline": "skyline"}
NEG = set("fall falls fell drop drops crash loss losses risk risks warn warns fear recession cut cuts layoff layoffs decline crisis slump plunge collapse debt deficit threat pressure shortage default downturn worry trouble".split())
POS = set("rise rises rose gain gains growth record surge profit boost rally recover recovery strong improve expand success opportunity jump soar benefit".split())
STOPW = set("a an the of to in on for and or at by with from as is are was were be been being this that these those it its has have had not but his her their our your more most than into out up about also just very can could would should may might will which who whom what when where while there here they them he she we you i so if then because due".split())
UP = set("rise rises rose rising up higher gain gains grew grow growth surge surged jump jumped soar soared increase increased climb climbed record boost rally".split())
DOWN = set("fall falls fell falling down lower drop dropped decline declined slump plunge plunged decrease decreased cut cuts loss losses shrink shrank slide slid crash".split())
HUMAN = set("people workers households consumers families investors employees customers citizens shoppers buyers borrowers owners".split())
V_SHOP = set("buy buying bought spend spending shop shopping purchase purchases paid pay".split())
V_WORRY = set("lose lost layoffs layoff worry worried struggle struggling cost costs fear afraid unemployed debt".split())
V_CELEB = set("win won gain gains profit profits celebrate success record growth benefit".split())
V_WORK = set("work works working hire hiring jobs job employ employed career careers".split())
NUMRE = re.compile(r"([\$£€]?)(\d[\d,]*(?:\.\d+)?)\s?(%|percent|billion|million|trillion|thousand)?", re.I)
COMPARE = re.compile(r"\b(?:versus|vs|whereas|while|on the other hand|compared (?:to|with)|but|however|than)\b", re.I)
CAUSE = re.compile(r"\b(?:because of|because|due to|as a result|leads? to|led to|caused|causes|triggered|therefore|which means|resulting in|driven by|thanks to)\b", re.I)
STEPS = re.compile(r"\b(?:first|second|third|then|next|finally|after that)\b", re.I)
QUOTEY = re.compile(r"\b(?:said|says|according to|reported|stated|announced)\b", re.I)
PHOTO_OK = {"scene", "kinetic", "people", "ripple", "gauge"}
SFX = {"kinetic": [(0.1, "whoosh"), (0.6, "pop")], "stat": [(0.2, "rise")], "bars": [(0.25, "rise"), (0.55, "rise")],
       "timeline": [(0.3, "tick"), (0.6, "tick")], "flow": [(0.1, "pop"), (0.4, "pop")], "versus": [(0.4, "thud")],
       "headline": [(0.1, "paper"), (0.7, "click")], "map": [(0.1, "whoosh")], "hist": [(0.0, "whoosh")], "poster": [(0.0, "whoosh")],
       "collage": [(0.2, "paper"), (0.7, "paper")], "gauge": [(0.2, "rise")], "ripple": [(0.25, "thud")], "chapter": [(0.0, "impact")],
       "outro": [(0.9, "click"), (1.1, "ding")], "people": [(0.0, "murmur")], "scene": []}


def env_of(text):
    t = " " + re.sub(r"[^a-z0-9&' ]", " ", text.lower()) + " "
    best = (None, 0)
    for env, kws in ENVS:
        sc = sum(len(re.findall(r"\b" + re.escape(k) + (r"\b" if len(k) <= 3 else ""), t)) for k in kws)
        if sc > best[1]:
            best = (env, sc)
    return best


def annotate(scenes, topic, profile):
    d, _ = env_of(topic["headline"] + " " + " ".join(topic["keywords"]))
    d = d or "globe"
    for s in scenes:
        env, sc = env_of(s["text"])
        w = re.findall(r"[a-z]+", s["text"].lower())
        sent = sum(x in POS for x in w) - sum(x in NEG for x in w)
        s["plan"] = {"env": env or d, "score": sc, "mood": "dramatic" if sent < 0 else "bright" if sent > 0 else "neutral",
                     "char": bool(set(w) & HUMAN)}
    return d


def key_phrase(text, n=4):
    out = [w.strip(".,;:!?\"'()") for w in text.split()]
    out = [w for w in out if w and w.lower() not in STOPW and not re.fullmatch(r"[\d,.]+", w)]
    s = " ".join(out[:n]).strip()
    return (s[:1].upper() + s[1:])[:30] if s else ""


def find_nums(text):
    out = []
    for m in NUMRE.finditer(text):
        sym, num, unit = m.group(1) or "", m.group(2), (m.group(3) or "").lower()
        try:
            val = float(num.replace(",", ""))
        except ValueError:
            continue
        if not sym and not unit and (1900 <= val <= 2100 or val < 100):
            continue
        suffix, cls = ("%", "%") if unit in ("%", "percent") else (" " + unit, sym + unit) if unit else ("", sym or "n")
        out.append({"val": val, "sym": sym, "suffix": suffix, "dec": len(num.split(".")[1]) if "." in num else 0, "cls": cls, "pos": m.start()})
    return out


def find_years(text):
    return sorted({int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text)})


def direction(ws):
    u, d = len(ws & UP), len(ws & DOWN)
    return 1 if u > d else -1 if d > u else 0


def kin_words(text, kws):
    sent = re.split(r"(?<=[.!?])\s+", text.strip())[0]
    ws = sent.split()
    if len(ws) > 9:
        parts = [p for p in re.split(r",|;| — | - ", sent) if p.strip()]
        ws = (max(parts[:2], key=lambda p: len(p.split())) if parts else sent).split()[:9]
    ws = [w.strip(".,;:!?\"'()") for w in ws if w.strip(".,;:!?\"'()")]
    sc = []
    for i, w in enumerate(ws):
        s = (3 if re.search(r"\d", w) else 0) + (2 if w[:1].isupper() and i > 0 else 0) + (2 if w.lower() in kws else 0) + (1 if len(w) >= 7 else 0)
        sc.append((s, len(w), i))
    top = {i for s, _, i in sorted(sc, reverse=True)[:2] if s >= 2} or {max(sc, key=lambda x: x[1])[2]} if sc else set()
    return [[w if i in top else (w if w == "I" else w.lower()), "b" if i in top else "l"] for i, w in enumerate(ws)]


def countries_in(text, idx):
    t = " " + re.sub(r"[^a-z. ]", " ", text.lower()) + " "
    found = []
    for k in sorted(idx, key=len, reverse=True):
        if (" " + k + " ") in t and idx[k] not in found:
            found.append(idx[k])
    return found[:3]


def _groups(sents, k):
    tot = sum(len(x.split()) for x in sents)
    out, cur, cw = [], [], 0
    for i, x in enumerate(sents):
        cur.append(x)
        cw += len(x.split())
        if len(out) < k - 1 and cw >= tot / float(k) and len(sents) - i - 1 >= (k - 1 - len(out)):
            out.append(cur)
            cur, cw = [], 0
    if cur:
        out.append(cur)
    return out


def _alloc(groups, n):
    w = [max(1, sum(len(x.split()) for x in g)) for g in groups]
    fr = [max(3 * FPS, int(round(n * x / float(sum(w))))) for x in w]
    fr[-1] = n - sum(fr[:-1])
    return fr


def choose(text, sc, ctx, first):
    low = text.lower()
    ws = set(re.findall(r"[a-z']+", low))
    p = sc["plan"]
    nums, years = find_nums(text), find_years(text)
    d = direction(ws) or {"dramatic": -1, "bright": 1}.get(p["mood"], 0)
    kind = sc["kind"]
    if kind == "outro":
        return "outro", {}
    if first and kind == "bullets" and sc.get("bullets"):
        return "flow", {"nodes": list(sc["bullets"])[:5]}
    if first and kind == "versus":
        return "versus", {"left": "Supporters point to the benefits and long-term gains", "right": "Critics warn about costs, risks and timing", "tilt": 0}
    C = []
    if len(nums) >= 2 and nums[0]["cls"] == nums[1]["cls"] and re.search(r"\bfrom\b|\bthan\b|versus|compared|\bvs\b|\bto\b", low):
        a, b = nums[0], nums[1]
        la, lb = ("Before", "After") if re.search(r"\bfrom\b.*\bto\b", low) else (key_phrase(text[max(0, a["pos"] - 40):a["pos"]], 2) or "Value", key_phrase(text[max(0, b["pos"] - 40):b["pos"]], 2) or "Value")
        C.append((8.0, "bars", {"a": dict(a, label=la), "b": dict(b, label=lb)}))
    if nums:
        n0 = nums[0]
        C.append((6.0 + (2 if kind == "stat" else 0), "stat", {"val": n0["val"], "sym": n0["sym"], "suffix": n0["suffix"], "dec": n0["dec"], "dir": d,
                                                                "label": " ".join(text.split()[:14]), "icon": ENV_ICON.get(p["env"], "coins")}))
    if years:
        ys, labels = years[:4], None
        if len(ys) == 1 and ys[0] < datetime.date.today().year:
            ys, labels = [ys[0], datetime.date.today().year], [str(ys[0]), "Today"]
        C.append((7.0, "timeline", {"years": ys, "labels": labels}))
    arts = ctx["arts"]
    if QUOTEY.search(text) or '"' in text or p["score"] == 0 and kind == "text" and random.random() < 0.15:
        a = arts[ctx["ai"] % len(arts)]
        ctx["ai"] += 1
        C.append((5.8 if QUOTEY.search(text) else 2.0, "headline", {"src": a["source"], "title": re.sub(r"\s[-|–]\s[^-|–]{2,40}$", "", a["title"]),
                                                                      "date": ctx.get("date_of", {}).get(a["link"], ""), "snip": (a["sentences"][0][:130] if a["sentences"] else "")}))
    segs = [x for x in CAUSE.split(text) if len(x.split()) >= 2]
    if len(segs) >= 2:
        nodes = list(dict.fromkeys(k for k in (key_phrase(x, 4) for x in segs[:4]) if k))
        if len(nodes) >= 2:
            C.append((5.5, "flow", {"nodes": nodes}))
    st = [x for x in STEPS.split(text) if len(x.split()) >= 3]
    if len(st) >= 3:
        nodes = [k for k in (key_phrase(x, 4) for x in st[:4]) if k]
        if len(nodes) >= 3:
            C.append((5.0, "flow", {"nodes": nodes}))
    m = COMPARE.search(text)
    if m or sc["sec"] == 5:
        left, right = ((key_phrase(text[:m.start()], 5) or "One side"), (key_phrase(text[m.end():], 5) or "Other side")) if m else ("Supporters", "Critics")
        C.append((4.5 if sc["sec"] != 5 else 6.0, "versus", {"left": left, "right": right, "tilt": 1 if re.search(r"\b(but|however)\b", low) else 0}))
    cs = countries_in(text, ctx["geo"]) if ctx["geo"] else []
    if cs and ctx["hist"].count("map") < max(1, len(ctx["hist"]) // 9):
        C.append((6.8 + 0.5 * len(cs), "map", {"countries": cs}))
    if p["env"] and p["score"] > 0:
        C.append((3.0 + min(p["score"], 4) + (3 if kind == "hook" else 0), "scene", {"env": p["env"], "drift": d}))
    else:
        C.append((1.8, "scene", {"env": ctx["env"], "drift": d}))
    if ws & HUMAN or p["char"]:
        act = "shop" if ws & V_SHOP else "worry" if ws & V_WORRY else "celebrate" if ws & V_CELEB else "work" if ws & V_WORK else "walk"
        C.append((3.2 + (0.8 if act != "walk" else 0), "people", {"action": act, "count": 3}))
    g = ws & {"risk", "uncertain", "uncertainty", "pressure", "tension", "volatile", "volatility", "fear"}
    if g:
        C.append((4.0, "gauge", {"level": 0.8 if p["mood"] == "dramatic" else 0.35, "glabel": sorted(g)[0]}))
    if ws & {"spread", "global", "ripple", "effect", "effects", "impact", "impacts", "across", "worldwide", "consequences"}:
        C.append((3.8, "ripple", {}))
    kw = kin_words(text, ctx["kws"])
    if kw:
        body = " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[1:])[:110]
        kb = 2.4 + (2.5 if config.IS_SHORT else 0) + (2 if kind == "hook" else 0) - (3 if ctx["hist"].count("kinetic") > 0.25 * len(ctx["hist"]) + 1 else 0)
        C.append((kb, "kinetic", {"words": kw, "body": body, "icon": ENV_ICON.get(p["env"], "coins")}))
    C.append((1.0, "ripple", {}))
    hist = ctx["hist"]
    best = max(C, key=lambda x: x[0] - 2.2 * hist[-3:].count(x[1]) - (1.0 if hist and hist[-1] == x[1] else 0) + random.random() * 0.2)
    return best[1], best[2]


def _tk(t):
    return {w for w in re.findall(r"[a-z]{3,}", t.lower()) if w not in STOPW}


def _year(txt):
    ys = find_years(txt)
    return str(ys[0]) if ys else ""


def attach_photos(shots, imgs):
    n = len(shots)
    if not imgs or n < 4:
        return
    short = config.IS_SHORT
    uses, last = {im["id"]: 0 for im in imgs}, {}

    def score(im, s):
        sc = len(_tk(s.get("_text", "")) & set(im["tags"]))
        if im.get("env") and im["env"] == s.get("penv"):
            sc += 2
        return sc + (1.5 if im.get("entity") else 0)
    p0 = max(imgs, key=lambda im: score(im, shots[0]))
    shots[0]["photo"] = p0["id"]
    uses[p0["id"]] += 1
    cap = 1 if short else 2
    max_ph = 1 if short else max(3, int(n * 0.40))
    cnt, last_i, col_done = 0, -9, False
    for i, s in enumerate(shots):
        if i < 2 or s.get("title") or s["kind"] in ("outro", "chapter") or cnt >= max_ph or i - last_i < 2:
            continue
        cand = [im for im in imgs if uses[im["id"]] < cap and i - last.get(im["id"], -99) >= 8]
        if not cand:
            continue
        best = max(cand, key=lambda im: score(im, s))
        if config.DRY and cnt == 0:
            pass
        elif score(best, s) < 1.0 or s["kind"] not in PHOTO_OK:
            continue
        if not short and not col_done and s["frames"] >= 5 * FPS and s["sec"] in (3, 4, 5) and len(cand) >= 3:
            top = sorted(cand, key=lambda im: -score(im, s))[:3]
            s["kind"], s["photos"], s["label"] = "collage", [im["id"] for im in top], key_phrase(s.get("_text", ""), 4)
            for im in top:
                uses[im["id"]] += 1
                last[im["id"]] = i
            col_done = True
        else:
            s["kind"], s["photo"] = "hist", best["id"]
            s["year"], s["caption"] = _year(s.get("_text", "")), key_phrase(best["title"], 5) or "Archive"
            s["credit"] = f"Photo: {best['author'][:28]} | {best['license'][:28]}"
            uses[best["id"]] += 1
            last[best["id"]] = i
        s["sfx"] = [(o, nm) for o, nm in SFX.get(s["kind"], [])]
        cnt += 1
        last_i = i


def plan(scenes, topic, profile, imgs=None):
    th = style.THEMES[profile["theme"] % len(style.THEMES)]
    default_env = annotate_default(topic)
    geo = image_fetcher.country_index()
    ctx = {"arts": topic["articles"], "ai": random.randint(0, 3), "kws": set(topic["keywords"]), "env": default_env, "hist": [],
           "geo": geo, "date_of": {a["link"]: (datetime.datetime.utcfromtimestamp(a["epoch"]).strftime("%b %d, %Y").replace(" 0", " ") if a.get("epoch") else "") for a in topic["articles"]}}
    head = re.sub(r"\s[-|–]\s[^-|–]{2,40}$", "", topic["headline"]).strip()
    shots, tagged, first_done = [], set(), False
    for sc in scenes:
        n, cur = sc["frames"], sc["start_f"]

        def base(kind, frames, params, text=""):
            b = {"kind": kind, "frames": frames, "start_f": cur, "fps": FPS, "th": th, "seed": random.randint(0, 10 ** 6), "sec": sc["sec"],
                 "penv": sc["plan"]["env"], "_text": text[:300], "sfx": [(o * frames / FPS, nm) for o, nm in SFX.get(kind, [])]}
            b.update(params)
            return b
        if sc["sec"] > 0 and sc["sec"] not in tagged and n >= 7 * FPS and not config.IS_SHORT:
            tagged.add(sc["sec"])
            shots.append(base("chapter", 2 * FPS, {"num": sc["sec"], "title": CHAPTERS[sc["sec"]], "nowipe": False}))
            ctx["hist"].append("chapter")
            cur += 2 * FPS
            n -= 2 * FPS
        sents = [x for x in re.split(r"(?<=[.!?])\s+", sc["text"].strip()) if x] or [sc["text"]]
        k = max(1, min(3, int(round(n / (6.0 * FPS))), len(sents)))
        groups, fr = [sents], [n]
        while k > 1:
            g = _groups(sents, k)
            f = _alloc(g, n)
            if len(g) == k and min(f) >= 2 * FPS:
                groups, fr = g, f
                break
            k -= 1
        first = True
        for g, f in zip(groups, fr):
            txt = " ".join(g)
            if not first_done:
                kind, params = "poster", {"title": head, "date": topic.get("date", ""), "source": topic["articles"][0]["source"],
                                          "icon": ENV_ICON.get(default_env, "coins"), "first": True}
                first_done = True
            else:
                kind, params = choose(txt, sc, ctx, first)
                if sc["sec"] > 0 and sc["sec"] not in tagged:
                    params["tag"] = NAMES[sc["sec"]]
                    tagged.add(sc["sec"])
            ctx["hist"].append(kind)
            shots.append(base(kind, f, params, txt))
            cur += f
            first = False
    attach_photos(shots, imgs or [])
    for s in shots:
        s.pop("_text", None)
    print("shot plan:", len(shots), "shots", dict(Counter(s["kind"] for s in shots)))
    return shots


def annotate_default(topic):
    e, _ = env_of(topic["headline"] + " " + " ".join(topic["keywords"]))
    return e or "globe"
