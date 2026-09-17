<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { Check, Copy } from '@lucide/vue'
import { decodeMessage, EmptyMessageError, MAX_MESSAGE_LENGTH, MessageTooLongError } from '@/services/decodeService'
import { findLocalPatternMatch } from '@/services/localPatterns'
import { getPatterns } from '@/services/patternsService'
import { reviewMessage } from '@/services/reviewService'
import { useCardsStore } from '@/stores/cards'
import { useDecodesStore } from '@/stores/decodes'
import { ELEMENT_LABELS, NOT_SPECIFIED, type DecodeResult } from '@/types/decode'
import type { Pattern, SavedCard } from '@/types/pattern'
import type { DecodeRecord } from '@/types/decode'
import {
  REVIEW_FIELD_LABELS,
  type FullReview,
  type QuickReview,
  type ReviewField,
  type ReviewGap,
} from '@/types/review'

const cardsStore = useCardsStore()
const decodesStore = useDecodesStore()

const SAMPLE =
  "Hi,\n\nWhen you get a chance, could you take a look at the Q3 deck and tighten up the numbers section? Would be great to have it before the leadership sync.\n\nAlso, loop in whoever owns the pricing slide if that's easier.\n\nThanks!"

const state = reactive({
  message: '',
  error: '',
  loading: false,
  result: null as DecodeResult | null,
  // Keyed by field name from whichever source produced the gap list -
  // ElementKey while the extractor is answering, ReviewField once the
  // model has. `string` is the honest type for a set spanning both, and
  // narrowing it to one vocabulary is what made the stale-tick bug above
  // possible to write.
  checked: new Set<string>(),
  matchedPattern: null as Pattern | null,
  record: null as DecodeRecord | null,
  savedCard: null as SavedCard | null,
  showSaved: false,
  // The model-backed reading. Arrives seconds after the instant decode above,
  // so it is tracked separately and rendered only once it lands - the page is
  // never blocked waiting for it.
  llm: null as FullReview | null,
  llmLoading: false,
  // Stage one. It lands in milliseconds and carries the three models'
  // read of the message, which nothing used to render - see registerChips.
  quick: null as QuickReview | null,
  // Which asks the reader has ticked off. Session-only and keyed by the
  // ask's own text: the list is rebuilt when the model answers, and an
  // index would then point at a different ask than the one that was ticked.
  done: new Set<string>(),
})

// The span currently being pointed at, highlighted in the original message.
//
// This is the page's main interactive idea. Every claim carries a span that
// was verified server-side - message.slice(start, end) === text - so pointing
// at a finding can show exactly which characters it came from, rather than
// asking the reader to take it on trust and hunt for the phrase themselves.
// For a literal reader that hunt is the expensive part.
const activeSpan = ref<[number, number] | null>(null)

function showSpan(span?: [number, number] | null) {
  activeSpan.value = span && span.length === 2 ? span : null
}
function clearSpan() {
  activeSpan.value = null
}

/** The original message, split so the active span can be marked up. */
const messageParts = computed(() => {
  const text = state.message
  const span = activeSpan.value
  if (!span) return [{ text, hit: false }]
  const [start, end] = span
  // Defensive: a span from a stale response could point outside this
  // message. Showing the message unhighlighted is the right failure.
  if (!(Number.isInteger(start) && Number.isInteger(end)) || start < 0 || end > text.length || start >= end) {
    return [{ text, hit: false }]
  }
  return [
    { text: text.slice(0, start), hit: false },
    { text: text.slice(start, end), hit: true },
    { text: text.slice(end), hit: false },
  ]
})

async function review() {
  const text = state.message.trim()
  if (!text) {
    state.error = 'The box is empty. Paste a message and we will go through it together.'
    return
  }

  state.error = ''
  state.loading = true
  try {
    state.result = await decodeMessage(text)
    state.checked = new Set()
    state.matchedPattern = null
    if (state.result.category) {
      const patterns = await getPatterns()
      const candidates = patterns.filter((p) => p.category === state.result!.category)
      // Prefer the specific pattern the wording actually points to. Only
      // fall back to "the one candidate in this category" when there's no
      // ambiguity to begin with — never guess between several.
      const specific = findLocalPatternMatch(text)
      state.matchedPattern =
        candidates.find((p) => p.id === specific?.id) ?? (candidates.length === 1 ? (candidates[0] ?? null) : null)
    }
    // Keep the decode so the work survives the session and a card can point
    // back at the message. Local only - see stores/decodes.ts.
    state.record = decodesStore.save(text, state.result, state.matchedPattern?.id ?? null)
    
    // Deliberately not awaited. The decode above is already on screen; this
    // takes seconds and fills in the closer reading when it arrives. It
    // resolves to a degraded result rather than throwing, so it can never
    // break a decode that already worked.
    state.llm = null
    state.llmLoading = true
    state.quick = null
    void reviewMessage(text, (quick) => {
      // Stage one, in milliseconds. Only accept it if the reader has not
      // already moved on, the same guard stage two carries.
      if (state.message.trim() === text) state.quick = quick
    })
      .then((result) => {
        // Ignore a late reply for a message the user has moved on from.
        if (state.message.trim() !== text) return
        state.llm = result

        // The gap list is re-keyed when the model answers: the extractor
        // names fields "task" and "for_whom", the model names them
        // "required_action" and "responsible_person". A tick made during the
        // wait is stored by field name, so without this it survives as a key
        // matching no row - invisible in the panel, and silently absent from
        // the copied questions. Keep the ticks that still name a live gap and
        // drop the rest, which the user sees happen rather than discovers
        // later in an incomplete paste.
        const live = new Set(gaps.value.map((gap) => gap.field))
        state.checked = new Set([...state.checked].filter((f) => live.has(f)))
      })
      .finally(() => {
        // Unguarded on purpose. The guard above stops a stale reading being
        // shown; this flag must clear either way, or editing the message
        // mid-request leaves the spinner running forever.
        state.llmLoading = false
      })
  } catch (err) {
    // The decoder decides what counts as a message - one rule, server-side,
    // mirrored offline. See decodeService.
    state.result = null
    state.record = null
    if (err instanceof EmptyMessageError) {
      state.error = 'This does not look like a message yet. Paste the message text itself and try again.'
    } else if (err instanceof MessageTooLongError) {
      state.error = err.message
    } else {
      throw err
    }
  } finally {
    state.loading = false
  }
}

