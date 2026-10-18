import hashlib
import re
from dataclasses import dataclass

UNIT_TYPES = ("decision", "constraint", "state", "todo", "entity", "question", "fact")

TYPE_PREFIX = {
    "decision": "d",
    "constraint": "c",
    "state": "s",
    "todo": "t",
    "entity": "e",
    "question": "q",
    "fact": "f",
}

TYPE_PRIORITY = {
    "constraint": 1.0,
    "decision": 0.95,
    "state": 0.85,
    "todo": 0.8,
    "fact": 0.5,
    "entity": 0.45,
    "question": 0.4,
}

EXACT_REGEXES = [
    re.compile(r"https?://[^\s,;)\]\"']+"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\bv?\d+(?:\.\d+){1,}\b"),
    re.compile(r"\b\d+(?:\.\d+)?%"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}\b",
        re.I,
    ),
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b"),
    re.compile(r"[$€£]\d[\d,]*(?:\.\d+)?"),
    re.compile(r"\b(?=[0-9a-fA-F]*\d)(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{8,}\b"),
    re.compile(r"\b[A-Z][A-Z0-9]{1,}-\d+\b"),
    re.compile(r"\b[A-Za-z][\w]*-\d+(?:-\d+)*(?![\w.-])"),
    re.compile(r"\b[A-Za-z][\w-]*[-_][\w-]*\d[\w-]*\b|\b[A-Za-z][\w-]*\d[\w-]*[-_][\w-]*\b"),
    re.compile(r"\b\w+=\w+\b"),
    re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|m|h|d|kb|mb|gb|tb|k|m|b)\b"),
    re.compile(r"\b\d[\d,]{1,}\b"),
    re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|dev|ai|co|internal|local)(?:/[\w./-]*)?\b"),
    re.compile(r"\b\w*[a-z]\w*_\w+\b"),
    re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]*)+\b"),
    re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b"),
    re.compile(r"(?<!\w)(?:/|\./|\.\./)[\w./-]+"),
    re.compile(
        r"\b[\w-]+\.(?:py|js|ts|tsx|jsx|java|go|rs|rb|c|h|cpp|sql|json|yaml|yml|toml|env|md|txt|csv|sh|cfg|ini|lock)\b"
    ),
]

_NEGATIONS = re.compile(r"\b(?:not|never|no|none|without|cannot|can't|don't|doesn't|won't|isn't|aren't|didn't)\b", re.I)

