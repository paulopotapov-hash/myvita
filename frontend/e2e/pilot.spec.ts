import { expect, request, test, type APIRequestContext, type Page } from '@playwright/test'
import { nextTotp, throttleLogin, totp } from './mfa'

const password = 'E2e-Senha-Forte-123!'
// Production settings close every public entry point (onboarding, self-registration, direct staff
// creation). The pilot then starts from clinics created by the staging seed
// (backend/scripts/seed_staging.py, STAGING_SEED_EMAIL_DOMAIN=PILOT_SEED_DOMAIN) and onboards
// everyone else through invitations; staff enrol MFA in the browser.
const SEED_DOMAIN = process.env.PILOT_SEED_DOMAIN ?? ''
const SEED_PASSWORD = process.env.SEED_PASSWORD ?? ''

async function csrf(page: Page) {
  const cookie = (await page.context().cookies()).find((item) => item.name === 'myvita_csrf')
  expect(cookie).toBeDefined()
  return { 'X-CSRF-Token': cookie!.value }
}

async function apiCsrf(context: APIRequestContext) {
  const cookie = (await context.storageState()).cookies.find((item) => item.name === 'myvita_csrf')
  expect(cookie).toBeDefined()
  return { 'X-CSRF-Token': cookie!.value }
}

async function signIn(page: Page, email: string, secret: string) {
  await throttleLogin()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Palavra-passe').fill(secret)
  await page.getByRole('button', { name: 'Entrar' }).click()
}

/** The login page's second-factor step, answered with a TOTP or a recovery code. A TOTP is
 * produced only after waiting for the login budget, so it is never stale when submitted. */
async function answerSecondFactor(page: Page, code: string | (() => Promise<string>)) {
  await expect(page.getByRole('heading', { name: 'Verificação em dois passos' })).toBeVisible()
  await throttleLogin()
  await page.getByLabel('Código de verificação').fill(typeof code === 'string' ? code : await code())
  await page.getByRole('button', { name: 'Verificar' }).click()
}

/** Mandatory MFA enrolment in the merged UI: read the key the screen shows (as an authenticator
 * app would), answer with a code, keep the one-time recovery codes. */
async function enrolMfaInBrowser(page: Page) {
  await expect(page.getByRole('heading', { name: 'Ativar autenticação de dois fatores' })).toBeVisible()
  await page.getByRole('button', { name: 'Configurar autenticação de dois fatores' }).click()
  const secret = (await page.getByLabel('Chave secreta').innerText()).replace(/\s/g, '')
  await page.getByLabel('Código de 6 dígitos').fill(await nextTotp(secret))
  await page.getByRole('button', { name: 'Ativar' }).click()
  const codes = page.getByRole('list', { name: 'Códigos de recuperação' })
  await expect(codes).toBeVisible()
  const recovery = (await codes.getByRole('listitem').allInnerTexts()).map((code) => code.trim())
  expect(recovery.length).toBeGreaterThan(1)
  await page.getByRole('button', { name: 'Guardei os códigos — continuar' }).click()
  await expect(page).toHaveURL(/\/app/)
  return { secret, recovery }
}

/** API session for a seeded clinic admin, enrolling MFA through the real API where required. */
async function seededAdminSession(baseURL: string | undefined, email: string) {
  const context = await request.newContext({ baseURL })
  await throttleLogin()
  expect((await context.post('/api/v1/auth/login', { data: { email, password: SEED_PASSWORD } })).status()).toBe(200)
  const me = await (await context.get('/api/v1/auth/me')).json() as { pending_action: string | null }
  if (me.pending_action === 'mfa_setup') {
    const setup = await context.post('/api/v1/auth/mfa/setup', { headers: await apiCsrf(context) })
    expect(setup.status()).toBe(200)
    const { secret } = await setup.json() as { secret: string }
    const enabled = await context.post('/api/v1/auth/mfa/enable', {
      headers: await apiCsrf(context), data: { code: await nextTotp(secret) },
    })
    expect(enabled.status()).toBe(200)
  }
  return context
}

/** Merged access model (Parent A): clinicians reach a patient only through an active care
 * assignment, made by the clinic admin. */
async function assignToCareTeam(page: Page, patientId: string, staffId: string) {
  const assigned = await page.request.post(`/api/v1/patients/${patientId}/care-team`, {
    headers: await csrf(page),
    data: { staff_id: staffId },
  })
  expect(assigned.status()).toBe(201)
}

