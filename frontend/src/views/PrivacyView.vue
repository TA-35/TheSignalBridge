<script setup lang="ts">
/**
 * Privacy policy.
 *
 * Every factual claim on this page was checked against the code before it was
 * written, because a privacy policy that overstates is worse than none:
 *
 *   "not logged"          - no logger call touches a message body in
 *                           backend/app/routes/*.py or the inference service.
 *   "no database"         - neither the decode nor the review route writes to
 *                           the database; the only persistence is the
 *                           browser's own localStorage.
 *   "sent to NVIDIA"      - Src/source/pipeline/config.py posts the message to
 *                           https://integrate.api.nvidia.com/v1. This is the
 *                           disclosure the page exists for. It is stated
 *                           plainly and early rather than buried, because it
 *                           is the part a reader would not guess.
 *   "no cookies"          - nothing sets document.cookie; there are no
 *                           analytics or advertising scripts on the site.
 *   "clear it yourself"   - SettingsView calls decodesStore.clear() and
 *                           cardsStore.clear().
 *   "no audio reaches us" - Dictate (components/VoiceInput.vue,
 *                           composables/useSpeechInput.ts) uses the browser's
 *                           Web Speech API; only the resulting text goes into
 *                           the message box, and nothing is sent until the
 *                           reader presses Decode or Compose.
 *
 * If any of those change, this page has to change with them.
 */
import { RouterLink } from 'vue-router'

// Set this before launch. Left visibly unset rather than filled with an
// address nobody reads - a contact route that silently goes nowhere is the
// one thing on this page that would be actively misleading.
const CONTACT = ''

const LAST_UPDATED = '6 October 2026'
</script>

<template>
  <div class="policy">
    <header class="policy__head">
      <h1>Privacy</h1>
      <p class="policy__lede">
        This page explains what happens to a message when you paste it into
        BetweenWords. The short version: it is analysed, it is never stored
        on our servers, and part of the analysis happens at NVIDIA.
      </p>
      <p class="policy__date">Last updated {{ LAST_UPDATED }}</p>
    </header>

    <section>
      <h2>What happens to a message you paste</h2>
      <p>
        When you decode a message, the text is sent to our API so it can be
        analysed. Two things then happen to it.
      </p>
      <p>
        First, it is read locally by a language-processing library that finds
        dates, names and requests in the text. Nothing leaves our servers for
        that part.
      </p>
      <p>
        Second, for the interpretation — the part headed “A closer reading” —
        the message is sent to
        <strong>NVIDIA’s AI service</strong> (<code>integrate.api.nvidia.com</code>),
        which is operated by NVIDIA in the United States. We do this because the
        model that produces the reading runs there and not on our servers. Your
        message is subject to NVIDIA’s own terms and privacy practices while it
        is with them.
      </p>
      <p class="policy__callout">
        If a message is confidential enough that sending it to a third-party AI
        provider would be a problem, do not paste it here.
      </p>
    </section>

    <section>
      <h2>Speaking instead of typing</h2>
      <p>
        The <strong>Dictate</strong> button under the message box uses your
        browser’s built-in speech recognition. Your browser turns what you say
        into text in the box, and you can read and correct it there. We never
        receive any audio. The text is only sent to us when you press Decode or
        Compose, exactly as if you had typed it.
      </p>
      <p>
        That speech recognition is run by your browser’s maker, not by us, and
        it may send the audio to their servers to recognise it. In Chrome, for
        example, it is processed by Google’s speech service. Their privacy
        terms apply to that audio. If you would rather nothing you say leaves
        your device, type instead.
      </p>
    </section>

    <section>
      <h2>What we do not do</h2>
      <ul>
        <li>We do not write your messages to any database.</li>
        <li>We do not log the text of your messages.</li>
        <li>We do not use cookies.</li>
        <li>We do not run analytics, tracking or advertising of any kind.</li>
        <li>We do not have user accounts, so nothing is tied to your identity.</li>
        <li>We do not sell or share anything with anyone beyond what is described above.</li>
      </ul>
    </section>

    <section>
      <h2>What is stored, and where</h2>
      <p>
        Your decode history, your study cards and your settings are saved in
        your own browser, using its local storage. They stay on the device you
        are using. They are not uploaded to us, they are not synced between your
        devices, and we cannot see them.
      </p>
      <p>
        Because decode history includes the messages you pasted, clearing it
        clears them. You can do that at any time from
        <RouterLink to="/settings">Settings</RouterLink>. Clearing your browser
        data for this site has the same effect.
      </p>
    </section>

    <section>
      <h2>Server logs</h2>
      <p>
        Our web server keeps ordinary access logs: the IP address a request came
        from, the time, and which address was requested. These do not contain
        message content. They exist so we can keep the service running and see
        when something is broken or being abused.
      </p>
    </section>

    <section>
      <h2>Who we are</h2>
      <p>
        BetweenWords is a student project built for FIT5120 at Monash
        University. It is not a commercial service, and it is not covered by a
        company’s support or retention commitments. Treat it accordingly.
      </p>
      <p v-if="CONTACT">
        Questions about this page, or about data you have put into the site:
        <a :href="`mailto:${CONTACT}`">{{ CONTACT }}</a>.
      </p>
      <p v-else>
        Questions about this page can be raised with the project team through
        the unit’s usual channels.
      </p>
    </section>

    <section>
      <h2>Changes</h2>
      <p>
        If what the site does with your messages changes, this page changes with
        it, and the date at the top moves.
      </p>
    </section>
  </div>
</template>

<style scoped>
.policy {
  max-width: 68ch;
  margin: 0 auto;
  padding: 8px 0 64px;
}

.policy__head {
  margin-bottom: 36px;
}

h1 {
  font-size: 30px;
  line-height: 1.2;
  margin: 0 0 14px;
  color: var(--color-text);
}

.policy__lede {
  font-size: 16px;
  line-height: 1.6;
  color: var(--color-text);
  margin: 0 0 12px;
}

.policy__date {
  /* --color-text-muted, not --color-text-faint: faint measures 2.96:1 on the
     light background, below the 4.5:1 WCAG AA needs for text this size. */
  font-size: 13px;
  color: var(--color-text-muted);
  margin: 0;
}

section {
  margin-bottom: 32px;
}

h2 {
  font-size: 18px;
  line-height: 1.3;
  margin: 0 0 12px;
  color: var(--color-text);
}

p {
  font-size: 15px;
  line-height: 1.65;
  margin: 0 0 12px;
  color: var(--color-text);
}

ul {
  margin: 0;
  padding-left: 20px;
}

li {
  font-size: 15px;
  line-height: 1.65;
  margin-bottom: 6px;
  color: var(--color-text);
}

code {
  font-family: var(--font-mono);
  font-size: 13.5px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--color-surface-soft);
  overflow-wrap: anywhere;
}

.policy__callout {
  padding: 14px 16px;
  border-left: 3px solid var(--color-primary);
  background: var(--color-primary-soft-bg);
  border-radius: 0 6px 6px 0;
  margin-top: 16px;
}

a {
  color: var(--color-primary-strong-text);
}

@media (max-width: 640px) {
  h1 { font-size: 25px; }
  .policy { padding-bottom: 40px; }
}
</style>