FILLER_PREFIX = re.compile(
    r"^(?:okay|ok|so|well|anyway|basically|actually|honestly|look|listen|wait|hold on|hang on|yes|yeah|yep|"
    r"yup|correct|right|exactly|indeed|hello|hi|hey|you know|i think|i guess|i believe|"
    r"it seems(?: like)?|it looks like|just|simply|please note that|note that|remember that|also|fyi|btw)"
    r"\b[,:\-–—]?\s+",
    re.I,
)
DECISION_MARKER = re.compile(r"^(?:decision|decided|agreed|conclusion)\s*[:,\-–—]\s*", re.I)
DECISION_PREFIX = re.compile(
    r"^(?:we|i|the team|team|everyone)\s+(?:have\s+|has\s+)?(?:decided|agreed|chose|settled(?:\s+on)?|went with)\s+"
    r"(?:to\s+|that\s+|on\s+|with\s+)?",
    re.I,
)
SPEAKER_PREFIX = re.compile(
    r"^(?:\[[^\]]{1,30}\]\s*|(?:user|human|assistant|system|model|ai|tool)\s*[:>]\s*)", re.I
)
THERE_COPULA = re.compile(r"^there\s+(?:is|are|was|were)\s+", re.I)
ARTICLE_PREFIX = re.compile(r"^(?:the|this|that|these|those)\s+(?=[a-z0-9])", re.I)
CUE_ONLY = re.compile(
    r"^(?:wait|correction|update|edit|revision|actually|instead|scratch that|hold on)[:!,\s]*$", re.I
)
COPULA = re.compile(r"(^|\s)(?:is|are|was|were)\s+(?=[a-z0-9])", re.I)
VALUE_CONNECTOR = re.compile(
    r"\b(?:changed|updated|switched|moved|raised|lowered|increased|decreased|set|bumped|now)"
    r"\s+(?:the\s+)?(?:to\s+)?(?=\d)",
    re.I,
)
TO_VALUE = re.compile(r"(^|\s)to\s+(?=\d)", re.I)
ATOMIC_SPLIT = re.compile(r",\s+(?!(?:and|but)\b)|;\s+|\s+(?:and|but)\s+")
META_NOISE = re.compile(
    r"^(?:(?:i|you|we)\s+)?(?:'ll|will|can)\s+remember\b|"
    r"^i(?:'ll| will| can| should)?\s+(?:remember|note|keep|save|store|track)\b|"
    r"^i have (?:everything|all|it)\b|"
    r"^let me(?!\s+(?:recap|confirm|repeat|restate|summari[sz]e|make sure)\b)\b|^let's\b|"
    r"^here(?:'s| is)\b|^sounds good\b|^will do\b|^understood\b|"
    r"^(?:quick )?(?:context dump|planning notes|research notes|meeting notes|summary of)\b",
    re.I,
)
ACK_START = re.compile(
    r"^(?:thanks|thank you|got it|understood|noted|makes sense|sounds good|good luck|cheers|"
    r"will do|no problem|that works|good to know|i have (?:everything|all)\b|"
    r"everything(?: for the handoff)?$)",
    re.I,
)
FRAGMENT = re.compile(
    r"^(?:two|three|four|a couple|a few|several)\b.*\b(?:constraints?|things?|items?|points?|steps?|options?)$",
    re.I,
)
ACK_PREFIX = re.compile(
    r"^(?:(?:yep|yeah|yes|sure|right|okay|ok|well|alright|got it|understood|noted|good|great|"
    r"perfect|cool|nice|thanks|thank you|makes sense|that(?:'s| is) right|correct|exactly|close)"
    r"[.,!]?\s+)",
    re.I,
)
ORDINAL_PREFIX = re.compile(r"^(?:first|second|third|finally|then|also)\b[,\s]+\s*", re.I)
PRONOUN_PREFIX = re.compile(r"^(?:we|i|you|our|it)\s+", re.I)
DEPLOY_LEAD = re.compile(r"^for (?:deploys?|releases?|rollouts?|ops)\b[:,]\s*", re.I)
CHOICE_CUE = re.compile(
    r"\b(?:use|uses|using|decided|decision|choose|chose|chosen|pick(?:ed)?|adopt(?:ed)?|"
    r"going with|went with|switch(?:ed)? to|instead|rather than)\b",
    re.I,
)
TEMPORAL_CLAUSE = re.compile(
    r"^(?:after|before|following|once|when)\s+(?:the\s+)?(?:[\w./:-]+\s+){1,4}?"
    r"(?=(?:we|you|they|i|it|the|this|that)\b)",
    re.I,
)
PREP_THE = re.compile(
    r"\b(in|on|at|for|with|from|of|around|about|into|across|through|over|under) the\s+(?=[a-z0-9])",
    re.I,
)
CONFIG_LEAD = re.compile(r"\b(?:config(?:uration)?\s+file|config|file|path)\s+(?:is\s+)?(?=/\S)", re.I)
TRAILING_NOUN = re.compile(r"\s+(?:dashboard|dashboards)$", re.I)
LEAD_SEE = re.compile(r"^watch\s+(?=[A-Za-z0-9/])", re.I)
RUN_REMAIN = re.compile(r"^(?:runs?|remains?|stays?)\s+(?=[a-z0-9/])", re.I)
VERB_FOR = re.compile(r"\b(?:runs?|takes?|lasts?)\s+(?:for|about|around)\s+(?=\d)", re.I)
ABOUT_NUM = re.compile(r"\b(?:about|around|roughly|approximately)\s+(?=\d)", re.I)
LIVES_IN = re.compile(r"\b(?:lives?|stored|located)\s+in\s+(?=[a-z0-9/])", re.I)
NO_PREFIX = re.compile(r"^(?:no|nope|nah|not really)[,.]\s+", re.I)
TODO_MARKER = re.compile(r"^(?:todo|to-do|action item|next step)\s*[:,\-–—]\s*", re.I)
REPO_LEAD = re.compile(r"^(?:repo|repository)\s+", re.I)
CLUSTER_LEAD = re.compile(r"\b(in|on)\s+(?:cluster|region|namespace)\s+(?=[a-z0-9])", re.I)
CONTAINS = re.compile(r"\bcontains\s+(?=[A-Za-z0-9/])", re.I)
ON_DATE = re.compile(r"\b(?:on|at|for)\s+(?=\d{4}-\d{2}-\d{2}\b)", re.I)
SHIPS = re.compile(r"\s+(?:ships?|lands?|goes live)$", re.I)
ARTICLE_MID = re.compile(r"\b(?:a|an)\s+(?=[a-z])", re.I)
THE_RANKED = re.compile(
    r"\bthe\s+(?=(?:last|first|next|same|only|other|remaining|estimated|actual|whole|entire|"
    r"payload|cursor|baseline|dataset|vector|index|batch)\b)",
    re.I,
)
PROD_LEAD = re.compile(r"^(?:Production|Prod)\s+(?=[a-z])", re.I)
EXACTLY = re.compile(r"\bexactly\s+(?=\d)", re.I)
ADJ_PREFIX = re.compile(r"^(?:the\s+)?(?:affected|relevant|aforementioned)\s+", re.I)
KEEP_MIND = re.compile(r"\bkeep (?:that|this) in mind(?:,?\s+because)?\s*", re.I)
WORKS_AS = re.compile(r"\b(?:works?|serves?)\s+as\s+(?:the\s+)?", re.I)
TRAILING_HELP = re.compile(r"\s+if (?:you|we) (?:need|want|like)\b.*$", re.I)
RECAP_LEAD = re.compile(
    r"^(?:"
    r"(?:to recap|recap|to summari[sz]e|in summary|quick summary)\b[^:]{0,80}:|"
    r"let me\s+(?:recap|confirm|repeat|restate|summari[sz]e|make sure)[^:]{0,90}:|"
    r"(?:just\s+)?to\s+(?:confirm|clarify|be\s+sure|be\s+clear|be\s+safe)[^:]{0,70}:|"
    r"one more thing[:,]\s*|to add detail\s*,\s*|for (?:completeness|background|context|reference)[:,]\s*|"
    r"for the record[:,]\s*|as a (?:reminder|note)[:,]\s*|quick (?:context|notes?|update)[^:]{0,50}:"
    r")",
    re.I,
)
CHATTER = re.compile(
    r"\b(?:matters? a lot|let me know|does(?: that| this) make sense|as an ai model|feel free to)\b", re.I
)
OPEN_QUESTION = re.compile(
    r"\b(?:open question|open item|unclear|unknown|tbd|to be decided|investigate|need to know|still deciding|"
    r"not sure (?:whether|if|how)|figure out (?:whether|if|how)|no decision)\b",
    re.I,
)


