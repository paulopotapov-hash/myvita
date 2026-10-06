import { readFileSync } from 'node:fs'
import path from 'node:path'
import { expect, request } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'

export const PASSWORD = 'SenhaForte123!'
export const AUTH_DIR = path.join(import.meta.dirname, '.auth')

export type Role = 'clinic_admin' | 'doctor' | 'nurse' | 'patient' | 'other_patient'

export interface Seed {
  clinicId: string
  emails: Record<Role, string>
  names: Record<Role, string>
  staffIds: { doctor: string; nurse: string }
  patientIds: { patient: string; other_patient: string }
}

export function authState(role: Role): string {
  return path.join(AUTH_DIR, `${role}.json`)
}

/** Swap the browser's cookies to a pre-seeded role without spending a login. */
export async function switchRole(context: BrowserContext, role: Role): Promise<void> {
  const state = JSON.parse(readFileSync(authState(role), 'utf-8')) as { cookies: Parameters<BrowserContext['addCookies']>[0] }
  await context.clearCookies()
  await context.addCookies(state.cookies)
}

export function loadSeed(): Seed {
  return JSON.parse(readFileSync(path.join(AUTH_DIR, 'seed.json'), 'utf-8')) as Seed
}

/** Local `YYYY-MM-DDTHH:mm` for a datetime-local input, `days` from today. */
export function futureSlot(days: number, hour = 9, minute = 0): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  date.setHours(hour, minute, 0, 0)
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export async function loginThroughUi(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Palavra-passe').fill(password)
  await page.getByRole('button', { name: 'Entrar' }).click()
}

export async function expectNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }))
  expect(overflow.scroll, `${label}: page is ${overflow.scroll}px wide in a ${overflow.client}px viewport`).toBeLessThanOrEqual(
    overflow.client,
  )
}

// Must match `baseURL` in playwright.config.ts (the Vite server that proxies /api to the real backend).
const FRONTEND_URL = 'http://localhost:5174'

/** Creates test data through the real API as an already-logged-in role (no UI login, no rate-limit cost). */
export async function apiAs<T = unknown>(
  role: Role,
  method: 'POST' | 'PATCH',
  url: string,
  data?: object,
  tolerate: number[] = [],
): Promise<T | null> {
  const context = await request.newContext({ baseURL: FRONTEND_URL, storageState: authState(role) })
  try {
    const { cookies } = await context.storageState()
    const csrf = cookies.find((cookie) => cookie.name === 'myvita_csrf')?.value ?? ''
    const response = await context.fetch(url, { method, data, headers: { 'X-CSRF-Token': csrf } })
    // Seeding is idempotent: a worker restart after a failure re-runs beforeAll hooks.
    if (tolerate.includes(response.status())) return null
    expect(response.ok(), `${method} ${url} -> ${response.status()} ${await response.text()}`).toBe(true)
    return (await response.json()) as T
  } finally {
    await context.dispose()
  }
}

export async function seedAppointment(days: number, reason: string, hour = 9): Promise<void> {
  const seed = loadSeed()
  await apiAs('doctor', 'POST', '/api/v1/appointments', {
    patient_id: seed.patientIds.patient,
    staff_id: seed.staffIds.doctor,
    scheduled_at: new Date(futureSlot(days, hour)).toISOString(),
    duration_minutes: 30,
    reason,
  }, [409])
}

/** A record, a medication and a consent on the patient file, so clinical screens have real content. */
export async function seedClinicalContent(tag: string): Promise<void> {
  const seed = loadSeed()
  const patientId = seed.patientIds.patient
  await apiAs('doctor', 'POST', `/api/v1/patients/${patientId}/medical-records`, {
    title: `Registo ${tag}`,
    content: 'Conteúdo clínico de teste com texto suficientemente longo para testar a quebra de linha em ecrãs pequenos.',
  })
  await apiAs('doctor', 'POST', `/api/v1/patients/${patientId}/medications`, {
    name: `Medicamento ${tag}`,
    dosage: '500 mg',
    route: 'oral',
    frequency: '8/8h',
    instructions: 'Instruções de teste com texto longo para verificar a quebra de linha em ecrãs pequenos.',
    start_date: '2026-01-15',
  })
  await apiAs('patient', 'POST', `/api/v1/patients/${patientId}/consents`, {
    consent_type: 'communications',
    purpose: `Finalidade ${tag}`,
  }, [409])
}

/** Elements that stick out of the viewport and are not inside a deliberately scrollable container. */
export async function findOverflowingElements(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const limit = document.documentElement.clientWidth
    const scrollable = (element: Element | null): boolean => {
      for (let node = element; node && node !== document.body; node = node.parentElement) {
        const { overflowX } = getComputedStyle(node)
        if (overflowX === 'auto' || overflowX === 'scroll') return true
      }
      return false
    }
    const found: string[] = []
    for (const element of document.body.querySelectorAll('*')) {
      const box = element.getBoundingClientRect()
      if (box.width === 0 || box.height === 0) continue
      if (getComputedStyle(element).position === 'fixed') continue
      if (box.right > limit + 1 && !scrollable(element.parentElement)) {
        const label = element.getAttribute('aria-label') ?? element.textContent?.trim().slice(0, 30) ?? ''
        found.push(`<${element.tagName.toLowerCase()}> "${label}" right=${Math.round(box.right)} > ${limit}`)
      }
    }
    return found.slice(0, 8)
  })
}

export async function expectViewportOverflowDetectorWorks(page: Page): Promise<void> {
  await page.setContent('<div style="width:3000px">wide</div>')
  expect((await findOverflowingElements(page)).length).toBeGreaterThan(0)
}
