import random
import numpy as np, soundfile as sf
from scipy import signal
from scipy.ndimage import uniform_filter1d
from pedalboard import Pedalboard, Compressor, Limiter, PeakFilter, LowpassFilter
import config

SR = config.SR
rng = np.random.default_rng()
SHIFT = random.choice([-3, -2, -1, 0, 1, 2, 3])
CHORDS = {"calm": [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]], "tense": [[57, 60, 64], [50, 53, 57], [52, 56, 59], [57, 60, 64]],
          "hope": [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]], "dark": [[50, 53, 57], [58, 62, 65], [55, 58, 62], [57, 61, 64]]}
_carve = Pedalboard([PeakFilter(2800, -4.0, 0.8), LowpassFilter(9500)])


def mid(m):
    return 440.0 * 2 ** ((m + SHIFT - 69) / 12)


def _f(kind, fc):
    fc = np.atleast_1d(fc) / (SR / 2)
    return signal.butter(2, fc if len(fc) > 1 else fc[0], kind)


def lp(x, fc):
    b, a = _f("low", fc)
    return signal.lfilter(b, a, x)


def hp(x, fc):
    b, a = _f("high", fc)
    return signal.lfilter(b, a, x)


def _add(dst, x, start):
    n = len(dst)
    start %= n
    m = min(len(x), n - start)
    dst[start:start + m] += x[:m]
    r = len(x) - m
    while r > 0:
        k = min(r, n)
        dst[:k] += x[m:m + k]
        m += k
        r -= k


def _t(d):
    return np.arange(int(d * SR)) / SR


def _pad(f, dur):
    t = _t(dur)
    y = np.zeros_like(t)
    for c in (-8, 0, 9):
        ff = f * 2 ** (c / 1200)
        y += np.sin(2 * np.pi * ff * t) + 0.3 * np.sin(4 * np.pi * ff * t) + 0.12 * np.sin(6 * np.pi * ff * t)
    env = np.minimum(1, t / 1.2) * np.minimum(1, np.maximum(0, dur - t) / 1.6)
    return (y * env * (0.85 + 0.15 * np.sin(2 * np.pi * 0.1 * t)) / 3.5).astype(np.float32)


def _pluck(f, dur=1.2):
    t = _t(dur)
    y = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) * np.exp(-t * 6)
    return (y * np.exp(-t * 4.5) * np.minimum(1, t / 0.005)).astype(np.float32)


def _bass(f, dur):
    t = _t(dur)
    return (np.sin(2 * np.pi * f * t) * np.minimum(1, t / 0.05) * np.minimum(1, np.maximum(0, dur - t) / 0.8)).astype(np.float32)


def _kick():
    t = _t(0.35)
    return (np.sin(2 * np.pi * np.cumsum(45 + 55 * np.exp(-t * 18)) / SR) * np.exp(-t * 9)).astype(np.float32)


def _hat():
    t = _t(0.08)
    return (hp(rng.standard_normal(len(t)), 6000) * np.exp(-t * 55)).astype(np.float32)


_cache = {}


def _loop(mood):
    if mood in _cache:
        return _cache[mood]
    chords, dur = CHORDS[mood], 4.0
    n = int(SR * dur * len(chords))
    L, R = np.zeros(n, np.float32), np.zeros(n, np.float32)
    pat = random.choice([[0, 1, 2, 1, 0, 2, 1, 2], [0, 2, 1, 2, 0, 1, 2, 1], [2, 1, 0, 1, 2, 0, 1, 0]])
    for ci, ch in enumerate(chords):
        s = int(ci * dur * SR)
        body = sum(_pad(mid(m), dur + 1.5) for m in ch) * 0.5
        bass = _bass(mid(ch[0] - 12), dur + 1.5) * 0.8
        k = min(len(body), len(bass))
        blk = (body[:k] + bass[:k]).astype(np.float32)
        _add(L, blk, s)
        _add(R, blk, s + int(0.012 * SR))
        for q in range(8):
            _add(L if q % 2 == 0 else R, _pluck(mid(ch[pat[q]] + 12)) * 0.16, s + int(q * 0.5 * SR))
        for beat in range(4):
            sb = s + int(beat * SR)
            for d in (L, R):
                _add(d, _kick() * 0.30, sb)
                _add(d, _hat() * 0.05, sb + int(0.5 * SR))
    st = np.stack([lp(L, 4500), lp(R, 4500)]).astype(np.float32)
    try:
        st = _carve(st, SR)
    except Exception as e:
        print("carve skipped:", e)
    _cache[mood] = (st * (0.6 / (np.abs(st).max() + 1e-9))).astype(np.float32)
    return _cache[mood]