def is_open_question(text):
    if OPEN_QUESTION.search(text):
        return True
    return bool(re.match(r"^(?:should|could|would)\s+we\b", text.strip(), re.I))


TAIL_LEAD = re.compile(
    r"^(?:\d|hard|soft|strict|extra|only|just|still|also|and|with|from|under|due to|so|that|which|"
    r"because|known|takes?)\b",
    re.I,
)


def is_tail_fragment(text):
    if not TAIL_LEAD.match(text.strip()):
        return False
    if exact_tokens(text):
        return False
    if (
        _CONSTRAINT.search(text)
        or _DECISION.search(text)
        or _TODO.search(text)
        or _STATE.search(text)
        or is_open_question(text)
        or text.strip().endswith("?")
    ):
        return False
    return len(content_words(text)) <= 3

ACKS = {
    "good", "noted", "ok", "okay", "sure", "thanks", "thank you", "got it", "great", "nice",
    "perfect", "understood", "sounds good", "cool", "awesome", "hmm", "ah", "oh", "hi", "hello",
    "hey", "cheers", "welcome", "no problem", "np", "anytime",
}


def is_noise(text):
    t = text.strip().strip(".!?,").lower()
    if not t:
        return True
    if t in ACKS:
        return True
    ex = exact_tokens(t)
    if ex:
        return False
    if META_NOISE.match(t) or ACK_START.match(t) or FRAGMENT.match(t):
        return True
    if CHATTER.search(t):
        return True
    if len(t.split()) <= 6 and re.match(r"^(?:if|when|once|after|before|unless|while)\b", t):
        return True
    cw = content_words(t)
    if len(cw) <= 2 and not (
        _CONSTRAINT.search(t) or _DECISION.search(t) or _TODO.search(t) or _STATE.search(t)
        or is_open_question(t) or t.rstrip().endswith("?")
    ):
        return True
    words = t.split()
    if len(words) <= 2 and all(w in STOPWORDS or w in ACKS for w in words):
        return True
    return False


