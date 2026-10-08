import re, sys, json, queue, threading, subprocess
import config
from script_writer import P_NUM, P_BACK, P_COUNTER, P_IMPACT

SYSTEM = ("You are a senior business journalist and YouTube scriptwriter for a finance and business explainer channel. "
          "You write spoken narration for a human narrator in plain, vivid, conversational English. "
          "Use ONLY the supplied FACTS for specific claims, names, numbers and dates. Never invent statistics, quotes, people, "
          "companies or sources. You may add general, widely known explanations of finance concepts. "
          "Write entirely in your own words and never copy phrases from the facts. "
          "No headings, no bullet points, no emojis, no stage directions, no quotation marks. "
          "Never promise returns, never predict prices, and never give personalised financial advice. "
          "Output only the narration text.")


class LLMUnavailable(Exception):
    pass


_proc, _q, _crashes, MAX_CRASHES = None, None, 0, 4


def _reader(p, q):
    try:
        for line in p.stdout:
            if line.startswith("@@"):
                q.put(line[2:].strip())
    except Exception:
        pass
    q.put(None)


def _stop():
    global _proc
    p, _proc = _proc, None
    if p is None:
        return
    try:
        p.stdin.close()
    except Exception:
        pass
    try:
        p.terminate()
        p.wait(timeout=15)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _start():
    global _proc, _q
    _stop()
    if not config.LLM_PATH.exists():
        raise LLMUnavailable(f"model file missing: {config.LLM_PATH}")
    _q = queue.Queue()
    _proc = subprocess.Popen([sys.executable, "-X", "faulthandler", str(config.BASE / "llm_worker.py")], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True, bufsize=1, cwd=str(config.BASE))
    threading.Thread(target=_reader, args=(_proc, _q), daemon=True).start()
    if _q.get(timeout=1200) != "READY":
        raise RuntimeError("LLM worker exited before ready")
    print("LLM worker ready", flush=True)


def load():
    global _crashes
    while True:
        try:
            _start()
            return
        except LLMUnavailable:
            raise
        except Exception as e:
            _crashes += 1
            print(f"LLM start problem ({_crashes}/{MAX_CRASHES}):", repr(e)[:200], flush=True)
            _stop()
            if _crashes >= MAX_CRASHES:
                raise LLMUnavailable("LLM worker could not start")


def unload():
    _stop()


def _ask(payload, timeout=900):
    global _crashes
    while True:
        try:
            if _proc is None or _proc.poll() is not None:
                _start()
            _proc.stdin.write(json.dumps(payload) + "\n")
            _proc.stdin.flush()
            msg = _q.get(timeout=timeout)
            if msg is None:
                raise RuntimeError("LLM worker died")
            d = json.loads(msg)
            if "error" in d:
                raise RuntimeError(d["error"])
            return d["text"]
        except LLMUnavailable:
            raise
        except Exception as e:
            _crashes += 1
            print(f"LLM problem ({_crashes}/{MAX_CRASHES}):", repr(e)[:200], flush=True)
            _stop()
            if _crashes >= MAX_CRASHES:
                raise LLMUnavailable("LLM worker keeps crashing")


def _words(t):
    return re.findall(r"[a-z0-9']+", t.lower())


def _nums(t):
    return {m.replace(",", "").rstrip(".") for m in re.findall(r"\d[\d,]*\.?\d*", t)}


class Facts:
    def __init__(self, topic):
        self.head = re.sub(r"\s[-|–]\s[^-|–]{2,40}$", "", topic["headline"]).strip()
        self.kw = topic["keywords"]
        self.gen = [x for a in topic["articles"] for x in a["sentences"]]
        w = topic.get("wiki")
        self.wiki = w["sentences"] if w else []
        self.num = [x for x in self.gen if P_NUM(x)]
        self.back = [x for x in self.gen if P_BACK(x)]
        self.counter = [x for x in self.gen if P_COUNTER(x)]
        self.impact = [x for x in self.gen if P_IMPACT(x)]
        self.cur = {}
        self.ng = {7: set(), 10: set()}
        self.numset = set()
        for x in self.gen + self.wiki + [self.head]:
            self.numset |= _nums(x)
            w_ = _words(x)
            for n in (7, 10):
                for i in range(len(w_) - n + 1):
                    self.ng[n].add(tuple(w_[i:i + n]))

    def pick(self, pool, k, key):
        if not pool:
            return []
        c = self.cur.get(key, 0)
        self.cur[key] = c + k
        return [pool[(c + i) % len(pool)] for i in range(min(k, len(pool)))]

    def facts_for(self, kind):
        core = self.gen[:3]
        if kind == "num":
            f = self.pick(self.num, 3, "num") + self.pick(self.gen, 2, "gen")
        elif kind == "back":
            f = self.pick(self.wiki, 4, "wiki") + self.pick(self.back, 3, "back")
        elif kind == "counter":
            f = self.pick(self.counter, 4, "counter") + self.pick(self.gen, 2, "gen")
        elif kind == "impact":
            f = self.pick(self.impact, 4, "impact") + self.pick(self.gen, 2, "gen")
        else:
            f = self.pick(self.gen, 4, "gen") + self.pick(self.wiki, 2, "wiki")
        seen = []
        for x in core + f:
            if x not in seen:
                seen.append(x)
        return seen[:9]


BAD_START = ("sure", "here is", "here's", "certainly", "narration", "note:")


def _validate(facts, text, n=7):
    text = text.replace("’", "'").replace("‘", "'").replace("—", ", ").replace("–", "-")
    text = re.sub(r"[#*_`>]+", " ", text)
    text = re.sub(r"^\s*[-•\d]+[.)]?\s+", "", text, flags=re.M)
    text = re.sub(r"[^\x20-\x7E\n]", " ", text)
    out = []
    for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip()):
        s = s.strip()
        if len(s.split()) < 4:
            continue
        low = s.lower()
        if low.startswith(BAD_START) or "as an ai" in low or '"' in s:
            continue
        if any(x not in facts.numset and not (x.isdigit() and int(x) <= 10) for x in _nums(s)):
            continue
        w = _words(s)
        if any(tuple(w[i:i + n]) in facts.ng[n] for i in range(len(w) - n + 1)):
            continue
        out.append(s)
    return " ".join(out)


def write(facts, beat):
    fact_txt = "\n".join("- " + f[:300] for f in facts.facts_for(beat["kind"]))
    user = (f"TOPIC HEADLINE: {facts.head}\nKEY TERMS: {', '.join(facts.kw[:5])}\n\n"
            f"FACTS (use for specifics; rephrase everything in your own words):\n{fact_txt}\n\n"
            f"TASK: {beat['instruction']}\nLength: about {beat['words']} words. Write only the narration.")
    best = ""
    for temp, n in ((0.8, 7), (1.0, 7), (1.0, 10)):
        raw = _ask({"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                    "max_tokens": int(beat["words"] * 1.8) + 40, "temperature": temp})
        clean = _validate(facts, raw, n)
        if len(clean.split()) > len(best.split()):
            best = clean
        if len(best.split()) >= max(25, beat["words"] * 0.5):
            break
    return best
