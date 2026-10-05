# Compose style guide and output contract

What a good rewrite looks like. Use this for the 10% spot-check, for verifying the gold set, and as the
rubric for the LLM judge. The prompt the model sees is built from the same rules in
`Src/source/pipeline/compose_prompt.py` — if this guide and that module ever disagree, fix both in the
same PR.

## The job

A neurotypical (NT) colleague writes a message. We rewrite it so a neurodivergent (ND) reader gets the
meaning without having to decode it. The sender sees the rewrite and accepts, edits or discards it before
sending, so the rewrite is written **in the sender's voice**, as the message they would send.

**Same meaning, clearer form.** Nothing is added that the sender didn't mean, nothing is dropped that they
did.

## What a good rewrite does

1. **States the real ask plainly.** "If you get a chance, could you maybe look at…" becomes "Could you
   please look at…". If there is no ask, don't invent one.
2. **Makes who / what / when explicit — using only what the message says.** If it says "this week", the
   rewrite says "this week", not "by Friday". If it gives no deadline, the rewrite gives none.
3. **Says the urgency the message actually carries.** "No rush, but before Thursday" has a deadline;
   say so. Don't raise or lower the urgency.
4. **Names implied feelings when they change how the message should be read.** "I needed it yesterday"
   carries frustration; "I'm frustrated it's late" says it out loud so it isn't guessed at. Don't add
   feelings that aren't there.
5. **Stays warm.** Clear is not blunt. Keep greetings, thanks and kindness. Remove hedging, not courtesy.
   A rewrite that reads cold or robotic fails, even if it's accurate.
6. **Leaves clear messages alone.** If the message is already direct and plain, return it unchanged.
   Over-editing is a failure too.

## Hard rules (automatic filters reject these)

- No name, organisation, date, time, amount or number that isn't in the original. Keep every one that is.
  Placeholders like `[PHONE_REDACTED]` count as entities and must be kept.
- No change of facts or commitments (the NLI check rejects contradictions).
- Length between 0.5× and 2.5× the original word count.
- **Circa messages** (`Q: … / Reply: …`): rewrite the **reply only**. The question is context. The
  rewrite may use details from the question (e.g. answering "No, I can't make Friday's lunch").

## Change notes

Every rewrite comes with **1–3 notes**, each **under 20 words**, telling the sender what changed and why.

- Say what changed and why, in plain words: "Made the request direct: please review the Q3 numbers."
- One idea per note. Most important first.
- Don't explain the rewrite back word for word, and don't lecture the sender.
- If nothing needed changing, exactly one note: `Already clear, kept as written.`

## Output contract

The model returns a single JSON object, nothing else:

```json
{"rewrite": "...", "notes": ["...", "..."]}
```

The teacher model that generates training data also fills in `meaning` (it is stored in the training
record, not shown to the sender):

```json
{"meaning": {"ask": "", "deadline": "", "urgency": "low|medium|high", "tone": "", "implied": ""},
 "rewrite": "...", "notes": ["..."]}
```

- `ask` — what the reader is being asked to do, or "" if nothing.
- `deadline` — the deadline exactly as the message states it, or "".
- `urgency` — `low`, `medium` or `high`, as the message carries it.
- `tone` — a few words on how the sender comes across.
- `implied` — anything meant but not said (a feeling, an expectation, a "no"), or "".

## Classifier signals

Each message comes with three classifier signals (tone, politeness, circa). They are **hints**: small
models, not trained on workplace email, often wrong. The message text always wins. A failed classifier
appears as `unknown` with confidence `0.00` and must be ignored.

## Spot-check: pass or fail

Mark a pair **fail** if any of these is true:

- The meaning changed: a fact, commitment, deadline or urgency is different.
- Something was added that the sender didn't say or clearly mean.
- The real ask is still buried, or a clear message was needlessly rewritten.
- It reads cold, curt or robotic where the original was friendly.
- A note is wrong, vague, or describes a change that wasn't made.

Over 20% fails in a batch → fix the prompt and regenerate. Don't hand-edit pairs.

## Examples

The few-shot examples in `Src/source/pipeline/prompts/compose_examples.json` are the reference examples
for this guide: a hedged request, a blunt complaint, an over-polite request, an already-clear message,
and a Circa reply.