// How the message reads, from the three models that run at stage one.
//
// These already ran on every message and their output went nowhere but the
// LLM prompt - `comments` appeared in types/review.ts and in no component.
// Register is the hardest thing to infer from a workplace message and the
// most useful thing to be told, so it is now the first thing on the page.
//
// Stated as plain English, never as a model name or a raw score. A reader
// wants "sounds politely worded", not "politeness: high (1.0)".
const REGISTER_WORDS: Record<string, Record<string, string>> = {
  politeness: {
    high: 'politely worded',
    medium: 'plainly worded',
    low: 'blunt',
  },
  tone: {
    formal: 'formal',
    neutral: 'neutral in tone',
    casual: 'casual',
  },
  circa: {
    direct: 'a direct ask',
    indirect: 'an indirect ask',
    yes: 'a direct ask',
    no: 'an indirect ask',
  },
}

// Below this, the model is guessing more than reading. Shown, but labelled -
// hiding a weak signal is dishonest and presenting it as firm is worse.
const LOW_CONFIDENCE = 0.5

const registerChips = computed(() => {
  const comments = state.quick?.comments ?? []
  return comments
    // confidence 0 is the adapters' "model unavailable" stub. There is no
    // reading to report, so there is no chip - an empty slot is better than
    // a chip saying "unknown", which reads as a claim about the message.
    .filter((c) => c.confidence > 0)
    .map((c) => ({
      model: c.model,
      word: REGISTER_WORDS[c.model]?.[c.label] ?? '',
      unsure: c.confidence < LOW_CONFIDENCE,
    }))
    .filter((c) => c.word)
})

/** Claims worth showing: those with a reading, in a stable field order. */
const llmClaims = computed(() => {
  const order: ReviewField[] = [
    'purpose', 'required_action', 'responsible_person', 'deadline', 'priority', 'context',
  ]
  return [...(state.llm?.claims ?? [])]
    .filter((c) => c.text?.trim())
    .sort((a, b) => order.indexOf(a.field) - order.indexOf(b.field))
    .map((c) => ({
      ...c,
      label: REVIEW_FIELD_LABELS[c.field] ?? c.field,
    }))
})

// The model's claims split by the job they do on the page. An action is
// something to go and do; everything else is something the message settles.
// They were rendered as one undifferentiated list before, under the extractor's
// panels - which is why the model's output read as a footnote to spaCy rather
// than as the answer.
const modelActions = computed(() =>
  llmClaims.value.filter((c) => c.field === 'required_action'),
)
const modelSettled = computed(() =>
  llmClaims.value.filter((c) => c.field !== 'required_action'),
)

function reset() {
  state.message = ''
  state.error = ''
  state.result = null
  // The closer reading belongs to the message that was cleared.
  state.llm = null
  state.llmLoading = false
  state.quick = null
  state.done = new Set()
  activeSpan.value = null
  state.checked = new Set()
  state.matchedPattern = null
  state.record = null
  state.showSaved = false
}

// F7: explicit, opt-in save. A card is saved even with no library match —
// what the message left unsaid is the lesson either way.
function makeFlashcard() {
  if (!state.record) return
  state.savedCard = cardsStore.save(state.record, state.matchedPattern)
  state.showSaved = true
}

// The saved-card dialog.
//
// It covers the page and takes the keyboard with it, so it has to behave like
// a dialog rather than merely look like one: focus moves in when it opens and
// returns to whatever opened it when it closes, Escape dismisses it, and Tab
// cycles inside it. Without the trap, the first Tab landed on "Start a new
// message" behind the backdrop - a control the reader cannot see.
const savedModal = ref<HTMLElement | null>(null)
let lastFocused: HTMLElement | null = null

function closeSaved() {
  state.showSaved = false
}

watch(
  () => state.showSaved,
  async (open) => {
    if (open) {
      lastFocused = document.activeElement as HTMLElement | null
      await nextTick()
      savedModal.value?.focus()
      return
    }
    // Guard the restore: reset() also closes this, and "View in Study"
    // navigates away, either of which can leave the trigger unmounted.
    if (lastFocused && document.contains(lastFocused)) lastFocused.focus()
    lastFocused = null
  },
)

const FOCUSABLE =
  'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])'

