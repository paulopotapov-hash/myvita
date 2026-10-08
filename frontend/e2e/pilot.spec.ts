import { expect, request, test } from '@playwright/test'

const password = 'E2e-Senha-Forte-123!'

async function csrf(page: import('@playwright/test').Page) {
  const cookie = (await page.context().cookies()).find((item) => item.name === 'myvita_csrf')
  expect(cookie).toBeDefined()
  return { 'X-CSRF-Token': cookie!.value }
}

test('pilot flow and cross-tenant security through browser proxy', async ({ page, baseURL }) => {
  const suffix = Date.now().toString()
  const adminEmail = `admin-${suffix}@example.com`
  const staffEmail = `doctor-${suffix}@example.com`
  const patientEmail = `patient-${suffix}@example.com`

  const seed = await request.newContext({ baseURL })
  const clinicResponse = await seed.post('/api/v1/clinics', { data: {
    clinic_name: `Clínica E2E ${suffix}`,
    admin_full_name: 'Admin E2E',
    admin_email: adminEmail,
    admin_password: password,
  } })
  expect(clinicResponse.status()).toBe(201)
  const clinic = await clinicResponse.json() as { id: string }

  await page.goto('/login')
  await page.getByLabel('Email').fill(adminEmail)
  await page.getByLabel('Palavra-passe').fill(password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL(/\/app/)

  const staffResponse = await page.request.post('/api/v1/staff', {
    headers: await csrf(page),
    data: { full_name: 'Doctor E2E', email: staffEmail, password, staff_role: 'doctor' },
  })
  expect(staffResponse.status()).toBe(201)

  const patientResponse = await seed.post('/api/v1/patients/register', {
    data: { clinic_id: clinic.id, full_name: 'Paciente E2E', email: patientEmail, password },
  })
  expect(patientResponse.status()).toBe(201)
  const patient = await patientResponse.json() as { id: string }
  const otherClinic = await seed.post('/api/v1/clinics', { data: {
    clinic_name: `Outra Clínica ${suffix}`, admin_full_name: 'Outro Admin',
    admin_email: `other-admin-${suffix}@example.com`, admin_password: password,
  } })
  const otherClinicBody = await otherClinic.json() as { id: string }
  const otherPatient = await seed.post('/api/v1/patients/register', { data: {
    clinic_id: otherClinicBody.id, full_name: 'Paciente Outra Clínica',
    email: `other-patient-${suffix}@example.com`, password,
  } })
  const otherPatientBody = await otherPatient.json() as { id: string }
  await seed.dispose()

  await page.getByRole('button', { name: 'Sair' }).click()
  await page.getByLabel('Email').fill(staffEmail)
  await page.getByLabel('Palavra-passe').fill(password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL(/\/app/)
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
  await page.getByLabel('Email').fill(patientEmail)
  await page.getByLabel('Palavra-passe').fill(password)
  await page.getByRole('button', { name: 'Entrar' }).click()
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

  await page.getByLabel('Email').fill(patientEmail)
  await page.getByLabel('Palavra-passe').fill(password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL(/\/patient/)
  await page.context().clearCookies()
  await page.goto('/patient/consultas')
  await expect(page).toHaveURL(/\/login/)
})