/** Patients join by invitation: a clinic member invites, the patient accepts anonymously. */
async function invitePatient(inviter: APIRequestContext, baseURL: string | undefined, data: { full_name: string; email: string }) {
  const invitation = await inviter.post('/api/v1/invitations/patients', { headers: await apiCsrf(inviter), data })
  expect(invitation.status()).toBe(201)
  const { token } = await invitation.json() as { token: string }
  const anonymous = await request.newContext({ baseURL })
  const accepted = await anonymous.post('/api/v1/invitations/accept', { data: { token, password } })
  expect(accepted.status()).toBe(200)
  const user = await accepted.json() as { patient_id: string }
  await anonymous.dispose()
  return { id: user.patient_id }
}

test('pilot flow and cross-tenant security through browser proxy', async ({ page, baseURL }) => {
  test.setTimeout(300_000)
  const suffix = Date.now().toString()
  const staffEmail = `doctor-${suffix}@example.com`
  const patientEmail = `patient-${suffix}@example.com`
  const registration = { full_name: 'Paciente E2E', email: patientEmail, password }

  const seed = await request.newContext({ baseURL })
  const clinicResponse = await seed.post('/api/v1/clinics', { data: {
    clinic_name: `Clínica E2E ${suffix}`,
    admin_full_name: 'Admin E2E',
    admin_email: `admin-${suffix}@example.com`,
    admin_password: password,
  } })
  // Production settings: public onboarding is closed, so the pilot starts from a seeded clinic.
  const production = clinicResponse.status() === 403
  if (!production) expect(clinicResponse.status()).toBe(201)
  else expect(SEED_DOMAIN && SEED_PASSWORD, 'PILOT_SEED_DOMAIN and SEED_PASSWORD are required with public onboarding closed').toBeTruthy()
  const adminEmail = production ? `admin-a@${SEED_DOMAIN}` : `admin-${suffix}@example.com`

  await page.goto('/login')
  await signIn(page, adminEmail, production ? SEED_PASSWORD : password)
  // Production: clinic admins must enrol a second factor before anything else (merged UI flow).
  const adminMfa = production ? await enrolMfaInBrowser(page) : null
  await expect(page).toHaveURL(/\/app/)
  const clinicId = (await (await page.request.get('/api/v1/auth/me')).json() as { clinic_id: string }).clinic_id

  let doctorStaffId = ''
  let staffInvitationToken = ''
  let patient: { id: string }
  if (!production) {
    const staffResponse = await page.request.post('/api/v1/staff', {
      headers: await csrf(page),
      data: { full_name: 'Doctor E2E', email: staffEmail, password, staff_role: 'doctor' },
    })
    expect(staffResponse.status()).toBe(201)
    doctorStaffId = (await staffResponse.json() as { id: string }).id
    const patientResponse = await seed.post('/api/v1/patients/register', { data: { clinic_id: clinicId, ...registration } })
    expect(patientResponse.status()).toBe(201)
    patient = await patientResponse.json() as { id: string }
    await assignToCareTeam(page, patient.id, doctorStaffId)
  } else {
    // Every public entry point refuses, with the same 403 and no session.
    for (const [url, data] of [
      ['/api/v1/patients/register', { clinic_id: clinicId, ...registration }],
      ['/api/v1/clinics', { clinic_name: `Outra ${suffix}`, admin_full_name: 'Outro Admin', admin_email: `x-${suffix}@example.com`, admin_password: password }],
    ] as const) {
      const refused = await seed.post(url, { data })
      expect(refused.status(), url).toBe(403)
      expect(refused.headers()['set-cookie'] ?? '', url).not.toContain('myvita_session')
    }
    expect((await (await seed.get('/api/v1/clinics')).json() as unknown[]).length).toBe(0)
    expect((await page.request.post('/api/v1/staff', {
      headers: await csrf(page),
      data: { full_name: 'Doctor E2E', email: staffEmail, password, staff_role: 'doctor' },
    })).status()).toBe(403)
    // Staff and patients join by invitation.
    const staffInvitation = await page.request.post('/api/v1/invitations/staff', {
      headers: await csrf(page),
      data: { full_name: 'Doctor E2E', email: staffEmail, staff_role: 'doctor' },
    })
    expect(staffInvitation.status()).toBe(201)
    staffInvitationToken = (await staffInvitation.json() as { token: string }).token
    patient = await invitePatient(page.request, baseURL, { full_name: registration.full_name, email: patientEmail })
  }

  let otherPatientBody: { id: string }
  if (!production) {
    const otherClinic = await seed.post('/api/v1/clinics', { data: {
      clinic_name: `Outra Clínica ${suffix}`, admin_full_name: 'Outro Admin',
      admin_email: `other-admin-${suffix}@example.com`, admin_password: password,
    } })
    const otherClinicBody = await otherClinic.json() as { id: string }
    const otherPatient = await seed.post('/api/v1/patients/register', { data: {
      clinic_id: otherClinicBody.id, full_name: 'Paciente Outra Clínica',
      email: `other-patient-${suffix}@example.com`, password,
    } })
    otherPatientBody = await otherPatient.json() as { id: string }
  } else {
    const otherAdmin = await seededAdminSession(baseURL, `admin-b@${SEED_DOMAIN}`)
    otherPatientBody = await invitePatient(otherAdmin, baseURL, {
      full_name: 'Paciente Outra Clínica', email: `other-patient-${suffix}@example.com`,
    })
    await otherAdmin.dispose()
  }
  await seed.dispose()

  await page.getByRole('button', { name: 'Sair' }).click()
  let doctorMfa: { secret: string; recovery: string[] } | null = null
  let doctorPassword = password
  if (!production) {
    await signIn(page, staffEmail, password)
    // Merged security (Parent A): staff created by an admin must set their own password first.
    await expect(page.getByRole('heading', { name: 'Alterar palavra-passe', level: 1 })).toBeVisible()
    doctorPassword = `${password}-Proprio`
    await page.getByLabel('Palavra-passe atual').fill(password)
    await page.getByLabel('Nova palavra-passe', { exact: true }).fill(doctorPassword)
    await page.getByLabel('Confirmar nova palavra-passe').fill(doctorPassword)
    await page.getByRole('button', { name: 'Alterar palavra-passe' }).click()
    await expect(page).toHaveURL(/\/app/)
    await expect(page.getByRole('heading', { name: 'Alterar palavra-passe' })).toHaveCount(0)
  } else {
    // The invited doctor accepts in the browser and sets a password; the new session must then
    // enrol MFA before anything else.
    await page.goto(`/convite#token=${staffInvitationToken}`)
    await expect(page.getByRole('heading', { name: 'Aceitar convite' })).toBeVisible()
    await page.getByLabel('Nova palavra-passe').fill(doctorPassword)
    await page.getByLabel('Confirmar palavra-passe').fill(doctorPassword)
    await page.getByRole('button', { name: 'Ativar conta' }).click()
    await expect(page.getByText('Conta ativada.')).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await page.getByRole('link', { name: 'Continuar' }).click()
    doctorMfa = await enrolMfaInBrowser(page)
  }
  if (adminMfa && doctorMfa) {
    // The invited doctor's staff record exists only now: the admin signs back in (TOTP in the
    // browser) to make the care assignment, then the doctor signs in with a TOTP.
    const staffList = await (await page.request.get('/api/v1/staff')).json() as { id: string; full_name: string }[]
    doctorStaffId = staffList.find((entry) => entry.full_name === 'Doctor E2E')!.id
    await page.getByRole('button', { name: 'Sair' }).click()
    await signIn(page, adminEmail, SEED_PASSWORD)
    await answerSecondFactor(page, () => nextTotp(adminMfa.secret))
    await expect(page).toHaveURL(/\/app/)
    await assignToCareTeam(page, patient.id, doctorStaffId)
    await page.getByRole('button', { name: 'Sair' }).click()
    await signIn(page, staffEmail, doctorPassword)
    await answerSecondFactor(page, () => nextTotp(doctorMfa!.secret))
    await expect(page).toHaveURL(/\/app/)
  }
  await page.goto('/app/consultas')
  await page.getByLabel('Pesquisar paciente').fill('Paciente E2E')
  await page.getByLabel('Paciente', { exact: true }).selectOption(patient.id)
  await page.getByLabel('Profissional').selectOption({ label: 'Doctor E2E' })
  await page.getByLabel('Data e hora').fill('2030-10-20T10:30')
  await page.getByRole('button', { name: 'Marcar consulta' }).click()
  await expect(page.getByText('Consulta marcada com sucesso.')).toBeVisible()
  await page.getByRole('button', { name: 'Detalhes' }).first().click()
  await page.getByRole('button', { name: 'Confirmar' }).click()
  await page.getByRole('alertdialog', { name: 'Confirmar consulta' }).getByRole('button', { name: 'Confirmar' }).click()
  await expect(page.getByText('Consulta confirmada.')).toBeVisible()

  await page.goto(`/app/pacientes/${patient.id}`)
  await page.getByRole('tab', { name: 'Registos clínicos' }).click()
  await page.getByLabel('Título do registo').fill('Observação E2E')
  await page.getByLabel('Conteúdo clínico').fill('Conteúdo clínico sintético para validação E2E.')
  await page.getByRole('button', { name: 'Criar registo' }).click()
  await expect(page.getByRole('status')).toHaveText('Registo clínico guardado.')
  await page.getByRole('button', { name: 'Editar' }).click()
  await page.getByLabel('Conteúdo clínico').fill('Conteúdo clínico sintético atualizado.')
  await page.getByRole('button', { name: 'Guardar alterações' }).click()
  await expect(page.getByText('Conteúdo clínico sintético atualizado.')).toBeVisible()

  expect((await page.request.get(`/api/v1/patients/${otherPatientBody.id}`)).status()).toBe(404)
  expect((await page.request.post('/api/v1/staff', {
    headers: await csrf(page),
    data: { full_name: 'Sem Permissão', email: `forbidden-${suffix}@example.com`, password, staff_role: 'doctor' },
  })).status()).toBe(403)
  expect((await page.request.patch(`/api/v1/patients/${patient.id}`, {
    data: { phone: '910000000' },
  })).status()).toBe(403)

  await page.getByRole('button', { name: 'Sair' }).click()
  await signIn(page, patientEmail, password)
  await expect(page).toHaveURL(/\/patient/)
  await page.goto('/patient/consultas')
  await expect(page.locator('span').filter({ hasText: 'Confirmada' })).toBeVisible()
  await page.goto('/patient/saude')
  await page.getByRole('tab', { name: 'Registos clínicos' }).click()
  await expect(page.getByText('Conteúdo clínico sintético atualizado.')).toBeVisible()
  await page.goto('/patient/notificacoes')
  await expect(page.getByText('Consulta confirmada')).toBeVisible()
  await page.getByRole('button', { name: 'Marcar como lida' }).first().click()
  await expect(page.getByLabel('1 não lidas nesta página')).toBeVisible()
  await page.goto('/patient/consentimentos')
  await page.getByLabel('Finalidade').fill('Validação sintética E2E')
  await page.getByRole('button', { name: 'Conceder' }).click()
  await expect(page.getByText('Consentimento concedido e registado no histórico.')).toBeVisible()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Revogar' }).click()
  await expect(page.getByText('Consentimento revogado. O histórico foi preservado.')).toBeVisible()
  await page.getByRole('button', { name: 'Sair' }).click()
  await expect(page).toHaveURL(/\/login/)

  await signIn(page, patientEmail, password)
  await expect(page).toHaveURL(/\/patient/)
  await page.context().clearCookies()
  await page.goto('/patient/consultas')
  await expect(page).toHaveURL(/\/login/)

  if (doctorMfa) {
    // MFA end to end in the merged frontend: no session after the password alone; a wrong code is
    // refused; a recovery code signs in exactly once.
    await signIn(page, staffEmail, doctorPassword)
    await expect(page.getByRole('heading', { name: 'Verificação em dois passos' })).toBeVisible()
    expect((await page.request.get('/api/v1/auth/me')).status()).toBe(401)
    const step = Math.floor(Date.now() / 30_000)
    const valid = [step - 1, step, step + 1].map((candidate) => totp(doctorMfa!.secret, candidate))
    await answerSecondFactor(page, ['000000', '111111', '222222', '333333'].find((code) => !valid.includes(code))!)
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveURL(/\/login/)
    await page.getByRole('button', { name: 'Voltar' }).click()

    const [recovery] = doctorMfa.recovery
    await signIn(page, staffEmail, doctorPassword)
    await answerSecondFactor(page, recovery)
    await expect(page).toHaveURL(/\/app/)
    expect((await (await page.request.get('/api/v1/auth/me')).json() as { email: string }).email).toBe(staffEmail)
    await page.getByRole('button', { name: 'Sair' }).click()

    await signIn(page, staffEmail, doctorPassword)
    await answerSecondFactor(page, recovery)
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveURL(/\/login/)
    expect((await page.request.get('/api/v1/auth/me')).status()).toBe(401)
  }
})