function trapTab(event: KeyboardEvent) {
  const root = savedModal.value
  if (!root) return
  const items = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (el) => el.offsetParent !== null,
  )
  if (!items.length) return
  const first = items[0]!
  const last = items[items.length - 1]!
  const active = document.activeElement
  // The dialog root itself holds focus on open, so shift-tabbing from it
  // wraps to the end rather than escaping backwards into the page.
  if (event.shiftKey && (active === first || active === root)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

function loadSample() {
  state.message = SAMPLE
  state.error = ''
}

function editMessage() {
  state.result = null
}

function toggleChecked(field: string) {
  if (state.checked.has(field)) state.checked.delete(field)
  else state.checked.add(field)
  // Remember which questions the user judged worth asking.
  if (state.record) decodesStore.setAsked(state.record.id, [...state.checked])
}

// What the message settles. The model's own claims when it answered - each
// one a verified quote plus what it means - and the extractor's elements
// otherwise.
//
// The extractor branch still de-duplicates against the asks list, because
// both come from the same extraction and it repeats itself. The model branch
// needs no such filter: its actions and its settled fields are disjoint by
// construction, split out of one list above.
const coveredRows = computed(() => {
  if (modelSettled.value.length) {
    return modelSettled.value.map((c) => ({
      field: c.field as string,
      label: c.label,
      value: c.text,
      reading: c.reading ?? '',
      span: c.span,
    }))
  }
  if (!state.result) return []
  const asks = new Set(todo.value.map((t) => t.text.trim().toLowerCase()))
  return state.result.covered
    .map((field) => ({
      field: field as string,
      label: ELEMENT_LABELS[field],
      value: state.result!.elements[field],
      reading: '',
      span: state.result!.spans?.[field] ?? null,
    }))
    .filter((row) => !asks.has(row.value.trim().toLowerCase()))
})

// The gaps, and the question that closes each. The model decides these from
// the message; the extractor decides them from keyword rules and is often
// wrong both ways. Both arrive in the same shape, so there is one renderer.
const gaps = computed(() => {
  // Shape-checked, not just presence-checked. The previous inference build
  // returned `missing` as a list of bare field names, so during a rollout
  // where the frontend is ahead of the service this reads `g.field` off a
  // string and renders a row with no label and no question. Anything that is
  // not {field, question} is ignored, which falls through to the extractor -
  // the same thing that happens when the model has not answered yet.
  const fromModel = (state.llm?.missing ?? []).filter(
    (g): g is ReviewGap =>
      !!g && typeof g === 'object' && !!(g as ReviewGap).field
      && !!(g as ReviewGap).question,
  )
  if (fromModel.length) {
    return fromModel.map((g) => ({
      field: g.field as string,
      label: REVIEW_FIELD_LABELS[g.field] ?? g.field,
      question: g.question,
    }))
  }
  if (!state.result) return []
  return state.result.missing.map((m) => ({
    field: m.field as string,
    label: ELEMENT_LABELS[m.field],
    question: m.prompt,
  }))
})
// Model first, extractor as the fallback - the same pattern for all three
// panels below. The extractor path is not dead code: it is what the page
// shows for the first few seconds, and what it keeps showing if the model
// fails verification or never answers.
const todo = computed(() => {
  if (modelActions.value.length) {
    return modelActions.value.map((c) => ({
      text: c.text,
      detail: '',
      reading: c.reading ?? '',
      span: c.span,
    }))
  }
  if (!state.result) return []

  const tasks = state.result.tasks ?? []
  if (tasks.length) {
    return tasks.map((task) => {
      const known = [
        task.deadline !== NOT_SPECIFIED ? `by ${task.deadline}` : null,
        task.for_whom !== NOT_SPECIFIED ? `for ${task.for_whom}` : null,
        task.time !== NOT_SPECIFIED ? `at ${task.time}` : null,
      ].filter(Boolean)
      return { text: task.text, detail: known.join(' · '), reading: '', span: null }
    })
  }

  const single = state.result.elements.task
  return single && single !== NOT_SPECIFIED
    ? [{ text: single, detail: '', reading: '', span: null }]
    : []
})

// Ticking asks off. Not persistence - a reader who comes back tomorrow
// re-decodes - but a place to put "I have done that one" so the list stops
// being a wall of undifferentiated demands. Knowing which of three things is
// left is the difference between a task and a decision about a task.
function toggleDone(text: string) {
  if (state.done.has(text)) state.done.delete(text)
  else state.done.add(text)
}

const doneCount = computed(
  () => todo.value.filter((item) => state.done.has(item.text)).length,
)

// Sections the reader has folded away, remembered between decodes.
//
// Everything starts open on purpose. Hidden content is a worse default than
// a long page: it cannot be scanned, and it makes the page a different shape
// each visit. Folding is offered for readers who want fewer things demanding
// attention at once, and the choice is theirs to keep.
const SECTIONS_KEY = 'readtheroom.decode.folded'

function loadFolded(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(SECTIONS_KEY)
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : {}
  } catch {
    // Private mode, blocked storage, or corrupt JSON. Everything open is the
    // right answer in all three.
    return {}
  }
}

const folded = reactive<Record<string, boolean>>(loadFolded())

function toggleFold(key: string) {
  folded[key] = !folded[key]
  try {
    localStorage.setItem(SECTIONS_KEY, JSON.stringify(folded))
  } catch {
    // Preference lost, page unaffected.
  }
}

const checkedPrompts = computed(() =>
  gaps.value.filter((gap) => state.checked.has(gap.field)),
)

// The message the user actually sends, assembled the moment they tick.
//
// The questions in it are the model's, written from their message. The
// greeting, opener and sign-off are fixed strings, and that is deliberate
// rather than lazy: there is nothing in the received message that licenses a
// name, and inventing one is the single thing this whole pipeline refuses to
// do. "Hi" addresses anyone; "Hi Sarah" is a fabrication the user would send
// under their own name.
//
// The opener avoids "before I get started" for the same reason the panel
// headings avoid it - not every decoded message is a task assigned to the
// reader, and an update or a thank-you note would make that phrasing read as
// a non-sequitur.
//
// Two registers, because "will this read as rude?" is the thing that stops
// people sending the message at all, and it is not a question you can answer
// for someone else - it depends on the workplace. Offering both and letting
// them pick is faster than either guessing or leaving them to rewrite it.
const draftTone = ref<'plain' | 'warm'>('plain')

