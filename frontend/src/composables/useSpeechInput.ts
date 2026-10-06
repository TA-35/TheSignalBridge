// Speech to text through the browser's own Web Speech API.
//
// No audio reaches our servers. The browser's speech service turns speech
// into text (in Chrome that service is Google's, in Safari Apple's), and the
// text only goes anywhere when the reader presses Decode or Compose - the
// same as if they had typed it. PrivacyView says so; keep the two in step.
//
// Firefox has no implementation, so `supported` is false there and the mic
// button is not rendered at all rather than offered and then failing.
import { onScopeDispose, ref } from 'vue'

// TypeScript's DOM lib ships the event types but not the recognizer itself.
interface Recognizer extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  abort(): void
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null
  onend: (() => void) | null
}
type RecognizerCtor = new () => Recognizer

function recognizerCtor(): RecognizerCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as { SpeechRecognition?: RecognizerCtor; webkitSpeechRecognition?: RecognizerCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

// The rewriter is English-only, so recognise English. Keep the reader's own
// English variant when they have one - an Australian accent is recognised
// better as en-AU than as en-US.
function recognitionLang(): string {
  const lang = typeof navigator === 'undefined' ? '' : navigator.language
  return lang.toLowerCase().startsWith('en') ? lang : 'en-AU'
}

const ERROR_MESSAGES: Record<string, string> = {
  'not-allowed': 'Microphone access is blocked. Allow it in your browser’s site settings to dictate.',
  'service-not-allowed': 'Your browser’s speech service is turned off, so dictation is not available.',
  'audio-capture': 'No microphone was found.',
  'no-speech': 'Didn’t catch anything. Try again a little closer to the microphone.',
  network: 'Dictation needs an internet connection in this browser.',
  'language-not-supported': 'Your browser can’t recognise English speech here.',
}

export function useSpeechInput(onFinalText: (text: string) => void) {
  const Ctor = recognizerCtor()
  const supported = Ctor !== null
  const listening = ref(false)
  const interim = ref('')
  const error = ref('')
  let recognizer: Recognizer | null = null

  function start() {
    if (!Ctor || listening.value) return
    error.value = ''
    interim.value = ''
    const r = new Ctor()
    r.lang = recognitionLang()
    r.continuous = true
    r.interimResults = true

    r.onresult = (event) => {
      let pending = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (!result?.[0]) continue
        if (result.isFinal) onFinalText(result[0].transcript.trim())
        else pending += result[0].transcript
      }
      interim.value = pending.trim()
    }
    r.onerror = (event) => {
      // "aborted" is our own stop(); not something to show the reader.
      if (event.error !== 'aborted') error.value = ERROR_MESSAGES[event.error] ?? 'Dictation stopped unexpectedly.'
    }
    r.onend = () => {
      listening.value = false
      interim.value = ''
      recognizer = null
    }

    recognizer = r
    listening.value = true
    try {
      r.start()
    } catch {
      // start() throws if the browser is already capturing for another tab.
      listening.value = false
      recognizer = null
      error.value = 'Dictation could not start. Close other tabs using the microphone and try again.'
    }
  }

  function stop() {
    recognizer?.stop()
  }

  function toggle() {
    if (listening.value) stop()
    else start()
  }

  // Leaving the page must release the microphone.
  onScopeDispose(() => recognizer?.abort())

  return { supported, listening, interim, error, start, stop, toggle }
}
