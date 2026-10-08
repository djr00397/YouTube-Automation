import re, random

CHAPTERS = ["Intro", "The Core Question", "What We Will Cover", "How We Got Here", "The Evidence",
            "The Other Side", "The Big Picture", "What You Can Do", "Final Thoughts"]
NAMES = ["Visual Hook", "Core Question", "Overview", "Background", "Evidence", "Both Sides", "Big Picture", "Action Plan", "Outro"]
MOODS = ["tense", "tense", "calm", "dark", "calm", "dark", "calm", "hope", "hope"]
SEC_EMO = ["serious", "normal", "normal", "serious", "serious", "serious", "serious", "normal", "normal"]
NUM = re.compile(r"(?:[\$£€]\s?\d[\d,\.]*\s?(?:billion|million|trillion|thousand)?|\d[\d,\.]*\s?(?:%|percent|billion|million|trillion|thousand))", re.I)


def big_num(s):
    m = NUM.search(s)
    return m.group(0).strip().rstrip(".,") if m else None


def has(x, keys):
    l = x.lower()
    return any(k in l for k in keys)


P_NUM = lambda x: bool(big_num(x))
P_BACK = lambda x: has(x, ["since ", "last year", "years ago", "previously", "history", "decade", "earlier this", "founded", "began", "in 20", "in 19"])
P_COUNTER = lambda x: has(x, ["however", "critics", "concern", "risk", "warn", "despite", "although", "downside", "skeptic", "worry", "but "])
P_IMPACT = lambda x: has(x, ["consumer", "investor", "market", "jobs", "prices", "household", "economy", "workers", "shareholders", "inflation", "rates", "expected", "forecast"])


def tts_clean(t):
    t = re.sub(r"https?://\S+", "", t)
    for sym, word in (("$", "dollars"), ("£", "pounds"), ("€", "euros")):
        t = re.sub(re.escape(sym) + r"\s?(\d[\d,\.]*)\s*(billion|million|trillion|thousand)", r"\1 \2 " + word, t, flags=re.I)
    t = t.replace("%", " percent").replace("&", " and ").replace("—", ", ").replace("–", " to ")
    t = t.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", t)).strip()


def clean_head(h):
    return re.sub(r"\s[-|–]\s[^-|–]{2,40}$", "", h).strip()


HOOKS = ["Open with a surprising question that the story raises.",
         "Open with a bold, honest contrast between what people assume and what is actually happening.",
         "Open by setting a short, vivid everyday scene that connects to the story, then reveal the topic.",
         "Open with the single most striking fact, framed as a puzzle to solve.",
         "Open by speaking directly to the viewer about how this could touch their wallet, then name the topic."]
OUTROS = ["Write the outro: invite viewers to like, subscribe, turn on notifications and share their thoughts in the comments. Warm sign-off.",
          "Write the outro: ask viewers one thoughtful question about the topic to answer in the comments, then invite them to subscribe and share. Friendly sign-off.",
          "Write the outro: thank viewers, suggest they subscribe for more clear business explainers, and invite them to like and share. Calm sign-off."]
DEEP = ["the numbers behind the headline and what they do and do not prove", "who the key players are and what each of them wants",
        "the incentives that drive the decisions in this story", "how the timeline could unfold from here, without predicting specifics",
        "lessons for long-term thinking that this story teaches", "common mistakes people make when reacting to news like this"]


