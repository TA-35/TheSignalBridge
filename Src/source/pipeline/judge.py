"""LLM judge for Compose rewrites (eval harness).

Pairwise judge: given an original message and two candidate OUTPUTS (A and B,
each with a rewrite, its notes and its extracted meaning), decide which output
has fewer and less severe faults against the Compose spot-check rubric.
Pointwise scorer: score one output 0-2 on four criteria, for validating the
judge against human scores.

Reference-free: the judge never sees a gold/reference rewrite. A = few-shot
baseline, B = fine-tuned model. Judge: nvidia/nemotron-3-super-120b-a12b on
NVIDIA NIM at temperature 0, a different model family from the teacher
(DeepSeek) and the student (Qwen).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from . import compose_prompt as cp
from .config import PROVIDER_DEFAULTS

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "nvidia/nemotron-3-super-120b-a12b")
JUDGE_TEMPERATURE = 0.0
JUDGE_MAX_TOKENS = 4000

_NVIDIA = PROVIDER_DEFAULTS["nvidia"]


class JudgeError(RuntimeError):
    """The judge could not be reached, or would not return a usable verdict."""


JUDGE_SYSTEM = """You are the quality judge for a tool that rewrites workplace \
messages so a neurodivergent reader can understand them without decoding. You \
are shown one original message and two candidate outputs, A and B. Each output \
has a rewrite, its change notes, and the meaning it extracted. Decide which \
output is better by how few and how minor its faults are. Judge against the \
original only: you are shown no reference answer, and neither output's length \
should sway you.

An output is faulty when any of these is true:
- The meaning changed: a fact, commitment, deadline or urgency differs from \
the original.
- Something was added that the sender did not say or clearly mean, including a \
guess at missing information instead of a note asking for it.
- The real ask is still buried, several asks are run together in one sentence, \
or a message that was already clear was needlessly rewritten.
- An idiom or figure of speech was left in where a literal reader could \
misread it.
- It reads cold, curt or robotic where the original was friendly.
- A note is wrong, vague, or describes a change that was not made.
- The extracted meaning disagrees with the original: wrong ask, invented \
deadline, or urgency raised or lowered.

Pick the output with fewer and less severe faults. If they are genuinely \
equal, answer "tie", but use it sparingly. Reply with ONE JSON object and \
nothing else: {"winner": "A" | "B" | "tie", "reason": "<one sentence naming \
the deciding fault, under 30 words>"}"""


SCORE_CRITERIA = ("meaning_kept", "clarity", "warmth", "notes_accurate")

SCORE_SYSTEM = """You are scoring one rewrite produced by a tool that rewrites \
workplace messages so a neurodivergent reader can understand them without \
decoding. You see the original message and one output (its rewrite, notes and \
extracted meaning). Score it against the original only; you are shown no \
reference answer.

Score each criterion 0, 1 or 2:
- meaning_kept: 2 = same meaning, nothing added or dropped; 1 = a small detail \
changed or added; 0 = a fact, commitment, deadline or urgency changed, or \
information was invented.
- clarity: 2 = main ask first, literal language, several asks each on their own \
line; 1 = mostly clear but one ask buried or an idiom left in; 0 = ask buried, \
asks run together, or a clear message needlessly rewritten.
- warmth: 2 = keeps greetings, thanks and courtesy, reads friendly; 1 = a \
little flat; 0 = cold, curt or robotic where the original was friendly.
- notes_accurate: 2 = notes correctly describe the changes made; 1 = a note is \
vague; 0 = a note is wrong or describes a change that was not made.

