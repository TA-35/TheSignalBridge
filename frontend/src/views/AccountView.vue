<script setup lang="ts">
// One door for both sign-in and sign-up. Nobody arriving here knows which
// they need - they know they want their cards on this device - so the page
// answers "what is this for" first and offers both actions together.
//
// The account is genuinely optional, and the page says so rather than
// implying the site is gated. Everything works signed out.
import { onMounted, ref, watch } from 'vue'
import { KeyRound, Library, Smartphone } from '@lucide/vue'
import { useAccountStore } from '@/stores/account'

const accountStore = useAccountStore()

// Shown once, right after the handle is minted. Signing in never needs it -
// the browser offers the account by itself - but it is what identifies this
// account to a person, so it gets one clear moment on screen.
const justCreated = ref(false)

// The "this device doesn't know me yet" path. Hidden until asked for: most
// people signing in are on a device that already holds their passkey, and
// offering a code field first would suggest typing something is the norm.
const showPairing = ref(false)
const pairHandle = ref('')
const pairCode = ref('')

// Deleting the account. Moved here from Settings so everything an account
// can do lives in one place.
const showDelete = ref(false)

async function confirmDelete() {
  await accountStore.remove()
  showDelete.value = false
}

onMounted(() => {
  if (!accountStore.ready) void accountStore.refresh()
})

// Signing out should not leave the "you just made this" banner behind.
watch(
  () => accountStore.signedIn,
  (signedIn) => {
    if (!signedIn) justCreated.value = false
  },
)

async function create() {
  await accountStore.create()
  justCreated.value = accountStore.signedIn
}

async function pair() {
  await accountStore.pair(pairHandle.value, pairCode.value)
  if (accountStore.signedIn) {
    pairHandle.value = ''
    pairCode.value = ''
    showPairing.value = false
  }
}
</script>