def split_atomic(text):
    if ";" not in text and "," not in text and not re.search(r"\band\b|\bbut\b", text, re.I):
        return [text]
    if len(text) < 20:
        return [text]
    parts = [p.strip(" ,;") for p in ATOMIC_SPLIT.split(text)]
    parts = [p for p in parts if p]
    if len(parts) < 2 or any(len(p.split()) < 2 and not exact_tokens(p) for p in parts):
        return [text]
    if any(not re.search(r"[A-Za-z]", p) for p in parts):
        return [text]
    rich = sum(1 for p in parts if _is_rich(p))
    if rich == 0:
        return [text]
    want = exact_tokens(text)
    have = set()
    for p in parts:
        have |= {t for t in want if t in p}
    if have != want:
        return [text]
    return parts


def _is_rich(part):
    if exact_tokens(part):
        return True
    if _CONSTRAINT.search(part) or _DECISION.search(part) or _TODO.search(part) or _STATE.search(part):
        return True
    if is_open_question(part):
        return True
    words = part.split()
    for w in words[1:]:
        if re.match(r"^[A-Z][a-z]", w) or re.match(r"^[A-Z]{2,}", w) or "_" in w or re.match(r"^[a-z]+[A-Z]", w):
            return True
    return False

_CONSTRAINT = re.compile(
    r"\b(?:must(?:\s+not)?|never|always|required|cannot|can't|do not|don't|only\s+(?:use|allow|accept)|"
    r"at most|at least|no more than|no less than|limited to|forbidden|prohibited|mandatory|not allowed)\b",
    re.I,
)
_DECISION = re.compile(
    r"\b(?:decided|decision|agreed|chose|chosen|selected|adopted|approved|settled on|we'll use|we will use|"
    r"going with)\b",
    re.I,
)
_TODO = re.compile(
    r"\b(?:todo|to-do|next step|action item|needs? to|must remember to|should\b|plan(?:ning)? to|"
    r"will\s+(?:need|have) to|remaining|follow[- ]?up|pending|left to do)\b",
    re.I,
)
_STATE = re.compile(
    r"\b(?:currently|in[- ]progress|status|blocked|stuck|completed|done|finished|implemented|deployed|"
    r"passing|failing|working on|started|paused|waiting on|ready|migrated|rolled back|shipped)\b",
    re.I,
)
_QUESTION_START = re.compile(
    r"^(?:what|why|how|when|where|who|whom|which|whose|can|could|should|would|will|is|are|was|were|"
    r"do|does|did|has|have|shall)\b",
    re.I,
)
_ENTITY = re.compile(
    r"(?:`[^`]+`|\b[A-Z][A-Z0-9_]{2,}\b|\b[a-z]+(?:[A-Z][a-z0-9]*)+\b|\b\w*_\w+\b|[\w./-]*\.\w{2,6}\b)"
    r"\s+(?:is (?:a|an|the)\b|are (?:a|an|the)\b|refers to|means|stands for|defined as|called|named)\b"
)

