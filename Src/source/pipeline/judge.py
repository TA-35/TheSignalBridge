"""LLM judge for Compose rewrites (eval harness).

Pairwise judge: given an original message and two candidate OUTPUTS (A and B,
each with a rewrite, its notes and its extracted meaning), decide which output
has fewer and less severe faults against the Compose spot-check rubric.
Pointwise scorer: score one output 0-2 on four criteria, for validating the
judge against human scores.

Reference-free: the judge sees the source, the two outputs and the rubric only,
never a gold rewrite and never the classifier signals (neither helps judge
rewrite quality and either could sway the verdict). A = few-shot baseline,
B = fine-tuned model. Judge: nvidia/nemotron-3-super-120b-a12b on NVIDIA NIM at
temperature 0, a different model family from the teacher (DeepSeek) and the
student (Qwen).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from . import compose_prompt as cp
from .config import PROVIDER_DEFAULTS

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "nvidia/nemotron-3-super-120b-a12b")  # Get the judge model name from the environment or use the default
JUDGE_TEMPERATURE = 0.0  # Set temperature to zero for more consistent responses
JUDGE_MAX_TOKENS = 4000  # Set the maximum tokens allowed in the judge response

_NVIDIA = PROVIDER_DEFAULTS["nvidia"]  # Get the NVIDIA API settings from the config


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
the deciding fault, under 30 words>"}"""  # Tell the judge how to compare two outputs and return a winner


