import io, random, wave
import numpy as np, soundfile as sf, librosa
from scipy import signal
from scipy.ndimage import uniform_filter1d
from pedalboard import Pedalboard, HighpassFilter, PeakFilter, HighShelfFilter, Compressor, Limiter
import config, script_writer

SR = config.SR
_piper = None
EMO = {"normal": dict(length=1.05, noise=0.50, noisew=0.60, gain=1.00), "serious": dict(length=1.10, noise=0.45, noisew=0.55, gain=0.97),
       "exclaim": dict(length=0.99, noise=0.60, noisew=0.70, gain=1.05), "question": dict(length=1.04, noise=0.55, noisew=0.65, gain=1.00)}
_b1 = Pedalboard([HighpassFilter(80), PeakFilter(300, -2.5, 0.9), PeakFilter(3500, 3.0, 0.8), HighShelfFilter(9000, 1.5),
                  Compressor(threshold_db=-24, ratio=2.5, attack_ms=8, release_ms=100)])
_b2 = Pedalboard([Limiter(threshold_db=-1.5)])


def load():
    global _piper
    from piper import PiperVoice
    for name in config.VOICE_MODELS:
        p = config.VOICES / f"{name}.onnx"
        if p.exists():
            _piper = PiperVoice.load(str(p))
            print("TTS voice:", name)
            return
    raise RuntimeError("No Piper voice model in voices/")


def _raw(text, emo):
    from piper import SynthesisConfig
    e = EMO.get(emo, EMO["normal"])
    cfg = SynthesisConfig(length_scale=e["length"] * random.uniform(0.98, 1.02), noise_scale=e["noise"], noise_w_scale=e["noisew"])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        _piper.synthesize_wav(text, wf, syn_config=cfg)
    buf.seek(0)
    y, sr = sf.read(buf, dtype="float32")
    return (y.mean(1) if y.ndim > 1 else y), sr


def _tail(y, semis, frac=0.3):
    n = int(len(y) * (1 - frac))
    if n < 2000 or len(y) - n < 2000:
        return y
    t = librosa.effects.pitch_shift(y[n:], sr=SR, n_steps=semis)
    x = int(0.01 * SR)
    out = np.concatenate([y[:n], t[:len(y) - n]])
    out[n - x:n] = np.linspace(1, 0, x) * y[n - x:n] + np.linspace(0, 1, x) * out[n - x:n]
    return out


def deess(y):
    sib = signal.sosfilt(signal.butter(4, [5000, 9500], "band", fs=SR, output="sos"), y)
    win = max(1, int(0.004 * SR))
    ratio = uniform_filter1d(np.abs(sib), win) / (uniform_filter1d(np.abs(y), win) + 1e-6)
    g = uniform_filter1d(np.clip(0.45 / np.maximum(ratio, 1e-6), 0.35, 1.0), win)
    return (y - sib * (1 - g)).astype(np.float32)


def norm(y, target=0.09):
    pk0 = float(np.abs(y).max()) or 1.0
    act = np.abs(y) > 0.02 * pk0
    rms = float(np.sqrt(np.mean(y[act] ** 2))) if act.any() else float(np.sqrt(np.mean(y ** 2)))
    y = y * (target / max(rms, 1e-5))
    pk = float(np.abs(y).max())
    return (y * 0.92 / pk if pk > 0.92 else y).astype(np.float32)


def synth(text, emo="normal"):
    y, sr = _raw(script_writer.tts_clean(text), emo)
    y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    y, _ = librosa.effects.trim(y, top_db=38)
    if emo == "question":
        y = _tail(y, 1.0)
    y = np.concatenate([y, np.zeros(int(0.08 * SR), np.float32)])
    y = _b1(y[None, :].astype(np.float32), SR)[0]
    y = norm(deess(y))
    y = _b2(y[None, :].astype(np.float32), SR)[0]
    y, _ = librosa.effects.trim(y, top_db=48)
    return np.clip(y, -0.98, 0.98).astype(np.float32)
