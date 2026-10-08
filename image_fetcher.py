import os, re, io, json, html, time, hashlib, shutil, tarfile
import concurrent.futures as cf
from collections import Counter
import requests
from PIL import Image, ImageFilter, ImageStat
import config

UA = {"User-Agent": f"FinanceExplainerBot/1.0 ({config.WIKI_CONTACT}; educational explainer videos)"}
COMMONS = "https://commons.wikimedia.org/w/api.php"
OPENVERSE = "https://api.openverse.org/v1/images/"
IMGDIR = config.BUILD / "images"
ENV_Q = {"candles": ["stock exchange trading floor", "stock market trading screens"], "barrels": ["oil refinery", "crude oil barrels"],
         "containers": ["container port cranes", "cargo ship containers"], "bank": ["central bank building", "bank headquarters facade"],
         "houses": ["suburban houses neighborhood", "housing construction site"], "chip": ["semiconductor wafer", "data center servers"],
         "coins": ["banknotes currency", "gold coins"], "crowd": ["commuters city street", "shoppers market"],
         "globe": ["container shipping routes", "world map economy"], "skyline": ["city skyline business district", "office buildings downtown"]}
STOP = set("a an the of to in on for and or at by with from as is are was were be been this that it its has have had not but his her their more than into out up about new says said will over after under amid".split())
STOPCAP = set("The This That These Those How Why What When Where Who Which After Before Over Under With Without From Into Amid Says Said New Big Top Here There Their".split())
BAD_TITLE = re.compile(r"\b(logo|icon|nude|naked|sex|porn|gore|corpse|dead body|massacre|execution|screenshot|stub|wordmark|signature|coat of arms)\b", re.I)
LIC_OK = re.compile(r"^(cc0|pd\b|pd-|public domain|cc[- ]by[- ]\d)", re.I)
ALIASES = {"us": "United States of America", "u.s.": "United States of America", "usa": "United States of America", "america": "United States of America",
           "united states": "United States of America", "uk": "United Kingdom", "britain": "United Kingdom", "uae": "United Arab Emirates",
           "south korea": "South Korea", "korea": "South Korea", "russia": "Russia", "czech": "Czechia", "ivory coast": "Ivory Coast"}
DEMONYMS = {"american": "United States of America", "chinese": "China", "indian": "India", "russian": "Russia", "japanese": "Japan",
            "german": "Germany", "french": "France", "british": "United Kingdom", "saudi": "Saudi Arabia", "iranian": "Iran",
            "israeli": "Israel", "turkish": "Turkey", "brazilian": "Brazil", "mexican": "Mexico", "canadian": "Canada",
            "australian": "Australia", "italian": "Italy", "spanish": "Spain", "ukrainian": "Ukraine", "egyptian": "Egypt",
            "nigerian": "Nigeria", "pakistani": "Pakistan", "bangladeshi": "Bangladesh", "indonesian": "Indonesia", "argentine": "Argentina"}


def _toks(s):
    return {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in STOP}


def _clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def _get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=40)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 + 3 * i)
                continue
            return r
        except Exception:
            time.sleep(1 + i)
    return None


def entities(topic):
    h = re.sub(r"\s[-|–]\s[^-|–]{2,40}$", "", topic["headline"])
    out = []
    for m in re.finditer(r"[A-Z][A-Za-z&.'-]+(?:\s+(?:of|the|and|&)\s+[A-Z][A-Za-z&.'-]+|\s+[A-Z][A-Za-z&.'-]+)*", h):
        words = m.group(0).split()
        while words and words[0] in STOPCAP:
            words = words[1:]
        e = " ".join(words).strip(" .'-")
        if len(e) >= 4 and e not in out:
            out.append(e)
    return out[:3]


def recent_ids(last_files=15):
    ids, n = set(), 0
    for f in reversed(sorted(config.USED.glob("*.json"))[-60:]):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if d.get("images"):
            ids |= set(d["images"])
            n += 1
            if n >= last_files:
                break
    return ids


