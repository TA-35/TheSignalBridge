<script setup lang="ts">
// The other direction from Decode. You paste a message you have already
// written; it comes back saying the same thing more explicitly, with a short
// account of what changed.
//
// What this page deliberately does NOT do: pick a tone. The rewrite keeps
// the register of the draft - the classifiers tell the model what that
// register is, and the eval penalises a rewrite whose politeness drops. A
// tone selector here would promise something the model is not trained to do.
import { computed, reactive, ref } from 'vue'
import { Check, ChevronDown, Clock, Lightbulb } from '@lucide/vue'
import {
  composeMessage,
  EmptyMessageError,
  MAX_MESSAGE_LENGTH,
  MessageTooLongError,
} from '@/services/composeService'
import {
  failedFactCheck,
  isAlreadyClear,
  type ComposeQuick,
  type ComposeResult,
} from '@/types/compose'
import VoiceInput from '@/components/VoiceInput.vue'
import MissingCheck from '@/components/MissingCheck.vue'
import RewriteFeedback from '@/components/RewriteFeedback.vue'
import { clearHabits, habitSummary, MIN_DRAFTS, readHabits, recordDraft } from '@/utils/draftHabits'
import { applyAnswers, findMissing, type Answer, type MissingKey } from '@/utils/missing'

const SAMPLE =
  "Hi,\n\nWhen you get a chance, could you take a look at the Q3 deck and tighten up the numbers section? Would be great to have it before the leadership sync.\n\nThanks!"

const state = reactive({
  message: '',
  error: '',
  errorTitle: '',
  loading: false,
  quick: null as ComposeQuick | null,
  result: null as ComposeResult | null,
})

const alreadyClear = computed(() => !!state.result && isAlreadyClear(state.result))

// Urgency rides beside the version switch rather than waiting inside the
// breakdown: it is the one field that changes what the reader does next.
const URGENCY_WORDS: Record<string, string> = {
  high: 'High urgency',
  medium: 'Medium urgency',
  low: 'Low urgency',
}
const urgency = computed(() => URGENCY_WORDS[state.result?.meaning.urgency ?? ''] ?? '')

/** The five fields the model reports, in a fixed order, empty ones dropped. */
const meaningRows = computed(() => {
  const meaning = state.result?.meaning
  if (!meaning) return []
  return [
    { label: 'The ask', value: meaning.ask },
    { label: 'By when', value: meaning.deadline },
    { label: 'How urgent', value: meaning.urgency },
    { label: 'Reads as', value: meaning.tone },
    { label: 'Left unsaid', value: meaning.implied },
  ].filter((row) => !!row.value)
})

// What the draft leaves a literal reader to guess (utils/missing.ts). A
// question once answered isn't asked again for the draft the answer went
// into, even where the words that raised it are still there - "no rush"
// stays in the draft after "This is urgent." is added.
const answered = ref<{ draft: string; keys: Set<MissingKey> }>({ draft: '', keys: new Set() })
const missingItems = computed(() => {
  const r = state.result
  if (!r?.rewrite) return []
  const skip = state.message === answered.value.draft ? answered.value.keys : new Set<MissingKey>()
  return findMissing(state.message, r.meaning, r.notes).filter((item) => !skip.has(item.key))
})

// The 👍/👎 card starts fresh for every answer, even a second rewrite of the
// same draft, and says whether the sender's answers above went into it.
const answerCount = ref(0)
const afterCard = computed(() => state.message === answered.value.draft && answered.value.keys.size > 0)

// What the writer's own drafts tend to leave out (utils/draftHabits.ts):
// counted once per draft, in this browser only, as gap kinds and a day. Not
// again for the version their answers made, nor for the same text composed
// twice - the text it compares against is held in memory here, never stored.
const habits = ref(readHabits())
const habitView = computed(() => habitSummary(habits.value))
let lastCounted = ''
const HABIT_LINE: Record<MissingKey, string> = {
  when: 'No deadline',
  who: 'No one named to do it',
  what: 'A vague ask, like “take a look”',
  urgency: 'Unclear urgency, like “no rush”',
}
const HABIT_TIP: Record<MissingKey, string> = {
  when: 'Add a day and time, such as “by 3pm Friday”.',
  who: 'Name the person: “Sam, can you…” rather than “can someone…”.',
  what: 'Say the action you want: “check the totals match” rather than “take a look”.',
  urgency: 'Say how much it matters: “I need it by Friday” or “only if you have time”.',
}
function countDraft(text: string, result: ComposeResult) {
  if (!result.rewrite || text === lastCounted || state.message === answered.value.draft) return
  lastCounted = text
  // A draft that asks for nothing (a thank-you, an update) leaves nothing out.
  const gaps = result.meaning.ask.trim() ? findMissing(state.message, result.meaning, result.notes).map((i) => i.key) : []
  habits.value = recordDraft(gaps)
}
function forgetHabits() {
  clearHabits()
  habits.value = []
}