SUPERSEDE_CUE = re.compile(
    r"(?:no longer|instead|changed to|changed from|updated to|updated from|switched to|switch(?:ed|ing)? to|"
    r"moved to|now use|actually|correction|replaced|supersedes|revert(?:ed)?|scratch that|not anymore)",
    re.I,
)

STOPWORDS = set(
    """a an the and or but if then else of to in on at by for with from as is are was were be been being am
    it its this that these those i we you he she they them our your their my me us do does did done have has
    had having will would shall should can could may might must not no nor so than too very just also there
    here what which who whom whose when where why how about into over under again more most some any all each
    other such only own same new now still per via using used use get got make made also like need needs
    into out up down off because since while during before after until between within every through
    says said say want wanted keep keeps""".split()
)

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?")
_TOKEN_RE = re.compile(r"[A-Za-z_][\w.-]*|\d[\w.,-]*|[^\s\w]")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)]|#)\s+")


@dataclass
class ExtractedUnit:
    type: str
    text: str
    source_text: str
    model: str | None = None


def exact_tokens(text):
    found = set()
    for rx in EXACT_REGEXES:
        for m in rx.finditer(text):
            found.add(m.group(0).rstrip(".,;:!?"))
    return {t for t in found if t}


def content_words(text):
    out = set()
    for w in _WORD_RE.findall(text.lower()):
        if len(w) >= 2 and w not in STOPWORDS:
            out.add(w)
    return out


def fingerprint(text):
    norm = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def normalize(text):
    s = text.strip().strip("\"'“”")
    s = re.sub(r"\s+", " ", s)
    return s


def strip_speaker(text):
    return SPEAKER_PREFIX.sub("", text, count=1)


def compress(text, type_):
    original = normalize(text)
    s = original
    for _ in range(4):
        s2 = strip_speaker(s)
        s2 = FILLER_PREFIX.sub("", s2, count=1)
        s2 = LEAD_SEE.sub("", s2, count=1)
        s2 = RECAP_LEAD.sub("", s2, count=1)
        s2 = ACK_PREFIX.sub("", s2, count=1)
        s2 = NO_PREFIX.sub("", s2, count=1)
        s2 = ORDINAL_PREFIX.sub("", s2, count=1)
        s2 = DEPLOY_LEAD.sub("", s2, count=1)
        s2 = PROD_LEAD.sub("", s2, count=1)
        s2 = REPO_LEAD.sub("", s2, count=1)
        s2 = TEMPORAL_CLAUSE.sub("", s2, count=1)
        s2 = ADJ_PREFIX.sub("", s2, count=1)
        s2 = DECISION_MARKER.sub("", s2, count=1)
        s2 = TODO_MARKER.sub("", s2, count=1)
        s2 = THERE_COPULA.sub("", s2, count=1)
        if type_ == "decision":
            s2 = DECISION_PREFIX.sub("", s2, count=1)
        s2 = PRONOUN_PREFIX.sub("", s2, count=1)
        s2 = RUN_REMAIN.sub("", s2, count=1)
        s2 = ARTICLE_PREFIX.sub("", s2, count=1)
        s2 = COPULA.sub(r"\1", s2)
        s2 = LIVES_IN.sub("", s2)
        s2 = CONTAINS.sub("", s2)
        s2 = CLUSTER_LEAD.sub(r"\1 ", s2)
        s2 = VALUE_CONNECTOR.sub("", s2)
        s2 = EXACTLY.sub("", s2)
        s2 = ABOUT_NUM.sub("", s2)
        s2 = VERB_FOR.sub("", s2)
        s2 = TO_VALUE.sub(r"\1", s2)
        s2 = ON_DATE.sub("", s2)
        s2 = KEEP_MIND.sub("", s2, count=1)
        s2 = WORKS_AS.sub("", s2, count=1)
        s2 = TRAILING_HELP.sub("", s2, count=1)
        s2 = ARTICLE_MID.sub("", s2)
        s2 = THE_RANKED.sub("", s2)
        s2 = CONFIG_LEAD.sub("", s2, count=1)
        s2 = PREP_THE.sub(r"\1 ", s2)
        s2 = TRAILING_NOUN.sub("", s2, count=1)
        s2 = SHIPS.sub("", s2, count=1)
        s2 = normalize(s2)
        if s2 == s:
            break
        s = s2
    if type_ == "question":
        s = s.rstrip().rstrip(".!;,")
        if not s.endswith("?"):
            s += "?"
    else:
        s = s.rstrip().rstrip(".!;,?")
    if original.endswith("?") and type_ != "question":
        type_ = "question"
    if len(s) < 3:
        return original
    missing = [t for t in exact_tokens(original) if t not in s]
    if missing:
        return original
    if _NEGATIONS.search(original) and not _NEGATIONS.search(s):
        return original
    return s