def plan(topic, profile):
    beats = []
    rng = random.Random(profile["order_seed"])
    angles = DEEP[:]
    rng.shuffle(angles)

    def add(sec, name, instr, words, kind="any", optional=False):
        beats.append(dict(order=len(beats), sec=sec, name=name, instruction=instr, words=words, kind=kind, optional=optional))

    add(0, "Hook", f"Write the opening hook. {HOOKS[profile['hook'] % len(HOOKS)]} Name the topic and tease what this video will reveal. Be honest: no exaggeration or false promises.", 90)
    add(1, "Core Question", "State the core question or problem this story raises. Ask it directly, explain why ordinary people should care, and summarise what happened in plain words.", 120)
    add(2, "Overview", "Give a short chapter overview of what the video covers: the background and root cause, the evidence, both sides of the argument, the real impact, and a practical call to action.", 90)
    add(3, "Background", "Explain the historical context: how did we get here? Walk through the timeline in simple words.", 180, "back")
    add(3, "Root Cause", "Explain the root cause: which underlying pressures, decisions or trends made this happen?", 180, "back")
    add(3, "Key Concept", "Explain one finance concept that helps understand this story, with a simple everyday example.", 150, "any", True)
    for i in range(1, 10):
        add(4, f"Evidence {i}", f"Evidence point {i}: present one concrete piece of evidence or data point from the FACTS (different from earlier points), explain in plain words what it means and why it matters.", 160, "num", optional=i > 4)
    for j, a in enumerate(angles):
        add(4, f"Deep Dive {j + 1}", f"Deep dive: explore {a}. Stay general where the FACTS are silent.", 170, "any", True)
    add(4, "Key Concept", "Explain another finance concept relevant to this evidence with a simple everyday example.", 150, "any", True)
    add(5, "The Case For", "Explain the strongest case in favour: what do supporters, companies or officials argue, and why?", 160)
    add(5, "The Case Against", "Explain the strongest case against: what do critics, risks and downsides look like?", 160, "counter")
    add(5, "Weighing Both", "Weigh both sides fairly and be honest about what is uncertain or still unknown.", 140)
    add(5, "What To Watch", "Describe what analysts and observers are likely to watch next, without predicting specific outcomes.", 130, "any", True)
    add(6, "Households", "Zoom out: explain the real impact on households, workers and consumers.", 170, "impact")
    add(6, "Investors", "Explain the real impact on investors, businesses and the wider economy.", 170, "impact")
    add(6, "Past Episodes", "Compare this to similar past episodes in general terms, without inventing specific details.", 140, "any", True)
    add(6, "Scenarios", "Describe a best case, a worst case and a most likely case, making clear these are scenarios and not predictions.", 160, "any", True)
    add(6, "Misconceptions", "Clear up common misconceptions viewers may have about this topic.", 150, "any", True)
    add(6, "Global Angle", "Explain how other countries and global markets could be affected.", 150, "any", True)
    add(6, "Small Business", "Explain what this could mean for small businesses and young people starting their careers.", 150, "any", True)
    add(6, "Viewer Questions", "Answer three questions viewers commonly ask about this topic, in plain words.", 160, "any", True)
    add(7, "Action Plan", "Give a practical, calm action plan in five steps: verify information before reacting, understand your own exposure, keep an emergency fund, diversify, and keep learning. General education only, no specific investment recommendations, no promised returns.", 240)
    add(7, "Disclaimer", "Write a short educational disclaimer saying this video is general information, not financial advice, and that viewers should consider a licensed professional.", 40)
    add(8, "Recap", "Recap the main lessons of the video in plain words.", 100)
    add(8, "Outro", OUTROS[profile["outro"] % len(OUTROS)], 60)
    return beats


def plan_short(topic, profile):
    beats = []

    def add(sec, name, instr, words, kind="any"):
        beats.append(dict(order=len(beats), sec=sec, name=name, instruction=instr, words=words, kind=kind, optional=False))

    add(0, "Hook", f"Write a one or two sentence hook. {HOOKS[profile['hook'] % len(HOOKS)]} Honest, no exaggeration. Maximum 25 words.", 25)
    add(4, "Key Fact", "State the single most important fact or number from the story and explain it in plain words. Maximum 40 words.", 38, "num")
    add(6, "Why It Matters", "Explain in plain words why this matters to ordinary people's money, jobs or prices. Maximum 40 words.", 38, "impact")
    add(7, "Takeaway", "Give one calm, general takeaway viewers can remember. No investment advice, no predictions. Maximum 30 words.", 28)
    add(8, "Outro", "One short sentence inviting viewers to follow for more daily business explainers and to share their thoughts in the comments. Maximum 18 words.", 16)
    return beats


def _sents(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def _group(sents, maxw=42):
    out, cur = [], []
    for s in sents:
        if cur and sum(len(x.split()) for x in cur) + len(s.split()) > maxw:
            out.append(" ".join(cur))
            cur = []
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return out


STEPS = ["Verify before you react", "Know your exposure", "Keep an emergency fund", "Diversify your risk", "Keep learning"]


def to_scenes(beat, text, headline, maxw=42):
    sec, name, scenes = beat["sec"], beat["name"], []
    for i, t in enumerate(_group(_sents(text), maxw)):
        end = t.rstrip()[-1:]
        emo = "question" if end == "?" else "exclaim" if end == "!" else SEC_EMO[sec]
        sc = dict(sec=sec, text=t, kind="text", emotion=emo, optional=beat["optional"], seq=(beat["order"], i), heading=name)
        n = big_num(t)
        if sec == 0:
            sc["kind"] = "hook"
        elif name == "Overview" and i == 0:
            sc.update(kind="bullets", bullets=["Background & root cause", "The evidence", "Both sides", "The real impact", "What you can do"])
        elif name == "The Case For" and i == 0:
            sc["kind"] = "versus"
        elif name == "Action Plan" and i == 0:
            sc.update(kind="bullets", bullets=STEPS)
        elif name == "Outro":
            sc["kind"] = "outro"
        elif n:
            sc.update(kind="stat", big=n)
        scenes.append(sc)
    return scenes