function addMissing(answers: Partial<Record<MissingKey, Answer>>) {
  const earlier = state.message === answered.value.draft ? answered.value.keys : new Set<MissingKey>()
  state.message = applyAnswers(state.message, missingItems.value, answers)
  answered.value = { draft: state.message, keys: new Set([...earlier, ...(Object.keys(answers) as MissingKey[])]) }
  editing.value = false
  shown.value = 'rewrite'
  void rewrite()
}

async function rewrite() {
  const text = state.message.trim()
  state.error = ''
  state.errorTitle = ''
  state.quick = null
  state.result = null
  state.loading = true

  try {
    state.result = await composeMessage(text, (quick) => {
      state.quick = quick
    })
    answerCount.value++
    countDraft(text, state.result)
  } catch (err) {
    if (err instanceof EmptyMessageError) {
      state.errorTitle = 'Nothing to rewrite yet'
      state.error = 'Paste the message you are about to send and we will go through it.'
    } else if (err instanceof MessageTooLongError) {
      state.errorTitle = 'That message is too long'
      state.error = err.message
    } else {
      state.errorTitle = 'Something went wrong'
      state.error = 'Try again in a moment.'
    }
  } finally {
    state.loading = false
  }
}

function loadSample() {
  state.message = SAMPLE
  state.error = ''
}

function startOver() {
  state.message = ''
  state.result = null
  state.quick = null
  state.error = ''
  state.errorTitle = ''
}

function editDraft() {
  state.result = null
  state.quick = null
}

// Which version the single panel shows. One panel with a switch rather than
// two side by side: the question is which one to send, not how they differ
// word by word.
const shown = ref<'rewrite' | 'original'>('rewrite')

// The rewrite is a starting point, not a verdict - editing it here means the
// copy button hands over what the sender actually wants to send.
const editing = ref(false)
const edited = ref('')

const rewriteText = computed(() => (editing.value ? edited.value : state.result?.rewrite ?? ''))

function toggleEditing() {
  if (!editing.value) {
    edited.value = state.result?.rewrite ?? ''
    shown.value = 'rewrite'
  }
  editing.value = !editing.value
}

// Closed by default: the breakdown is what you open when something in the
// rewrite looks wrong, and noise when it doesn't.
const breakdownOpen = ref(false)

const copyState = ref<'idle' | 'copied' | 'failed'>('idle')
let copyResetTimer: ReturnType<typeof setTimeout> | undefined