SCORE_CRITERIA = ("meaning_kept", "clarity", "warmth", "notes_accurate")  # Four criteria used to score each rewrite

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
"warmth": 0, "notes_accurate": 0} with each value 0, 1 or 2."""  # Tell the judge how to score one output from 0 to 2 on each criterion


def _render_output(out):
    lines = [f"Rewrite:\n{str(out.get('rewrite', '')).strip()}"]  # Get the rewrite and add its heading

    notes = out.get("notes") or []  # Get the notes or use an empty list

    if notes:
        lines.append("Notes:")  # Add a heading if notes are available
        lines += [f"- {str(n).strip()}" for n in notes]  # Add each note as a separate line

    meaning = out.get("meaning") or {}  # Get the extracted meaning or use an empty dictionary

    if meaning:
        lines.append("Extracted meaning:")  # Add a heading for the meaning details

        for k in ("ask", "deadline", "urgency", "tone", "implied"):  # Go through each meaning field
            lines.append(f"- {k}: {str(meaning.get(k, '')).strip()}")  # Add the field name and its value

    return "\n".join(lines)  # Combine all the lines into one formatted text


def build_judge_prompt(source, signals, output_a, output_b):
    # Keep signals out of the prompt so they do not influence the judge
    question, message = cp.split_circa(source)  # Separate the question and reply if the source is from Circa
    parts = []  # Store the different parts of the judge prompt

    if question is not None:
        parts += ["The message is a reply to this question:",
                  f"<question>\n{question}\n</question>", "",
                  "Original reply (this is what was rewritten):",
                  f"<original>\n{message}\n</original>", ""]  # Include the question for context and the original reply

    else:
        parts += ["Original message (this is what was rewritten):",
                  f"<original>\n{message}\n</original>", ""]  # Include the original message when there is no separate question

    parts += [f"<output_A>\n{_render_output(output_a)}\n</output_A>", "",
              f"<output_B>\n{_render_output(output_b)}\n</output_B>"]  # Add both model outputs for comparison

    return "\n".join(parts)  # Combine all parts into the final judge prompt


_clients: dict = {}  # Store the API client so it can be reused


def _client():
    if "nvidia" not in _clients:  # Create a client only if one does not already exist
        from openai import OpenAI  # Import the OpenAI client used to call NVIDIA's API

        key = os.environ.get(_NVIDIA["key_env"]) or os.environ.get("NVIDIA_API_KEY")  # Get the NVIDIA API key from environment variables

        if not key:
            raise JudgeError(f"no NVIDIA key; set {_NVIDIA['key_env']} in the environment")  # Stop if no API key is available

        _clients["nvidia"] = OpenAI(base_url=_NVIDIA["base_url"], api_key=key,
                                    timeout=120.0, max_retries=2)  # Create the NVIDIA API client with timeout and retry settings

    return _clients["nvidia"]  # Return the existing or newly created client


def _extract_json(text):
    cleaned = re.sub(r"```(?:json)?", "", str(text)).strip()  # Remove Markdown code fences and extra spaces

    matches = list(re.finditer(r"\{.*?\}", cleaned, re.S))  # Find possible JSON objects in the response

    if not matches:
        raise JudgeError("no JSON object in the judge reply")  # Stop if the response contains no JSON object

    for m in reversed(matches):  # Check matching JSON objects starting from the last one
        try:
            data = json.loads(m.group(0))  # Try to convert the matched text into JSON

        except json.JSONDecodeError:
            continue  # Skip the match if it is not valid JSON

        if isinstance(data, dict) and ("winner" in data or "meaning_kept" in data):
            return data  # Return JSON that contains an expected judge result field

    for m in reversed(matches):  # Try the matches again if no expected fields were found
        try:
            return json.loads(m.group(0))  # Return the first valid JSON object found in reverse order

        except json.JSONDecodeError:
            continue  # Skip invalid JSON objects

    raise JudgeError("judge reply has no parseable JSON object")  # Stop if no valid JSON could be extracted


def _call(system, user, _retried=False):
    client = _client()  # Get the NVIDIA API client

    try:
        resp = client.chat.completions.create(
            model=JUDGE_MODEL, temperature=JUDGE_TEMPERATURE, max_tokens=JUDGE_MAX_TOKENS,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])  # Send the system instructions and user prompt to the judge

    except Exception as exc:
        raise JudgeError(f"request failed: {type(exc).__name__}") from exc  # Raise an error if the API request fails

    choices = getattr(resp, "choices", None) or []  # Get the response choices or use an empty list

    if not choices:
        raise JudgeError("response had no choices")  # Stop if the API returned no response choices

    content = getattr(choices[0].message, "content", None)  # Get the text from the first response choice

    if not content:
        # Do not use reasoning content because it may contain an incomplete answer
        if not _retried:
            return _call(system, user, _retried=True)  # Retry once if the response is empty

        raise JudgeError("response had no content after retry "
                         f"(finish_reason={getattr(choices[0], 'finish_reason', None)})")  # Stop if the second attempt is also empty

    return _extract_json(content)  # Extract and return the JSON from the judge response


@dataclass
class Verdict:
    winner: str   # Store the winner as A, B, or tie
    reason: str  # Store the reason given by the judge
    model: str  # Store the name of the judge model


@dataclass
class PairResult:
    winner: str   # Store the final winner as a, b, tie, or no_decision
    agree: bool  # Store whether both judging orders agreed
    order_ab: Verdict  # Store the result when A was shown first
    order_ba: Verdict  # Store the result when B was shown first


@dataclass
class Scores:
    meaning_kept: int  # Store the score for keeping the original meaning
    clarity: int  # Store the score for how clear the rewrite is
    warmth: int  # Store the score for keeping a friendly tone
    notes_accurate: int  # Store the score for how accurate the notes are
    model: str  # Store the judge model name

    @property
    def total(self):
        return self.meaning_kept + self.clarity + self.warmth + self.notes_accurate  # Add all four scores to get the total out of 8


def judge_once(source, signals, output_a, output_b):
    data = _call(JUDGE_SYSTEM, build_judge_prompt(source, signals, output_a, output_b))  # Ask the judge to compare both outputs

    winner = str(data.get("winner", "")).strip().upper()  # Get the winner and convert it to uppercase

    if winner not in ("A", "B", "TIE"):
        raise JudgeError(f"judge winner {data.get('winner')!r} is not A/B/tie")  # Reject a result that is not A, B, or tie

    return Verdict(winner=("tie" if winner == "TIE" else winner),
                   reason=str(data.get("reason", "")).strip(), model=JUDGE_MODEL)  # Return the winner, reason, and judge model


def _system_winner(pos_winner, a_shown_first):
    if pos_winner == "tie":
        return "tie"  # Keep the result as a tie if the judge selected tie

    if a_shown_first:
        return "a" if pos_winner == "A" else "b"  # Match the judge's answer to the original model when A was first

    return "b" if pos_winner == "A" else "a"  # Reverse the mapping when B was shown first


def judge_pair(source, signals, output_a, output_b):
    v_ab = judge_once(source, signals, output_a, output_b)  # Judge the outputs with A shown first

    v_ba = judge_once(source, signals, output_b, output_a)  # Judge the same outputs with B shown first

    w1 = _system_winner(v_ab.winner, True)  # Convert the first judgment to the original model label
    w2 = _system_winner(v_ba.winner, False)  # Convert the second judgment to the original model label

    winner, agree = (w1, True) if w1 == w2 else ("no_decision", False)  # Keep the winner only if both judgments agree

    return PairResult(winner=winner, agree=agree, order_ab=v_ab, order_ba=v_ba)  # Return the final result and both individual judgments


def score_output(source, signals, output):
    question, message = cp.split_circa(source)  # Separate the question and reply if the source is from Circa

    ctx = ""  # Start with empty question context

    if question is not None:
        ctx = f"The message is a reply to this question:\n<question>\n{question}\n</question>\n\n"  # Add the original question as context

    user = (f"{ctx}Original message:\n<original>\n{message}\n</original>\n\n"
            f"Output to score:\n<output>\n{_render_output(output)}\n</output>")  # Build the prompt containing the original message and one output

    data = _call(SCORE_SYSTEM, user)  # Ask the judge to score the output on four criteria

    def clamp(k):
        try:
            v = int(round(float(data.get(k))))  # Get the score, convert it to a number, and round it

        except (TypeError, ValueError):
            raise JudgeError(f"scorer missing/invalid {k}: {data.get(k)!r}")  # Stop if the score is missing or invalid

        return max(0, min(2, v))  # Keep the score between 0 and 2

    return Scores(clamp("meaning_kept"), clamp("clarity"),
                  clamp("warmth"), clamp("notes_accurate"), model=JUDGE_MODEL)  # Return all four scores and the judge model


if __name__ == "__main__":
    src = ("Q: are you coming to the team lunch friday?\n"
           "Reply: i mean if things wrap up maybe but who knows lol")  # Create a sample question and indirect reply

    a = {"meaning": {"ask": "", "deadline": "", "urgency": "low",
                     "tone": "uncertain, friendly", "implied": "might not come"},
         "rewrite": ("I'm not sure yet. If I finish my work in time I'll come to "
                     "the team lunch on Friday. I'll let you know."),
         "notes": ["Made the uncertain reply explicit.", "Removed the idiom 'who knows'."]}  # Create sample output A with its meaning, rewrite, and notes

    b = {"meaning": {"ask": "", "deadline": "", "urgency": "low",
                     "tone": "dismissive", "implied": ""},
         "rewrite": "Maybe. Who knows.", "notes": ["Kept it short."]}  # Create sample output B with its meaning, rewrite, and notes

    result = judge_pair(src, None, a, b)  # Compare both sample outputs using the judge

    print(f"winner={result.winner}  agree={result.agree}")  # Display the final winner and whether both orders agreed
    print(f"  A first: {result.order_ab.winner}  ({result.order_ab.reason})")  # Display the result when A was shown first
    print(f"  B first: {result.order_ba.winner}  ({result.order_ba.reason})")  # Display the result when B was shown first
    print("pointwise score of A:", score_output(src, None, a))  # Display the four individual scores for output A