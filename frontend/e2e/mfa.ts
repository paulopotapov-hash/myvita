import { createHmac } from 'node:crypto'

// The specs' authenticator app: RFC 6238 TOTP with backend/app/core/mfa.py's parameters (SHA-1,
// 6 digits, 30 s). Secrets come from the real enrolment response or screen and stay in memory only.
const PERIOD_SECONDS = 30
const BASE32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'

function base32Decode(input: string): Buffer {
  const bytes: number[] = []
  let buffer = 0
  let bits = 0
  for (const char of input.replace(/[\s=]/g, '').toUpperCase()) {
    const value = BASE32.indexOf(char)
    if (value < 0) throw new Error('Invalid base32 secret')
    buffer = (buffer << 5) | value
    bits += 5
    if (bits >= 8) {
      bits -= 8
      bytes.push((buffer >> bits) & 0xff)
    }
  }
  return Buffer.from(bytes)
}

export function totp(secret: string, step: number): string {
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(step))
  const digest = createHmac('sha1', base32Decode(secret)).update(counter).digest()
  const offset = digest[digest.length - 1] & 0x0f
  const value = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000
  return value.toString().padStart(6, '0')
}

const lastStep = new Map<string, number>()

/** The next code the backend will accept for this secret. Each step is accepted once and the
 * backend allows one step of drift, so this uses the current or the next step and otherwise
 * waits for a fresh one, exactly like a person waiting for the app to show a new code. */
export async function nextTotp(secret: string): Promise<string> {
  for (;;) {
    const now = Math.floor(Date.now() / 1000 / PERIOD_SECONDS)
    const step = Math.max(now, (lastStep.get(secret) ?? -1) + 1)
    if (step <= now + 1) {
      lastStep.set(secret, step)
      return totp(secret, step)
    }
    await new Promise((resolve) => setTimeout(resolve, (now + 1) * PERIOD_SECONDS * 1000 - Date.now() + 250))
  }
}

// Login and second-factor verification share one per-IP rate limit (10/min). Specs running in the
// same worker draw from this one budget (6/min) so they never trip it for each other.
const loginStamps: number[] = []
export async function throttleLogin(): Promise<void> {
  for (;;) {
    const now = Date.now()
    while (loginStamps.length && now - loginStamps[0] > 60_000) loginStamps.shift()
    if (loginStamps.length < 6) {
      loginStamps.push(now)
      return
    }
    await new Promise((resolve) => setTimeout(resolve, loginStamps[0] + 60_500 - now))
  }
}

/** The base32 secret inside an otpauth:// URI. */
export function secretFromOtpauth(uri: string): string {
  const secret = new URL(uri).searchParams.get('secret')
  if (!secret) throw new Error('otpauth URI without a secret')
  return secret
}