async function copyText(text: string) {
  if (!text) return
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

const copyRewrite = () => copyText(rewriteText.value)
</script>

<template>
  <div class="compose">
    <!-- Intake ------------------------------------------------------- -->
    <template v-if="!state.result">
      <div class="intro">
        <h1>Make your message clear</h1>
        <p>
          Paste a message you're about to send. 
          We'll rewrite it so it's harder to misread.
        </p>
      </div>

      <div class="panes">
        <div class="pane">
          <div class="pane__head">
            <span class="pane__label">Your draft</span>
            <span
              class="char-count"
              :class="{ 'char-count--over': state.message.length > MAX_MESSAGE_LENGTH }"
            >
              {{ state.message.length }} / {{ MAX_MESSAGE_LENGTH }}
            </span>
          </div>

          <textarea
            id="compose-draft"
            v-model="state.message"
            class="draft-box"
            :class="{ 'draft-box--error': !!state.error }"
            placeholder="Hi, when you get a chance, could you take a look at…"
            spellcheck="false"
            :aria-invalid="!!state.error"
            :aria-describedby="state.error ? 'compose-error' : undefined"
          />

          <VoiceInput v-model="state.message" :max-length="MAX_MESSAGE_LENGTH" />

          <div v-if="state.error" id="compose-error" class="error-banner" role="alert">
            <span class="error-dot" />
            <div>
              <strong>{{ state.errorTitle }}</strong>
              <p>{{ state.error }}</p>
            </div>
          </div>

          <div class="pane__foot">
            <button type="button" class="link-button" @click="loadSample">Use a sample message</button>
            <div class="pane__buttons">
              <button type="button" class="btn btn--secondary" @click="startOver">Clear</button>
              <button type="button" class="btn btn--primary" :disabled="state.loading" @click="rewrite">
                {{ state.loading ? 'Rewriting...' : 'Compose' }}
              </button>
            </div>
          </div>
        </div>

        <aside class="pane pane--preview">
          <span class="preview__mark" aria-hidden="true">
            <Lightbulb :size="22" :stroke-width="1.6" />
          </span>
          <h2 class="preview__title">What comes back</h2>
          <p class="preview__note">
            1. We find hints, hedges and hidden deadlines in your message.
          </p>
          <p class="preview__note">
            2. We rewrite it so the ask and the timing are stated plainly.
          </p>
          <p class="preview__note">
            3. You see what changed and why, then copy it or keep your original.
          </p>

          <!-- The writer's own habits, once there are enough drafts to show one -->
          <section v-if="habitView.drafts >= MIN_DRAFTS" class="habits" aria-labelledby="habits-title">
            <h3 id="habits-title" class="habits__title">Your last {{ habitView.drafts }} drafts</h3>
            <ul v-if="habitView.counts.length" class="habits__list">
              <li v-for="c in habitView.counts" :key="c.key">
                {{ HABIT_LINE[c.key] }}: <strong>{{ c.count }} of {{ habitView.drafts }}</strong>
              </li>
            </ul>
            <p v-else class="habits__note">Every one said when, who, what exactly and how urgent.</p>
            <p v-if="habitView.counts.length" class="habits__tip">{{ HABIT_TIP[habitView.counts[0]!.key] }}</p>
            <p class="habits__foot">
              Counted in this browser only, never your words.
              <button type="button" class="link-button" @click="forgetHabits">Clear counts</button>
            </p>
          </section>
        </aside>
      </div>
    </template>

    <!-- Result ------------------------------------------------------- -->
    <template v-else>
      <!-- Already clear. The verdict comes first: presenting an unchanged
           message under "here is your rewrite" reads as a tool that did
           nothing at all. -->
      <template v-if="alreadyClear">
        <div class="verdict">
          <span class="verdict__mark" aria-hidden="true"><Check :size="18" :stroke-width="2.2" /></span>
          <div>
            <h1>Your message is already clear</h1>
            <p>
              We didn't find any hints, hedges or hidden deadlines to spell out. It's ready to send
              as it is.
            </p>
          </div>
        </div>

        <div class="layout">
          <div class="layout__main">
            <section class="card">
              <p class="card__eyebrow">Your message, unchanged</p>
              <p class="message">{{ state.message }}</p>
            </section>

            <section class="card card--reason">
              <span class="reason__mark" aria-hidden="true"><Check :size="14" :stroke-width="2.2" /></span>
              <div>
                <strong>Why nothing changed</strong>
                <p>{{ state.result.notes[0] }}</p>
              </div>
            </section>

            <MissingCheck v-if="missingItems.length" :items="missingItems" @add="addMissing" />

            <RewriteFeedback
              :key="answerCount"
              :model="state.result.model ?? 'unknown'"
              :kept-as-written="true"
              :after-card="afterCard"
            />
          </div>

          <aside class="actions-panel">
            <h2 class="actions-panel__title">Actions</h2>
            <button type="button" class="btn btn--primary" @click="copyText(state.message)">
              {{ copyState === 'copied' ? 'Copied' : 'Copy message' }}
            </button>
            <hr class="actions-panel__rule" />
            <p class="actions-panel__note">Want to check another message?</p>
            <button type="button" class="text-link" @click="startOver">Start over</button>
          </aside>
        </div>
      </template>

      <!-- Nothing safe to show: the grounding check rejected the rewrite, or
           the service could not be reached. A flagged rewrite is never
           rendered - it reads as finished text and would be sent as-is. -->
      <template v-else-if="!state.result.rewrite">
        <h1 class="page-title">No rewrite this time</h1>

        <div class="layout">
          <div class="layout__main">
            <section class="card card--blocked">
              <strong>
                {{
                  failedFactCheck(state.result)
                    ? "The rewrite didn't pass our fact check, so we're not showing it."
                    : "The rewriter couldn't be reached."
                }}
              </strong>
              <p>
                A rewrite that drops or invents a detail is worse than none, so you get your own
                words back rather than something you would have to check line by line.
              </p>
            </section>

            <section class="card">
              <p class="card__eyebrow">Your message, unchanged</p>
              <p class="message">{{ state.message }}</p>
            </section>
          </div>

          <aside class="actions-panel">
            <h2 class="actions-panel__title">Actions</h2>
            <button type="button" class="btn btn--primary" @click="copyText(state.message)">
              {{ copyState === 'copied' ? 'Copied' : 'Copy my message' }}
            </button>
            <button type="button" class="btn btn--secondary" @click="editDraft">Edit draft</button>
            <hr class="actions-panel__rule" />
            <button type="button" class="text-link" @click="startOver">Start over</button>
          </aside>
        </div>
      </template>

      <!-- Rewritten -->
      <template v-else>
        <h1 class="page-title">Here's your clearer message</h1>

        <div class="switch-row">
          <div class="switch" role="tablist" aria-label="Which version to show">
            <button
              type="button"
              role="tab"
              class="switch__tab"
              :class="{ 'switch__tab--on': shown === 'rewrite' }"
              :aria-selected="shown === 'rewrite'"
              @click="shown = 'rewrite'"
            >
              Clearer version
            </button>
            <button
              type="button"
              role="tab"
              class="switch__tab"
              :class="{ 'switch__tab--on': shown === 'original' }"
              :aria-selected="shown === 'original'"
              @click="shown = 'original'; editing = false"
            >
              Your original
            </button>
          </div>

          <!-- The one field that changes what the reader does next, so it
               sits in the open rather than inside the breakdown. -->
          <span v-if="urgency" class="urgency">
            <Clock :size="13" :stroke-width="2" aria-hidden="true" />
            {{ urgency }}
          </span>
        </div>

        <div class="layout">
          <div class="layout__main">
            <section class="card card--message">
              <textarea
                v-if="editing"
                id="compose-edit"
                v-model="edited"
                class="edit-box"
                aria-label="Edit the clearer version"
              />
              <p v-else class="message">
                {{ shown === 'rewrite' ? state.result.rewrite : state.message }}
              </p>
            </section>

            <MissingCheck v-if="missingItems.length" :items="missingItems" @add="addMissing" />

            <section v-if="state.result.notes.length && shown === 'rewrite'" class="card">
              <h2 class="card__title">What changed and why</h2>
              <ol class="notes">
                <li v-for="(note, i) in state.result.notes" :key="i">
                  <span class="notes__num" aria-hidden="true">{{ i + 1 }}</span>
                  <span>{{ note }}</span>
                </li>
              </ol>
            </section>

            <RewriteFeedback
              :key="answerCount"
              :model="state.result.model ?? 'unknown'"
              :kept-as-written="false"
              :after-card="afterCard"
            />

            <!-- Folded away: useful when something in the rewrite looks
                 wrong, noise when it doesn't. -->
            <section v-if="meaningRows.length" class="card card--fold">
              <button
                type="button"
                class="fold"
                :aria-expanded="breakdownOpen"
                aria-controls="compose-breakdown"
                @click="breakdownOpen = !breakdownOpen"
              >
                <span class="card__title">Your message, broken down</span>
                <ChevronDown
                  class="fold__caret"
                  :class="{ 'fold__caret--open': breakdownOpen }"
                  :size="18"
                  :stroke-width="2"
                  aria-hidden="true"
                />
              </button>

              <div v-show="breakdownOpen" id="compose-breakdown">
                <dl class="meaning">
                  <div v-for="row in meaningRows" :key="row.label" class="meaning__row">
                    <dt>{{ row.label }}</dt>
                    <dd>{{ row.value }}</dd>
                  </div>
                </dl>
                <p class="card__hint">
                  Read from your draft, not added to it. If something here is wrong, the message
                  probably says it less clearly than you meant.
                </p>
              </div>
            </section>

            <!-- Phone only: the side panel becomes a bar of the two buttons
                 you actually press, so these two keep a home in the page. -->
            <div class="inline-links">
              <button type="button" class="text-link" @click="editDraft">Keep my original instead</button>
              <button type="button" class="text-link" @click="startOver">Start over</button>
            </div>

            <p class="footnote">Nothing is sent from here. Copy it when you're ready.</p>
          </div>

          <aside class="actions-panel">
            <h2 class="actions-panel__title">Actions</h2>
            <button type="button" class="btn btn--primary" @click="copyRewrite">
              {{ copyState === 'copied' ? 'Copied' : 'Copy clearer version' }}
            </button>
            <button type="button" class="btn btn--secondary" @click="toggleEditing">
              {{ editing ? 'Done editing' : 'Edit clearer version' }}
            </button>
            <button type="button" class="text-link panel-only" @click="editDraft">Keep my original</button>
            <hr class="actions-panel__rule panel-only" />
            <p class="actions-panel__note panel-only">Want to try a different message?</p>
            <button type="button" class="text-link panel-only" @click="startOver">Start over</button>
          </aside>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.compose {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1240px;
}

.intro {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 60ch;
}

.intro h1 {
  font-family: var(--font-serif);
  font-size: clamp(32px, 4.4vw, 46px);
  font-weight: 500;
  line-height: 1.08;
  letter-spacing: -0.025em;
  margin: 0;
  text-wrap: balance;
}

.intro p {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.panes {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
}

@media (min-width: 1040px) {
  .panes {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-frame);
}

.pane__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.pane__label {
  font-size: 14.5px;
  font-weight: 600;
}

.draft-box {
  width: 100%;
  flex: 1;
  min-height: 300px;
  resize: vertical;
  padding: 16px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  font-size: 15.5px;
  line-height: 1.68;
  color: var(--color-text);
}

.draft-box::placeholder {
  color: var(--color-text-muted);
  opacity: 1;
}

.draft-box:focus {
  outline: none;
  border-color: var(--color-primary);
}

.draft-box--error,
.draft-box--error:focus {
  border-color: var(--color-danger-text);
}


.pane__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.pane__buttons {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pane--preview {
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  padding: 32px 28px;
  border: 3px dashed var(--color-border-muted, #667168);
  background: var(--color-primary-soft-bg,  #FAFAF9);
}

.preview__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: var(--color-surface);
  color: var(--color-primary);
  margin-bottom: 4px;
}

.btn {
  padding: 13px 22px;
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
}

.preview__title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 500;
  letter-spacing: -0.012em;
}

.preview__note {
  margin: 0;
  max-width: 38ch;
  text-align: left;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

/* The writer's own habits, under the three steps in the same panel. */
.habits {
  display: grid;
  gap: 8px;
  width: 100%;
  max-width: 38ch;
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
  text-align: left;
}

.habits__title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 500;
  color: var(--color-text);
}

.habits__list {
  display: grid;
  gap: 4px;
  margin: 0;
  padding-left: 18px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--color-text);
}

.habits__note,
.habits__tip {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: var(--color-text);
}

.habits__foot {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.char-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.char-count--over {
  color: var(--color-warn-text);
  font-weight: 600;
}

.link-button {
  padding: 8px 0;
  margin: -8px 0;
  border: none;
  background: none;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--color-primary-strong-text);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.error-banner {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--color-warn-border);
  background: var(--color-warn-bg);
}

.error-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-warn-dot);
  margin-top: 7px;
  flex: none;
}

