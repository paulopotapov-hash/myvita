// Pilot UAT against a deployed stack with the synthetic seed (backend/scripts/seed_staging.py).
//   E2E_BASE_URL=https://staging.example SEED_PASSWORD=... npx playwright test e2e/uat.spec.ts
// One test per UAT scenario ID (see docs/pilot/UAT_SCENARIOS.md). Synthetic data only.
import AxeBuilder from '@axe-core/playwright'
import { expect, request, test, type APIRequestContext, type Page } from '@playwright/test'
import { nextTotp, throttleLogin } from './mfa'

const BASE = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:18083'
const PW = process.env.SEED_PASSWORD ?? ''
const DOMAIN = process.env.EMAIL_DOMAIN ?? 'staging.example'
const RUN = Date.now().toString(36)
const email = (name: string) => `${name}@${DOMAIN}`

// The login endpoint is rate limited per IP (10/min); every login and second-factor check goes
// through one budget shared with the other specs in this worker (e2e/mfa.ts).
const throttle = throttleLogin

type Reply = { status: number; body: any; headers: Record<string, string>; text: string }

// Where staff MFA is required (production settings), each staff account enrols through the real
// API on first use and the harness then acts as its authenticator app. Memory only, never logged.
const mfaSecrets = new Map<string, string>()

class Api {
  readonly ctx: APIRequestContext
  readonly mail: string
  readonly relogin: boolean
  // Explicit fields: tsconfig.e2e.json enables erasableSyntaxOnly (no parameter properties).
  private constructor(ctx: APIRequestContext, mail: string, relogin: boolean) {
    this.ctx = ctx
    this.mail = mail
    this.relogin = relogin
  }
  static async as(mail: string, relogin = true) {
    const api = new Api(await request.newContext({ baseURL: BASE }), mail, relogin)
    const reply = await api.login()
    expect(reply.status, `login ${mail}: ${reply.text}`).toBe(200)
    await api.completeAccountSetup()
    return api
  }
  async login(password = PW): Promise<Reply> {
    const reply = await this.limited('/api/v1/auth/login', async () => ({ email: this.mail, password }))
    // A second factor is required: answer the challenge with the enrolled authenticator.
    const secret = mfaSecrets.get(this.mail)
    if (reply.status !== 202 || !reply.body?.mfa_required || !secret) return reply
    return this.limited('/api/v1/auth/mfa/verify', async () => ({ code: await nextTotp(secret) }))
  }
  // Login and second-factor verification share the per-IP login rate limit. The body is built
  // after waiting for the budget, so a TOTP code is never stale when it is sent.
  private async limited(path: string, body: () => Promise<unknown>): Promise<Reply> {
    for (let attempt = 0; ; attempt++) {
      await throttle()
      const reply = await this.raw('POST', path, await body(), false)
      // Another process (or an earlier run) may share the per-IP budget: wait out the window once or twice.
      if (reply.status !== 429 || attempt >= 4) return reply
      await new Promise((resolve) => setTimeout(resolve, 61_000))
    }
  }
  /** Does what the merged security model (Parent A) requires before an account can work, through
   * the real API: the first-login password change for staff created by an administrator (here, by
   * the staging seed), then MFA enrolment where MFA is required for staff. A no-op otherwise. */
  async completeAccountSetup() {
    let me = (await this.get('/api/v1/auth/me')).body
    if (me.must_change_password) {
      // Seed password → temporary → seed password (only "different from the current one" is enforced),
      // so every later login keeps using SEED_PASSWORD.
      const temporary = `${PW}-first-login`
      for (const [current, next] of [[PW, temporary], [temporary, PW]]) {
        const changed = await this.post('/api/v1/auth/change-password', { current_password: current, new_password: next })
        expect(changed.status, `first-login password change ${this.mail}: ${changed.text}`).toBe(204)
      }
      me = (await this.get('/api/v1/auth/me')).body
    }
    if (me.pending_action === 'mfa_setup') {
      const setup = await this.post('/api/v1/auth/mfa/setup')
      expect(setup.status, `MFA setup ${this.mail}: ${setup.text}`).toBe(200)
      const enabled = await this.post('/api/v1/auth/mfa/enable', { code: await nextTotp(setup.body.secret) })
      expect(enabled.status, `MFA enable ${this.mail}: ${enabled.text}`).toBe(200)
      expect(enabled.body.recovery_codes.length).toBeGreaterThan(0)
      mfaSecrets.set(this.mail, setup.body.secret)
      me = (await this.get('/api/v1/auth/me')).body
    }
    expect(me.pending_action ?? null, `account ${this.mail} still has a pending action`).toBeNull()
  }
  async csrf() {
    return (await this.ctx.storageState()).cookies.find((c) => c.name === 'myvita_csrf')?.value
  }
  async raw(method: string, path: string, data?: unknown, csrf: boolean | string = true, headers: Record<string, string> = {}): Promise<Reply> {
    const sent = { ...headers }
    if (typeof csrf === 'string') sent['x-csrf-token'] = csrf
    else if (csrf && method !== 'GET') {
      const token = await this.csrf()
      if (token) sent['x-csrf-token'] = token
    }
    const response = await this.ctx.fetch(path, { method, data, headers: sent })
    const text = await response.text()
    let body: any = null
    try {
      body = JSON.parse(text)
    } catch {
      /* non-JSON */
    }
    return { status: response.status(), body, headers: response.headers(), text }
  }
  async send(method: string, path: string, data?: unknown, csrf: boolean | string = true) {
    let reply = await this.raw(method, path, data, csrf)
    if (reply.status === 401 && this.relogin) {
      expect((await this.login()).status).toBe(200)
      reply = await this.raw(method, path, data, csrf)
    }
    return reply
  }
  get = (path: string) => this.send('GET', path)
  post = (path: string, data?: unknown) => this.send('POST', path, data)
  patch = (path: string, data?: unknown) => this.send('PATCH', path, data)
}