<template>
  <div class="login">
    <header class="intro">
      <h1>Account settings</h1>
    </header>

    <p v-if="!accountStore.ready" class="pending">Checking whether you're signed in…</p>

    <!-- Signed in ------------------------------------------------------- -->
    <section v-else-if="accountStore.signedIn" class="panel">
      
      <p v-if="justCreated" class="flash">
        Account created.
      </p>

      <p class="id-label">Your ID</p>
      <p class="id-code">{{ accountStore.account?.handle }}</p>

      <!-- A passkey cannot be copied, so a second device gets its own. This
           is the device that authorises that. -->
      <div class="pairing">
        <h2>Use a second device</h2>
        <p class="panel__body">
          Your passkey only works in the browser that made it. To sign in somewhere else, get a
          code here and enter it there. That device then makes its own passkey and needs no code
          again.
        </p>

        <template v-if="accountStore.pairing">
          <p class="code">{{ accountStore.pairing.code }}</p>
          <p class="code-note">
            Enter your ID <strong>{{ accountStore.pairing.handle }}</strong> and this code on the
            other device, under &ldquo;this device doesn't know me yet&rdquo;. It lasts
            {{ accountStore.pairing.expires_in_minutes }} minutes and works once.
          </p>
        </template>

        <button
          type="button"
          class="btn btn--secondary"
          :disabled="accountStore.busy"
          @click="accountStore.requestPairingCode"
        >
          {{ accountStore.busy ? 'Working…' : accountStore.pairing ? 'Get a new code' : 'Get a pairing code' }}
        </button>

        <!-- Was missing: without it a failed request looked like a button
             that does nothing at all. -->
        <p v-if="accountStore.error" class="error" role="alert">{{ accountStore.error }}</p>
      </div>

      <!-- Kept at the bottom, behind a confirmation, and never in the
           header menu: it is one click from losing the account, and the
           menu is somewhere people click quickly. -->
      <div class="danger">
        <h2>Delete this account</h2>
        <p class="panel__body">
          Removes your ID and every passkey registered to it. Your saved cards stay in this
          browser. They were never uploaded. It can't be undone.
        </p>
        <button type="button" class="btn btn--danger" :disabled="accountStore.busy" @click="showDelete = true">
          Delete my account
        </button>
      </div>
    </section>
    

    <!-- No passkey support ---------------------------------------------- -->
    <section v-else-if="!accountStore.supported" class="panel">
      <h2>This browser can't do passkeys</h2>
      <p class="panel__body">
        Accounts need a browser that supports passkeys: a recent version of Chrome, Safari, Edge or
        Firefox. Nothing else on the site is affected: your cards and settings are
        stored in this browser either way.
      </p>
      <div class="actions">
        <RouterLink to="/decode" class="btn btn--primary">Decode a message</RouterLink>
      </div>
    </section>

    <!-- Signed out ------------------------------------------------------ -->
    <section v-else class="panel">
      <h2>Sign in with passkey, or create a new account</h2>
      <p class="panel__body">
        Either way, your device proves it's you, with a fingerprint, your face, or the
        screen lock you already use.
      </p>

      <div class="actions">
        <button type="button" class="btn btn--primary" :disabled="accountStore.busy" @click="accountStore.login">
          {{ accountStore.busy ? 'Waiting for your device…' : 'Sign in with a passkey' }}
        </button>
        <button type="button" class="btn btn--secondary" :disabled="accountStore.busy" @click="create">
          Create an account
        </button>
      </div>

      <p v-if="accountStore.error" class="error" role="alert">{{ accountStore.error }}</p>

      <!-- The fallback, folded away. Someone whose passkey is on this
           device never needs it, and a visible code field would imply
           typing something is the normal way in. -->
      <div class="fallback">
        <h2>Sign in from a new device without a passkey?</h2>
        <button
          v-if="!showPairing"
          type="button"
          class="link-button"
          @click="showPairing = true"
        >
          This device doesn't know me yet
        </button>

        <form v-else class="pair-form" @submit.prevent="pair">
          <p class="panel__body">
            On a device you're already signed in on, open this page and choose
            <strong>Get a pairing code</strong>. Then enter your ID and that code here.
          </p>

          <div class="fields">
            <label class="field field--short">
              <span>Your ID</span>
              <input
                id="pair-handle"
                v-model="pairHandle"
                type="text"
                inputmode="text"
                autocapitalize="characters"
                autocomplete="off"
                spellcheck="false"
                maxlength="4"
                placeholder="7KQ2"
              />
            </label>
            <label class="field">
              <span>Pairing code</span>
              <input
                id="pair-code"
                v-model="pairCode"
                type="text"
                inputmode="text"
                autocapitalize="characters"
                autocomplete="off"
                spellcheck="false"
                maxlength="6"
                placeholder="4F7K2Q"
              />
            </label>
          </div>

          <div class="actions">
            <button
              type="submit"
              class="btn btn--primary"
              :disabled="accountStore.busy || !pairHandle.trim() || !pairCode.trim()"
            >
              {{ accountStore.busy ? 'Waiting for your device…' : 'Pair this device' }}
            </button>
            <button type="button" class="btn btn--secondary" @click="showPairing = false">
              Cancel
            </button>
          </div>
        </form>
      </div>

      <ul class="points">
        <h2>Why create an account?</h2>
        <li>
          <span class="points__mark" aria-hidden="true"><KeyRound :size="16" :stroke-width="1.8" /></span>
          <span>
            <strong>No password. </strong>
            Your device keeps the key and we keep only the public half of it, so there is nothing
            here worth stealing.
          </span>
        </li>
        <li>
          <span class="points__mark" aria-hidden="true"><Library :size="16" :stroke-width="1.8" /></span>
          <span>
            <strong>Your progress on any device. </strong>
            Saved library cards and progress follow you when you sign in elsewhere. Cards saved
            from a message stay on the device that made them, and we never save the text of your
            messages on our server.
          </span>
        </li>
        <li>
          <span class="points__mark" aria-hidden="true"><Smartphone :size="16" :stroke-width="1.8" /></span>
          <span>
            <strong>One browser to start.</strong>
            A passkey lives in the password manager that made it, so a second browser needs its
            own. Signing in offers "use another device" if your phone holds one.
          </span>
        </li>
      </ul>
    </section>

    <div v-if="showDelete" class="modal-backdrop" @click="showDelete = false">
      <div
        class="modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-title"
        aria-describedby="delete-body"
        tabindex="-1"
        @click.stop
        @keydown.esc="showDelete = false"
      >
        <strong id="delete-title">Delete account {{ accountStore.account?.handle }}?</strong>
        <p id="delete-body">
          Your ID and its passkeys are removed for good. Saved cards stay in this browser. This
          can't be undone.
        </p>
        <div class="modal-actions">
          <button type="button" class="btn btn--danger-solid" :disabled="accountStore.busy" @click="confirmDelete">
            Delete account
          </button>
          <button type="button" class="btn btn--secondary" @click="showDelete = false">Keep it</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login {
  max-width: 560px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.intro h1 {
  margin: 0 0 8px;
  font-family: var(--font-serif);
  font-size: clamp(27px, 3.4vw, 34px);
  font-weight: 500;
  line-height: 1.15;
  letter-spacing: -0.02em;
  text-wrap: balance;
}

.intro p {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.65;
  color: var(--color-text-muted);
}

.pending {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 24px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}

.panel h2 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 500;
  letter-spacing: -0.01em;
}

