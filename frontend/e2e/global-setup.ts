import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { request } from '@playwright/test'
import type { APIRequestContext, FullConfig } from '@playwright/test'
import { AUTH_DIR, PASSWORD } from './support'
import type { Role, Seed } from './support'

const CSRF_COOKIE = 'myvita_csrf'

async function csrfHeader(context: APIRequestContext): Promise<Record<string, string>> {
  const { cookies } = await context.storageState()
  const token = cookies.find((cookie) => cookie.name === CSRF_COOKIE)?.value
  if (!token) throw new Error('No CSRF cookie in the seeded session')
  return { 'X-CSRF-Token': token }
}

async function ok<T>(response: import('@playwright/test').APIResponse, what: string): Promise<T> {
  if (!response.ok()) throw new Error(`E2E seed failed at "${what}": ${response.status()} ${await response.text()}`)
  return (await response.json()) as T
}

/**
 * Builds one deterministic clinic through the real public API, then stores a
 * logged-in browser state per role. Registration and onboarding already return a
 * session, so only the two staff roles spend login rate-limit budget (10/min).
 * The database itself is reset on every run by e2e/start-backend.sh.
 */
export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = String(config.projects[0].use.baseURL)
  mkdirSync(AUTH_DIR, { recursive: true })

  const emails: Record<Role, string> = {
    clinic_admin: 'admin.e2e@example.pt',
    doctor: 'doctor.e2e@example.pt',
    nurse: 'nurse.e2e@example.pt',
    patient: 'patient.e2e@example.pt',
    other_patient: 'other.patient.e2e@example.pt',
  }
  const names: Record<Role, string> = {
    clinic_admin: 'Admin Clínica E2E',
    doctor: 'Doutora Teste E2E',
    nurse: 'Enfermeiro Teste E2E',
    patient: 'Paciente Um E2E',
    other_patient: 'Paciente Dois E2E',
  }
  const save = (context: APIRequestContext, role: Role) =>
    context.storageState({ path: path.join(AUTH_DIR, `${role}.json`) })

  const admin = await request.newContext({ baseURL })
  const clinic = await ok<{ id: string }>(
    await admin.post('/api/v1/clinics', {
      data: {
        clinic_name: 'Clínica E2E',
        admin_full_name: names.clinic_admin,
        admin_email: emails.clinic_admin,
        admin_password: PASSWORD,
      },
    }),
    'clinic onboarding',
  )
  await save(admin, 'clinic_admin')

  const staffIds: Record<'doctor' | 'nurse', string> = { doctor: '', nurse: '' }
  for (const role of ['doctor', 'nurse'] as const) {
    const created = await ok<{ id: string }>(
      await admin.post('/api/v1/staff', {
        headers: await csrfHeader(admin),
        data: {
          full_name: names[role],
          email: emails[role],
          password: PASSWORD,
          staff_role: role,
          specialty: role === 'doctor' ? 'Medicina Geral' : undefined,
          require_password_change: false,
        },
      }),
      `create ${role}`,
    )
    staffIds[role] = created.id
  }

  // Since Phase 1, clinicians reach a patient only through an explicit care assignment.
  // Patient one gets the doctor and the nurse; patient two stays unassigned for denial checks.
  const patientIds = { patient: '', other_patient: '' }
  for (const role of ['patient', 'other_patient'] as const) {
    const context = await request.newContext({ baseURL })
    const registered = await ok<{ id: string }>(
      await context.post('/api/v1/patients/register', {
        data: { clinic_id: clinic.id, full_name: names[role], email: emails[role], password: PASSWORD },
      }),
      `register ${role}`,
    )
    patientIds[role] = registered.id
    await save(context, role)
    await context.dispose()
  }
  for (const role of ['doctor', 'nurse'] as const) {
    await ok(
      await admin.post(`/api/v1/patients/${patientIds.patient}/care-team`, {
        headers: await csrfHeader(admin),
        data: { staff_id: staffIds[role] },
      }),
      `assign ${role}`,
    )
  }
  await admin.dispose()

  for (const role of ['doctor', 'nurse'] as const) {
    const context = await request.newContext({ baseURL })
    await ok(await context.post('/api/v1/auth/login', { data: { email: emails[role], password: PASSWORD } }), `login ${role}`)
    await save(context, role)
    await context.dispose()
  }

  // Nothing in the backend creates notifications yet, so the inbox is seeded directly.
  seedNotifications(emails.patient)

  const seed: Seed = { clinicId: clinic.id, emails, names, staffIds, patientIds }
  writeFileSync(path.join(AUTH_DIR, 'seed.json'), JSON.stringify(seed, null, 2))
}

function seedNotifications(patientEmail: string): void {
  const databaseUrl = (process.env.E2E_DATABASE_URL ?? 'postgresql+psycopg://myvita:myvita@localhost:5432/myvita_e2e_test').replace(
    '+psycopg',
    '',
  )
  const sql = `
    INSERT INTO notifications (id, clinic_id, user_id, title, message, is_read)
    SELECT gen_random_uuid(), clinic_id, id, v.title, v.message, false
    FROM users, (VALUES
      ('Consulta confirmada', 'A sua consulta foi confirmada.'),
      ('Resultados disponíveis', 'Os seus resultados estão disponíveis.')
    ) AS v(title, message)
    WHERE lower(email) = lower('${patientEmail.replace(/'/g, "''")}');`
  execFileSync('psql', [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-q', '-c', sql], { stdio: 'inherit' })
}
