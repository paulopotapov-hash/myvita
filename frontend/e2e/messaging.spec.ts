import { expect, test } from '@playwright/test'
import { apiAs, apiStatus, loadSeed, switchRole } from './support'

// Rewritten at integration (Phase 6) for the merged messaging model: Parent B's one-to-one
// threads with decisions M1-M6. Parent A's spec covered the shared inbox, subject, status and
// escalation, which are on the post-pilot roadmap.
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

  test('a professional whose assignment ended is denied and the thread turns read-only for the patient', async ({ page }) => {
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

    // M2: the patient keeps the history but cannot write into a thread nobody can read.
    await switchRole(page.context(), 'patient')
    await page.goto(`/patient/mensagens/${nurseThread}`)
    await expect(page.getByText('Mensagem da enfermagem E2E.')).toBeVisible()
    await expect(
      page.getByRole('status').filter({ hasText: 'Esta conversa já não está activa. Para continuar, contacte a clínica.' }),
    ).toBeVisible()
    await expect(page.getByLabel('Mensagem', { exact: true })).toHaveCount(0)
    expect(await apiStatus('patient', 'POST', `/api/v1/conversations/${nurseThread}/messages`, { body: 'Olá?' })).toBe(403)

    // The doctor's thread with the same patient is unaffected.
    await page.goto(`/patient/mensagens/${doctorThread}`)
    await expect(page.getByLabel('Mensagem', { exact: true })).toBeVisible()
  })
})