def search_commons(q, limit=24):
    r = _get(COMMONS, {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6,
                       "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1600, "origin": "*"})
    if not r or r.status_code != 200:
        return []
    try:
        pages = (r.json().get("query") or {}).get("pages") or {}
    except Exception:
        return []
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [None])[0]
        if not ii:
            continue
        md = ii.get("extmetadata") or {}
        lic = ((md.get("LicenseShortName") or {}).get("value", "") or "").strip()
        w, h = ii.get("width", 0), ii.get("height", 0)
        if not LIC_OK.match(lic) or ii.get("mime") not in ("image/jpeg", "image/png") or w < 1000 or h < 600 or not 0.6 <= w / float(h) <= 2.4:
            continue
        title = re.sub(r"\.\w{3,4}$", "", re.sub(r"^File:", "", p.get("title", ""))).replace("_", " ")
        if BAD_TITLE.search(title):
            continue
        out.append({"title": title, "url": ii.get("thumburl") or ii.get("url"), "page": ii.get("descriptionurl", ""),
                    "author": (_clean((md.get("Artist") or {}).get("value", "")) or "Unknown author")[:60], "license": lic,
                    "source": "Wikimedia Commons", "_idx": p.get("index", 999)})
    out.sort(key=lambda x: x["_idx"])
    return out


def search_openverse(q, limit=12):
    r = _get(OPENVERSE, {"q": q, "license": "cc0,pdm,by", "page_size": limit, "mature": "false", "category": "photograph"})
    if not r or r.status_code != 200:
        return []
    out = []
    try:
        items = r.json().get("results", [])
    except Exception:
        return []
    for it in items:
        lic = it.get("license", "")
        name = "CC0" if lic == "cc0" else "Public domain" if lic == "pdm" else f"CC BY {it.get('license_version', '')}".strip()
        w, h, title = it.get("width") or 0, it.get("height") or 0, _clean(it.get("title", ""))
        if not it.get("url") or w < 1000 or h < 600 or BAD_TITLE.search(title) or not 0.6 <= w / float(h) <= 2.4:
            continue
        out.append({"title": title or "Photo", "url": it["url"], "page": it.get("foreign_landing_url", ""),
                    "author": (_clean(it.get("creator", "")) or "Unknown author")[:60], "license": name, "source": "Openverse"})
    return out


def rss_candidates(topic):
    """সব ফিডের পুল থেকে বিষয়-মিলিয়ে ছবি (প্রকাশকের কপিরাইট — RSS_IMAGES=0 দিলে বন্ধ)"""
    if not config.RSS_IMAGES:
        return []
    kw = set(topic.get("keywords") or [])
    for e in entities(topic):
        kw |= _toks(e)
    out, seen = [], set()
    for a in topic["articles"]:
        if a.get("image"):
            out.append((9, {"title": a["title"], "url": a["image"], "page": a["link"], "author": a["source"], "source": "RSS: " + a["source"]}))
            seen.add(a["image"])
    for p in topic.get("pool", []):
        sc = len(set(p["tokens"]) & kw)
        if p["image"] and p["image"] not in seen and sc >= 2:
            seen.add(p["image"])
            out.append((sc, {"title": p["title"], "url": p["image"], "page": p["link"], "author": p["source"], "source": "RSS: " + p["source"]}))
    out.sort(key=lambda x: -x[0])
    res = []
    for _, c in out[:16]:
        c.update(license="Publisher image (rights belong to the publisher)", rss=True, env=None, entity=True, query=c["title"])
        res.append(c)
    return res


def _download(c):
    r = _get(c["url"])
    if not r or r.status_code != 200 or len(r.content) < (8000 if c.get("rss") else 20000):
        return None
    try:
        im = Image.open(io.BytesIO(r.content))
        im.load()
        im = im.convert("RGB")
    except Exception:
        return None
    w, h = im.size
    if w < (560 if c.get("rss") else 900) or h < (300 if c.get("rss") else 500):
        return None
    if max(w, h) > 1920:
        k = 1920.0 / max(w, h)
        im = im.resize((int(w * k), int(h * k)), Image.LANCZOS)
    try:
        if ImageStat.Stat(im.convert("L").resize((160, 160)).filter(ImageFilter.FIND_EDGES)).mean[0] < 2.0:
            return None
    except Exception:
        pass
    im.save(IMGDIR / f"{c['id']}.jpg", "JPEG", quality=88)
    return {"id": c["id"], "file": f"{c['id']}.jpg", "title": c["title"][:90], "author": c["author"], "license": c["license"],
            "page": c["page"], "source": c["source"], "env": c.get("env"), "entity": bool(c.get("entity")),
            "tags": sorted(_toks(c["query"]) | _toks(c["title"])), "w": im.width, "h": im.height}


def fetch(topic, scenes, limit=None):
    limit = limit or config.IMG_MAX
    shutil.rmtree(IMGDIR, ignore_errors=True)
    IMGDIR.mkdir(parents=True, exist_ok=True)
    used = recent_ids()
    envs = [e for e, _ in Counter(s["plan"]["env"] for s in scenes).most_common(4)]
    queries = [(e, None, True) for e in entities(topic)]
    kws = topic.get("keywords") or []
    if len(kws) >= 2:
        queries.append((" ".join(kws[:2]), None, False))
    for e in envs:
        for q in ENV_Q.get(e, []):
            queries.append((q, e, False))
    per_q = 4 if config.IS_SHORT else 6
    groups, seen = [], set()

    def addg(res, env, ent, q, cap):
        g = []
        for r in res:
            cid = hashlib.sha1((r["source"] + r["title"]).encode("utf-8")).hexdigest()[:12]
            if cid in seen or cid in used:
                continue
            seen.add(cid)
            r.update(id=cid, env=env, entity=ent, query=q)
            g.append(r)
            if len(g) >= cap:
                break
        groups.append(g)

    for q, env, ent in queries:
        addg(search_commons(q), env, ent, q, per_q)
        time.sleep(0.4)
    if sum(len(g) for g in groups) < config.IMG_MIN:
        print("Commons gave few candidates -> trying Openverse")
        for q, env, ent in queries[:6]:
            addg(search_openverse(q), env, ent, q, 3)
            time.sleep(0.5)
    cands = []
    for c in rss_candidates(topic):
        c["id"] = hashlib.sha1(c["url"].encode("utf-8")).hexdigest()[:12]
        if c["id"] not in used:
            cands.append(c)
    for i in range(per_q):
        for g in groups:
            if i < len(g):
                cands.append(g[i])
    cands = cands[:int(limit * 1.6) + 2]
    metas = []
    with cf.ThreadPoolExecutor(5) as ex:
        for m in ex.map(_download, cands):
            if m:
                metas.append(m)
    metas = metas[:limit]
    (IMGDIR / "images.json").write_text(json.dumps(metas, ensure_ascii=False), encoding="utf-8")
    print(f"images: {len(metas)} downloaded from {len(cands)} candidates | rss: {sum(1 for m in metas if m['source'].startswith('RSS'))}")
    return metas


def pack(used_ids):
    IMGDIR.mkdir(parents=True, exist_ok=True)
    try:
        metas = json.loads((IMGDIR / "images.json").read_text(encoding="utf-8"))
    except Exception:
        metas = []
    metas = [m for m in metas if m["id"] in used_ids]
    keep = {m["file"] for m in metas}
    for f in IMGDIR.glob("*.jpg"):
        if f.name not in keep:
            f.unlink()
    (IMGDIR / "images.json").write_text(json.dumps(metas, ensure_ascii=False), encoding="utf-8")
    with tarfile.open(config.BUILD / "images.tar", "w") as tf:
        for f in sorted(IMGDIR.iterdir()):
            tf.add(str(f), arcname=f.name)
    print(f"images packed: {len(metas)}")
    return metas


def reserve_images(ids):
    if not ids or config.DRY:
        return
    ts = int(time.time())
    (config.USED / f"{ts}-{os.getenv('GITHUB_RUN_ID', 'local')}-{os.getenv('GITHUB_RUN_ATTEMPT', '0')}-img.json").write_text(
        json.dumps({"ts": ts, "images": sorted(ids)}))
    import news_fetcher
    news_fetcher.push_used()


# ---------- মানচিত্র: Natural Earth (পাবলিক ডোমেইন) ----------
def fetch_geo():
    f = IMGDIR / "world.json"
    r = _get(config.GEO_URL)
    if not r or r.status_code != 200:
        print("geo data unavailable -> no map shots")
        return False
    out = []
    for ft in r.json().get("features", []):
        pr, g = ft.get("properties", {}), ft.get("geometry") or {}
        polys = [g["coordinates"]] if g.get("type") == "Polygon" else g.get("coordinates", []) if g.get("type") == "MultiPolygon" else []
        rings = [[[round(x, 1), round(y, 1)] for x, y in p[0]] for p in polys if p]
        name = pr.get("ADMIN") or pr.get("NAME")
        if name and rings:
            out.append({"n": name, "p": rings})
    f.write_text(json.dumps(out), encoding="utf-8")
    print("geo countries:", len(out))
    return True


def country_index():
    """বাক্যাংশ -> দেশের নাম (স্ক্রিপ্টে দেশ চেনার জন্য)"""
    try:
        names = [e["n"] for e in json.loads((IMGDIR / "world.json").read_text(encoding="utf-8"))]
    except Exception:
        return {}
    idx = {n.lower(): n for n in names}
    for k, v in list(ALIASES.items()) + list(DEMONYMS.items()):
        if v in names:
            idx[k] = v
    return idx