Reply with ONE JSON object and nothing else: {"meaning_kept": 0, "clarity": 0, \
"warmth": 0, "notes_accurate": 0} with each value 0, 1 or 2."""


def _format_signals(signals):
    return "\n".join(f"- {s['model']}: {s['label']} ({s['confidence']:.2f})"
                     for s in cp.clean_signals(signals))


def _render_output(out):
    lines = [f"Rewrite:\n{str(out.get('rewrite', '')).strip()}"]
    notes = out.get("notes") or []
    if notes:
        lines.append("Notes:")
        lines += [f"- {str(n).strip()}" for n in notes]
    meaning = out.get("meaning") or {}
    if meaning:
        lines.append("Extracted meaning:")
        for k in ("ask", "deadline", "urgency", "tone", "implied"):
            lines.append(f"- {k}: {str(meaning.get(k, '')).strip()}")
    return "\n".join(lines)


def build_judge_prompt(source, signals, output_a, output_b):
    question, message = cp.split_circa(source)
    parts = ["Classifier signals (hints only, often wrong):",
             _format_signals(signals), ""]
    if question is not None:
        parts += ["The message is a reply to this question:",
                  f"<question>\n{question}\n</question>", "",
                  "Original reply (this is what was rewritten):",
                  f"<original>\n{message}\n</original>", ""]
    else:
        parts += ["Original message (this is what was rewritten):",
                  f"<original>\n{message}\n</original>", ""]
    parts += [f"<output_A>\n{_render_output(output_a)}\n</output_A>", "",
              f"<output_B>\n{_render_output(output_b)}\n</output_B>"]
    return "\n".join(parts)


_clients: dict = {}


def _client():
    if "nvidia" not in _clients:
        from openai import OpenAI
        key = os.environ.get(_NVIDIA["key_env"]) or os.environ.get("NVIDIA_API_KEY")
        if not key:
            raise JudgeError(f"no NVIDIA key; set {_NVIDIA['key_env']} in the environment")
        _clients["nvidia"] = OpenAI(base_url=_NVIDIA["base_url"], api_key=key,
                                    timeout=120.0, max_retries=2)
    return _clients["nvidia"]


def _extract_json(text):
    cleaned = re.sub(r"```(?:json)?", "", str(text)).strip()
    matches = list(re.finditer(r"\{.*?\}", cleaned, re.S))
    if not matches:
        raise JudgeError("no JSON object in the judge reply")
    for m in reversed(matches):
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and ("winner" in data or "meaning_kept" in data):
            return data
    for m in reversed(matches):
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
    raise JudgeError("judge reply has no parseable JSON object")


def _content_of(choice):
    msg = getattr(choice, "message", None)
    content = getattr(msg, "content", None)
    if content:
        return content
    return getattr(msg, "reasoning_content", None)


@dataclass
class Verdict:
    winner: str   # "A", "B", or "tie"
    reason: str
    model: str


@dataclass
class PairResult:
    winner: str   # "a", "b", "tie", or "no_decision"
    agree: bool
    order_ab: Verdict
    order_ba: Verdict


@dataclass
class Scores:
    meaning_kept: int
    clarity: int
    warmth: int
    notes_accurate: int
    model: str

    @property
    def total(self):
        return self.meaning_kept + self.clarity + self.warmth + self.notes_accurate


def _call(system, user):
    client = _client()
    try:
        resp = client.chat.completions.create(
            model=JUDGE_MODEL, temperature=JUDGE_TEMPERATURE, max_tokens=JUDGE_MAX_TOKENS,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
    except Exception as exc:
        raise JudgeError(f"request failed: {type(exc).__name__}") from exc
    choices = getattr(resp, "choices", None) or []
    if not choices:
        raise JudgeError("response had no choices")
    content = _content_of(choices[0])
    if not content:
        raise JudgeError(f"response had no content (finish_reason={getattr(choices[0], 'finish_reason', None)})")
    return _extract_json(content)


def judge_once(source, signals, output_a, output_b):
    """One verdict for A vs B in the given order. output_* are {meaning, rewrite, notes}."""
    data = _call(JUDGE_SYSTEM, build_judge_prompt(source, signals, output_a, output_b))
    winner = str(data.get("winner", "")).strip().upper()
    if winner not in ("A", "B", "TIE"):
        raise JudgeError(f"judge winner {data.get('winner')!r} is not A/B/tie")
    return Verdict(winner=("tie" if winner == "TIE" else winner),
                   reason=str(data.get("reason", "")).strip(), model=JUDGE_MODEL)


def _system_winner(pos_winner, a_shown_first):
    if pos_winner == "tie":
        return "tie"
    if a_shown_first:
        return "a" if pos_winner == "A" else "b"
    return "b" if pos_winner == "A" else "a"


def judge_pair(source, signals, output_a, output_b):
    """Position-swapped comparison. A system wins only if both orderings pick it."""
    v_ab = judge_once(source, signals, output_a, output_b)
    v_ba = judge_once(source, signals, output_b, output_a)
    w1 = _system_winner(v_ab.winner, True)
    w2 = _system_winner(v_ba.winner, False)
    winner, agree = (w1, True) if w1 == w2 else ("no_decision", False)
    return PairResult(winner=winner, agree=agree, order_ab=v_ab, order_ba=v_ba)


def score_output(source, signals, output):
    """Pointwise: score one output 0-2 on each of the four criteria."""
    question, message = cp.split_circa(source)
    ctx = ""
    if question is not None:
        ctx = f"The message is a reply to this question:\n<question>\n{question}\n</question>\n\n"
    user = (f"Classifier signals (hints only):\n{_format_signals(signals)}\n\n"
            f"{ctx}Original message:\n<original>\n{message}\n</original>\n\n"
            f"Output to score:\n<output>\n{_render_output(output)}\n</output>")
    data = _call(SCORE_SYSTEM, user)

    def clamp(k):
        try:
            v = int(round(float(data.get(k))))
        except (TypeError, ValueError):
            raise JudgeError(f"scorer missing/invalid {k}: {data.get(k)!r}")
        return max(0, min(2, v))

    return Scores(clamp("meaning_kept"), clamp("clarity"),
                  clamp("warmth"), clamp("notes_accurate"), model=JUDGE_MODEL)


if __name__ == "__main__":
    src = ("Q: are you coming to the team lunch friday?\n"
           "Reply: i mean if things wrap up maybe but who knows lol")
    sig = [cp.failed_signal("tone"), cp.failed_signal("politeness"), cp.failed_signal("circa")]
    a = {"meaning": {"ask": "", "deadline": "", "urgency": "low",
                     "tone": "uncertain, friendly", "implied": "might not come"},
         "rewrite": ("I'm not sure yet. If I finish my work in time I'll come to "
                     "the team lunch on Friday. I'll let you know."),
         "notes": ["Made the uncertain reply explicit.", "Removed the idiom 'who knows'."]}
    b = {"meaning": {"ask": "", "deadline": "", "urgency": "low",
                     "tone": "dismissive", "implied": ""},
         "rewrite": "Maybe. Who knows.",
         "notes": ["Kept it short."]}
    result = judge_pair(src, sig, a, b)
    print(f"winner={result.winner}  agree={result.agree}")
    print(f"  A first: {result.order_ab.winner}  ({result.order_ab.reason})")
    print(f"  B first: {result.order_ba.winner}  ({result.order_ba.reason})")
    print("pointwise score of A:", score_output(src, sig, a))