.error-banner strong {
  display: block;
  font-size: 14px;
  color: var(--color-warn-text);
}

.error-banner p {
  margin: 3px 0 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-warn-text-soft);
}

.page-title,
.verdict h1 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: clamp(27px, 3.4vw, 36px);
  font-weight: 500;
  line-height: 1.14;
  letter-spacing: -0.022em;
  text-wrap: balance;
}

/* "Nothing to do" leads with a mark rather than a card, so the verdict is
   readable before anything else on the screen. */
.verdict {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.verdict p {
  margin: 8px 0 0;
  max-width: 54ch;
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.verdict__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 38px;
  height: 38px;
  margin-top: 2px;
  border-radius: 999px;
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

/* Message on the left, the things you can do with it on the right. */
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

@media (min-width: 900px) {
  .layout {
    grid-template-columns: minmax(0, 1fr) 282px;
    gap: 28px;
  }
}

.layout__main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.switch {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border-radius: 10px;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface-soft);
}

.switch__tab {
  padding: 8px 16px;
  border: none;
  border-radius: 7px;
  background: none;
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--color-text-muted);
  cursor: pointer;
}

.switch__tab--on {
  background: var(--color-surface);
  color: var(--color-text);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(58, 55, 51, 0.08);
}

.urgency {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  background: var(--color-warn-bg);
  color: var(--color-warn-text);
  font-size: 12.5px;
  font-weight: 600;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 22px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.card--message {
  min-height: 170px;
}

.card--fold {
  padding: 8px 22px 10px;
}

.card__eyebrow {
  margin: 0;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-faint);
}