def _music(sections, total):
    out = np.zeros((2, total), np.float32)
    for a, b, mood in sections:
        lo = _loop(mood)
        n = int((b - a + 2.0) * SR)
        if n < 2:
            continue
        seg = np.tile(lo, (1, int(np.ceil(n / lo.shape[1]))))[:, :n]
        fade = max(1, min(int(1.5 * SR), n // 2))
        env = np.ones(n, np.float32)
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        s = max(0, int((a - 1.0) * SR))
        e = min(total, s + n)
        if e > s:
            out[:, s:e] += seg[:, :e - s] * env[:e - s]
    return out


# ---- সব সাউন্ড ইফেক্ট কোডে তৈরি ----
def _noise(n):
    return rng.standard_normal(n).astype(np.float32)


def whoosh(d=0.9):
    n = int(d * SR)
    t = np.linspace(0, 1, n)
    x = _noise(n)
    return ((lp(x, 800) * (1 - t) + hp(x, 2500) * t) * np.sin(np.pi * t) ** 2).astype(np.float32)


def impact():
    t = _t(1.2)
    return (np.sin(2 * np.pi * np.cumsum(40 + 80 * np.exp(-t * 8)) / SR) * np.exp(-t * 4) + lp(_noise(len(t)), 900) * np.exp(-t * 12) * 0.5).astype(np.float32)


def riser(d=2.6):
    n = int(d * SR)
    t = np.arange(n) / SR
    return ((np.sin(2 * np.pi * np.cumsum(200 + 1400 * (t / d) ** 2) / SR) * 0.3 + hp(_noise(n), 1500) * 0.4) * (t / d) ** 2).astype(np.float32)


def ding():
    t = _t(1.5)
    return (sum(np.sin(2 * np.pi * f * t) * np.exp(-t * k) for f, k in ((880, 3), (1320, 4), (1760, 6))) / 3).astype(np.float32)


def coin():
    t = _t(0.5)
    a = (np.sin(2 * np.pi * 2400 * t) + 0.6 * np.sin(2 * np.pi * 3600 * t)) * np.exp(-t * 14)
    b = np.roll(np.sin(2 * np.pi * 3200 * t) * np.exp(-t * 12), int(0.07 * SR))
    return ((a + 0.7 * b) / 2).astype(np.float32)


def pop():
    t = _t(0.15)
    return (np.sin(2 * np.pi * np.cumsum(500 + 300 * np.exp(-t * 40)) / SR) * np.exp(-t * 25)).astype(np.float32)


def tick():
    t = _t(0.05)
    return (hp(_noise(len(t)), 2500) * np.exp(-t * 120)).astype(np.float32)


def rise():
    t = _t(0.9)
    env = np.minimum(1, t / 0.2) * np.minimum(1, (0.9 - t) / 0.1)
    return (np.sin(2 * np.pi * np.cumsum(300 + 700 * (t / 0.9)) / SR) * env * 0.6).astype(np.float32)


def paper():
    t = _t(0.35)
    return (hp(_noise(len(t)), 3000) * np.exp(-t * 9) * (0.6 + 0.4 * np.sin(t * 90))).astype(np.float32)


def murmur():
    t = _t(2.5)
    return (lp(hp(_noise(len(t)), 300), 1800) * np.sin(np.pi * t / 2.5) ** 2 * (0.6 + 0.4 * np.sin(2 * np.pi * 3.3 * t))).astype(np.float32)


def thud():
    t = _t(0.5)
    return (np.sin(2 * np.pi * 70 * t) * np.exp(-t * 9)).astype(np.float32)


def click():
    t = _t(0.08)
    return (np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 60) + hp(_noise(len(t)), 3000) * np.exp(-t * 80) * 0.5).astype(np.float32)


SFX = {"whoosh": (whoosh, 0.16), "impact": (impact, 0.30), "riser": (riser, 0.18), "ding": (ding, 0.20), "coin": (coin, 0.14),
       "pop": (pop, 0.16), "tick": (tick, 0.12), "rise": (rise, 0.12), "paper": (paper, 0.14), "murmur": (murmur, 0.07),
       "thud": (thud, 0.22), "click": (click, 0.20)}


def mix(voice, sections, events, out_path):
    total = len(voice)
    try:
        mus = _music(sections, total)
        env = uniform_filter1d(np.abs(voice), size=max(1, int(0.25 * SR)))
        env = np.clip(np.roll(env, -int(0.10 * SR)) / 0.035, 0, 1)
        gain = uniform_filter1d(0.20 * (1 - 0.85 * env), size=max(1, int(0.20 * SR)))
        mus *= gain[None, :].astype(np.float32)
    except Exception as e:
        print("music failed, voice only:", e)
        mus = np.zeros((2, total), np.float32)
    sfx = np.zeros(total, np.float32)
    for t, name in events:
        try:
            fn, vol = SFX[name]
            x = fn() * vol
            s = int(max(0, t) * SR)
            if s < total:
                m = min(len(x), total - s)
                sfx[s:s + m] += x[:m]
        except Exception as e:
            print("sfx failed:", name, e)
    st = (np.stack([voice, voice]) + mus + sfx[None, :]).astype(np.float32)
    try:
        st = Pedalboard([Compressor(threshold_db=-16, ratio=2.0, attack_ms=20, release_ms=200), Limiter(threshold_db=-1.0)])(st, SR)
    except Exception as e:
        print("mastering failed:", e)
    sf.write(str(out_path), np.ascontiguousarray(np.clip(st, -0.99, 0.99).T), SR, subtype="PCM_16")
