import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  type Account,
  type PairingCode,
  createAccount,
  createPairingCode,
  currentAccount,
  deleteAccount,
  pairWithCode,
  passkeysAvailable,
  PasskeyCancelled,
  signIn,
  signOut,
} from '@/services/accountService'
import { useActivityStore } from '@/stores/activity'

// Who is signed in, if anyone. Deliberately thin: an account changes what
// the app can REMEMBER, never what it can do. Every page works signed out,
// and nothing here gates a feature.
export const useAccountStore = defineStore('account', () => {
  const account = ref<Account | null>(null)
  const busy = ref(false)
  const error = ref('')
  // Until the first /me answers, "signed out" would be a guess - the pages
  // that show account state wait for this rather than flashing the wrong one.
  const ready = ref(false)

  const signedIn = computed(() => account.value !== null)
  const supported = computed(() => passkeysAvailable())

  async function refresh() {
    account.value = await currentAccount()
    ready.value = true
  }

  // One wrapper for the three actions that talk to an authenticator: they
  // share the same busy flag, the same error handling, and the same rule
  // that a dismissed prompt is not a failure worth reporting.
  async function run(action: () => Promise<Account | null>) {
    busy.value = true
    error.value = ''
    try {
      account.value = await action()
    } catch (err) {
      if (!(err instanceof PasskeyCancelled)) {
        error.value = err instanceof Error ? err.message : 'Something went wrong.'
      }
    } finally {
      busy.value = false
    }
  }

  const create = () => run(createAccount)
  const login = () => run(signIn)

  // The code shown on the device that is already signed in. Held in memory
  // only - the server stores a hash and cannot show it again.
  const pairing = ref<PairingCode | null>(null)

  async function requestPairingCode() {
    busy.value = true
    error.value = ''
    try {
      pairing.value = await createPairingCode()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Could not create a code.'
    } finally {
      busy.value = false
    }
  }

  const pair = (handle: string, code: string) =>
    run(() => pairWithCode(handle.trim().toUpperCase(), code.trim().toUpperCase()))

  // Sign-out clears this browser's progress, so it saves it to the account
  // first. If the account can't confirm the save (offline, or the session
  // ran out), nothing happens and the caller gets 'unsaved' to ask the
  // person; `discard` is their answer to sign out anyway. `stillWanted` is
  // asked once the save is done: the person may have chosen to stay signed
  // in while it was on the wire. The sign-out request after that can't be
  // called back, and `busy` is true while it runs.
  const logout = async (
    discard = false,
    stillWanted: () => boolean = () => true,
  ): Promise<'signedOut' | 'unsaved' | 'failed' | 'cancelled'> => {
    const activity = useActivityStore()
    if (account.value && !discard && !(await activity.saveToAccount())) return 'unsaved'
    if (!stillWanted()) return 'cancelled'
    // A change made during the sign-out request below can't be saved once it
    // finishes; the page only allows that by clicking in the same instant.
    await run(async () => {
      await signOut()
      pairing.value = null
      return null
    })
    if (account.value) return 'failed' // `error` says why
    // Signing in merged the account's days, views and reviews into this
    // browser. Left behind, the next account to sign in here would upload them
    // as its own. Only once the sign-out has gone through: while still signed
    // in, clearAll() deletes the account's own copy as well.
    activity.clearAll()
    return 'signedOut'
  }

  const remove = () =>
    run(async () => {
      await deleteAccount()
      return null
    })

  return {
    account,
    busy,
    error,
    ready,
    signedIn,
    supported,
    pairing,
    refresh,
    create,
    login,
    logout,
    remove,
    requestPairingCode,
    pair,
  }
})
