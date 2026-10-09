import math, os, re, json, random
import cairo
import numpy as np
from PIL import Image, ImageFilter, ImageOps
import config, fx

PI = math.pi
LW, LH, S, FPS = config.LW, config.LH, config.S, config.FPS
LAND = LW >= LH
U = min(LW, LH)
ST = {"dir": "", "meta": {}, "cache": {}, "geo": None, "keep": [], "grain": None}
WHITE = (255, 255, 255)
FACE = {"sb": ("Liberation Serif", 0, 1), "si": ("Liberation Serif", 1, 0), "sr": ("Liberation Serif", 0, 0),
        "nb": ("Liberation Sans", 0, 1), "nr": ("Liberation Sans", 0, 0)}


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def eout(t):
    return 1 - (1 - clamp(t)) ** 3


def seg(t, a, b):
    return clamp((t - a) / (b - a)) if b > a else 1.0


def col(c, rgb, a=1.0):
    c.set_source_rgba(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, a)


def mixc(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def font(c, st, size):
    n, sl, bd = FACE[st]
    c.select_font_face(n, cairo.FONT_SLANT_ITALIC if sl else cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bd else cairo.FONT_WEIGHT_NORMAL)
    c.set_font_size(size)


def tw(c, s, size, st="sb"):
    font(c, st, size)
    return c.text_extents(s).x_advance


def text(c, s, x, y, size, rgb, a=1.0, st="sb", al="l"):
    font(c, st, size)
    w = c.text_extents(s).x_advance
    x = x - w / 2 if al == "c" else x - w if al == "r" else x
    col(c, rgb, a)
    c.move_to(x, y)
    c.show_text(s)
    return w


def text_stroke(c, s, x, y, size, fill, stroke=(0, 0, 0), lw=6, st="sb"):
    font(c, st, size)
    c.move_to(x, y)
    c.text_path(s)
    col(c, stroke)
    c.set_line_width(lw)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    c.stroke_preserve()
    col(c, fill)
    c.fill()


def rrect(c, x, y, w, h, r):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    c.new_sub_path()
    c.arc(x + w - r, y + r, r, -PI / 2, 0)
    c.arc(x + w - r, y + h - r, r, 0, PI / 2)
    c.arc(x + r, y + h - r, r, PI / 2, PI)
    c.arc(x + r, y + r, r, PI, 1.5 * PI)
    c.close_path()


def chip(c, label, x, y, size, bg, fg=WHITE, a=1.0, st="nb"):
    w = tw(c, label, size, st) + size * 1.2
    rrect(c, x, y, w, size * 1.7, size * 0.25)
    col(c, bg, a)
    c.fill()
    text(c, label, x + size * 0.6, y + size * 1.2, size, fg, a, st)
    return w


def shadow_rect(c, x, y, w, h, r, a=0.35):
    for i in range(6):
        k = i * U * 0.004
        col(c, (0, 0, 0), a / 7)
        rrect(c, x - k + U * 0.01, y - k + U * 0.016, w + 2 * k, h + 2 * k, r + k)
        c.fill()


def dots(c, x0, y0, x1, y1, step, r, rgb, a):
    col(c, rgb, a)
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            c.arc(x, y, r, 0, 2 * PI)
            c.fill()
            x += step
        y += step


# ---------------- ছবি ----------------
def set_dir(d):
    ST["dir"] = str(d)
    try:
        ST["meta"] = {m["id"]: m for m in json.load(open(os.path.join(ST["dir"], "images.json"), encoding="utf-8"))}
    except Exception:
        ST["meta"] = {}
    print("image index:", len(ST["meta"]))


def surf(im):
    a = np.asarray(im.convert("RGBA"), dtype=np.float32)
    a[..., :3] *= a[..., 3:4] / 255.0
    b = np.ascontiguousarray(a[..., [2, 1, 0, 3]].astype(np.uint8))
    ST["keep"].append(b)
    return cairo.ImageSurface.create_for_data(b, cairo.FORMAT_ARGB32, b.shape[1], b.shape[0], b.shape[1] * 4)


def get(pid, var="col", torn=False, seed=1):
    key = (pid, var, torn, seed)
    if key in ST["cache"]:
        return ST["cache"][key]
    m, g = ST["meta"].get(pid), None
    if m:
        try:
            im = Image.open(os.path.join(ST["dir"], m["file"])).convert("RGB")
            k = min(1.0, (140 if var == "bl" else 1400) / float(max(im.size)))
            if k < 1:
                im = im.resize((max(2, int(im.width * k)), max(2, int(im.height * k))), Image.LANCZOS)
            if var == "bw":
                im = ImageOps.autocontrast(im.convert("L"), cutoff=1).convert("RGB")
            elif var == "ht":
                im = fx.halftone(im, cell=max(3, int(im.width / 240)))
            elif var == "dk":
                im = fx.duotone(im, (8, 12, 28), (226, 232, 244))
            elif var == "bl":
                im = im.filter(ImageFilter.GaussianBlur(2))
            if torn:
                im = fx.torn_frame(im, max(8, int(im.width / 70)), seed)
            g = (surf(im), im.width, im.height)
        except Exception as e:
            print("image load failed:", pid, repr(e)[:100])
    ST["cache"][key] = g
    return g


def blit(c, g, x, y, w, h, a=1.0):
    sf, sw, sh = g
    c.save()
    c.translate(x, y)
    c.scale(w / float(sw), h / float(sh))
    c.set_source_surface(sf, 0, 0)
    c.get_source().set_filter(cairo.FILTER_GOOD)
    c.paint_with_alpha(a)
    c.restore()


def cover(c, g, x, y, w, h, zoom=1.0, fx_=0.5, fy_=0.5, a=1.0):
    sf, sw, sh = g
    k = max(w / float(sw), h / float(sh)) * zoom
    c.save()
    c.rectangle(x, y, w, h)
    c.clip()
    c.translate(x - (sw * k - w) * fx_, y - (sh * k - h) * fy_)
    c.scale(k, k)
    c.set_source_surface(sf, 0, 0)
    c.get_source().set_filter(cairo.FILTER_GOOD)
    c.paint_with_alpha(a)
    c.restore()


def place(c, g, cx, cy, w, ang=0.0, a=1.0, shadow=True):
    sf, sw, sh = g
    h = w * sh / float(sw)
    c.save()
    c.translate(cx, cy)
    c.rotate(ang)
    if shadow:
        shadow_rect(c, -w / 2, -h / 2, w, h, U * 0.006)
    c.translate(-w / 2, -h / 2)
    c.scale(w / float(sw), h / float(sh))
    c.set_source_surface(sf, 0, 0)
    c.get_source().set_filter(cairo.FILTER_GOOD)
    c.paint_with_alpha(a)
    c.restore()
    return h


def paper_bg(c, s, dark=False):
    th = s["th"]
    base = tuple(th["dark"] if dark else th["paper"])
    key = ("paper", base, dark)
    if key not in ST["cache"]:
        ST["cache"][key] = (surf(fx.paper(LW, LH, 11, base, 0.04 if dark else 0.10)), LW, LH)
    blit(c, ST["cache"][key], 0, 0, LW, LH)


# ---------------- টেক্সট লেআউট ----------------
def layout(c, words, maxw, size, stl):
    sp = tw(c, " ", size, stl)
    items, lines, x = [], [[]], 0.0
    for i, w in enumerate(words):
        ww = tw(c, w, size, stl)
        if x > 0 and x + ww > maxw:
            lines.append([])
            x = 0.0
        it = [w, x, len(lines) - 1, ww, i]
        items.append(it)
        lines[-1].append(it)
        x += ww + sp
    return items, lines


def fit_lines(c, words, maxw, maxh, size, mn, stl="sb", lhk=1.12):
    while True:
        items, lines = layout(c, words, maxw, size, stl)
        if len(lines) * size * lhk <= maxh or size <= mn:
            return size, items, lines
        size -= 2


def pick_hl(words):
    idx = [i for i, w in enumerate(words) if re.search(r"\d", w) or (w[:1].isupper() and len(w) > 3 and i > 0)]
    return set(idx[:2]) if idx else {len(words) - 1}


def marker(c, x, y, w, size, rgb, p, seed):
    if p <= 0:
        return
    r = random.Random(seed)

    def j():
        return r.uniform(-size * 0.05, size * 0.05)
    top, bot, xr = y - size * 0.80, y + size * 0.16, x + (w + 8) * p
    col(c, rgb, 0.92)
    c.move_to(x - 4 + j(), top + j())
    c.line_to(xr + j(), top + j())
    c.line_to(xr + j(), bot + j())
    c.line_to(x - 4 + j(), bot + j())
    c.close_path()
    c.fill()


def draw_words(c, words, x0, y0, maxw, size, lh, th, st, delay=0.0, hl=(), stl="sb", rgb=None, al="l", stagger=0.06):
    rgb = rgb or th["ink"]
    items, lines = layout(c, words, maxw, size, stl)

    def sx(ln):
        w = lines[ln][-1][1] + lines[ln][-1][3]
        return 0 if al == "l" else (maxw - w) / 2 if al == "c" else maxw - w
    for it in items:
        if it[4] in hl:
            marker(c, x0 + sx(it[2]) + it[1], y0 + it[2] * lh, it[3], size, th["hl"],
                   eout(seg(st, delay + 0.3 + it[4] * stagger, delay + 0.7 + it[4] * stagger)), it[4] * 7 + 3)
    for it in items:
        a = ease(seg(st, delay + it[4] * stagger, delay + it[4] * stagger + 0.3))
        if a > 0:
            text(c, it[0], x0 + sx(it[2]) + it[1], y0 + it[2] * lh + (1 - a) * size * 0.25, size, rgb, a, stl)
    return len(lines)


def kin(c, words, cx, cy, maxw, base, th, st, delay=0.0):
    """kinetic typography: হালকা ইটালিক সেরিফ + মোটা রঙিন শব্দ, এক এক করে ঢোকে"""
    its = []
    for w, k in words:
        sz, stl = (base * 1.55, "sb") if k == "b" else (base, "si")
        its.append([w.upper() if k == "b" else w, k, sz, stl, tw(c, w.upper() if k == "b" else w, sz, stl)])
    sp, lines, x = base * 0.3, [[]], 0.0
    for it in its:
        if x > 0 and x + it[4] > maxw:
            lines.append([])
            x = 0.0
        lines[-1].append(it)
        x += it[4] + sp
    hs = [max(i[2] for i in ln) * 1.15 for ln in lines]
    y, idx = cy - sum(hs) / 2 + hs[0] * 0.8, 0
    for ln, h in zip(lines, hs):
        x = cx - (sum(i[4] for i in ln) + sp * (len(ln) - 1)) / 2
        for it in ln:
            a = ease(seg(st, delay + idx * 0.13, delay + idx * 0.13 + 0.35))
            idx += 1
            if a > 0:
                colr = th["acc"] if it[1] == "b" else th["ink"]
                yy = y + (1 - a) * it[2] * 0.3
                for dx in ((-4, 0, 4) if a < 0.7 else (0,)):
                    text(c, it[0], x + dx, yy, it[2], colr, a * (0.35 if a < 0.7 else 1.0), it[3])
            x += it[4] + sp
        y += h


# ---------------- আইকন ----------------
def _ell(c, x, y, rx, ry):
    c.save()
    c.translate(x, y)
    c.scale(rx, ry)
    c.arc(0, 0, 1, 0, 2 * PI)
    c.restore()


def _ic_coins(c, z, th, a, t):
    for i in range(3):
        _ell(c, 0, z * 0.2 - i * z * 0.16, z * 0.34, z * 0.11)
        col(c, th["acc2"], a)
        c.fill_preserve()
        col(c, th["ink"], a)
        c.set_line_width(z * 0.015)
        c.stroke()


def _ic_coin(c, z, th, a, t):
    c.arc(0, 0, z * 0.4, 0, 2 * PI)
    col(c, th["acc2"], a)
    c.fill_preserve()
    col(c, th["ink"], a)
    c.set_line_width(z * 0.02)
    c.stroke()
    text(c, "$", 0, z * 0.14, z * 0.42, th["ink"], a, "sb", "c")


def _ic_bank(c, z, th, a, t):
    col(c, th["ink"], a)
    c.move_to(-z * 0.45, -z * 0.1)
    c.line_to(0, -z * 0.42)
    c.line_to(z * 0.45, -z * 0.1)
    c.close_path()
    c.fill()
    for i in range(4):
        c.rectangle(-z * 0.36 + i * z * 0.24, -z * 0.04, z * 0.1, z * 0.34)
    c.fill()
    c.rectangle(-z * 0.46, z * 0.34, z * 0.92, z * 0.08)
    col(c, th["acc"], a)
    c.fill()


def _ic_barrel(c, z, th, a, t):
    rrect(c, -z * 0.25, -z * 0.36, z * 0.5, z * 0.72, z * 0.1)
    col(c, th["ink"], a)
    c.fill()
    for y in (-0.2, 0.15):
        c.rectangle(-z * 0.26, z * y, z * 0.52, z * 0.06)
    col(c, th["acc"], a)
    c.fill()


def _ic_container(c, z, th, a, t):
    rrect(c, -z * 0.46, -z * 0.22, z * 0.92, z * 0.44, z * 0.03)
    col(c, th["acc"], a)
    c.fill()
    col(c, th["ink"], a * 0.6)
    for i in range(9):
        c.rectangle(-z * 0.4 + i * z * 0.1, -z * 0.2, z * 0.02, z * 0.4)
    c.fill()


def _ic_chip(c, z, th, a, t):
    col(c, th["ink"], a)
    for i in range(5):
        for sd in (-1, 1):
            c.rectangle(-z * 0.2 + i * z * 0.1 - z * 0.015, sd * z * 0.3 - z * 0.05, z * 0.03, z * 0.1)
            c.rectangle(sd * z * 0.3 - z * 0.05, -z * 0.2 + i * z * 0.1 - z * 0.015, z * 0.1, z * 0.03)
    c.fill()
    rrect(c, -z * 0.26, -z * 0.26, z * 0.52, z * 0.52, z * 0.04)
    c.fill()
    rrect(c, -z * 0.14, -z * 0.14, z * 0.28, z * 0.28, z * 0.02)
    col(c, th["acc"], a)
    c.fill()


def _ic_house(c, z, th, a, t):
    c.rectangle(-z * 0.3, -z * 0.05, z * 0.6, z * 0.38)
    col(c, th["paper"], a)
    c.fill_preserve()
    col(c, th["ink"], a)
    c.set_line_width(z * 0.02)
    c.stroke()
    c.move_to(-z * 0.38, -z * 0.05)
    c.line_to(0, -z * 0.38)
    c.line_to(z * 0.38, -z * 0.05)
    c.close_path()
    col(c, th["acc"], a)
    c.fill()
    c.rectangle(-z * 0.06, z * 0.12, z * 0.12, z * 0.21)
    col(c, th["ink"], a)
    c.fill()


def _ic_chart(c, z, th, a, t):
    for i, h in enumerate((0.25, 0.4, 0.33, 0.55)):
        c.rectangle(-z * 0.36 + i * z * 0.19, z * 0.3 - z * h, z * 0.13, z * h)
        col(c, th["acc"] if i == 3 else th["ink"], a)
        c.fill()
    col(c, th["acc2"], a)
    c.set_line_width(z * 0.03)
    c.move_to(-z * 0.4, z * 0.1)
    c.line_to(-z * 0.12, -z * 0.05)
    c.line_to(z * 0.12, z * 0.02)
    c.line_to(z * 0.4, -z * 0.28)
    c.stroke()


def _ic_globe(c, z, th, a, t):
    col(c, th["ink"], a)
    c.set_line_width(z * 0.02)
    c.arc(0, 0, z * 0.4, 0, 2 * PI)
    c.stroke()
    for k in (0.25, 0.6):
        _ell(c, 0, 0, z * 0.4 * k, z * 0.4)
        c.stroke()
    c.move_to(-z * 0.4, 0)
    c.line_to(z * 0.4, 0)
    c.stroke()
    c.arc(z * 0.12, -z * 0.12, z * 0.05, 0, 2 * PI)
    col(c, th["acc"], a)
    c.fill()


def _ic_person(c, z, th, a, t):
    col(c, th["ink"], a)
    c.arc(0, -z * 0.28, z * 0.12, 0, 2 * PI)
    c.fill()
    rrect(c, -z * 0.17, -z * 0.14, z * 0.34, z * 0.5, z * 0.1)
    col(c, th["acc"], a)
    c.fill()


def _ic_doc(c, z, th, a, t):
    rrect(c, -z * 0.28, -z * 0.38, z * 0.56, z * 0.76, z * 0.03)
    col(c, th["paper"], a)
    c.fill_preserve()
    col(c, th["ink"], a)
    c.set_line_width(z * 0.02)
    c.stroke()
    for i in range(5):
        c.rectangle(-z * 0.2, -z * 0.28 + i * z * 0.13, z * (0.4 if i < 4 else 0.22), z * 0.04)
    col(c, th["acc"], a)
    c.fill()


def _ic_skyline(c, z, th, a, t):
    for i, h in enumerate((0.3, 0.55, 0.4, 0.7, 0.35)):
        c.rectangle(-z * 0.4 + i * z * 0.17, z * 0.3 - z * h, z * 0.15, z * h)
        col(c, th["acc"] if i == 3 else th["ink"], a)
        c.fill()


ICONS = {"coins": _ic_coins, "coin": _ic_coin, "bank": _ic_bank, "barrel": _ic_barrel, "container": _ic_container, "chip": _ic_chip,
         "house": _ic_house, "chart": _ic_chart, "globe": _ic_globe, "person": _ic_person, "doc": _ic_doc, "skyline": _ic_skyline}
ENV_ICON = {"candles": "chart", "barrels": "barrel", "containers": "container", "bank": "bank", "houses": "house", "chip": "chip",
            "coins": "coins", "crowd": "person", "globe": "globe", "skyline": "skyline"}


def icon(c, name, cx, cy, z, th, a=1.0, t=0.0):
    for i in range(5):
        col(c, (0, 0, 0), 0.05 * a)
        _ell(c, cx + z * 0.05, cy + z * 0.5, z * (0.36 + i * 0.05), z * (0.07 + i * 0.012))
        c.fill()
    c.save()
    c.translate(cx, cy)
    ICONS.get(name, _ic_coins)(c, z, th, a, t)
    c.restore()


def figure(c, x, y, h, colr, th, walk=0.0, arms=(0.3, 0.3), mood=1):
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    lw = h * 0.07
    hip, sh = (x, y - h * 0.42), (x, y - h * 0.74)
    col(c, th["ink"])
    c.set_line_width(lw)
    for sg in (-1, 1):
        a = math.sin(walk) * 0.5 * sg
        c.move_to(*hip)
        c.line_to(hip[0] + math.sin(a) * h * 0.42, hip[1] + math.cos(a) * h * 0.42)
    c.stroke()
    col(c, colr)
    c.set_line_width(lw * 1.7)
    c.move_to(*hip)
    c.line_to(*sh)
    c.stroke()
    c.set_line_width(lw * 0.9)
    for i, sg in enumerate((-1, 1)):
        c.move_to(*sh)
        c.line_to(sh[0] + sg * math.sin(arms[i]) * h * 0.36, sh[1] + math.cos(arms[i]) * h * 0.36)
    c.stroke()
    col(c, (236, 192, 160))
    c.arc(x, y - h * 0.88, h * 0.11, 0, 2 * PI)
    c.fill()
    col(c, th["ink"])
    c.set_line_width(max(1.2, h * 0.012))
    if mood:
        c.arc(x, y - h * (0.865 if mood > 0 else 0.82), h * 0.04, 0.3 if mood > 0 else PI + 0.3, PI - 0.3 if mood > 0 else 2 * PI - 0.3)
        c.stroke()
      # ---------------- সাধারণ ফিনিশ: ভিগনেট, গ্রেইন, ট্রানজিশন, ট্যাগ ----------------
def finish(c, s, t, dark=False):
    th = s["th"]
    dur = s["frames"] / float(FPS)
    st = t * dur
    vg = cairo.RadialGradient(LW / 2, LH / 2, U * 0.45, LW / 2, LH / 2, max(LW, LH) * 0.8)
    vg.add_color_stop_rgba(0, 0, 0, 0, 0)
    vg.add_color_stop_rgba(1, 0, 0, 0, 0.5 if dark else 0.26)
    c.set_source(vg)
    c.paint()
    if ST["grain"] is None:
        ST["grain"] = [(surf(fx.grain(LW * 2 + 160, LH * 2 + 160, 5 + i)), LW * 2 + 160, LH * 2 + 160) for i in range(3)]
    r = random.Random(s["seed"] + int(st * FPS))
    c.save()
    c.scale(0.5, 0.5)
    c.set_source_surface(ST["grain"][r.randint(0, 2)][0], -r.randint(0, 150), -r.randint(0, 150))
    c.paint_with_alpha(0.55 if not dark else 0.8)
    c.restore()
    if s.get("tag") and st < 2.8 and s["kind"] != "chapter":
        a = clamp(min(st / 0.3, (2.8 - st) / 0.4))
        chip(c, s["tag"].upper(), U * 0.04, U * 0.04, U * 0.028, th["acc"], WHITE, a)
    if s.get("credit"):
        text(c, s["credit"], LW - U * 0.03, LH - U * 0.03, U * 0.017, WHITE if dark else th["ink"], 0.75, "nr", "r")
    if st < 0.38 and not s.get("nowipe"):
        p = st / 0.38
        x = (LW + U * 0.6) * p
        col(c, th["acc"], 0.92)
        c.move_to(x - U * 0.55 + U * 0.18, 0)
        c.line_to(x + U * 0.18, 0)
        c.line_to(x, LH)
        c.line_to(x - U * 0.55, LH)
        c.close_path()
        c.fill()
    if s.get("first") and st < 0.4:
        col(c, (0, 0, 0), 1 - st / 0.4)
        c.paint()


# ---------------- শট ----------------
def k_poster(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    g = get(s.get("photo"), "ht", True, s["seed"]) if s.get("photo") else None
    cx, cy = (LW * 0.74, LH * 0.52) if LAND else (LW * 0.5, LH * 0.34)
    r = (LH * 0.42 if LAND else LW * 0.50) * eout(seg(st, 0.0, 0.6))
    col(c, th["acc"], 0.96)
    c.arc(cx, cy, r, 0, 2 * PI)
    c.fill()
    k = eout(seg(st, 0.15, 0.85))
    pw = (LW * 0.44 if LAND else LW * 0.84) * (1 + 0.04 * t)
    if g:
        place(c, g, cx + (1 - k) * LW * 0.2, cy, pw, -0.03 + 0.02 * t, k)
    else:
        icon(c, s.get("icon", "coins"), cx, cy, U * 0.5 * k, th, k, t)
    tx, tmax = (LW * 0.05, LW * 0.5) if LAND else (LW * 0.07, LW * 0.86)
    ty0, th_ = (LH * 0.2, LH * 0.62) if LAND else (LH * 0.62, LH * 0.28)
    words = s["title"].split()
    size, items, lines = fit_lines(c, words, tmax, th_, 78 if LAND else 60, 30)
    if s.get("date"):
        chip(c, s["date"], tx, ty0 - size * 1.0 - U * 0.03, U * 0.026, th["acc"], WHITE, eout(seg(st, 0.2, 0.6)))
    draw_words(c, words, tx, ty0 + size * 0.7, tmax, size, size * 1.12, th, st, 0.4, pick_hl(words))
    yy = ty0 + len(lines) * size * 1.12 + size * 0.3
    if s.get("source"):
        a = ease(seg(st, 1.2, 1.8))
        text(c, s["source"], tx, yy + size * 0.5, size * 0.42, th["ink"], a, "sb")
        col(c, th["ink"], a * 0.6)
        c.rectangle(tx + tw(c, s["source"], size * 0.42) + 12, yy + size * 0.38, tmax * 0.35 * a, 1.5)
        c.fill()
    finish(c, s, t)


def k_hist(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s, True)
    gb = get(s.get("photo"), "bl")
    if gb:
        cover(c, gb, 0, 0, LW, LH, 1.15 + 0.06 * t, 0.5, 0.5, 0.55)
    col(c, (6, 10, 24), 0.55)
    c.paint()
    g = get(s.get("photo"), "dk", True, s["seed"])
    if g:
        w = (LW * 0.80 if LAND else LW * 0.92) * (1 + 0.05 * t)
        place(c, g, LW / 2, LH * 0.45, w, -0.012 + 0.02 * t, eout(seg(st, 0.0, 0.5)))
    col(c, th["acc"], 0.10)
    c.paint()
    a = eout(seg(st, 0.5, 1.1))
    px, py = (LW * 0.46 if LAND else LW * 0.08) + (1 - a) * LW * 0.3, LH * 0.70 if LAND else LH * 0.76
    pw = LW * 0.48 if LAND else LW * 0.84
    rrect(c, px, py, pw, U * 0.2, U * 0.012)
    col(c, (8, 12, 26), 0.82 * a)
    c.fill()
    col(c, th["acc"], a)
    c.rectangle(px, py, U * 0.012, U * 0.2)
    c.fill()
    if s.get("year"):
        text(c, s["year"], px + U * 0.04, py + U * 0.085, U * 0.075, WHITE, a, "sb")
    cap = (s.get("caption") or "")[:60]
    chip(c, cap, px + U * 0.04, py + U * 0.105, U * 0.027, th["acc"], WHITE, a, "sb")
    finish(c, s, t, True)


def polaroid(c, g, cx, cy, w, ang, a, th):
    sf, sw, sh = g
    ph = w * sh / float(sw)
    pad = w * 0.045
    c.save()
    c.translate(cx, cy)
    c.rotate(ang)
    hh = ph + pad * 3.2
    shadow_rect(c, -w / 2 - pad, -hh / 2, w + 2 * pad, hh, 3)
    rrect(c, -w / 2 - pad, -hh / 2, w + 2 * pad, hh, 3)
    col(c, (248, 246, 240), a)
    c.fill()
    blit(c, g, -w / 2, -hh / 2 + pad, w, ph, a)
    col(c, th["acc"], a)
    c.arc(0, -hh / 2 + pad * 0.1, w * 0.03, 0, 2 * PI)
    c.fill()
    c.restore()


def k_collage(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s, True)
    ids = s.get("photos") or []
    g0 = get(ids[0], "bl") if ids else None
    if g0:
        cover(c, g0, 0, 0, LW, LH, 1.2, 0.5, 0.5, 0.35)
    col(c, (10, 10, 14), 0.6)
    c.paint()
    pos = [(0.26, 0.40, -0.08), (0.74, 0.36, 0.07), (0.50, 0.68, 0.03)] if LAND else [(0.5, 0.22, -0.05), (0.5, 0.48, 0.06), (0.5, 0.74, -0.03)]
    w = U * (0.5 if LAND else 0.62)
    pts = []
    for i, pid in enumerate(ids[:3]):
        g = get(pid, "bw")
        if not g:
            continue
        a = eout(seg(st, 0.15 + i * 0.35, 0.7 + i * 0.35))
        x, y, ang = pos[i]
        polaroid(c, g, LW * x, LH * y + (1 - a) * LH * 0.2, w, ang * a, a, th)
        pts.append((LW * x, LH * y - w * 0.3))
    col(c, th["acc"], 0.9)
    c.set_line_width(max(1.5, U * 0.003))
    for i in range(len(pts) - 1):
        p = eout(seg(st, 0.9 + i * 0.4, 1.5 + i * 0.4))
        c.move_to(*pts[i])
        c.line_to(pts[i][0] + (pts[i + 1][0] - pts[i][0]) * p, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * p)
        c.stroke()
    lab = (s.get("label") or "").upper()
    if lab:
        a = ease(seg(st, 1.2, 1.8))
        size = U * 0.05
        ww = tw(c, lab, size) + U * 0.08
        rrect(c, LW / 2 - ww / 2, LH * 0.5 - size, ww, size * 2, size * 0.3)
        col(c, th["acc"], 0.88 * a)
        c.fill()
        text(c, lab, LW / 2, LH * 0.5 + size * 0.35, size, WHITE, a, "sb", "c")
    finish(c, s, t, True)


def k_kinetic(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    dots(c, LW * 0.08, LH * 0.08, LW * 0.92, LH * 0.92, U * 0.07, U * 0.0035, th["ink"], 0.17 * eout(seg(st, 0, 0.6)))
    ln = LW * 1.6
    c.save()
    c.set_dash([ln * eout(seg(st, 0.1, 1.2)), ln * 2])
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    col(c, th["acc"], 0.22)
    c.set_line_width(U * 0.06)
    c.move_to(-LW * 0.1, LH * 1.05)
    c.curve_to(LW * 0.25, LH * 0.55, LW * 0.55, LH * 0.8, LW * 1.1, LH * 0.15)
    c.stroke()
    c.restore()
    ix, iy, iz = (LW * 0.78, LH * 0.5, U * 0.5) if LAND else (LW * 0.5, LH * 0.2, LW * 0.5)
    col(c, th["ink"], 0.35)
    c.set_line_width(1.2)
    for i in range(2):
        c.arc(ix, iy, iz * (0.62 + 0.18 * i) * eout(seg(st, 0.1 * i, 0.9)), 0, 2 * PI)
        c.stroke()
    k = eout(seg(st, 0.05, 0.7))
    icon(c, s.get("icon", "coins"), ix, iy + math.sin(st * 1.6) * U * 0.012, iz * k, th, k, t)
    tcx, tmax = (LW * 0.36, LW * 0.5) if LAND else (LW * 0.5, LW * 0.82)
    cy = LH * 0.5 if LAND else LH * 0.55
    kin(c, s["words"], tcx, cy, tmax, U * (0.06 if LAND else 0.07), th, st, 0.25)
    if s.get("body"):
        a = ease(seg(st, 1.6, 2.2))
        lines = []
        cur = ""
        for w in s["body"].split():
            if tw(c, (cur + " " + w).strip(), U * 0.028, "nr") > tmax:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        lines.append(cur)
        for i, l in enumerate(lines[:3]):
            text(c, l, tcx, cy + U * (0.2 if LAND else 0.22) + i * U * 0.04, U * 0.028, th["ink"], 0.75 * a, "nr", "c")
    if st < 1.3:
        for i in range(5):
            p = (st * 0.9 + i * 0.17) % 1.4
            for q in range(6):
                pp = p - q * 0.025
                x = LW * (pp * 1.3 - 0.15)
                y = LH * (0.15 + 0.14 * i) + math.sin(pp * 5 + i) * U * 0.05
                col(c, th["acc2"], 0.5 * (1 - q / 6.0) * (1 - st / 1.3))
                c.arc(x, y, U * 0.03, 0, 2 * PI)
                c.fill()
    finish(c, s, t)


def _fmt(v, s):
    return f"{s.get('sym', '')}{v:,.{int(s.get('dec', 0))}f}{s.get('suffix', '')}"


def k_stat(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    val = float(s["val"])
    k = eout(seg(st, 0.1, 0.9))
    txt = _fmt(val * k, s)
    chip(c, "KEY FIGURE", LW * 0.07, LH * 0.14, U * 0.026, th["acc"], WHITE, eout(seg(st, 0, 0.4)))
    mw = LW * (0.5 if LAND else 0.86)
    size = U * 0.2
    while tw(c, txt if k > 0.99 else _fmt(val, s), size) > mw and size > 20:
        size -= 4
    x = LW * 0.07
    y = LH * (0.46 if LAND else 0.4)
    marker(c, x, y, tw(c, _fmt(val, s), size), size, th["hl"], eout(seg(st, 0.9, 1.5)), 5)
    text(c, txt, x, y, size, th["ink"], 1.0, "sb")
    d = s.get("dir", 0)
    if d:
        ax, ay = x + tw(c, _fmt(val, s), size) + size * 0.35, y - size * 0.3
        col(c, (60, 200, 120) if d > 0 else (220, 70, 60), eout(seg(st, 1.0, 1.4)))
        c.move_to(ax, ay + d * -size * 0.3)
        c.line_to(ax + size * 0.22, ay + d * size * 0.12)
        c.line_to(ax - size * 0.22, ay + d * size * 0.12)
        c.close_path()
        c.fill()
    if s.get("label"):
        words = s["label"].split()
        draw_words(c, words, x, y + U * 0.09, mw, U * 0.04, U * 0.052, th, st, 0.8, stl="si", al="l")
    cx, cy, rr = (LW * 0.78, LH * 0.5, U * 0.28) if LAND else (LW * 0.5, LH * 0.74, U * 0.2)
    if s.get("suffix") == "%" and val <= 100:
        c.set_line_cap(cairo.LINE_CAP_ROUND)
        c.set_line_width(rr * 0.2)
        col(c, th["ink"], 0.12)
        c.arc(cx, cy, rr, 0, 2 * PI)
        c.stroke()
        col(c, th["acc"])
        c.arc(cx, cy, rr, -PI / 2, -PI / 2 + 2 * PI * val / 100.0 * k + 0.001)
        c.stroke()
    else:
        icon(c, s.get("icon", "coins"), cx, cy, rr * 2 * k, th, k, t)
    finish(c, s, t)


def k_bars(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    A, B = s["a"], s["b"]
    mx = max(A["val"], B["val"], 1e-9)
    base, maxh, bw = LH * 0.74, LH * 0.45, LW * (0.16 if LAND else 0.26)
    for i, (it, x) in enumerate(((A, LW * 0.32), (B, LW * 0.68))):
        k = eout(seg(st, 0.1 + i * 0.3, 0.8 + i * 0.3))
        h = max(2.0, maxh * it["val"] / mx * k)
        col(c, th["acc"] if i else th["ink"], 0.92)
        c.rectangle(x - bw / 2, base - h, bw, h)
        c.fill()
        text(c, _fmt(it["val"] * k, it), x, base - h - U * 0.03, U * 0.06, th["ink"], 1.0, "sb", "c")
        text(c, it["label"][:22], x, base + U * 0.06, U * 0.036, th["ink"], 0.8, "si", "c")
    col(c, th["ink"], 0.5)
    c.rectangle(LW * 0.12, base, LW * 0.76, 2)
    c.fill()
    finish(c, s, t)


def k_timeline(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    ys = s["years"]
    lo, hi = min(ys), max(ys)
    lo = lo - 1 if lo == hi else lo
    x0, x1, y = LW * 0.1, LW * 0.9, LH * 0.5
    k = eout(seg(st, 0.0, 0.9))
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.set_line_width(U * 0.01)
    col(c, th["ink"], 0.25)
    c.move_to(x0, y)
    c.line_to(x1, y)
    c.stroke()
    col(c, th["acc"])
    c.move_to(x0, y)
    c.line_to(x0 + (x1 - x0) * k, y)
    c.stroke()
    for i, yr in enumerate(ys):
        x = x0 + (x1 - x0) * (yr - lo) / float(hi - lo)
        pk = eout(seg(st, 0.3 + 0.25 * i, 0.7 + 0.25 * i))
        col(c, th["acc"])
        c.arc(x, y, U * 0.026 * pk, 0, 2 * PI)
        c.fill()
        lab = str((s.get("labels") or [str(v) for v in ys])[i])
        up = i % 2 == 0
        text(c, lab, x, y - U * 0.1 if up else y + U * 0.17, U * 0.075, th["ink"], pk, "sb", "c")
        marker(c, x - tw(c, lab, U * 0.075) / 2, y - U * 0.1 if up else y + U * 0.17, tw(c, lab, U * 0.075), U * 0.075, th["hl"], 0.0, 1)
    finish(c, s, t)


def k_flow(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    nodes = s["nodes"][:5]
    n = len(nodes)
    if LAND:
        bw, bh = min(LW * 0.86 / n - U * 0.04, U * 0.42), U * 0.2
        pos = [(LW * 0.07 + bw / 2 + (LW * 0.86 - bw) * i / max(1, n - 1), LH * 0.5) for i in range(n)]
    else:
        bw, bh = LW * 0.76, min(LH * 0.72 / n - U * 0.03, U * 0.17)
        pos = [(LW / 2, LH * 0.16 + bh / 2 + (LH * 0.68 - bh) * i / max(1, n - 1)) for i in range(n)]
    for i in range(n):
        a0 = i * 0.9 / n
        k = eout(seg(st, a0, a0 + 0.35))
        if i > 0:
            p = eout(seg(st, a0 - 0.15, a0 + 0.2))
            (xa, ya), (xb, yb) = pos[i - 1], pos[i]
            col(c, th["acc"], 0.9)
            c.set_line_width(U * 0.008)
            c.move_to(xa + (bw / 2 if LAND else 0), ya + (0 if LAND else bh / 2))
            c.line_to(xa + (xb - xa) * p + (bw / 2 if LAND else 0) * (1 - p) - (bw / 2 if LAND else 0) * p,
                      ya + (yb - ya) * p + (0 if LAND else bh / 2) * (1 - p) - (0 if LAND else bh / 2) * p)
            c.stroke()
        if k <= 0.01:
            continue
        c.save()
        c.translate(*pos[i])
        c.scale(0.85 + 0.15 * k, 0.85 + 0.15 * k)
        shadow_rect(c, -bw / 2, -bh / 2, bw, bh, U * 0.02, 0.3 * k)
        rrect(c, -bw / 2, -bh / 2, bw, bh, U * 0.02)
        col(c, (252, 251, 247), k)
        c.fill_preserve()
        col(c, th["acc"] if i == n - 1 else th["ink"], k)
        c.set_line_width(U * (0.01 if i == n - 1 else 0.005))
        c.stroke()
        size, items, lines = fit_lines(c, nodes[i].split(), bw * 0.86, bh * 0.7, U * 0.05, 14)
        for ln_i, ln in enumerate(lines[:3]):
            text(c, " ".join(w[0] for w in ln), 0, -(len(lines) - 1) * size * 0.55 + ln_i * size * 1.1 + size * 0.3, size, th["ink"], k, "sb", "c")
        c.restore()
    finish(c, s, t)


def k_versus(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    tilt = s.get("tilt", 0)
    boxes = ([(LW * 0.05, LH * 0.2, LW * 0.42, LH * 0.6), (LW * 0.53, LH * 0.2, LW * 0.42, LH * 0.6)] if LAND
             else [(LW * 0.07, LH * 0.14, LW * 0.86, LH * 0.34), (LW * 0.07, LH * 0.52, LW * 0.86, LH * 0.34)])
    for i, (x, y, w, h) in enumerate(boxes):
        a = eout(seg(st, 0.1 + i * 0.3, 0.7 + i * 0.3))
        yy = y + (1 - a) * LH * 0.1 + (tilt * (-1 if i == 0 else 1) * U * 0.015 * ease(seg(st, 1.0, 1.8)))
        shadow_rect(c, x, yy, w, h, U * 0.02, 0.3 * a)
        rrect(c, x, yy, w, h, U * 0.02)
        col(c, (252, 251, 247), a)
        c.fill_preserve()
        col(c, (40, 160, 100) if i == 0 else (210, 60, 50), a)
        c.set_line_width(U * 0.008)
        c.stroke()
        chip(c, "THE CASE FOR" if i == 0 else "THE CASE AGAINST", x + w * 0.05, yy + h * 0.06, U * 0.026, (40, 160, 100) if i == 0 else (210, 60, 50), WHITE, a)
        words = (s.get("left", "") if i == 0 else s.get("right", "")).split() or ["—"]
        size, items, lines = fit_lines(c, words, w * 0.86, h * 0.5, U * 0.07, 16)
        draw_words(c, words, x + w * 0.07, yy + h * 0.45, w * 0.86, size, size * 1.12, th, st, 0.5 + i * 0.3)
    r = U * 0.07 * eout(seg(st, 0.7, 1.1))
    col(c, th["acc"])
    c.arc(LW / 2, LH * 0.5, r, 0, 2 * PI)
    c.fill()
    text(c, "VS", LW / 2, LH * 0.5 + r * 0.3, r * 0.8, WHITE, 1.0, "sb", "c")
    finish(c, s, t)


def k_headline(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    cw, ch = (LW * 0.80, LH * 0.66) if LAND else (LW * 0.90, LH * 0.5)
    x = (LW - cw) / 2
    a = eout(seg(st, 0, 0.45))
    y = (LH * 0.14 if LAND else LH * 0.2) + (1 - a) * LH * 0.15
    shadow_rect(c, x, y, cw, ch, U * 0.01, 0.4)
    rrect(c, x, y, cw, ch, U * 0.01)
    col(c, (252, 251, 247), 1.0)
    c.fill()
    chip(c, s.get("date", ""), x + cw * 0.05, y + ch * 0.07, U * 0.028, th["acc"]) if s.get("date") else None
    words = s["title"].split()
    size, items, lines = fit_lines(c, words, cw * 0.9, ch * 0.42, U * (0.08 if LAND else 0.06), 20)
    ty = y + ch * 0.32
    draw_words(c, words, x + cw * 0.05, ty, cw * 0.9, size, size * 1.12, th, st, 0.3, pick_hl(words))
    sy = ty + len(lines) * size * 1.12 + size * 0.1
    if s.get("snip"):
        sw = s["snip"].split()
        draw_words(c, sw, x + cw * 0.05, sy, cw * 0.9, U * 0.034, U * 0.046, th, st, 1.0, stl="nr", al="l", stagger=0.03)
    fy = y + ch * 0.9
    text(c, s.get("src", ""), x + cw * 0.05, fy, U * 0.05, th["ink"], ease(seg(st, 1.2, 1.7)), "sb")
    col(c, th["ink"], 0.5)
    c.rectangle(x + cw * 0.05 + tw(c, s.get("src", ""), U * 0.05) + 14, fy - U * 0.015, cw * 0.3 * ease(seg(st, 1.2, 1.9)), 1.5)
    c.fill()
    p = eout(seg(st, 1.3, 2.0))
    if p > 0:
        col(c, th["acc"], 0.95)
        c.set_line_width(U * 0.006)
        c.set_line_cap(cairo.LINE_CAP_ROUND)
        c.save()
        c.set_dash([U * 0.35 * p, U])
        c.move_to(x + cw * 0.82, y + ch * 0.92)
        c.curve_to(x + cw * 0.95, y + ch * 0.8, x + cw * 0.97, y + ch * 0.55, x + cw * 0.9, y + ch * 0.4)
        c.stroke()
        c.restore()
    finish(c, s, t)
  def load_geo():
    if ST["geo"] is None:
        ST["geo"] = {}
        try:
            for e in json.load(open(os.path.join(ST["dir"], "world.json"), encoding="utf-8")):
                polys = e["p"]
                big = max(polys, key=len)
                xs = [p[0] for p in big]
                ys = [p[1] for p in big]
                allx = [p[0] for r in polys for p in r]
                ally = [p[1] for r in polys for p in r]
                ST["geo"][e["n"]] = {"p": polys, "bb": (min(allx), min(ally), max(allx), max(ally)),
                                     "ctr": ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)}
        except Exception as ex:
            print("no geo data:", repr(ex)[:80])
    return ST["geo"]


def k_map(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    geo = load_geo()
    names = [n for n in s.get("countries", []) if n in geo]
    if not names:
        return k_ripple(c, s, t)
    paper_bg(c, s, True)
    x0 = min(geo[n]["bb"][0] for n in names)
    y0 = min(geo[n]["bb"][1] for n in names)
    x1 = max(geo[n]["bb"][2] for n in names)
    y1 = max(geo[n]["bb"][3] for n in names)
    lon_c, lat_c = (x0 + x1) / 2, (y0 + y1) / 2
    bw, bh = max(x1 - x0, 10) * 1.9, max(y1 - y0, 6) * 1.9
    sc = min(LW / bw, LH / bh) * (0.3 + 0.7 * eout(seg(t, 0, 0.95)))

    def P(lon, lat):
        return LW / 2 + (lon - lon_c) * sc, LH / 2 - (lat - lat_c) * sc

    def path(polys):
        for ring in polys:
            for i, (lo, la) in enumerate(ring):
                (c.move_to if i == 0 else c.line_to)(*P(lo, la))
            c.close_path()
    for n, e in geo.items():
        bx0, by0 = P(e["bb"][0], e["bb"][3])
        bx1, by1 = P(e["bb"][2], e["bb"][1])
        if bx1 < -50 or bx0 > LW + 50 or by1 < -50 or by0 > LH + 50 or n in names:
            continue
        path(e["p"])
        col(c, (70, 70, 76), 0.85)
        c.fill_preserve()
        col(c, (24, 24, 28), 0.9)
        c.set_line_width(0.6)
        c.stroke()
    for n in names:
        path(geo[n]["p"])
        col(c, WHITE, 0.35 * eout(seg(st, 0.4, 1.0)))
        c.set_line_width(U * 0.02)
        c.stroke_preserve()
        col(c, th["acc"], 0.96 * eout(seg(st, 0.3, 0.9)))
        c.fill_preserve()
        col(c, WHITE, 0.95)
        c.set_line_width(U * 0.003)
        c.stroke()
        lx, ly = P(*geo[n]["ctr"])
        text(c, n.upper(), lx, ly, U * 0.034, WHITE, ease(seg(st, 1.0, 1.5)), "sb", "c")
    finish(c, s, t, True)


def k_scene(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    env = s.get("env", "skyline")
    col(c, th["acc"], 0.12 * eout(seg(st, 0, 0.8)))
    c.arc(LW / 2, LH / 2, U * 0.42, 0, 2 * PI)
    c.fill()
    dots(c, LW * 0.08, LH * 0.08, LW * 0.92, LH * 0.92, U * 0.07, U * 0.003, th["ink"], 0.14)
    if env == "candles":
        r = random.Random(s["seed"])
        p, cs = 1.0, []
        for _ in range(16):
            o = p
            p = max(0.3, p * (1 + r.gauss(0.05 * s.get("drift", 0), 0.06)))
            cs.append((o, p, max(o, p) * (1 + abs(r.gauss(0, 0.03))), min(o, p) * (1 - abs(r.gauss(0, 0.03)))))
        mn, mx = min(q[3] for q in cs), max(q[2] for q in cs)
        xa, xb, ya, yb = LW * 0.08, LW * 0.92, LH * 0.2, LH * 0.8
        cw = (xb - xa) / 16
        f = eout(seg(st, 0.05, 1.6)) * 16
        for i, (o, cl, hi, lo) in enumerate(cs):
            k = clamp(f - i)
            if k <= 0:
                break
            colr = (40, 170, 110) if cl >= o else (214, 60, 50)
            cx = xa + cw * (i + 0.5)

            def Y(v):
                return yb - (v - mn) / (mx - mn + 1e-9) * (yb - ya)
            col(c, colr)
            c.set_line_width(max(2, cw * 0.08))
            c.move_to(cx, Y(hi * k + o * (1 - k)))
            c.line_to(cx, Y(lo * k + o * (1 - k)))
            c.stroke()
            c.rectangle(cx - cw * 0.3, min(Y(o), Y(o + (cl - o) * k)), cw * 0.6, max(3, abs(Y(o) - Y(o + (cl - o) * k))))
            c.fill()
    elif env == "crowd":
        k_people(c, dict(s, action="walk", count=5, nowipe=True), t)
        return
    else:
        ic = ENV_ICON.get(env, "coins")
        k = eout(seg(st, 0.05, 0.7))
        icon(c, ic, LW / 2, LH / 2 + math.sin(st * 1.5) * U * 0.012, U * 0.62 * k, th, k, t)
        for i in range(4):
            ang = st * 0.5 + i * PI / 2
            icon(c, ic, LW / 2 + math.cos(ang) * U * 0.5 * (LW / LH if LAND else 0.8), LH / 2 + math.sin(ang) * U * 0.34,
                 U * 0.16 * k, th, 0.8 * k, t)
    d = s.get("drift", 0)
    if d:
        a = eout(seg(st, 0.6, 1.0))
        col(c, (60, 200, 120) if d > 0 else (220, 70, 60), a)
        ax, ay = LW * 0.86, LH * 0.2
        c.move_to(ax, ay - d * U * 0.06)
        c.line_to(ax + U * 0.05, ay + d * U * 0.03)
        c.line_to(ax - U * 0.05, ay + d * U * 0.03)
        c.close_path()
        c.fill()
    finish(c, s, t)


def k_people(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    act, n = s.get("action", "walk"), int(s.get("count", 3))
    gy, hh = LH * 0.78, U * 0.42
    col(c, th["ink"], 0.12)
    for i in range(9):
        c.rectangle(LW * i / 8.0, gy - LH * (0.08 + 0.06 * ((i * 5) % 4)), LW / 8.0 - 4, LH * 0.3)
    c.fill()
    col(c, th["ink"], 0.4)
    c.rectangle(0, gy, LW, 3)
    c.fill()
    cols = [tuple(th["acc"]), tuple(th["acc2"]), (80, 160, 255), (120, 220, 150), (220, 110, 180)]
    for i in range(n):
        ph = i * 1.3
        xb = LW * (0.2 + 0.6 * i / max(1, n - 1)) if n > 1 else LW / 2
        w = st * 7 + ph
        if act in ("walk", "shop"):
            x = ((xb / LW + st * 0.07 + i * 0.07) % 1.2 - 0.1) * LW
            figure(c, x, gy, hh, cols[i % 5], th, w, (0.3 + 0.5 * math.sin(w), 0.3 - 0.5 * math.sin(w)), 1 if act == "shop" else 0)
        elif act == "worry":
            figure(c, xb, gy, hh, cols[i % 5], th, 0, (2.6 + 0.1 * math.sin(w), 2.6 - 0.1 * math.sin(w)), -1)
        elif act == "celebrate":
            figure(c, xb, gy - abs(math.sin(st * 6 + ph)) * hh * 0.15, hh, cols[i % 5], th, 0, (2.8, 2.8), 1)
        else:
            figure(c, xb, gy - hh * 0.1, hh * 0.95, cols[i % 5], th, 0, (1.0 + 0.15 * math.sin(w * 3), 1.0 - 0.15 * math.sin(w * 3)), 0)
    finish(c, s, t)


def k_gauge(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    cx, cy, r = LW / 2, LH * 0.62, U * 0.34
    c.set_line_width(U * 0.07)
    for i in range(24):
        col(c, mixc((60, 190, 120), (220, 60, 50), i / 23.0), 0.92)
        c.arc(cx, cy, r, PI + PI * i / 24.0, PI + PI * (i + 1) / 24.0 - 0.02)
        c.stroke()
    k = eout(seg(st, 0.1, 1.0))
    ang = PI + PI * clamp(s.get("level", 0.5) * k + math.sin(seg(st, 0.1, 1.2) * PI * 3) * 0.04 * (1 - seg(st, 0.6, 1.2)))
    col(c, th["ink"])
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.set_line_width(U * 0.016)
    c.move_to(cx, cy)
    c.line_to(cx + math.cos(ang) * r * 0.85, cy + math.sin(ang) * r * 0.85)
    c.stroke()
    c.arc(cx, cy, U * 0.03, 0, 2 * PI)
    c.fill()
    text(c, s.get("glabel", "Risk").upper(), cx, cy + U * 0.16, U * 0.06, th["ink"], 1.0, "sb", "c")
    finish(c, s, t)


def k_ripple(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    cx, cy, R = LW / 2, LH / 2, U * 0.55
    rnd = random.Random(s["seed"])
    radii = [R * ((st * 0.5 + i / 3.0) % 1.0) for i in range(3)]
    c.set_line_width(U * 0.008)
    for rr in radii:
        col(c, th["acc"], 0.6 * (1 - rr / R))
        c.arc(cx, cy, rr, 0, 2 * PI)
        c.stroke()
    for _ in range(16):
        a, d = rnd.random() * 2 * PI, (0.25 + 0.7 * rnd.random()) * R
        lit = max(math.exp(-((rr - d) / (U * 0.05)) ** 2) for rr in radii)
        col(c, th["ink"] if lit < 0.3 else th["acc"], 0.35 + 0.65 * lit)
        c.arc(cx + math.cos(a) * d, cy + math.sin(a) * d, U * (0.012 + 0.012 * lit), 0, 2 * PI)
        c.fill()
    col(c, th["acc"])
    c.arc(cx, cy, U * 0.05, 0, 2 * PI)
    c.fill()
    finish(c, s, t)


def k_chapter(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s, True)
    k = eout(seg(st, 0.0, 0.6))
    col(c, th["acc"])
    c.rectangle(0, LH * 0.5 - U * 0.005, LW * 0.5 * k, U * 0.01)
    c.fill()
    num = f"{int(s['num']):02d}"
    font(c, "sb", U * 0.5)
    c.move_to(LW * 0.07, LH * 0.62)
    c.text_path(num)
    col(c, th["paper"], 0.9 * k)
    c.set_line_width(2)
    c.stroke()
    text(c, "CHAPTER", LW * 0.07, LH * 0.2, U * 0.04, th["acc"], k, "nb")
    words = s["title"].upper().split()
    size, items, lines = fit_lines(c, words, LW * 0.7, LH * 0.3, U * 0.1, 24)
    draw_words(c, words, LW * 0.07, LH * 0.78, LW * 0.8, size, size * 1.1, th, st, 0.3, rgb=tuple(th["paper"]))
    finish(c, s, t, True)


def k_outro(c, s, t):
    th, dur = s["th"], s["frames"] / float(FPS)
    st = t * dur
    paper_bg(c, s)
    dots(c, LW * 0.08, LH * 0.08, LW * 0.92, LH * 0.92, U * 0.07, U * 0.0035, th["ink"], 0.17)
    kin(c, [["thanks", "l"], ["for", "l"], ["watching", "b"]], LW / 2, LH * 0.26, LW * 0.8, U * 0.07, th, st)
    k = eout(seg(st, 0.3, 0.8))
    cx, cy, bw, bh = LW / 2, LH * 0.52, U * 0.62, U * 0.17
    done = st > 1.4
    c.save()
    c.translate(cx, cy)
    c.scale(max(0.01, k * (0.94 if 1.3 < st < 1.45 else 1.0)), max(0.01, k * (0.94 if 1.3 < st < 1.45 else 1.0)))
    shadow_rect(c, -bw / 2, -bh / 2, bw, bh, bh * 0.25, 0.4)
    rrect(c, -bw / 2, -bh / 2, bw, bh, bh * 0.25)
    col(c, (150, 150, 155) if done else (230, 20, 20))
    c.fill()
    if not done:
        col(c, WHITE)
        c.move_to(-bw * 0.38, -bh * 0.22)
        c.line_to(-bw * 0.38, bh * 0.22)
        c.line_to(-bw * 0.28, 0)
        c.close_path()
        c.fill()
    text(c, "SUBSCRIBED" if done else "SUBSCRIBE", bw * 0.04, bh * 0.14, bh * 0.38, WHITE, 1.0, "nb", "c")
    c.restore()
    text(c, "LIKE   •   SHARE   •   COMMENT", cx, LH * 0.72, U * 0.04, th["acc"], ease(seg(st, 0.8, 1.3)), "sb", "c")
    finish(c, s, t)


KINDS = {"poster": k_poster, "hist": k_hist, "collage": k_collage, "kinetic": k_kinetic, "stat": k_stat, "bars": k_bars,
         "timeline": k_timeline, "flow": k_flow, "versus": k_versus, "headline": k_headline, "map": k_map, "scene": k_scene,
         "people": k_people, "gauge": k_gauge, "ripple": k_ripple, "chapter": k_chapter, "outro": k_outro}


def render_frame(c, s, t):
    try:
        KINDS.get(s["kind"], k_ripple)(c, s, t)
    except Exception as e:
        print("shot failed:", s.get("kind"), repr(e)[:150])
        try:
            k_ripple(c, s, t)
        except Exception:
            c.set_source_rgb(0.9, 0.9, 0.9)
            c.paint()


# ---------------- থাম্বনেইল (১২৮০x৭২০, ৫ ধরনের লেআউট) ----------------
def thumb(c, sp):
    th, L = sp["th"], sp["layout"] % 5
    W_, H_ = LW, LH
    words = sp["title"].upper().split()[:6] or ["BUSINESS"]
    pid = sp.get("photo")
    acc = tuple(th["acc"])
    s = {"th": th, "seed": sp["seed"], "frames": 24, "kind": "thumb"}
    gh = get(pid, "ht", True, sp["seed"]) if pid else None
    gb = get(pid, "bw") if pid else None
    if L == 0:
        paper_bg(c, s)
        col(c, acc)
        c.arc(W_ * 0.74, H_ * 0.52, H_ * 0.46, 0, 2 * PI)
        c.fill()
        if gh:
            place(c, gh, W_ * 0.74, H_ * 0.52, W_ * 0.44, -0.03)
        else:
            icon(c, sp.get("icon", "coins"), W_ * 0.74, H_ * 0.5, H_ * 0.55, th)
        size, items, lines = fit_lines(c, words, W_ * 0.5, H_ * 0.66, 100, 44)
        draw_words(c, words, W_ * 0.05, H_ * 0.5 - len(lines) * size * 0.56 + size * 0.85, W_ * 0.5, size, size * 1.12, th, 99, 0, pick_hl(words))
        chip(c, sp.get("badge", "EXPLAINED"), W_ * 0.05, H_ * 0.07, 26, acc)
    elif L == 1:
        if gb:
            cover(c, gb, 0, 0, W_, H_)
        else:
            col(c, th["dark"])
            c.paint()
        col(c, acc, 0.5)
        c.paint()
        col(c, th["paper"])
        r = random.Random(sp["seed"])
        c.move_to(0, H_)
        c.line_to(0, H_ * 0.7)
        x = 0
        while x < W_:
            x += r.randint(10, 30)
            c.line_to(x, H_ * 0.7 + r.randint(-9, 9))
        c.line_to(W_, H_)
        c.close_path()
        c.fill()
        size, items, lines = fit_lines(c, words, W_ * 0.9, H_ * 0.24, 90, 40)
        draw_words(c, words, W_ * 0.05, H_ * 0.78 + size * 0.6, W_ * 0.9, size, size * 1.1, th, 99, 0, set(), "sb", None, "c")
        chip(c, sp.get("badge", "EXPLAINED"), W_ * 0.05, H_ * 0.06, 26, acc)
    elif L == 2:
        paper_bg(c, s)
        col(c, th["acc2"])
        c.rectangle(W_ * 0.44, 0, W_ * 0.1, H_ * 0.28)
        c.fill()
        if gb:
            cover(c, gb, 0, 0, W_ * 0.52, H_)
        else:
            col(c, th["dark"])
            c.rectangle(0, 0, W_ * 0.52, H_)
            c.fill()
        size, items, lines = fit_lines(c, words, W_ * 0.4, H_ * 0.66, 96, 40)
        draw_words(c, words, W_ * 0.57, H_ * 0.5 - len(lines) * size * 0.56 + size * 0.85, W_ * 0.4, size, size * 1.1, th, 99, 0, set())
        text(c, words[-1] if len(words) == 1 else "", W_ * 0.57, H_ * 0.9, 20, acc)
        col(c, acc)
        c.rectangle(W_ * 0.57, H_ * 0.88, W_ * 0.3, 8)
        c.fill()
    elif L == 3:
        paper_bg(c, s)
        size, items, lines = fit_lines(c, words, W_ * 0.9, H_ * 0.42, 96, 40)
        draw_words(c, words, W_ * 0.05, H_ * 0.12 + size * 0.85, W_ * 0.9, size, size * 1.12, th, 99, 0, pick_hl(words))
        if gh:
            h = place(c, gh, W_ * 0.7, H_ * 0.72, W_ * 0.42, 0.03)
            col(c, acc)
            c.set_line_width(5)
            rrect(c, W_ * 0.49, H_ * 0.72 - h / 2 - 6, W_ * 0.42, h + 12, 6)
            c.stroke()
        else:
            icon(c, sp.get("icon", "coins"), W_ * 0.7, H_ * 0.7, H_ * 0.5, th)
        chip(c, sp.get("date", ""), W_ * 0.05, H_ * 0.82, 26, acc) if sp.get("date") else None
    else:
        col(c, acc)
        c.paint()
        col(c, th["dark"], 0.35)
        for i in range(-3, 9):
            c.move_to(i * W_ * 0.14, 0)
            c.line_to(i * W_ * 0.14 + W_ * 0.07, 0)
            c.line_to(i * W_ * 0.14 - W_ * 0.2 + W_ * 0.07, H_)
            c.line_to(i * W_ * 0.14 - W_ * 0.2, H_)
            c.close_path()
        c.fill()
        if gh:
            place(c, gh, W_ * 0.27, H_ * 0.55, W_ * 0.44, -0.04)
        else:
            icon(c, sp.get("icon", "coins"), W_ * 0.27, H_ * 0.52, H_ * 0.55, th)
        size, items, lines = fit_lines(c, words, W_ * 0.46, H_ * 0.7, 100, 44)
        items, lines = layout(c, words, W_ * 0.46, size, "sb")
        for it in items:
            text_stroke(c, it[0], W_ * 0.52 + it[1], H_ * 0.5 - len(lines) * size * 0.56 + size * 0.85 + it[2] * size * 1.1, size,
                        WHITE if it[4] % 2 == 0 else tuple(th["hl"]), (0, 0, 0), 8)