.panel__body {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.flash {
  margin: 0;
  padding: 9px 13px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
  font-size: 13.5px;
  font-weight: 600;
}

.id-label {
  margin: 0;
  font-size: 12.5px;
  color: var(--color-text-faint);
}

/* The one thing on this page worth setting large: four characters a person
   may have to read out, remember, or write down. */
.id-code {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 34px;
  font-weight: 600;
  letter-spacing: 0.16em;
  line-height: 1.1;
  color: var(--color-text);
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-primary-border);
  flex: none;
}

.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 2px;
}

.actions .btn {
  padding: 12px 18px;
  font-size: 14px;
}

.error {
  margin: 0;
  font-size: 13.5px;
  color: var(--color-danger-text);
}

.points {
  list-style: none;
  margin: 4px 0 0;
  padding: 16px 0 0;
  border-top: 1px solid var(--color-border-soft);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.points li {
  display: flex;
  gap: 11px;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.points strong {
  color: var(--color-text);
  font-weight: 600;
}

.danger {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  margin-top: 4px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border-soft);
}

.danger h2 {
  font-size: 17px;
}

.danger .btn {
  padding: 10px 16px;
  font-size: 13.5px;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(58, 55, 51, 0.28);
}

.modal {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 26px;
  border: 1px solid var(--color-border-strong);
  border-radius: 16px;
  background: var(--color-frame);
  box-shadow: 0 18px 44px rgba(58, 55, 51, 0.16);
}

.modal strong {
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 500;
}

.modal p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.modal-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.modal-actions .btn {
  padding: 11px 16px;
  font-size: 13.5px;
}

.pairing,
.fallback {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  margin-top: 4px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border-soft);
}

.pairing h2 {
  font-size: 17px;
}

/* Read aloud, or copied across by hand onto a phone - so it is set large,
   spaced, and in the face where 0 and O cannot be confused. */
.code {
  margin: 0;
  padding: 10px 16px;
  border: 1px dashed var(--color-primary-soft-border);
  border-radius: var(--radius-sm);
  background: var(--color-primary-soft-bg);
  font-family: var(--font-mono);
  font-size: 28px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--color-primary-strong-text);
}

.code-note {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.code-note strong {
  font-family: var(--font-mono);
  letter-spacing: 0.08em;
  color: var(--color-text);
}

.link-button {
  padding: 0;
  border: none;
  background: none;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-primary-strong-text);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.pair-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
}

.fields {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: 1;
  min-width: 150px;
  font-size: 12.5px;
  color: var(--color-text-muted);
}

.field--short {
  flex: 0 0 110px;
  min-width: 110px;
}

.field input {
  padding: 11px 13px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  font-family: var(--font-mono);
  font-size: 16px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--color-text);
  outline: none;
}

.field input:focus {
  border-color: var(--color-primary);
}

.points__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--color-primary-soft-bg);
  color: var(--color-primary);
}
</style>
