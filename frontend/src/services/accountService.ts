// Accounts, held by a passkey. The browser does the cryptography; this file
// only moves bytes between it and the API.
//
// Every call sends `credentials: 'include'`, because the session lives in an
// HttpOnly cookie rather than a token this code could hold. Script on the
// page cannot read that cookie, which is the point - but it does mean the
// fetch has to opt in, and the API has to answer with
// Access-Control-Allow-Credentials (it does; see backend/app/__init__.py).

const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined

export interface Account {
  handle: string
  created_at: string | null
}

// Thrown when the person cancelled the system prompt, or the device has no
// authenticator to offer. Not a fault, so the UI says nothing alarming.
export class PasskeyCancelled extends Error {
  constructor() {
    super('Passkey prompt was dismissed.')
    this.name = 'PasskeyCancelled'
  }
}

export class AccountError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AccountError'
  }
}

/** Whether this browser can do passkeys at all. */
export function passkeysAvailable(): boolean {
  return typeof window !== 'undefined' && !!window.PublicKeyCredential
}

// WebAuthn speaks ArrayBuffers; JSON does not. Both sides of the wire use
// base64url, which is the encoding the spec itself uses for these fields.
function toBuffer(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/')
  const binary = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4))
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes.buffer
}

function toBase64url(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

async function call(path: string, init: RequestInit = {}): Promise<Response> {
  if (!API_BASE) throw new AccountError('Accounts need the API, which is not configured here.')
  return fetch(`${API_BASE}/api/account${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

async function errorFrom(response: Response, fallback: string): Promise<AccountError> {
  const body = (await response.json().catch(() => ({}))) as { error?: string }
  if (body.error) return new AccountError(body.error)
  // No JSON body means the API never reached the route - a 404 from a
  // backend that has not been restarted, or a 500 from a missing table.
  // Carrying the status through is the difference between "it did nothing"
  // and a fault someone can act on.
  return new AccountError(`${fallback} (HTTP ${response.status})`)
}

/** The signed-in account, or null. Never throws on "nobody is signed in". */
export async function currentAccount(): Promise<Account | null> {
  if (!API_BASE) return null
  try {
    const response = await call('/me', { method: 'GET' })
    if (!response.ok) return null
    return (await response.json()) as Account
  } catch {
    // Offline, or the API is down. Signed out is the safe reading: the rest
    // of the app works without an account anyway.
    return null
  }
}

export async function createAccount(): Promise<Account> {
  const optionsResponse = await call('/register/options', { method: 'POST' })
  if (!optionsResponse.ok) throw await errorFrom(optionsResponse, 'Could not start sign-up.')
  const options = await optionsResponse.json()

  let credential: PublicKeyCredential | null
  try {
    credential = (await navigator.credentials.create({
      publicKey: {
        ...options,
        challenge: toBuffer(options.challenge),
        user: { ...options.user, id: toBuffer(options.user.id) },
        excludeCredentials: (options.excludeCredentials ?? []).map(
          (c: { id: string; type: string; transports?: string[] }) => ({
            ...c,
            id: toBuffer(c.id),
          }),
        ),
      },
    })) as PublicKeyCredential | null
  } catch {
    throw new PasskeyCancelled()
  }
  if (!credential) throw new PasskeyCancelled()

  const attestation = credential.response as AuthenticatorAttestationResponse
  const verifyResponse = await call('/register/verify', {
    method: 'POST',
    body: JSON.stringify({
      id: credential.id,
      rawId: toBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: toBase64url(attestation.clientDataJSON),
        attestationObject: toBase64url(attestation.attestationObject),
      },
    }),
  })
  if (!verifyResponse.ok) throw await errorFrom(verifyResponse, 'That passkey could not be saved.')
  return (await verifyResponse.json()) as Account
}

export async function signIn(): Promise<Account> {
  const optionsResponse = await call('/login/options', { method: 'POST' })
  if (!optionsResponse.ok) throw await errorFrom(optionsResponse, 'Could not start sign-in.')
  const options = await optionsResponse.json()

  let credential: PublicKeyCredential | null
  try {
    credential = (await navigator.credentials.get({
      publicKey: {
        ...options,
        challenge: toBuffer(options.challenge),
        // No allowCredentials: the passkey is discoverable, so the browser
        // offers whichever accounts it holds for this site and nobody has
        // to remember a handle.
        allowCredentials: [],
      },
    })) as PublicKeyCredential | null
  } catch {
    throw new PasskeyCancelled()
  }
  if (!credential) throw new PasskeyCancelled()

  const assertion = credential.response as AuthenticatorAssertionResponse
  const verifyResponse = await call('/login/verify', {
    method: 'POST',
    body: JSON.stringify({
      id: credential.id,
      rawId: toBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: toBase64url(assertion.clientDataJSON),
        authenticatorData: toBase64url(assertion.authenticatorData),
        signature: toBase64url(assertion.signature),
        userHandle: assertion.userHandle ? toBase64url(assertion.userHandle) : null,
      },
    }),
  })
  if (!verifyResponse.ok) throw await errorFrom(verifyResponse, 'That passkey could not be verified.')
  return (await verifyResponse.json()) as Account
}

export interface PairingCode {
  code: string
  handle: string
  expires_in_minutes: number
}

/** Asked for on a device that is already signed in. */
export async function createPairingCode(): Promise<PairingCode> {
  const response = await call('/pairing', { method: 'POST' })
  if (!response.ok) throw await errorFrom(response, 'Could not create a code.')
  return (await response.json()) as PairingCode
}

/**
 * The new device's half. The code buys one thing - permission to create a
 * passkey here - so this registers that passkey immediately and signs in
 * with it. From the next visit on, this device needs no code.
 */
export async function pairWithCode(handle: string, code: string): Promise<Account> {
  const claimResponse = await call('/pairing/claim', {
    method: 'POST',
    body: JSON.stringify({ handle, code }),
  })
  if (!claimResponse.ok) throw await errorFrom(claimResponse, 'That code is not valid.')
  const options = await claimResponse.json()

  let credential: PublicKeyCredential | null
  try {
    credential = (await navigator.credentials.create({
      publicKey: {
        ...options,
        challenge: toBuffer(options.challenge),
        user: { ...options.user, id: toBuffer(options.user.id) },
        excludeCredentials: (options.excludeCredentials ?? []).map(
          (c: { id: string; type: string }) => ({ ...c, id: toBuffer(c.id) }),
        ),
      },
    })) as PublicKeyCredential | null
  } catch {
    throw new PasskeyCancelled()
  }
  if (!credential) throw new PasskeyCancelled()

  const attestation = credential.response as AuthenticatorAttestationResponse
  const verifyResponse = await call('/pairing/verify', {
    method: 'POST',
    body: JSON.stringify({
      id: credential.id,
      rawId: toBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: toBase64url(attestation.clientDataJSON),
        attestationObject: toBase64url(attestation.attestationObject),
      },
    }),
  })
  if (!verifyResponse.ok) throw await errorFrom(verifyResponse, 'That passkey could not be saved.')
  return (await verifyResponse.json()) as Account
}

export async function signOut(): Promise<void> {
  await call('/logout', { method: 'POST' })
}

export async function deleteAccount(): Promise<void> {
  const response = await call('', { method: 'DELETE' })
  if (!response.ok) throw await errorFrom(response, 'Could not delete the account.')
}
