<script setup lang="ts">
// "Dictate" under a message box: speech becomes text in the box, where the
// reader can read and fix it before anything is sent. Used by Decode and
// Compose. Renders nothing in browsers without speech recognition.
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Mic, Square } from '@lucide/vue'
import { useSpeechInput } from '@/composables/useSpeechInput'

const props = defineProps<{ maxLength: number }>()
const message = defineModel<string>({ required: true })

const limitHit = ref(false)

function append(text: string) {
  if (!text) return
  const current = message.value
  const joined = current && !/\s$/.test(current) ? `${current} ${text}` : current + text
  if (joined.length > props.maxLength) {
    message.value = joined.slice(0, props.maxLength)
    limitHit.value = true
    speech.stop()
    return
  }
  message.value = joined
}

const speech = useSpeechInput(append)

function toggle() {
  limitHit.value = false
  speech.toggle()
}

// Long dictation would push the status line onto several rows; the last few
// words are enough to show it is hearing you.
const heard = computed(() => {
  const words = speech.interim.value.split(/\s+/).filter(Boolean)
  return (words.length > 8 ? '… ' : '') + words.slice(-8).join(' ')
})
</script>

<template>
  <div v-if="speech.supported" class="voice">
    <button
      type="button"
      class="btn voice__button"
      :class="speech.listening.value ? 'btn--primary' : 'btn--secondary'"
      :aria-pressed="speech.listening.value"
      @click="toggle"
    >
      <span v-if="speech.listening.value" class="voice__dot" aria-hidden="true" />
      <component :is="speech.listening.value ? Square : Mic" :size="15" :stroke-width="1.8" aria-hidden="true" />
      {{ speech.listening.value ? 'Stop' : 'Dictate' }}
    </button>

    <p class="voice__status" aria-live="polite">
      <template v-if="speech.error.value">
        <span class="voice__error">{{ speech.error.value }}</span>
      </template>
      <template v-else-if="limitHit">Stopped at the {{ maxLength }}-character limit.</template>
      <template v-else-if="speech.listening.value">
        <span v-if="heard" class="voice__heard">“{{ heard }}”</span>
        <span v-else>Listening. Speak your message, then press Stop.</span>
        <span class="voice__note">
          Your browser’s speech service turns this into text.
          <RouterLink to="/privacy">How this works</RouterLink>
        </span>
      </template>
    </p>
  </div>
</template>

<style scoped>
.voice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.voice__button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  font-size: 14px;
  flex-shrink: 0;
}

/* A recording light, so "listening" reads at a glance and not only from the
   label. Still, not pulsing, for readers who asked for reduced motion. */
.voice__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  /* The button's own text colour, so it shows on the primary fill in every
     theme without a colour of its own to keep in step. */
  background: currentColor;
  animation: voice-pulse 1.2s ease-in-out infinite;
}

@keyframes voice-pulse {
  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .voice__dot {
    animation: none;
  }
}

.voice__status {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1 1 220px;
  margin: 0;
  padding-top: 8px;
  font-size: 13.5px;
  color: var(--color-text-muted);
}

.voice__status:empty {
  display: none;
}

.voice__heard {
  color: var(--color-text);
  overflow-wrap: anywhere;
}

.voice__note {
  font-size: 12.5px;
  color: var(--color-text-faint);
}

.voice__note a {
  color: var(--color-primary-strong-text);
  text-underline-offset: 3px;
}

.voice__error {
  color: var(--color-danger-text);
}
</style>