async function uiLogin(page: Page, mail: string, password = PW, expectFailure = false) {
  await throttle()
  await page.goto('/login')
  await page.getByLabel('Email').fill(mail)
  await page.getByLabel('Palavra-passe').fill(password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  const secret = mfaSecrets.get(mail)
  if (secret && !expectFailure) {
    // Staff with MFA: the merged login page asks for the second factor before any session exists.
    await expect(page.getByRole('heading', { name: 'Verificação em dois passos' })).toBeVisible()
    await throttle()
    await page.getByLabel('Código de verificação').fill(await nextTotp(secret))
    await page.getByRole('button', { name: 'Verificar' }).click()
  }
  if (!expectFailure) await expect(page).toHaveURL(/\/(app|patient)(\/|$)/)
}

let slotCounter = 0
const slot = () => new Date(Date.UTC(2043, 0, 1) + ((Date.now() % 1_000_000) * 7 + slotCounter++) * 3_600_000).toISOString()

test.use({ baseURL: BASE, viewport: { width: 1280, height: 800 } })
test.describe.configure({ mode: 'serial' })

const world: Record<string, any> = {}

test.beforeAll(async () => {
  test.setTimeout(240_000)
  expect(PW, 'SEED_PASSWORD is required').not.toBe('')
  const names = ['admin-a', 'doctor-a', 'nurse-a', 'patient-a', 'admin-b', 'doctor-b', 'patient-b']
  // Api.as completes each account's mandatory setup (first-login password change, MFA enrolment
  // where required) through the real API before the scenarios start. No bypass.
  for (const name of names) world[name] = await Api.as(email(name))
  for (const name of names) world[`${name}-me`] = (await world[name].get('/api/v1/auth/me')).body
  const staffA = (await world['admin-a'].get('/api/v1/staff')).body
  world.doctorAStaffId = staffA.find((s: any) => s.full_name.startsWith('Doctor A')).id
  world.nurseAStaffId = staffA.find((s: any) => s.full_name.startsWith('Nurse A')).id
  world.doctorBStaffId = (await world['admin-b'].get('/api/v1/staff')).body.find((s: any) => s.full_name.startsWith('Doctor B')).id

  // Onboard extra synthetic users through the real invitation flow (public registration is disabled).
  async function invite(kind: 'staff' | 'patients', name: string, extra: object = {}) {
    const mail = email(`${name.toLowerCase().replace(/\s+/g, '-')}-${RUN}`)
    const created = await world['admin-a'].post(`/api/v1/invitations/${kind}`, { email: mail, full_name: name, ...extra })
    expect(created.status, created.text).toBe(201)
    const anon = await request.newContext({ baseURL: BASE })
    const accepted = await anon.post('/api/v1/invitations/accept', { data: { token: created.body.token, password: PW } })
    expect(accepted.status(), await accepted.text()).toBe(200)
    await anon.dispose()
    return mail
  }
  world.adminStaffMail = await invite('staff', 'Staff Admin A', { staff_role: 'admin' })
  world.patientA2Mail = await invite('patients', 'Patient A2')
  world.tempNurseName = `Temp Nurse ${RUN}`
  world.tempNurseMail = await invite('staff', world.tempNurseName, { staff_role: 'nurse' })
  world.tempPatientMail = await invite('patients', 'Temp Patient A')
  // The temporary nurse is logged in afresh by UAT-06 and UAT-15: finish its account setup now.
  await Api.as(world.tempNurseMail)
  world['staff-admin-a'] = await Api.as(world.adminStaffMail)
  world['patient-a2'] = await Api.as(world.patientA2Mail)
  world.patientA2Id = (await world['patient-a2'].get('/api/v1/auth/me')).body.patient_id
  world.patientAId = world['patient-a-me'].patient_id
  world.patientBId = world['patient-b-me'].patient_id
  world.clinicAId = world['admin-a-me'].clinic_id
  world.clinicBId = world['admin-b-me'].clinic_id

  // Merged access model (Parent A): doctors/nurses reach a patient only through an active care
  // assignment, made by the clinic admin (the staging seed predates it). 409 = already assigned.
  const assignments: [string, string, string][] = [
    ['admin-a', world.patientAId, world.doctorAStaffId],
    ['admin-a', world.patientAId, world.nurseAStaffId],
    ['admin-a', world.patientA2Id, world.doctorAStaffId],
    ['admin-a', world.patientA2Id, world.nurseAStaffId],
    ['admin-b', world.patientBId, world.doctorBStaffId],
  ]
  for (const [admin, patientId, staffId] of assignments) {
    const assigned = await world[admin].post(`/api/v1/patients/${patientId}/care-team`, { staff_id: staffId })
    expect([201, 409], `care team ${patientId}/${staffId}: ${assigned.text}`).toContain(assigned.status)
  }
})

test('UAT-01 Patient login, navigation, refresh and logout (browser)', async ({ page }) => {
  test.setTimeout(120_000)
  await uiLogin(page, email('patient-a'))
  await expect(page).toHaveURL(/\/patient$/)
  await expect(page.getByRole('heading', { name: 'Olá, Patient A' })).toBeVisible()
  for (const [link, path] of [['Consultas', '/patient/consultas'], ['Perfil', '/patient/perfil'], ['Notificações', '/patient/notificacoes'], ['Segurança', '/patient/seguranca']] as const) {
    await page.getByRole('navigation').getByRole('link', { name: link }).click()
    await expect(page).toHaveURL(new RegExp(`${path}$`))
  }
  await page.reload()
  await expect(page).toHaveURL(/\/patient\/seguranca$/)
  await expect(page.getByRole('heading', { name: 'Segurança da conta' })).toBeVisible()
  const storage = await page.evaluate(() => ({ local: Object.keys(localStorage).length, session: Object.keys(sessionStorage).length }))
  expect(storage).toEqual({ local: 0, session: 0 })
  await page.getByRole('button', { name: 'Sair' }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.goBack()
  await expect(page.getByRole('heading', { name: /Olá, Patient A/ })).toHaveCount(0)
  expect((await page.request.get('/api/v1/auth/me')).status()).toBe(401)
})

test('UAT-02 Patient sees own appointment and a generic notification (browser)', async ({ page }) => {
  test.setTimeout(120_000)
  const reason = `UAT motivo ${RUN}`
  const created = await world['doctor-a'].post('/api/v1/appointments', { patient_id: world.patientAId, staff_id: world.doctorAStaffId, scheduled_at: slot(), duration_minutes: 30, reason })
  expect(created.status, created.text).toBe(201)
  world.appointmentA1 = created.body
  await uiLogin(page, email('patient-a'))
  await page.getByRole('navigation').getByRole('link', { name: 'Consultas' }).click()
  await expect(page.getByRole('heading', { name: 'Consultas' })).toBeVisible()
  await expect(page.getByText(reason).first()).toBeVisible()
  await page.getByRole('navigation').getByRole('link', { name: 'Notificações' }).click()
  await expect(page.getByText('Consulta criada').first()).toBeVisible()
  await expect(page.getByText(reason)).toHaveCount(0)
  const notes = (await world['patient-a'].get('/api/v1/notifications')).body
  expect(notes.every((n: any) => !JSON.stringify(n).includes(reason))).toBe(true)
  // Another patient of the same clinic sees none of it.
  expect((await world['patient-a2'].get('/api/v1/appointments')).body.map((a: any) => a.id)).not.toContain(created.body.id)
})

test('UAT-03 Doctor finds and opens a patient of own clinic (browser)', async ({ page }) => {
  test.setTimeout(120_000)
  await uiLogin(page, email('doctor-a'))
  await expect(page).toHaveURL(/\/app$/)
  await page.getByRole('navigation').getByRole('link', { name: 'Pacientes' }).click()
  await expect(page.getByRole('heading', { name: 'Pacientes' })).toBeVisible()
  await expect(page.getByText('Patient A', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('Patient B')).toHaveCount(0)
  await page.goto(`/app/pacientes/${world.patientAId}`)
  await expect(page.getByText('Patient A', { exact: false }).first()).toBeVisible()
  const audit = await world['doctor-a'].get(`/api/v1/patients/${world.patientAId}`)
  expect(audit.status).toBe(200)
})

test('UAT-04 Clinic A users cannot reach clinic B (API and browser)', async ({ page }) => {
  test.setTimeout(120_000)
  const b = await world['doctor-b'].post('/api/v1/appointments', { patient_id: world.patientBId, staff_id: world.doctorBStaffId, scheduled_at: slot(), reason: 'UAT B' })
  const record = await world['doctor-b'].post(`/api/v1/patients/${world.patientBId}/medical-records`, { title: 'B synthetic', content: 'B synthetic content' })
  const medication = await world['doctor-b'].post(`/api/v1/patients/${world.patientBId}/medications`, { name: 'Bmed', dosage: '1 mg', start_date: '2043-01-01' })
  expect([b.status, record.status, medication.status]).toEqual([201, 201, 201])
  world.b = { appointment: b.body.id, record: record.body.id, medication: medication.body.id }
  const attackers = ['doctor-a', 'nurse-a', 'admin-a', 'staff-admin-a']
  for (const who of attackers) {
    const api = world[who]
    const probes: Array<[string, string, unknown?]> = [
      ['GET', `/api/v1/patients/${world.patientBId}`],
      ['GET', `/api/v1/patients/${world.patientBId}/medical-records`],
      ['GET', `/api/v1/medical-records/${world.b.record}`],
      ['GET', `/api/v1/medications/${world.b.medication}`],
      ['GET', `/api/v1/appointments/${world.b.appointment}`],
      ['PATCH', `/api/v1/appointments/${world.b.appointment}`, { duration_minutes: 45 }],
      ['POST', `/api/v1/appointments/${world.b.appointment}/cancel`],
      ['POST', `/api/v1/staff/${world.doctorBStaffId}/deactivate`],
      ['PATCH', `/api/v1/staff/${world.doctorBStaffId}/role`, { staff_role: 'admin' }],
      ['POST', '/api/v1/appointments', { patient_id: world.patientBId, staff_id: world.doctorAStaffId, scheduled_at: slot() }],
      ['POST', '/api/v1/appointments', { patient_id: world.patientAId, staff_id: world.doctorBStaffId, scheduled_at: slot() }],
    ]
    for (const [method, path, body] of probes) {
      const reply = await api.send(method, path, body)
      expect([403, 404], `${who} ${method} ${path} -> ${reply.status}`).toContain(reply.status)
      expect(reply.text).not.toContain('B synthetic')
    }
  }
  const listed = JSON.stringify([(await world['doctor-a'].get('/api/v1/patients')).body, (await world['admin-a'].get('/api/v1/staff')).body, (await world['doctor-a'].get('/api/v1/appointments')).body])
  expect(listed).not.toContain(world.clinicBId)
  expect(listed).not.toContain(world.patientBId)
  // Same through the browser URL.
  await uiLogin(page, email('doctor-a'))
  await page.goto(`/app/pacientes/${world.patientBId}`)
  await expect(page.getByText('Patient B')).toHaveCount(0)
  await expect(page.getByText(/não encontrad|sem permiss|erro/i).first()).toBeVisible()
  // B's data is untouched.
  expect((await world['doctor-b'].get(`/api/v1/appointments/${world.b.appointment}`)).body.duration_minutes).toBe(30)
})

test('UAT-05 Clinic admin creates staff through an invitation and the user can work (API + browser)', async ({ page }) => {
  test.setTimeout(120_000)
  const me = (await world['staff-admin-a'].get('/api/v1/auth/me')).body
  expect([me.role, me.staff_role, me.clinic_id]).toEqual(['staff', 'admin', world.clinicAId])
  await uiLogin(page, world.adminStaffMail)
  await expect(page).toHaveURL(/\/app$/)
  await expect(page.getByRole('navigation').getByRole('link', { name: 'Equipa' })).toHaveCount(0)
  await page.context().clearCookies()
  await uiLogin(page, email('admin-a'))
  await page.getByRole('navigation').getByRole('link', { name: 'Equipa' }).click()
  await expect(page.getByRole('heading', { name: 'Equipa', exact: true })).toBeVisible()
  await expect(page.getByText('Staff Admin A').first()).toBeVisible()
})

test('UAT-06 Disabled staff cannot log in and a live session ends at once', async ({ page }) => {
  test.setTimeout(150_000)
  const temp = await Api.as(world.tempNurseMail, false)
  const tempStaff = (await world['admin-a'].get('/api/v1/staff')).body.find((s: any) => s.full_name === world.tempNurseName)
  expect((await temp.get('/api/v1/patients')).status).toBe(200)
  const off = await world['admin-a'].post(`/api/v1/staff/${tempStaff.id}/deactivate`)
  expect(off.status).toBe(200)
  expect((await temp.get('/api/v1/auth/me')).status).toBe(401)
  expect((await temp.login()).status).toBe(401)
  await uiLogin(page, world.tempNurseMail, PW, true)
  await expect(page.getByText(/incorret|inválid|credenciais/i).first()).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
  const on = await world['admin-a'].post(`/api/v1/staff/${tempStaff.id}/activate`)
  expect(on.status).toBe(200)
  world.tempStaffId = tempStaff.id
})

test('UAT-07 A patient cannot access another patient (same clinic and other clinic)', async ({ page }) => {
  test.setTimeout(120_000)
  const record = await world['doctor-a'].post(`/api/v1/patients/${world.patientA2Id}/medical-records`, { title: 'A2 synthetic', content: 'A2 synthetic content' })
  expect(record.status).toBe(201)
  world.recordA2 = record.body.id
  const appointmentA2 = await world['doctor-a'].post('/api/v1/appointments', { patient_id: world.patientA2Id, staff_id: world.doctorAStaffId, scheduled_at: slot(), reason: 'A2 reason' })
  expect(appointmentA2.status).toBe(201)
  for (const path of [
    `/api/v1/patients/${world.patientA2Id}`,
    `/api/v1/patients/${world.patientBId}`,
    `/api/v1/patients/${world.patientA2Id}/medical-records`,
    `/api/v1/medical-records/${world.recordA2}`,
    `/api/v1/appointments/${appointmentA2.body.id}`,
    `/api/v1/patients/${world.patientBId}/medical-records`,
  ]) {
    const reply = await world['patient-a'].get(path)
    expect([403, 404], `${path} -> ${reply.status}`).toContain(reply.status)
    expect(reply.text).not.toContain('A2 synthetic')
  }
  expect((await world['patient-a'].patch(`/api/v1/patients/${world.patientA2Id}`, { phone: '999999999' })).status).toBeGreaterThanOrEqual(403)
  expect((await world['patient-a'].get('/api/v1/patients')).status).toBe(403)
  await uiLogin(page, email('patient-a'))
  await page.goto(`/patient/saude`)
  await expect(page.getByText('A2 synthetic')).toHaveCount(0)
  await page.goto(`/app/pacientes/${world.patientA2Id}`)
  await expect(page).not.toHaveURL(/\/app\/pacientes\//)
})

test('UAT-08 Nurse has clinical rights but not doctor-only or admin-only rights', async () => {
  const nurse = world['nurse-a']
  const record = await nurse.post(`/api/v1/patients/${world.patientAId}/medical-records`, { title: 'Nurse note', content: 'Synthetic nurse note' })
  expect(record.status).toBe(201)
  const med = await nurse.post(`/api/v1/patients/${world.patientAId}/medications`, { name: 'Nursemed', dosage: '2 mg', start_date: '2043-02-01' })
  expect(med.status).toBe(201)
  for (const [method, path, body] of [
    ['POST', `/api/v1/patients/${world.patientAId}/deactivate`],
    ['POST', '/api/v1/staff', { full_name: 'X Y', email: email('x'), password: PW, staff_role: 'doctor' }],
    ['POST', '/api/v1/invitations/staff', { email: email('y'), full_name: 'Y Z', staff_role: 'nurse' }],
    ['POST', `/api/v1/staff/${world.doctorAStaffId}/deactivate`],
    ['PATCH', `/api/v1/staff/${world.doctorAStaffId}/role`, { staff_role: 'admin' }],
    ['POST', `/api/v1/patients/${world.patientAId}/consents`, { consent_type: 'treatment', purpose: 'nurse must not' }],
  ] as const) {
    const reply = await nurse.send(method, path, body)
    expect(reply.status, `${method} ${path}`).toBe(403)
  }
})

test('UAT-09 Administrative staff operate the agenda but see no clinical content', async () => {
  const sa = world['staff-admin-a']
  const created = await sa.post('/api/v1/appointments', { patient_id: world.patientAId, staff_id: world.nurseAStaffId, scheduled_at: slot() })
  expect(created.status, created.text).toBe(201)
  const list = (await sa.get('/api/v1/appointments')).body
  expect(list.length).toBeGreaterThan(0)
  expect(list.every((a: any) => a.reason === null)).toBe(true)
  const denied = await sa.post('/api/v1/appointments', { patient_id: world.patientAId, staff_id: world.nurseAStaffId, scheduled_at: slot(), reason: 'not allowed' })
  expect(denied.status).toBe(403)
  for (const suffix of ['medical-records', 'medications', 'consents']) expect((await sa.get(`/api/v1/patients/${world.patientAId}/${suffix}`)).status).toBe(403)
  expect((await sa.get(`/api/v1/patients/${world.patientAId}`)).status).toBe(403)
  expect((await sa.post(`/api/v1/patients/${world.patientAId}/deactivate`)).status).toBe(403)
})

test('UAT-10 Doctor books an appointment in the browser; double click and conflicts do not duplicate', async ({ page }) => {
  test.setTimeout(150_000)
  await uiLogin(page, email('doctor-a'))
  await page.getByRole('navigation').getByRole('link', { name: 'Consultas' }).click()
  const when = new Date(Date.UTC(2044, 5, 1, 10, 0) + (Date.now() % 100_000) * 60_000)
  const local = `${when.getFullYear()}-${String(when.getMonth() + 1).padStart(2, '0')}-${String(when.getDate()).padStart(2, '0')}T${String(when.getHours()).padStart(2, '0')}:${String(when.getMinutes()).padStart(2, '0')}`
  const form = page.locator('form').filter({ has: page.getByLabel('Pesquisar paciente') })
  await form.getByLabel('Pesquisar paciente').fill('Patient A')
  await expect(form.locator('#patient').locator('option', { hasText: 'Patient A' }).first()).toBeAttached()
  await form.locator('#patient').selectOption({ label: 'Patient A' })
  await form.getByLabel('Profissional').selectOption({ label: 'Doctor A' })
  await form.getByLabel('Data e hora').fill(local)
  await form.getByLabel('Motivo (opcional)').fill(`UAT duplo clique ${RUN}`)
  await form.getByRole('button', { name: 'Marcar consulta' }).dblclick()
  await expect(page.getByText('Consulta marcada com sucesso.')).toBeVisible()
  const all = (await world['doctor-a'].get('/api/v1/appointments?page_size=100')).body.filter((a: any) => a.reason === `UAT duplo clique ${RUN}`)
  expect(all).toHaveLength(1)
  // Same slot again through the API: conflict, not a duplicate.
  const again = await world['doctor-a'].post('/api/v1/appointments', { patient_id: world.patientA2Id, staff_id: world.doctorAStaffId, scheduled_at: all[0].scheduled_at })
  expect(again.status).toBe(409)
  // Invalid input: bad duration, missing patient, unknown staff, past/invalid date.
  const bad = [
    { patient_id: world.patientAId, staff_id: world.doctorAStaffId, scheduled_at: slot(), duration_minutes: 1 },
    { staff_id: world.doctorAStaffId, scheduled_at: slot() },
    { patient_id: world.patientAId, staff_id: '00000000-0000-0000-0000-000000000000', scheduled_at: slot() },
    { patient_id: world.patientAId, staff_id: world.doctorAStaffId, scheduled_at: 'not-a-date' },
  ]
  const codes = await Promise.all(bad.map(async (payload) => (await world['doctor-a'].post('/api/v1/appointments', payload)).status))
  expect(codes.every((code) => [404, 422].includes(code)), JSON.stringify(codes)).toBe(true)
})

test('UAT-11 Clinical record lifecycle: create, update with versions, history, patient read', async ({ page }) => {
  test.setTimeout(120_000)
  const doctor = world['doctor-a']
  const created = await doctor.post(`/api/v1/patients/${world.patientAId}/medical-records`, { title: 'UAT record', content: 'Synthetic content v1' })
  expect(created.status).toBe(201)
  const id = created.body.id
  const v2 = await doctor.patch(`/api/v1/medical-records/${id}`, { title: 'UAT record', content: 'Synthetic content v2', expected_version: 1 })
  expect(v2.status).toBe(200)
  expect(v2.body.version).toBe(2)
  const stale = await doctor.patch(`/api/v1/medical-records/${id}`, { title: 'UAT record', content: 'overwrite', expected_version: 1 })
  expect(stale.status).toBe(409)
  const revisions = (await doctor.get(`/api/v1/medical-records/${id}/revisions`)).body
  expect(revisions.map((r: any) => r.content)).toEqual(expect.arrayContaining(['Synthetic content v1']))
  expect((await doctor.get(`/api/v1/medical-records/${id}`)).body.content).toBe('Synthetic content v2')
  expect((await world['patient-a'].get(`/api/v1/medical-records/${id}`)).body.content).toBe('Synthetic content v2')
  expect((await world['patient-a'].patch(`/api/v1/medical-records/${id}`, { title: 'x', content: 'x', expected_version: 2 })).status).toBeGreaterThanOrEqual(403)
  expect((await world['patient-a2'].get(`/api/v1/medical-records/${id}`)).status).toBe(404)
  await uiLogin(page, email('patient-a'))
  await page.goto('/patient/saude')
  await page.getByRole('tab', { name: 'Registos clínicos' }).click()
  await expect(page.getByText('UAT record').first()).toBeVisible()
  world.recordA1 = id
})

test('UAT-12 Medications: create, edit, deactivate, invalid values, isolation', async () => {
  const doctor = world['doctor-a']
  const created = await doctor.post(`/api/v1/patients/${world.patientAId}/medications`, { name: 'Synthamol', dosage: '5 mg', frequency: '2x/day', start_date: '2043-03-01', end_date: '2043-03-10' })
  expect(created.status).toBe(201)
  const id = created.body.id
  expect((await doctor.patch(`/api/v1/medications/${id}`, { instructions: 'after food' })).body.instructions).toBe('after food')
  const invalid = [
    { name: '', dosage: '5 mg', start_date: '2043-03-01' },
    { name: 'X', dosage: '', start_date: '2043-03-01' },
    { name: 'X', dosage: '1 mg', start_date: 'tomorrow' },
    { name: 'X', dosage: '1 mg', start_date: '2043-03-10', end_date: '2043-03-01' },
    { name: 'X'.repeat(500), dosage: '1 mg', start_date: '2043-03-01' },
  ]
  for (const payload of invalid) expect((await doctor.post(`/api/v1/patients/${world.patientAId}/medications`, payload)).status).toBe(422)
  expect((await world['patient-a'].get(`/api/v1/medications/${id}`)).status).toBe(200)
  expect((await world['patient-a2'].get(`/api/v1/medications/${id}`)).status).toBe(404)
  expect((await world['doctor-b'].get(`/api/v1/medications/${id}`)).status).toBe(404)
  expect((await world['patient-a'].patch(`/api/v1/medications/${id}`, { dosage: '99 g' })).status).toBeGreaterThanOrEqual(403)
  expect((await doctor.post(`/api/v1/medications/${id}/deactivate`)).body.status).not.toBe('active')
})

test('UAT-13 Notifications: generic text, own-only, mark read, idempotent', async () => {
  const patient = world['patient-a']
  const list = (await patient.get('/api/v1/notifications')).body
  expect(list.length).toBeGreaterThan(0)
  for (const n of list) expect(`${n.title} ${n.message}`).not.toMatch(/UAT|motivo|diagn|record|medic/i)
  const target = list.find((n: any) => !n.is_read) ?? list[0]
  const first = await patient.post(`/api/v1/notifications/${target.id}/read`)
  const second = await patient.post(`/api/v1/notifications/${target.id}/read`)
  expect([first.status, second.status]).toEqual([200, 200])
  expect(second.body.read_at).toBe(first.body.read_at)
  expect((await world['patient-a2'].post(`/api/v1/notifications/${target.id}/read`)).status).toBe(404)
  expect((await world['doctor-a'].post(`/api/v1/notifications/${target.id}/read`)).status).toBe(404)
  expect((await world['patient-b'].post(`/api/v1/notifications/${target.id}/read`)).status).toBe(404)
})

test('UAT-14 Consent: only the patient records it; history, revoke, duplicates; no clinical gating (documented limit)', async () => {
  const patient = world['patient-a']
  const purpose = `UAT consent ${RUN}`
  const granted = await patient.post(`/api/v1/patients/${world.patientAId}/consents`, { consent_type: 'research', purpose })
  expect(granted.status).toBe(201)
  expect(granted.body.status).toBe('granted')
  expect(Date.parse(granted.body.granted_at)).toBeGreaterThan(Date.now() - 120_000)
  expect((await patient.post(`/api/v1/patients/${world.patientAId}/consents`, { consent_type: 'research', purpose })).status).toBe(409)
  for (const who of ['doctor-a', 'nurse-a', 'admin-a', 'staff-admin-a', 'patient-a2'])
    expect((await world[who].post(`/api/v1/patients/${world.patientAId}/consents`, { consent_type: 'research', purpose: 'forged' })).status, who).toBeGreaterThanOrEqual(403)
  expect((await world['doctor-a'].get(`/api/v1/consents/${granted.body.id}`)).status).toBe(200)
  expect((await world['doctor-b'].get(`/api/v1/consents/${granted.body.id}`)).status).toBe(404)
  const revoked = await patient.post(`/api/v1/consents/${granted.body.id}/revoke`)
  expect(revoked.status).toBe(200)
  expect(revoked.body.status).toBe('revoked')
  expect(Date.parse(revoked.body.revoked_at)).toBeGreaterThanOrEqual(Date.parse(granted.body.granted_at))
  expect((await patient.post(`/api/v1/consents/${granted.body.id}/revoke`)).status).toBe(409)
  const history = (await patient.get(`/api/v1/patients/${world.patientAId}/consents`)).body
  expect(history.find((c: any) => c.id === granted.body.id).status).toBe('revoked')
  // Documented limitation: revocation is recorded but does not gate clinical access.
  expect((await world['doctor-a'].get(`/api/v1/patients/${world.patientAId}/medical-records`)).status).toBe(200)
})

test('UAT-15 Clinic admin manages the team and cannot touch another clinic', async () => {
  const admin = world['admin-a']
  const temp = await Api.as(world.tempNurseMail, false)
  expect((await temp.get('/api/v1/patients')).status).toBe(200)
  const roleChange = await admin.patch(`/api/v1/staff/${world.tempStaffId}/role`, { staff_role: 'doctor', specialty: 'Synthetic' })
  expect(roleChange.status).toBe(200)
  expect((await temp.get('/api/v1/auth/me')).status).toBe(401)
  expect((await temp.login()).status).toBe(200)
  expect((await temp.get('/api/v1/auth/me')).body.staff_role).toBe('doctor')
  expect((await admin.post(`/api/v1/staff/${(await admin.get('/api/v1/auth/me')).body.id}/deactivate`)).status).toBeGreaterThanOrEqual(400)
  expect((await world['admin-b'].post(`/api/v1/staff/${world.tempStaffId}/deactivate`)).status).toBe(404)
  expect((await world['admin-b'].patch(`/api/v1/staff/${world.tempStaffId}/role`, { staff_role: 'admin' })).status).toBe(404)
  expect((await temp.get('/api/v1/auth/me')).status).toBe(200)
  const staffA = (await admin.get('/api/v1/staff')).body
  expect(staffA.every((s: any) => s.clinic_id === world.clinicAId)).toBe(true)
})

test('UAT-16 Authentication negatives behave identically and leak nothing', async ({ page }) => {
  test.setTimeout(150_000)
  const anon = await request.newContext({ baseURL: BASE })
  const attempts = [
    { email: email('doctor-a'), password: 'Wrong-Password-1!' },
    { email: `nobody-${RUN}@${DOMAIN}`, password: PW },
  ]
  const replies = []
  for (const data of attempts) {
    await throttle()
    const r = await anon.post('/api/v1/auth/login', { data })
    replies.push({ status: r.status(), body: await r.json(), cookies: r.headers()['set-cookie'] ?? '' })
  }
  expect(replies[0].status).toBe(401)
  expect(replies[1]).toEqual(replies[0])
  for (const data of [{}, { email: 'not-an-email', password: 'x' }, { email: email('doctor-a') }, 'text']) {
    await throttle()
    const r = await anon.post('/api/v1/auth/login', { data: data as any })
    expect(r.status()).toBe(422)
    expect(await r.text()).not.toMatch(/Traceback|sqlalchemy|psycopg/i)
  }
  // CSRF: authenticated unsafe request without or with a wrong token is refused.
  expect((await world['patient-a'].send('POST', '/api/v1/notifications/00000000-0000-0000-0000-000000000000/read', undefined, false)).status).toBe(403)
  expect((await world['patient-a'].send('POST', '/api/v1/notifications/00000000-0000-0000-0000-000000000000/read', undefined, 'wrong')).status).toBe(403)
  // Browser: a wrong password shows a clear message and no session.
  await uiLogin(page, email('patient-a'), 'Wrong-Password-1!', true)
  await expect(page.getByText(/incorret/i).first()).toBeVisible()
  expect((await page.request.get('/api/v1/auth/me')).status()).toBe(401)
  await anon.dispose()
})

test('UAT-17 Password change and logout revoke other sessions; protected pages do not survive logout', async ({ page }) => {
  test.setTimeout(150_000)
  const first = await Api.as(world.tempPatientMail, false)
  const second = await Api.as(world.tempPatientMail, false)
  const next = `Changed-${RUN}-Pass-9!`
  expect((await first.post('/api/v1/auth/change-password', { current_password: 'wrong-wrong-1', new_password: next })).status).toBe(400)
  expect((await first.post('/api/v1/auth/change-password', { current_password: PW, new_password: next })).status).toBe(204)
  expect((await first.get('/api/v1/auth/me')).status).toBe(200)
  expect((await second.get('/api/v1/auth/me')).status).toBe(401)
  expect((await second.login(PW)).status).toBe(401)
  expect((await second.login(next)).status).toBe(200)
  expect((await second.post('/api/v1/auth/logout')).status).toBe(204)
  expect((await first.get('/api/v1/auth/me')).status).toBe(401)
  await page.goto('/patient/saude')
  await expect(page).toHaveURL(/\/login/)
  await page.goto('/app')
  await expect(page).toHaveURL(/\/login/)
})

test('UAT-18 Audit evidence is produced for the actions above (read via database in the report step)', async () => {
  // The audit table has no API reader by design; evidence is collected by scripts/pilot_audit_evidence.sh.
  const reply = await world['admin-a'].get('/api/v1/audit-logs')
  expect(reply.status).toBe(404)
})

test('UAT-19 Errors are clean: no traces, SQL or paths, and a request id is returned', async () => {
  const doctor = world['doctor-a']
  const replies: Reply[] = [
    await doctor.get('/api/v1/patients/not-a-uuid'),
    await doctor.get(`/api/v1/patients/${'0'.repeat(8)}-0000-0000-0000-000000000000`),
    await doctor.post('/api/v1/appointments', { patient_id: 1 }),
    await doctor.send('POST', '/api/v1/appointments', {}, false),
    await world['patient-a'].get('/api/v1/patients'),
    await (await request.newContext({ baseURL: BASE })).get('/api/v1/auth/me').then(async (r) => ({ status: r.status(), body: null, headers: r.headers(), text: await r.text() })),
    await doctor.get('/api/v1/does-not-exist'),
  ]
  for (const reply of replies) {
    expect(reply.status).toBeGreaterThanOrEqual(400)
    expect(reply.status).toBeLessThan(500)
    expect(reply.headers['x-request-id']).toBeTruthy()
    expect(reply.text).not.toMatch(/Traceback|File "|sqlalchemy|psycopg|SELECT |INSERT |\/app\/|postgres/i)
  }
  const proxied = await world['doctor-a'].raw('GET', '/openapi.json')
  expect(proxied.headers['content-type'] ?? '').not.toContain('json')
})

test('UAT-20 UI recovers from backend outage, refresh and back/forward', async ({ page }) => {
  test.setTimeout(150_000)
  await uiLogin(page, email('doctor-a'))
  await page.getByRole('navigation').getByRole('link', { name: 'Pacientes' }).click()
  await expect(page.getByText('Patient A').first()).toBeVisible()
  await page.route('**/api/**', (route) => route.abort())
  await page.reload()
  await expect(page.getByRole('alert').first().or(page.getByText(/erro|indispon|falh|tentar/i).first()).first()).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('body')).not.toContainText('Traceback')
  await page.unroute('**/api/**')
  const retry = page.getByRole('button', { name: /tentar/i }).first()
  if (await retry.count()) await retry.click()
  else await page.reload()
  await expect(page.getByText('Patient A').first()).toBeVisible({ timeout: 20_000 })
  await page.getByRole('navigation').getByRole('link', { name: 'Consultas' }).click()
  await page.goBack()
  await expect(page).toHaveURL(/\/app\/pacientes/)
  await page.goForward()
  await expect(page).toHaveURL(/\/app\/consultas/)
  await page.goto('/app/rota-inexistente')
  await expect(page.getByRole('heading', { name: /não encontrada/i })).toBeVisible()
  // Network offline: the failed action is reported, then works after reconnecting.
  await page.context().setOffline(true)
  await page.reload().catch(() => undefined)
  await page.context().setOffline(false)
  await page.goto('/app/pacientes')
  await expect(page.getByText('Patient A').first()).toBeVisible()
})

test('UAT-21 Responsive layout: no horizontal overflow on phone and tablet widths', async ({ page }) => {
  test.setTimeout(150_000)
  for (const size of [{ width: 375, height: 700 }, { width: 768, height: 900 }]) {
    await page.setViewportSize(size)
    await page.goto('/login')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
  await uiLogin(page, email('patient-a'))
  await expect(page).toHaveURL(/\/patient/)
  for (const path of ['/patient', '/patient/consultas', '/patient/seguranca']) {
    await page.goto(path)
    await expect(page.locator('main, body').first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), path).toBe(true)
  }
})

test('UAT-22 Accessibility: no serious or critical axe violations and keyboard login works', async ({ page }) => {
  test.setTimeout(240_000)
  const found: string[] = []
  async function scan(label: string) {
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
    for (const v of results.violations.filter((x) => ['serious', 'critical'].includes(x.impact ?? ''))) found.push(`${label}: ${v.id} (${v.impact}) x${v.nodes.length}`)
  }
  await page.goto('/login')
  await scan('login')
  // Keyboard-only login.
  await page.getByLabel('Email').focus()
  await page.keyboard.type(email('doctor-a'))
  await page.keyboard.press('Tab')
  await page.keyboard.type(PW)
  await throttle()
  await page.keyboard.press('Enter')
  const secret = mfaSecrets.get(email('doctor-a'))
  if (secret) {
    // Second factor, still keyboard-only: the code field takes focus on its own.
    const code = page.getByLabel('Código de verificação')
    await expect(code).toBeFocused()
    await scan('login (second factor)')
    await throttle()
    await page.keyboard.type(await nextTotp(secret))
    await page.keyboard.press('Enter')
  }
  await expect(page).toHaveURL(/\/app$/)
  for (const path of ['/app', '/app/consultas', '/app/pacientes', '/app/notificacoes', '/app/perfil', '/app/seguranca']) {
    await page.goto(path)
    await page.waitForLoadState('networkidle')
    await scan(path)
  }
  await page.getByRole('button', { name: 'Sair' }).click()
  await uiLogin(page, email('patient-a'))
  for (const path of ['/patient', '/patient/consultas', '/patient/saude', '/patient/consentimentos', '/patient/notificacoes', '/patient/perfil', '/patient/seguranca']) {
    await page.goto(path)
    await page.waitForLoadState('networkidle')
    await scan(path)
    expect(await page.locator('h1').count(), `${path} needs a level-1 heading`).toBeGreaterThan(0)
  }
  expect(found, found.join('\n')).toEqual([])
})
