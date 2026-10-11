# Compose style guide and output contract

What a good rewrite looks like. Use this for the 10% spot-check, for verifying the gold set, and as the
rubric for the LLM judge. The prompt the model sees is built from the same rules in
`Src/source/pipeline/compose_prompt.py` and `Src/source/pipeline/prompts/` — if this guide and the prompt
ever disagree, fix both in the same PR. Any change to the prompt files changes `fingerprint()`, and the
filter rejects generated data made with a different one, so regenerate after a prompt change.

## The job

The sender gives us either a message they have already written, or rough notes about what they want to
say (typed or dictated: "tell Sam I cant do the thing friday, maybe next week"). We write the message a
neurodivergent (ND) reader can understand without having to decode it. The sender sees it and accepts,
edits or discards it before sending, so it is written **in the sender's voice**, as the message they
would send.

**Same meaning, clearer form.** Nothing is added that the sender didn't mean, nothing is dropped that they
did.

## What a good rewrite does

1. **Puts the main point or the ask first.** "If you get a chance, could you maybe look at…" becomes
   "Could you please look at…". If there is no ask, don't invent one.
2. **Lists two or more asks, steps or items as bullet points**, one per line starting with `- `, so none
   of them gets missed.
3. **Uses literal words.** Idioms, sarcasm and figures of speech become what they mean: "circle back"
   becomes "talk about this again", "once the dust settles" becomes "once things are calmer".
4. **Makes who / what / when explicit — using only what the input says.** If it says "this week", the
   rewrite says "this week", not "by Friday". If it gives no deadline, the rewrite gives none.
5. **Says whether a reply or an action is needed, and whether anything is optional**, when the input
   makes that clear. Carries the urgency the input has: "No rush, but before Thursday" has a deadline, so
   say so. Never raise or lower the urgency.
6. **Names implied feelings when they change how the message should be read.** "I needed it yesterday"
   carries frustration; "I'm frustrated it's late" says it out loud so it isn't guessed at. Don't add
   feelings that aren't there.
7. **Uses short sentences, one idea each, and stays warm.** Cut filler, not courtesy: keep greetings,
   thanks and kindness. Clear is not blunt. A rewrite that reads cold or robotic fails, even if it's
   accurate.
8. **Leaves clear messages alone.** If the message is already direct and plain, return it unchanged.
   Over-editing is a failure too.

## When something is missing

Rough notes often leave things out: what "the thing" or "it" is, who it's for, when it's due. **Don't
guess.** Write around the gap and say in a note what the sender should add ("You didn't say what 'the
thing' is. Name it so Sam knows what is moving."). The sender can fix it before sending; the model can't
know it.

## Hard rules (automatic filters reject these)

- No name, organisation, date, time, amount or number that isn't in the input. Keep every one that is.
  Placeholders like `[PHONE_REDACTED]` and `[URL]` count as entities and must be kept.
- No change of facts or commitments (the NLI check rejects contradictions).
- Length between 0.5× and 2.5× the original word count.
- **Circa messages** (`Q: … / Reply: …`): rewrite the **reply only**. The question is context. The
  rewrite may use details from the question (e.g. answering "No, I can't come to the team lunch on
  Friday").

## Change notes

Every rewrite comes with **1–3 notes**, each **under 20 words**, telling the sender what changed and why.

- Say what changed and why, in plain words: "Made the request direct: please review the Q3 numbers."
- One idea per note. Most important first.
- If something is missing, a note says what to add (see above).
- Don't explain the rewrite back word for word, and don't lecture the sender.
- If nothing needed changing, exactly one note: `Already clear, kept as written.`

## Output contract

One format for everything: the teacher that generates training data, the few-shot baseline and the
fine-tuned model all return a single JSON object, nothing else, with `meaning` first so it is worked out
before the rewrite:

```json
{"meaning": {"ask": "", "deadline": "", "urgency": "low|medium|high", "tone": "", "implied": ""},
 "rewrite": "...", "notes": ["..."]}
```

- `ask` — what the reader is being asked to do, or "" if nothing.
- `deadline` — the deadline exactly as the input states it, or "".
- `urgency` — `low`, `medium` or `high`, as the input carries it.
- `tone` — a few words on how the sender comes across.
- `implied` — anything meant but not said (a feeling, an expectation, a "no"), or "".

`compose_prompt.RESPONSE_SCHEMA` enforces this shape at serving time and `parse_response` checks it.
`meaning` is stored in the training record and shown to the sender alongside the rewrite.

## Teacher (generating training pairs)

Training pairs come from `deepseek-ai/deepseek-v4.1-flash` on NVIDIA NIM. It was picked in a 20-message
bake-off on this prompt: valid JSON 20/20, no invented facts, median 18 s a message. GLM-5.3-flash was
three times slower and invented a fact; Gemma-4-31B was not reachable.

- Messages: `cp.build_messages(source, signals, few_shot=True)`.
- `temperature` 0.3, `max_tokens` 4000 (it reasons before answering; the answer itself is under ~600
  tokens).
- Parse with `cp.parse_response(reply)`. If it fails, still write the record with the reply text under
  `raw`, so the filter's `json_valid` check rejects it and counts it.
- Write `data/generated/<dataset>_gen.jsonl`, one record per line with `id`, `dataset`, `source`,
  `signals`, `meaning`, `rewrite`, `notes`, `model` and `prompt_version` (= `cp.fingerprint()`).
- Five requests in parallel is fine (20 messages in under 2 minutes); retry HTTP 429 and 504 with a
  back-off.

The LLM judge must come from a different model family than both the teacher (DeepSeek) and the model
being trained (Qwen), so it doesn't favour its own style. Use `nvidia/nemotron-3-super-120b-a12b` on NIM
at temperature 0: in an order-swapped check on 19 pairs it answered every one in ~11 s. GLM-5.3 timed
out on 14 of 19. It still has to be validated against the human rubric scores before its verdicts count.

## Classifier signals

Each input comes with three classifier signals (tone, politeness, circa). They are **hints**: small
models, not trained on workplace email, often wrong. The input text always wins. A failed classifier
appears as `unknown` with confidence `0.00` and must be ignored.

## Spot-check: pass or fail

Mark a pair **fail** if any of these is true:

- The meaning changed: a fact, commitment, deadline or urgency is different.
- Something was added that the sender didn't say or clearly mean, including a guess at missing
  information instead of a note asking for it.
- A reply to a question only implies its answer, and the rewrite still leaves it to be worked out.
  Stating an answer the reply clearly implies ("No, I can't come…", as in the Circa example) is the job,
  not an addition; stating one the reply doesn't settle is a guess.
- The real ask is still buried, several asks are run together in one sentence, or a clear message was
  needlessly rewritten.
- An idiom or figure of speech was left in where a literal reader could misread it.
- It reads cold, curt or robotic where the original was friendly.
- A note is wrong, vague, or describes a change that wasn't made.
- `meaning` disagrees with the input (wrong ask, invented deadline, urgency raised or lowered).

Over 20% fails in a batch → fix the prompt and regenerate. Don't hand-edit pairs.

## Examples

The few-shot examples in `Src/source/pipeline/prompts/compose_examples.json` are the reference examples
for this guide: a hedged request, a blunt complaint, an over-polite request, several asks in one
sentence, rough notes with something missing, idioms, an already-clear message, and a Circa reply. Their
signals come from the frozen adapters, run on the part that gets rewritten, except the Circa example's
tone, which is set to the failure shape on purpose so the model sees one.