const replyDraft = computed(() => {
  const questions = checkedPrompts.value.map((q) => q.question.trim()).filter(Boolean)
  if (!questions.length) return ''

  const count = questions.length === 1 ? 'one' : questions.length === 2 ? 'couple' : 'few'
  const opener =
    draftTone.value === 'warm'
      ? {
          one: 'Just one thing I wanted to check first, if that is okay:',
          couple: 'Just a couple of things I wanted to check first, if that is okay:',
          few: 'Just a few things I wanted to check first, if that is okay:',
        }[count]
      : {
          one: 'One thing I wanted to check:',
          couple: 'A couple of things I wanted to check:',
          few: 'A few things I wanted to check:',
        }[count]

  // A single question reads better inline than as a one-item bullet list.
  const body =
    questions.length === 1 ? questions[0] : questions.map((q) => `- ${q}`).join('\n')

  // Still no name in either register - see the note above. The warm version
  // adds a thank-you, which needs nothing from the message to be true.
  const greeting = draftTone.value === 'warm' ? 'Hi,\n\nThanks for this.' : 'Hi,'

  return `${greeting}\n\n${opener}\n\n${body}\n\nThanks!`
})

// What the cards show about the model's progress, as one sentence for the
// live region above. Kept in step with the card__status labels by hand -
// there are only three states, and phrasing them for listening is not the
// same job as phrasing them to sit in a header.
const readingStatus = computed(() => {
  if (state.llmLoading && !state.llm) return 'Reading the message closely. This usually takes 5 to 15 seconds.'
  if (state.llm?.degraded) return 'Showing only what was quoted directly.'
  if (state.llm) return 'The closer reading is ready.'
  return ''
})

const copyState = ref<'idle' | 'copied' | 'failed'>('idle')
let copyResetTimer: ReturnType<typeof setTimeout> | undefined

async function copyDraftToClipboard() {
  const text = replyDraft.value
  try {
    await navigator.clipboard.writeText(text)
    copyState.value = 'copied'
  } catch {
    copyState.value = 'failed'
  }
  clearTimeout(copyResetTimer)
  copyResetTimer = setTimeout(() => {
    copyState.value = 'idle'
  }, 2000)
}
</script>

