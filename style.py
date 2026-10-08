import random

THEMES = [
    {"name": "crimson", "paper": [240, 236, 226], "dark": [16, 16, 19], "ink": [20, 20, 22], "acc": [214, 40, 40], "acc2": [236, 176, 40], "hl": [250, 226, 70]},
    {"name": "emerald", "paper": [238, 238, 240], "dark": [12, 30, 26], "ink": [28, 30, 34], "acc": [0, 110, 66], "acc2": [212, 170, 40], "hl": [246, 226, 90]},
    {"name": "navy", "paper": [236, 238, 242], "dark": [10, 18, 38], "ink": [14, 22, 40], "acc": [222, 84, 40], "acc2": [40, 130, 200], "hl": [252, 224, 80]},
    {"name": "amber", "paper": [243, 236, 222], "dark": [24, 18, 12], "ink": [30, 22, 16], "acc": [200, 110, 20], "acc2": [170, 40, 40], "hl": [252, 214, 70]},
    {"name": "teal", "paper": [234, 240, 240], "dark": [8, 28, 34], "ink": [16, 30, 34], "acc": [0, 142, 150], "acc2": [230, 80, 60], "hl": [250, 228, 90]},
    {"name": "plum", "paper": [242, 236, 240], "dark": [26, 12, 30], "ink": [30, 16, 34], "acc": [150, 40, 120], "acc2": [236, 170, 50], "hl": [250, 226, 100]},
]
N_TITLES, N_THUMBS, N_HOOKS, N_OUTROS = 12, 5, 5, 3


def pick(hist, seed):
    """সর্বশেষ-ব্যবহারের হিসাবে ঘোরানো স্টাইল: পরপর দুই ভিডিওতে একই জিনিস আসে না"""
    rng = random.Random(seed)
    used = hist.get("styles", [])

    def lru(key, n):
        last = {}
        for i, s in enumerate(used):
            if key in s:
                last[s[key]] = i
        return sorted(range(n), key=lambda k: (last.get(k, -1), rng.random()))[0]

    return {"theme": lru("theme", len(THEMES)), "title_pat": lru("title_pat", N_TITLES), "thumb": lru("thumb", N_THUMBS),
            "hook": lru("hook", N_HOOKS), "outro": lru("outro", N_OUTROS), "seed": seed, "order_seed": rng.randint(0, 10 ** 6)}