.card__title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 500;
  color: var(--color-text);
}

/* Serif at reading size: this is the text someone is about to send, not a
   data field. */
.message {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 16px;
  line-height: 1.72;
  white-space: pre-wrap;
  color: var(--color-text);
}

.edit-box {
  width: 100%;
  min-height: 150px;
  resize: vertical;
  padding: 0;
  border: none;
  background: none;
  font-family: var(--font-serif);
  font-size: 16px;
  line-height: 1.72;
  color: var(--color-text);
}

.card--reason {
  flex-direction: row;
  align-items: flex-start;
  gap: 12px;
}

.card--reason strong {
  display: block;
  margin-bottom: 2px;
  font-size: 14.5px;
}

.card--reason p {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.reason__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

.card--blocked {
  border-color: var(--color-warn-border);
  background: var(--color-warn-bg);
}

.card--blocked strong {
  font-size: 14.5px;
  color: var(--color-warn-text);
}

.card--blocked p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-warn-text-soft);
}

.fold {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 12px 0;
  border: none;
  background: none;
  text-align: left;
  cursor: pointer;
}

.fold__caret {
  color: var(--color-text-muted);
  transition: transform 160ms ease;
}

.fold__caret--open {
  transform: rotate(180deg);
}

@media (prefers-reduced-motion: reduce) {
  .fold__caret {
    transition: none;
  }
}