<template>
  <div class="decode">
    <div v-if="!state.result" class="intake">
      <div class="intro">
        <h2>Paste the message</h2>
        <p>An email, a Slack message, a note from your manager...</p>
      </div>

      <div class="input-area">
        <textarea
          v-model="state.message"
          placeholder="Hi, when you get a chance, could you take a look at…"
          spellcheck="false"
          :class="{ 'input-area__box--error': !!state.error }"
          :aria-invalid="!!state.error"
          :aria-describedby="state.error ? 'decode-error' : undefined"
          class="input-area__box"
        />
        <div class="input-area__footer">
          <button type="button" class="link-button" @click="loadSample">Use a sample message</button>
          <span class="char-count" :class="{ 'char-count--over': state.message.length > MAX_MESSAGE_LENGTH }">
            {{ state.message.length }} / {{ MAX_MESSAGE_LENGTH }}
          </span>
        </div>
      </div>

      <div v-if="state.error" id="decode-error" class="error-banner" role="alert">
        <span class="error-dot" />
        <div>
          <strong>Please enter an actual message</strong>
          <p>{{ state.error }}</p>
        </div>
      </div>

      <div class="actions">
        <button type="button" class="btn btn--primary" :disabled="state.loading" @click="review">
          {{ state.loading ? 'Decoding...' : 'Decode Message' }}
        </button>
        <button type="button" class="btn btn--secondary" @click="reset">Reset</button>
      </div>
    </div>

    <template v-else>
      <div class="results-header">
        <div>
          <h2>Here's what the message says</h2>
          <p>What's stated stays visible. What's unclear stays open.</p>
        </div>
        <button type="button" class="btn btn--ghost" @click="editMessage">Edit message</button>
      </div>

      <div class="results-grid">
        <!-- Sticky so the message stays in view while the reader works down
             the findings. Every claim points back into this text, and a
             citation you have to scroll to is a citation you stop checking. -->
        <div class="original-panel">
          <p class="original-panel__label">The message</p>
          <p class="original-text">
            <template v-for="(part, i) in messageParts" :key="i">
              <mark v-if="part.hit" class="original-text__hit">{{ part.text }}</mark>
              <template v-else>{{ part.text }}</template>
            </template>
          </p>
        </div>

        <div class="findings">
          <!-- The reading's progress is drawn inside each card's header, which
               a screen reader never revisits once it has read past it. This
               is the same information as a region that is always mounted, so
               a change to it is actually announced. -->
          <p class="sr-only" aria-live="polite">{{ readingStatus }}</p>
          <!-- 1. How it reads ----------------------------------------------
               First because register is the hardest thing to infer from a
               work message and the most useful thing to be told, and because
               it arrives in milliseconds while the reading below takes
               seconds. Hedged in the copy: three small models, advisory. -->
          <div v-if="registerChips.length" class="register">
            <div class="register__line">
              <span class="register__lead">Reads as</span>
              <span
                v-for="chip in registerChips"
                :key="chip.model"
                class="register__chip"
                :class="{ 'register__chip--unsure': chip.unsure }"
              >
                {{ chip.word }}<template v-if="chip.unsure"> (not sure)</template>
              </span>
            </div>
            <p class="register__note">
              A guess from the wording, not a fact about the sender. Trust the words
              on the left over this.
            </p>
          </div>

          <!-- 2. What it means --------------------------------------------- -->
          <section class="card" :class="{ 'card--folded': folded.meaning }">
            <button type="button" class="card__head" :aria-expanded="!folded.meaning" @click="toggleFold('meaning')">
              <span class="card__index" aria-hidden="true">01</span>
              <span class="card__title">What this message means</span>
              <span v-if="state.llmLoading && !state.llm" class="card__status">
                reading closely — usually 5–15 seconds
              </span>
              <span v-else-if="state.llm?.degraded" class="card__status card__status--warn">
                showing only what was quoted directly
              </span>
              <span class="card__fold" aria-hidden="true">{{ folded.meaning ? '⌄' : '⌃' }}</span>
            </button>

            <div v-show="!folded.meaning" class="card__body">
              <template v-if="state.llmLoading && !state.llm">
                <div class="skeleton skeleton--wide" />
                <div class="skeleton skeleton--wide" />
                <div class="skeleton" />
              </template>
              <template v-else-if="state.llm">
                <p v-if="state.llm.summary" class="meaning">{{ state.llm.summary }}</p>
                <p v-else class="muted-line">No closer reading came back for this one.</p>
              </template>
              <p v-else class="muted-line">Reading the message…</p>
            </div>
          </section>

          <!-- 3. Asks, tickable -------------------------------------------- -->
          <section v-if="todo.length" class="card" :class="{ 'card--folded': folded.asks }">
            <button type="button" class="card__head" :aria-expanded="!folded.asks" @click="toggleFold('asks')">
              <span class="card__index" aria-hidden="true">02</span>
              <span class="card__title">What you're being asked to do</span>
              <span class="card__status">{{ doneCount }} of {{ todo.length }} done</span>
              <span class="card__fold" aria-hidden="true">{{ folded.asks ? '⌄' : '⌃' }}</span>
            </button>

            <div v-show="!folded.asks" class="card__body card__body--flush">
              <button
                v-for="(item, i) in todo"
                :key="i"
                type="button"
                class="ask"
                :class="{ 'ask--done': state.done.has(item.text) }"
                :aria-pressed="state.done.has(item.text)"
                @click="toggleDone(item.text)"
                @mouseenter="showSpan(item.span)"
                @mouseleave="clearSpan()"
                @focus="showSpan(item.span)"
                @blur="clearSpan()"
              >
                <span class="tick" :class="{ 'tick--on': state.done.has(item.text) }" aria-hidden="true" />
                <span class="ask__text">
                  <span class="ask__main">{{ item.text }}</span>
                  <span v-if="item.detail" class="ask__detail">{{ item.detail }}</span>
                  <span v-if="item.reading" class="ask__reading">{{ item.reading }}</span>
                </span>
              </button>
              <p class="card__hint">Ticking is just for you — nothing is sent anywhere.</p>
            </div>
          </section>

          <!-- 4. What it states, with its evidence -------------------------- -->
          <section v-if="coveredRows.length" class="card" :class="{ 'card--folded': folded.states }">
            <button type="button" class="card__head" :aria-expanded="!folded.states" @click="toggleFold('states')">
              <span class="card__index" aria-hidden="true">03</span>
              <span class="card__title">What the message states</span>
              <span class="card__fold" aria-hidden="true">{{ folded.states ? '⌄' : '⌃' }}</span>
            </button>

            <div v-show="!folded.states" class="card__body card__body--flush">
              <div
                v-for="row in coveredRows"
                :key="row.field"
                class="fact"
                :class="{ 'fact--live': !!row.span }"
                tabindex="0"
                @mouseenter="showSpan(row.span)"
                @mouseleave="clearSpan()"
                @focus="showSpan(row.span)"
                @blur="clearSpan()"
              >
                <span class="fact__label">{{ row.label }}</span>
                <span class="fact__body">
                  <span class="fact__value">{{ row.value }}</span>
                  <span v-if="row.reading" class="fact__reading">{{ row.reading }}</span>
                </span>
              </div>
              <p class="card__hint">Point at a row to light up where it came from.</p>
            </div>
          </section>

          <!-- 5. Gaps ------------------------------------------------------- -->
          <section class="card" :class="{ 'card--folded': folded.gaps }">
            <button type="button" class="card__head" :aria-expanded="!folded.gaps" @click="toggleFold('gaps')">
              <span class="card__index" aria-hidden="true">04</span>
              <span class="card__title">What it doesn't say</span>
              <span v-if="checkedPrompts.length" class="card__status">{{ checkedPrompts.length }} in your reply</span>
              <span class="card__fold" aria-hidden="true">{{ folded.gaps ? '⌄' : '⌃' }}</span>
            </button>

            <div v-show="!folded.gaps" class="card__body card__body--flush">
              <!-- Declarative, not an instruction. "Tick what matters to you"
                   asks the reader to judge what matters, which is often the
                   thing they came here unable to do - and an imperative reads
                   as pressure to anyone who bristles at being told. This says
                   what the control does and leaves the choice alone. -->
              <p class="card__hint card__hint--top">
                Anything you tick goes into the reply below. Anything you leave stays out.
              </p>
              <button
                v-for="gap in gaps"
                :key="gap.field"
                type="button"
                class="gap"
                :class="{ 'gap--on': state.checked.has(gap.field) }"
                :aria-pressed="state.checked.has(gap.field)"
                @click="toggleChecked(gap.field)"
              >
                <span class="tick" :class="{ 'tick--on': state.checked.has(gap.field) }" aria-hidden="true" />
                <span class="gap__text">
                  <span class="gap__label">{{ gap.label }}</span>
                  <span class="gap__q">{{ gap.question }}</span>
                </span>
              </button>
              <div v-if="!gaps.length" class="gap gap--empty">
                <span>This message answers everything it needed to.</span>
              </div>
            </div>
          </section>

          <!-- 6. The reply -------------------------------------------------- -->
          <section v-if="checkedPrompts.length" class="card card--reply">
            <div class="card__head card__head--static">
              <span class="card__index" aria-hidden="true">05</span>
              <span class="card__title">Your reply</span>
              <button type="button" class="copy-btn" @click="copyDraftToClipboard">
                <Check v-if="copyState === 'copied'" :size="14" :stroke-width="2" aria-hidden="true" />
                <Copy v-else :size="14" :stroke-width="2" aria-hidden="true" />
                <span aria-live="polite">{{
                  copyState === 'copied' ? 'Copied' : copyState === 'failed' ? "Couldn't copy" : 'Copy'
                }}</span>
              </button>
            </div>

            <div class="card__body">
              <div class="tone-pick" role="group" aria-label="Wording">
                <span class="tone-pick__lead">Wording</span>
                <button
                  type="button"
                  class="tone-pick__opt"
                  :class="{ 'tone-pick__opt--on': draftTone === 'plain' }"
                  :aria-pressed="draftTone === 'plain'"
                  @click="draftTone = 'plain'"
                >Plain</button>
                <button
                  type="button"
                  class="tone-pick__opt"
                  :class="{ 'tone-pick__opt--on': draftTone === 'warm' }"
                  :aria-pressed="draftTone === 'warm'"
                  @click="draftTone = 'warm'"
                >Warmer</button>
              </div>

              <!-- A <pre> because this is newline-formatted text meant to be
                   pasted elsewhere exactly as it reads here. Styled back to
                   the body font so it looks like a message, not code. -->
              <pre class="draft">{{ replyDraft }}</pre>
              <p class="card__hint">Copy it when you are ready. Nothing is sent from here.</p>
            </div>
          </section>

          <div v-if="!state.matchedPattern" class="notice">
            <span class="notice-dot" />
            <div>
              <strong>No library match for this wording</strong>
              <span>
                You can still keep this card, it will show the message and what it left
                unsaid, without a pattern explanation.
                <RouterLink to="/library">Browse the library</RouterLink> to see what is covered so far.
              </span>
            </div>
          </div>

          <div class="actions">
            <button
              v-if="state.record"
              type="button"
              class="btn btn--primary"
              @click="makeFlashcard"
            >
              Make it a Flashcard
            </button>
            <button type="button" class="btn btn--secondary" @click="reset">Start a new message</button>
          </div>
          <span v-if="state.matchedPattern" class="disclaimer">
            Or leaving this page without save a Flashcard :)
          </span>
        </div>
      </div>
    </template>

    <div v-if="state.showSaved" class="modal-backdrop" @click="closeSaved">
      <div
        ref="savedModal"
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="saved-title"
        tabindex="-1"
        @click.stop
        @keydown.esc="closeSaved"
        @keydown.tab="trapTab"
      >
        <div class="modal__title">
          <span class="modal__dot" />
          <strong id="saved-title">Flashcard created</strong>
        </div>
        <div class="modal__card">
          <strong>{{ state.savedCard?.name }}</strong>
          <span>{{ state.savedCard?.implies }}</span>
        </div>
        <p class="modal__note">It's in your Study section whenever you want it.</p>
        <div class="actions">
          <RouterLink to="/study" class="btn btn--primary">View in Study</RouterLink>
          <button type="button" class="btn btn--secondary" @click="closeSaved">Keep reading</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.decode {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.intake {
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.intro {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.intro h2 {
  font-family: var(--font-serif);
  font-size: 27px;
  font-weight: 500;
  letter-spacing: -0.015em;
  margin: 0;
}

.intro p {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.input-area {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.input-area__box {
  width: 100%;
  min-height: 262px;
  resize: vertical;
  padding: 18px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  font-size: 15.5px;
  line-height: 1.68;
  color: var(--color-text);
  outline: none;
}

.input-area__box:focus {
  border-color: var(--color-primary);
}

.input-area__box--error {
  border-color: #d8c9b8;
}

.input-area__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.char-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-faint);
  white-space: nowrap;
}

.char-count--over {
  color: var(--color-warn-text);
  font-weight: 600;
}

.link-button {
  align-self: flex-start;
  background: none;
  border: none;
  padding: 0;
  font-size: 13.5px;
  color: var(--color-primary);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.error-banner {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--color-warn-bg);
  border: 1px solid var(--color-warn-border);
}

.error-banner strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-warn-text);
  display: block;
}

.error-banner p {
  margin: 3px 0 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-warn-text-soft);
}

