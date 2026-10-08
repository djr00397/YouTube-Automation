import random
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


def halftone(im, cell=6, ink=(18, 18, 18), paper=(240, 236, 226), mix=0.55, angle=0.6):
    g = np.asarray(ImageOps.autocontrast(im.convert("L"), cutoff=2), dtype=np.float32) / 255.0
    g = np.clip((g - 0.5) * 1.25 + 0.5, 0, 1)
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ca, sa = np.cos(angle), np.sin(angle)
    u = (xx * ca + yy * sa) / cell * 2 * np.pi
    v = (-xx * sa + yy * ca) / cell * 2 * np.pi
    p = (np.sin(u) * np.sin(v) + 1) / 2
    out = g * (1 - mix) + (g > p).astype(np.float32) * mix
    ink = np.array(ink, np.float32)
    paper = np.array(paper, np.float32)
    return Image.fromarray(np.clip(ink + (paper - ink) * out[:, :, None], 0, 255).astype(np.uint8), "RGB")


def duotone(im, dark, light, contrast=1.15):
    g = np.asarray(ImageOps.autocontrast(im.convert("L"), cutoff=1), dtype=np.float32) / 255.0
    g = np.clip((g - 0.5) * contrast + 0.5, 0, 1)
    d, l = np.array(dark, np.float32), np.array(light, np.float32)
    return Image.fromarray(np.clip(d + (l - d) * g[:, :, None], 0, 255).astype(np.uint8), "RGB")


def torn_frame(im, border=14, seed=1, paper=(246, 242, 232)):
    rnd = random.Random(seed)
    w, h = im.size
    W, H = w + 2 * border, h + 2 * border

    def edge(n, amp):
        v, out = 0.0, []
        for _ in range(n):
            v = max(-amp, min(amp, v + rnd.uniform(-amp * 0.6, amp * 0.6)))
            out.append(v)
        return out
    n, n2, amp = max(24, W // 14), max(18, H // 14), border * 0.45
    pts = [(i * W / (n - 1), 2 + e) for i, e in enumerate(edge(n, amp))]
    pts += [(W - 2 - e, i * H / (n2 - 1)) for i, e in enumerate(edge(n2, amp))]
    pts += [(W - i * W / (n - 1), H - 2 - e) for i, e in enumerate(edge(n, amp))]
    pts += [(2 + e, H - i * H / (n2 - 1)) for i, e in enumerate(edge(n2, amp))]
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(0.8))
    out = Image.composite(Image.new("RGBA", (W, H), paper + (255,)), Image.new("RGBA", (W, H), paper + (0,)), m)
    out.alpha_composite(im.convert("RGBA"), (border, border))
    r, g, b, a = out.split()
    return Image.merge("RGBA", (r, g, b, ImageChops.multiply(a, m)))


def paper(w, h, seed, base, amp=0.1):
    rng = np.random.default_rng(seed)

    def nz(sw, sh):
        a = (rng.random((max(2, sh), max(2, sw))) * 255).astype(np.uint8)
        return np.asarray(Image.fromarray(a).resize((w, h), Image.BICUBIC), dtype=np.float32) / 255.0
    n = nz(w // 90, h // 90) * 0.55 + nz(w // 24, h // 24) * 0.3 + nz(w // 5, h // 5) * 0.15
    gy, gx = np.gradient(n)
    sh = np.clip(0.5 + (gx + gy) * 16, 0, 1)
    t = 1.0 - amp + amp * (0.55 * sh + 0.45 * n)
    rgb = np.clip(np.array(base, np.float32)[None, None, :] * t[:, :, None], 0, 255)
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def grain(w, h, seed, amax=34):
    n = np.random.default_rng(seed).random((h, w)).astype(np.float32)
    rgb = np.where(n > 0.5, 255, 0).astype(np.uint8)
    a = (np.abs(n - 0.5) * 2 * amax).astype(np.uint8)
    return Image.fromarray(np.stack([rgb, rgb, rgb, a], axis=2), "RGBA")