/* Numbered because the notes are a sequence of edits, not a set of tips. */
.notes {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.notes li {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  font-size: 14px;
  line-height: 1.55;
  color: var(--color-text);
}

.notes__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 22px;
  height: 22px;
  margin-top: 1px;
  border-radius: 999px;
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
  font-size: 11.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.meaning {
  margin: 0;
  display: flex;
  flex-direction: column;
}

.meaning__row {
  display: grid;
  grid-template-columns: 130px minmax(0, 1fr);
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--color-border-soft);
}

.meaning dt {
  font-size: 13px;
  color: var(--color-text-faint);
}

.meaning dd {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: var(--color-text);
}

.card__hint {
  margin: 10px 0 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-faint);
}

.footnote {
  margin: 0;
  font-size: 12.5px;
  color: var(--color-text-faint);
}

.actions-panel {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
  padding: 20px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.actions-panel__title {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.actions-panel .btn {
  width: 100%;
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 600;
}

.actions-panel__rule {
  margin: 6px 0 2px;
  border: none;
  border-top: 1px solid var(--color-border-soft);
}

.actions-panel__note {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}

.text-link {
  align-self: center;
  padding: 4px 0;
  border: none;
  background: none;
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-primary-strong-text);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* The two links that live in the side panel on a laptop. On a phone the
   panel becomes a bar of the two buttons you actually press, and these
   move into the page instead - see below. */
.inline-links {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

@media (min-width: 900px) {
  .inline-links {
    display: none;
  }
}

/* Phone: the actions panel stops being a column beside the message and
   becomes a bar pinned to the bottom, holding only Edit and Copy. Pinned
   because the message and its notes are longer than a phone screen, and
   the thing you came to do should not be at the end of a scroll. */
@media (max-width: 899px) {
  .panel-only {
    display: none;
  }

  .actions-panel {
    position: sticky;
    bottom: 0;
    z-index: 10;
    flex-direction: row-reverse;
    gap: 10px;
    margin: 4px -16px -8px;
    padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px));
    border: none;
    border-top: 1px solid var(--color-border);
    border-radius: 0;
    background: var(--color-frame);
  }

  .actions-panel__title {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .actions-panel .btn {
    flex: 1;
  }

  /* Copy is the primary action and sits on the right, so row-reverse puts
     it first in the DOM for a screen reader and last on screen. */
  .actions-panel .btn--secondary {
    flex: 0 0 38%;
  }

  .verdict__mark {
    width: 32px;
    height: 32px;
  }

  .card {
    padding: 18px;
  }
}
</style>