.error-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-warn-dot);
  margin-top: 7px;
  flex: 0 0 7px;
}

.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 2px;
}

.btn {
  padding: 13px 22px;
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.7;
  cursor: default;
}

.btn--primary {
  border: 1px solid var(--color-primary-border);
  background: var(--color-primary);
  color: var(--color-frame);
}

.btn--primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn--secondary {
  padding: 13px 20px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-frame);
  color: var(--color-text);
}

.btn--secondary:hover {
  background: var(--color-surface-soft);
}

.btn--ghost {
  padding: 8px 14px;
  border: 1px solid var(--color-border-strong);
  background: none;
  border-radius: 8px;
  font-size: 13.5px;
  color: var(--color-text);
  cursor: pointer;
}

.btn--ghost:hover {
  background: var(--color-surface-soft);
}

.results-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.results-header h2 {
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.015em;
  margin: 0 0 6px;
}

.results-header p {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.results-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.85fr) 1.15fr;
  gap: 20px;
  align-items: start;
}

@media (max-width: 720px) {
  .results-grid {
    grid-template-columns: 1fr;
  }
}

.original-panel {
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface-soft);
  padding: 18px;
}

/* Follows the scroll on desktop's two-column layout, stopping clear of the
   sticky app header (64px) - stays put while the longer analysis column
   scrolls past it. Mobile stacks the panels instead, so nothing sticks there. */
@media (min-width: 721px) {
  .original-panel {
    position: sticky;
    top: 80px;
    max-height: calc(100vh - 100px);
    overflow-y: auto;
  }
}

