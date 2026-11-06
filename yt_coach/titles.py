"""Title pattern analysis (heuristics, no ML)."""
from __future__ import annotations

import re
from collections import Counter

POWER_WORDS = {
    "secret", "secrets", "truth", "never", "always", "why", "how", "mistake", "mistakes",
    "rich", "poor", "money", "millionaire", "billionaire", "lesson", "lessons", "story",
    "shocking", "ultimate", "simple", "best", "worst", "stop", "dont", "don't", "life",
    "changed", "changes", "everything", "nobody", "everyone", "hidden", "powerful",
    "habit", "habits", "success", "failure", "regret", "wisdom", "truth", "exposed",
}
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_NUM = re.compile(r"\d")
_STOP = {"the", "a", "an", "of", "to", "and", "in", "is", "for", "you", "your", "that", "this", "it", "with", "on", "i", "my"}


def analyze_title(title: str) -> dict:
    words = re.findall(r"[\w']+", title.lower())
    power = sorted({w for w in words if w in POWER_WORDS})
    caps = [w for w in re.findall(r"\b[A-Z]{3,}\b", title)]
    return {
        "chars": len(title),
        "words": len(words),
        "has_number": bool(_NUM.search(title)),
        "starts_with_number": bool(re.match(r"\s*\d", title)),
        "is_question": title.strip().endswith("?") or (words[:1] and words[0] in {"why", "how", "what", "when", "who", "can", "do", "does", "is", "are"}),
        "power_words": power,
        "has_caps_word": bool(caps),
        "has_brackets": bool(re.search(r"[\(\[\|]", title)),
        "has_emoji": bool(_EMOJI.search(title)),
        "first_word": words[0] if words else "",
    }


def title_note(title: str) -> str:
    a = analyze_title(title)
    bits = [f"{a['chars']} chars/{a['words']} words"]
    if a["has_number"]:
        bits.append("starts with number" if a["starts_with_number"] else "contains number")
    if a["is_question"]:
        bits.append("question/curiosity opener")
    if a["power_words"]:
        bits.append("power words: " + ", ".join(a["power_words"]))
    if a["has_caps_word"]:
        bits.append("ALL-CAPS word")
    if a["has_brackets"]:
        bits.append("brackets/separator")
    if a["has_emoji"]:
        bits.append("emoji")
    return "; ".join(bits)


def summarize_patterns(titles: list[str]) -> dict:
    """Aggregate pattern rates across a set of titles."""
    if not titles:
        return {"count": 0}
    an = [analyze_title(t) for t in titles]
    n = len(an)

    def rate(k):
        return round(sum(1 for a in an if a[k]) / n, 2)

    wc = Counter(w for t in titles for w in re.findall(r"[a-z']+", t.lower()) if w not in _STOP and len(w) > 2)
    return {
        "count": n,
        "avg_chars": round(sum(a["chars"] for a in an) / n, 1),
        "avg_words": round(sum(a["words"] for a in an) / n, 1),
        "pct_with_number": rate("has_number"),
        "pct_question": rate("is_question"),
        "pct_caps_word": rate("has_caps_word"),
        "pct_brackets": rate("has_brackets"),
        "pct_emoji": rate("has_emoji"),
        "top_first_words": Counter(a["first_word"] for a in an if a["first_word"]).most_common(5),
        "top_words": wc.most_common(8),
        "power_word_hits": Counter(w for a in an for w in a["power_words"]).most_common(8),
    }
