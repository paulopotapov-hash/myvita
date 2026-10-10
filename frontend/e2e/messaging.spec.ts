import { expect, test } from '@playwright/test'
import { apiAs, apiStatus, loadSeed, switchRole } from './support'

// Care-team messaging (docs/clinical-messaging.md): threads opened by staff, shared by the
// patient's active care team (team inbox), nurse escalation, doctor close/reopen, M1-M6.
const seed = loadSeed()
const firstMessage = 'Queremos saber como tem corrido a recuperação.'
const reply = 'A recuperação está a correr bem.'

test.describe.serial('clinical messaging', () => {
  let doctorThread = ''
  let nurseThread = ''

  test.beforeAll(async () => {
    for (const staffId of [seed.staffIds.doctor, seed.staffIds.nurse]) {
      await apiAs('clinic_admin', 'POST', `/api/v1/patients/${seed.patientIds.patient}/care-team`, { staff_id: staffId }, [409])
    }
  })

  test.afterAll(async () => {
    // Leave the shared seed as other specs expect it: the nurse back on the care team.
    await apiAs('clinic_admin', 'POST', `/api/v1/patients/${seed.patientIds.patient}/care-team`, { staff_id: seed.staffIds.nurse }, [409])
  })

  test('staff start a conversation and the patient replies from the notification deep link', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    await page.goto('/app/mensagens')
    await page.getByRole('button', { name: 'Nova conversa' }).click()
    await page.getByLabel('Pesquisar paciente').fill(seed.names.patient)
    await page.getByRole('button', { name: 'Pesquisar', exact: true }).click()
    await page.getByRole('button', { name: `Iniciar conversa com ${seed.names.patient}` }).click()
    await expect(page).toHaveURL(/\/app\/mensagens\/[0-9a-f-]{36}$/)
    doctorThread = page.url().split('/').pop() ?? ''
    await page.getByLabel('Mensagem', { exact: true }).fill(firstMessage)
    await page.getByRole('button', { name: 'Enviar' }).click()
    await expect(page.getByText(firstMessage)).toBeVisible()

    await switchRole(page.context(), 'patient')
    await page.goto('/patient/notificacoes')
    const notification = page.getByRole('listitem').filter({ hasText: 'Nova mensagem' }).first()
    // M6: generic text, never the message body.
    await expect(notification).not.toContainText(firstMessage)
    await notification.getByRole('link', { name: 'Abrir conversa' }).click()
    await expect(page).toHaveURL(new RegExp(`/patient/mensagens/${doctorThread}$`))
    await expect(page.getByText(firstMessage)).toBeVisible()
    await page.getByLabel('Mensagem', { exact: true }).fill(reply)
    await page.getByRole('button', { name: 'Enviar' }).click()
    await expect(page.getByText(reply)).toBeVisible()

    await switchRole(page.context(), 'doctor')
    await page.goto(`/app/mensagens/${doctorThread}`)
    await expect(page.getByText(reply)).toBeVisible()
  })

  test('the patient cannot start a conversation', async ({ page }) => {
    await switchRole(page.context(), 'patient')
    await page.goto('/patient/mensagens')
    await expect(page.getByRole('link', { name: new RegExp(seed.names.doctor) })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Nova conversa' })).toHaveCount(0)
    // M4: the backend refuses it too, and patients never get the staff roster.
    expect(await apiStatus('patient', 'POST', '/api/v1/conversations', { patient_id: seed.patientIds.patient })).toBe(403)
    expect(await apiStatus('patient', 'GET', '/api/v1/staff')).toBe(404)
  })

  test('the care team shares the inbox: a nurse asks for review, a doctor closes and reopens', async ({ page }) => {
    // The nurse sees the doctor's thread and the patient's reply (team inbox).
    await switchRole(page.context(), 'nurse')
    await page.goto(`/app/mensagens/${doctorThread}`)
    await expect(page.getByText(reply)).toBeVisible()
    await page.getByRole('button', { name: 'Pedir revisão médica' }).click()
    await expect(page.getByText(/Revisão médica pedida/).first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Encerrar conversa' })).toHaveCount(0)

    // The doctor is notified generically and closes the conversation after confirming.
    await switchRole(page.context(), 'doctor')
    await page.goto('/app/notificacoes')
    const review = page.getByRole('listitem').filter({ hasText: 'Conversa para revisão médica' }).first()
    await expect(review).not.toContainText(reply)
    await review.getByRole('link', { name: 'Abrir conversa' }).click()
    await expect(page).toHaveURL(new RegExp(`/app/mensagens/${doctorThread}$`))
    await page.getByRole('button', { name: 'Encerrar conversa' }).click()
    await page.getByRole('alertdialog', { name: 'Encerrar conversa' }).getByRole('button', { name: 'Encerrar' }).click()
    await expect(page.getByRole('button', { name: 'Reabrir conversa' })).toBeVisible()

    // Closed is read-only for the patient, enforced by the backend.
    await switchRole(page.context(), 'patient')
    await page.goto(`/patient/mensagens/${doctorThread}`)
    await expect(page.getByRole('status').filter({ hasText: 'Esta conversa foi encerrada pela equipa clínica.' })).toBeVisible()
    await expect(page.getByLabel('Mensagem', { exact: true })).toHaveCount(0)
    await expect(page.getByText(/Revisão médica/)).toHaveCount(0)
    expect(await apiStatus('patient', 'POST', `/api/v1/conversations/${doctorThread}/messages`, { body: 'Olá?' })).toBe(403)

    await switchRole(page.context(), 'doctor')
    await page.goto(`/app/mensagens/${doctorThread}`)
    await page.getByRole('button', { name: 'Reabrir conversa' }).click()
    await expect(page.getByLabel('Mensagem', { exact: true })).toBeVisible()
  })

  test('a professional whose assignment ended loses access; the patient still reaches the remaining team', async ({ page }) => {
    const opened = await apiAs<{ id: string }>('nurse', 'POST', '/api/v1/conversations', { patient_id: seed.patientIds.patient })
    nurseThread = opened!.id
    await apiAs('nurse', 'POST', `/api/v1/conversations/${nurseThread}/messages`, { body: 'Mensagem da enfermagem E2E.' })
    await apiAs('clinic_admin', 'DELETE', `/api/v1/patients/${seed.patientIds.patient}/care-team/${seed.staffIds.nurse}`)

    // M1: the same answer as an unknown conversation, in the API and in the UI.
    expect(await apiStatus('nurse', 'GET', `/api/v1/conversations/${nurseThread}`)).toBe(404)
    expect(await apiStatus('nurse', 'POST', `/api/v1/conversations/${nurseThread}/messages`, { body: 'x' })).toBe(404)
    await switchRole(page.context(), 'nurse')
    await page.goto(`/app/mensagens/${nurseThread}`)
    await expect(page.getByText('Conversa não encontrada')).toBeVisible()
    await page.goto('/app/mensagens')
    await expect(page.getByRole('link', { name: new RegExp(seed.names.patient) })).toHaveCount(0)

    // The doctor is still on the care team, so the patient keeps the history and can still
    // write: the doctor reads it in the team inbox. (With nobody left on the team the thread
    // turns read-only (M2); covered by backend tests, since it would empty the shared seed's team.)
    await switchRole(page.context(), 'patient')
    await page.goto(`/patient/mensagens/${nurseThread}`)
    await expect(page.getByText('Mensagem da enfermagem E2E.')).toBeVisible()
    await expect(page.getByLabel('Mensagem', { exact: true })).toBeVisible()
    expect(await apiStatus('patient', 'POST', `/api/v1/conversations/${nurseThread}/messages`, { body: 'Olá, equipa.' })).toBe(201)
    expect(await apiStatus('doctor', 'GET', `/api/v1/conversations/${nurseThread}`)).toBe(200)

    // The doctor's thread with the same patient is unaffected.
    await page.goto(`/patient/mensagens/${doctorThread}`)
    await expect(page.getByLabel('Mensagem', { exact: true })).toBeVisible()
  })
})