.findings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Serif, because it is a letter the reader is about to send, and seeing it
   set like one is what makes it feel finished rather than generated. */
.draft {
  margin: 0;
  padding: 0;
  font-family: var(--font-serif);
  font-size: 15.5px;
  line-height: 1.75;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--color-text);
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 11px;
  border-radius: 7px;
  border: 1px solid var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.copy-btn:hover {
  border-color: var(--color-primary-border);
}

.disclaimer {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-faint);
}

.notice {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  background: var(--color-surface-soft);
  border: 1px solid var(--color-border-soft);
}

.notice-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-text-faint);
  margin-top: 7px;
  flex: 0 0 7px;
}

.notice strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  display: block;
}

.notice span {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(58, 55, 51, 0.28);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 40;
}

.modal {
  width: 100%;
  max-width: 430px;
  background: var(--color-frame);
  border: 1px solid var(--color-border-strong);
  border-radius: 16px;
  padding: 26px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: 0 18px 44px rgba(58, 55, 51, 0.16);
}

.modal__title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal__title strong {
  font-family: var(--font-serif);
  font-size: 21px;
  font-weight: 500;
  color: var(--color-text);
}

.modal__dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--color-primary);
}

.modal__card {
  border: 1px solid var(--color-border-soft);
  border-radius: 12px;
  background: var(--color-surface-soft);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.modal__card strong {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.modal__card span {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.modal__note {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}
@media (max-width: 640px) {
  .reading__source { grid-template-columns: 1fr; gap: 0.15rem; }
}

/* Placeholder lines while the model is still working. */
.skeleton {
  height: 0.85rem; border-radius: 4px; width: 58%;
  margin: 0.55rem 0;
  background: linear-gradient(90deg,
    var(--color-surface-sunken, #f0ebe2) 25%,
    rgba(255, 255, 255, 0.55) 50%,
    var(--color-surface-sunken, #f0ebe2) 75%);
  background-size: 200% 100%;
  animation: skeleton-sweep 1.4s ease-in-out infinite;
}
.skeleton--wide { width: 100%; }
.skeleton:first-child { margin-top: 0; }
@keyframes skeleton-sweep {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; }
}

/* ==========================================================================
   Decode results
   --------------------------------------------------------------------------
   Editorial, not dashboard. The first pass at this looked like generated
   scaffolding - every section an identical bordered box with a numbered
   circle, uniform padding, pills everywhere - so it reads as a template
   rather than as something written for a person.

   What changed, and why:
   - Borders removed. Sections separate by space and a very soft shadow, so
     the page reads as paper rather than as a form. A 1px rule everywhere is
     what makes a layout feel machine-assembled.
   - Serif for anything that is prose - the message, the headings, the
     reading. Sans is kept for labels and controls. That split is what makes
     a page feel written instead of rendered.
   - The numbered circles became small quiet indices. Order is still there
     for anyone reading linearly; it no longer shouts.
   - Generous, uneven spacing. Equal gaps everywhere is the other tell.

   What did NOT change, because it is load-bearing for the people this page
   is for: nothing is hidden by default, colour never carries meaning alone,
   and --color-text-faint stays unused here - it measures 2.96:1 on this
   background, below the 4.5:1 AA wants, and small print is where a
   struggling reader can least afford it.
   ========================================================================== */

.findings {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* --- the message ---------------------------------------------------------- */

.original-panel {
  position: sticky;
  top: 16px;
  border: 0;
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  padding: 26px 26px 28px;
  box-shadow:
    0 1px 2px rgba(58, 55, 51, 0.04),
    0 14px 34px -18px rgba(58, 55, 51, 0.18);
}

.original-panel__label {
  margin: 0 0 14px;
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

/* Serif, and roomy. This is somebody's letter, and setting it like one is
   the difference between reading it and scanning it. */
.original-text {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 16.5px;
  line-height: 1.82;
  letter-spacing: -0.003em;
  white-space: pre-wrap;
  /* Token, not a literal. #453f38 was picked against the paper ground and
     measures 1.45:1 on the dark surface, where it is the message itself
     that disappears. */
  color: var(--color-text);
}

/* The payoff of the spans pipeline: point at a finding and the exact
   characters it came from light up here. Underlined as well as tinted so it
   survives greyscale and colourblindness. */
.original-text__hit {
  background: linear-gradient(0deg, #fbe9b0 0%, #fdf3d2 100%);
  color: #3d3a33;
  border-radius: 2px;
  box-shadow: 0 0 0 3px #fdf3d2;
  text-decoration: underline;
  text-decoration-color: #d9a93a;
  text-decoration-thickness: 2px;
  text-underline-offset: 3px;
}

/* --- register ------------------------------------------------------------- */
/* A caption, not a component. It is one short observation and boxing it made
   it look more certain than three small models deserve. */

.register {
  padding: 2px 2px 0;
}

.register__line {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 9px;
}

.register__lead {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.register__chip {
  font-family: var(--font-serif);
  font-size: 17px;
  font-style: italic;
  color: var(--color-primary-strong-text);
}

.register__chip + .register__chip::before {
  content: '·';
  margin-right: 9px;
  font-style: normal;
  color: var(--color-text-muted);
}

.register__chip--unsure {
  color: var(--color-text-muted);
}

.register__note {
  margin: 7px 0 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
  max-width: 54ch;
}

/* --- sections ------------------------------------------------------------- */

.card {
  border: 0;
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  overflow: hidden;
  box-shadow:
    0 1px 2px rgba(58, 55, 51, 0.04),
    0 14px 34px -20px rgba(58, 55, 51, 0.16);
}

.card--reply {
  background: linear-gradient(180deg, var(--color-primary-soft-bg) 0%, var(--color-surface) 88px);
}

.card__head {
  width: 100%;
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 20px 24px 14px;
  background: none;
  border: 0;
  font: inherit;
  text-align: left;
  cursor: pointer;
  color: var(--color-text);
}

.card__head--static { cursor: default; align-items: center; }

/* A quiet index rather than a badge - order without decoration. */
.card__index {
  flex: none;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  padding-top: 3px;
}

.card__title {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 500;
  letter-spacing: -0.012em;
  line-height: 1.3;
}

.card__status {
  margin-left: auto;
  font-size: 12.5px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.card__status--warn { color: var(--color-warn-text); }

.card__fold {
  flex: none;
  width: 18px;
  text-align: center;
  font-size: 13px;
  color: var(--color-text-muted);
  transition: color 0.15s ease;
}

button.card__head:hover .card__fold { color: var(--color-primary); }

.card__body { padding: 0 24px 22px; }
.card__body--flush { padding: 0 0 6px; }

.card__hint {
  margin: 0;
  padding: 12px 24px 6px;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.card__hint--top { padding: 0 24px 10px; }

/* The one-line answer to "what is this message actually asking of me", so it
   is set as prose and given room, not as a data field. */
.meaning {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 17px;
  line-height: 1.68;
  letter-spacing: -0.005em;
  color: var(--color-text);
  max-width: 62ch;
}

.muted-line {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
}

/* --- tick ----------------------------------------------------------------- */

.tick {
  flex: none;
  width: 18px;
  height: 18px;
  margin-top: 1px;
  border: 1.5px solid var(--color-border-strong);
  border-radius: 6px;
  background: var(--color-surface);
  position: relative;
  transition: background 0.14s ease, border-color 0.14s ease;
}

.tick--on { background: var(--color-primary); border-color: var(--color-primary); }

/* Drawn, not coloured: ticked vs unticked has to be a shape, or it vanishes
   in greyscale and at low contrast. */
.tick--on::after {
  content: '';
  position: absolute;
  left: 5.5px;
  top: 1.5px;
  width: 4px;
  height: 9px;
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

/* --- rows ----------------------------------------------------------------- */

.ask,
.gap {
  width: 100%;
  display: flex;
  gap: 13px;
  align-items: flex-start;
  padding: 13px 24px;
  background: none;
  border: 0;
  font: inherit;
  text-align: left;
  cursor: pointer;
  color: var(--color-text);
  transition: background 0.14s ease;
}

/* Hairlines inset from the edge, so the card still reads as one surface. */
.ask + .ask,
.gap + .gap {
  box-shadow: inset 0 1px 0 rgba(58, 55, 51, 0.07);
}

.ask:hover,
.gap:hover { background: rgba(79, 122, 105, 0.055); }

.ask:focus-visible,
.gap:focus-visible,
.fact:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: -3px;
  border-radius: 8px;
}

.ask__text,
.gap__text { display: flex; flex-direction: column; gap: 4px; }

.ask__main {
  font-size: 15px;
  line-height: 1.5;
  transition: color 0.14s ease;
}

/* Struck through as well as dimmed - "done" must survive greyscale, and
   dimming alone reads as "disabled" rather than "finished". */
.ask--done .ask__main {
  text-decoration: line-through;
  text-decoration-color: rgba(107, 98, 89, 0.5);
  color: var(--color-text-muted);
}

.ask__detail {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-muted);
}

.ask__reading,
.fact__reading {
  font-family: var(--font-serif);
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
  max-width: 58ch;
}

/* --- stated facts --------------------------------------------------------- */

.fact {
  display: grid;
  grid-template-columns: 104px 1fr;
  gap: 16px;
  padding: 13px 24px;
  transition: background 0.14s ease;
}

.fact + .fact { box-shadow: inset 0 1px 0 rgba(58, 55, 51, 0.07); }
.fact--live { cursor: default; }
.fact--live:hover { background: rgba(217, 169, 58, 0.09); }

.fact__label {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  padding-top: 4px;
}

.fact__body { display: flex; flex-direction: column; gap: 4px; }
.fact__value { font-size: 15px; line-height: 1.5; }

/* --- gaps ----------------------------------------------------------------- */

.gap__label { font-size: 15px; font-weight: 600; letter-spacing: -0.006em; }

.gap__q {
  font-family: var(--font-serif);
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
  max-width: 58ch;
}

.gap--on { background: rgba(79, 122, 105, 0.075); }
.gap--empty { cursor: default; font-size: 14.5px; color: var(--color-text-muted); }
.gap--empty:hover { background: none; }

/* --- reply ---------------------------------------------------------------- */

.tone-pick {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 16px;
  padding: 3px;
  border-radius: 999px;
  background: rgba(58, 55, 51, 0.055);
}

.tone-pick__lead {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  padding: 0 8px 0 10px;
}

.tone-pick__opt {
  font: inherit;
  font-size: 13px;
  padding: 5px 15px;
  border-radius: 999px;
  border: 0;
  background: none;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
}

.tone-pick__opt--on {
  background: var(--color-surface);
  color: var(--color-primary-strong-text);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(58, 55, 51, 0.14);
}

@media (max-width: 720px) {
  .original-panel { position: static; padding: 22px; }
}

@media (max-width: 640px) {
  .fact { grid-template-columns: 1fr; gap: 4px; }
  .card__head { padding: 18px 18px 12px; }
  .card__body { padding: 0 18px 18px; }
  .card__hint { padding: 12px 18px 6px; }
  .ask, .gap, .fact { padding-left: 18px; padding-right: 18px; }
}

@media (prefers-reduced-motion: reduce) {
  .ask, .gap, .fact, .tick, .tone-pick__opt, .card__fold, .ask__main {
    transition: none;
  }
}
</style>
