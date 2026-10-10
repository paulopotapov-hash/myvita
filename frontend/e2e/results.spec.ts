import { expect, test } from '@playwright/test'
import { apiAs, apiStatus, loadSeed, openPatientFile, switchRole } from './support'

// P2.4-P2.6: a professional records a result as a draft, releases it, and the patient is
// notified generically; the deep link opens the result through the normal, authorized API.
const seed = loadSeed()
const title = 'Ferritina E2E'
const value = '412'

test.describe.serial('clinical results', () => {
  let resultId = ''

  test.beforeAll(async () => {
    await apiAs('clinic_admin', 'POST', `/api/v1/patients/${seed.patientIds.patient}/care-team`, {
      staff_id: seed.staffIds.doctor,
    }, [409])
  })

  test('a doctor records a draft, which the patient cannot see yet', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    await openPatientFile(page, seed.names.patient, 'Resultados')
    const panel = page.getByRole('tabpanel', { name: 'Resultados' })
    const form = panel.getByRole('form', { name: 'Registar resultado' })

    await form.getByRole('button', { name: 'Registar resultado' }).click()
    await expect(form.getByText('Indica a designação do resultado.')).toBeVisible()

    await form.getByLabel(/Designação/).fill(title)
    await form.getByLabel('Valor').fill(value)
    await form.getByLabel('Unidade').fill('ng/mL')
    await form.getByLabel('Intervalo de referência').fill('30-400')
    await form.getByLabel(/Data do resultado/).fill('2026-09-01')
    const created = page.waitForResponse((response) => response.url().includes(`/patients/${seed.patientIds.patient}/results`) && response.request().method() === 'POST')
    await form.getByRole('button', { name: 'Registar resultado' }).click()
    resultId = ((await (await created).json()) as { id: string }).id
    await expect(panel.getByRole('status')).toHaveText('Resultado guardado como rascunho.')
    await expect(panel.getByRole('listitem').filter({ hasText: title })).toContainText('Rascunho')

    expect(await apiStatus('patient', 'GET', `/api/v1/results/${resultId}`)).toBe(404)
  })

  test('the doctor releases it after confirmation', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    await openPatientFile(page, seed.names.patient, 'Resultados')
    const panel = page.getByRole('tabpanel', { name: 'Resultados' })
    const row = panel.getByRole('listitem').filter({ hasText: title })
    await row.getByRole('button', { name: 'Disponibilizar' }).click()
    await page.getByRole('alertdialog', { name: 'Disponibilizar resultado' }).getByRole('button', { name: 'Disponibilizar' }).click()
    await expect(panel.getByRole('status')).toHaveText('Resultado disponibilizado ao paciente.')
    await expect(row).toContainText('Disponibilizado')
    await expect(row.getByRole('button', { name: 'Editar' })).toHaveCount(0)
  })

  test('the patient is notified generically and the deep link opens that result', async ({ page }) => {
    await switchRole(page.context(), 'patient')
    await page.goto('/patient/notificacoes')
    const notification = page.getByRole('listitem').filter({ hasText: 'Novo resultado disponível' }).first()
    // No clinical content in the notification.
    await expect(notification).not.toContainText(title)
    await expect(notification).not.toContainText(value)
    await notification.getByRole('link', { name: 'Abrir resultado' }).click()

    await expect(page).toHaveURL(new RegExp(`/patient/resultados\\?result=${resultId}$`))
    const linked = page.locator('li[aria-current="true"]')
    await expect(linked).toContainText(title)
    await expect(linked).toContainText(`${value} ng/mL`)
    await expect(linked).toBeFocused()
    await expect(page.getByRole('form', { name: 'Registar resultado' })).toHaveCount(0)
    await expect(page.getByText('Rascunho')).toHaveCount(0)
    await page.setViewportSize({ width: 320, height: 800 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  })

  test('another patient cannot read the result, and the clinic admin has no clinical access', async () => {
    expect(await apiStatus('other_patient', 'GET', `/api/v1/results/${resultId}`)).toBe(404)
    expect(await apiStatus('clinic_admin', 'GET', `/api/v1/results/${resultId}`)).toBe(403)
    expect(await apiStatus('patient', 'GET', `/api/v1/results/${resultId}`)).toBe(200)
  })

  test('a correction is a new result and the patient keeps the original, marked as corrected', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    await openPatientFile(page, seed.names.patient, 'Resultados')
    const panel = page.getByRole('tabpanel', { name: 'Resultados' })
    const original = panel.getByRole('listitem').filter({ hasText: title }).filter({ hasText: 'Disponibilizado' }).first()
    await original.getByRole('button', { name: 'Registar correção' }).click()
    const form = panel.getByRole('form', { name: 'Registar correção' })
    await form.getByLabel('Valor').fill('214')
    await form.getByRole('button', { name: 'Registar correção' }).click()
    await expect(form.getByText(/Indica o motivo da correção/)).toBeVisible()
    await form.getByLabel(/Motivo da correção/).fill('Erro de transcrição E2E')
    await form.getByRole('checkbox', { name: 'Disponibilizar já ao paciente' }).check()
    await form.getByRole('button', { name: 'Registar correção' }).click()
    await expect(panel.getByRole('status')).toContainText('Correção registada e disponibilizada ao paciente.')
    // The released original stays exactly as released.
    expect(await apiStatus('doctor', 'PATCH', `/api/v1/results/${resultId}`, { value: '1' })).toBe(409)

    await switchRole(page.context(), 'patient')
    await page.goto('/patient/resultados')
    const corrected = page.getByRole('listitem').filter({ hasText: 'Corrigido' }).first()
    await expect(corrected).toContainText(`${value} ng/mL`)
    await expect(page.getByRole('listitem').filter({ hasText: '214 ng/mL' }).first()).toContainText('Correção')
    await expect(page.getByText('Erro de transcrição E2E')).toHaveCount(0)
  })
})