def classify(text):
    stripped = text.strip()
    if stripped.endswith("?"):
        return "question"
    if is_open_question(stripped):
        return "question"
    if _CONSTRAINT.search(stripped):
        return "constraint"
    if _DECISION.search(stripped):
        return "decision"
    if _QUESTION_START.match(stripped):
        return "question"
    if _TODO.search(stripped):
        return "todo"
    if _STATE.search(stripped):
        return "state"
    if _ENTITY.search(stripped):
        return "entity"
    return "fact"


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def attr_keys(text):
    tokens = _TOKEN_RE.findall(text)
    attr = {}
    for i, tok in enumerate(tokens):
        if not re.match(r"\d", tok):
            continue
        if DATE_RE.match(tok):
            key = "date"
        else:
            key = None
            skipped = 0
            j = i - 1
            while j >= 0 and skipped < 4:
                prev = tokens[j]
                if re.match(r"^[A-Za-z_][\w.-]*$", prev):
                    if prev.lower() in STOPWORDS or prev in ("is", "are", "was", "were", "of", "at", "to", "as"):
                        skipped += 1
                        j -= 1
                        continue
                    key = prev.lower()
                    break
                j -= 1
                skipped += 1
        if key:
            attr.setdefault(key, set()).add(tok)
    return {k: sorted(v) for k, v in attr.items()}


_SUFFIXES = ("ational", "ization", "ingly", "edly", "ation", "ing", "ly", "ed", "es", "al", "s", "e")
_IRREGULAR = {"kept": "keep", "made": "make", "taken": "take", "ran": "run", "said": "say"}


def stem(word):
    w = word.lower()
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if not w.isalpha():
        return w
    for _ in range(2):
        for suf in _SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        else:
            break
    return w


def stems(words):
    return {stem(w) for w in words}


def nonnumeric(words):
    return {w for w in words if not any(c.isdigit() for c in w)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def split_sentences(text):
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'#\[`])|\n+", text)
    out = []
    for p in pieces:
        p = _BULLET_RE.sub("", p).strip()
        if not p:
            continue
        if len(p) > 500:
            out.extend(_split_long(p))
        else:
            out.append(p)
    return out


def _split_long(text):
    parts = re.split(r"(?<=[;])\s+|(?<=,)\s+(?=[A-Z0-9\"'#`])", text)
    merged = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if merged and len(part) < 40:
            merged[-1] = merged[-1] + " " + part
        else:
            merged.append(part)
    if not merged:
        return [text]
    want = exact_tokens(text)
    have = set()
    for m in merged:
        have |= {t for t in want if t in m}
    if have != want:
        return [text]
    return [m for m in merged if len(m) >= 3]


def split_turns(content):
    if isinstance(content, str):
        return [(None, content)]
    turns = []
    for item in content or []:
        if isinstance(item, str):
            turns.append((None, item))
        elif isinstance(item, dict):
            text = item.get("text") or item.get("content") or ""
            model = item.get("model") or item.get("source_model")
            if text:
                turns.append((model, str(text)))
    return turns


def new_unit_id(existing=None):
    import secrets

    while True:
        uid = secrets.token_hex(4)
        if not existing or uid not in existing:
            return uid
