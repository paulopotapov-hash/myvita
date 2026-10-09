import { expect, test } from '@playwright/test'
import { apiAs, apiStatus, loadSeed, openPatientFile, switchRole } from './support'

// Rewritten at integration (Phase 6) for the merged documents flow (Parent B's DocumentsSection
// plus decisions D2-D5). Parent A's spec covered notes and versions, which were accepted as lost.
const seed = loadSeed()
const title = 'Relatório pós-operatório E2E'
const pdf = { name: 'relatorio-e2e.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\nE2E document\n%%EOF\n') }

test.describe.serial('clinical documents', () => {
  let documentId = ''

  test.beforeAll(async () => {
    await apiAs('clinic_admin', 'POST', `/api/v1/patients/${seed.patientIds.patient}/care-team`, {
      staff_id: seed.staffIds.doctor,
    }, [409])
  })

  test('staff upload a document with a title; the uploader is shown by name and nothing can delete it', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    await openPatientFile(page, seed.names.patient, 'Documentos')
    const panel = page.getByRole('tabpanel', { name: 'Documentos' })

    // D5: a title is required before anything is sent.
    await panel.getByLabel(/Novo documento/).setInputFiles(pdf)
    await panel.getByRole('button', { name: 'Carregar documento' }).click()
    await expect(panel.getByText('Indica um título para o documento.')).toBeVisible()

    await panel.getByLabel('Título do documento').fill(title)
    const uploaded = page.waitForResponse((response) => response.url().includes(`/patients/${seed.patientIds.patient}/documents`) && response.request().method() === 'POST')
    await panel.getByRole('button', { name: 'Carregar documento' }).click()
    documentId = ((await (await uploaded).json()) as { id: string }).id
    await expect(panel.getByRole('status')).toContainText(`“${title}” carregado com sucesso`)

    const row = panel.getByRole('listitem').filter({ hasText: title })
    await expect(row).toContainText('relatorio-e2e.pdf')
    // D2: the uploader's display name, never an internal id.
    await expect(row).toContainText(`Carregado por ${seed.names.doctor}`)
    // D3: append-only. No delete control in the UI and no delete route in the API.
    await expect(panel.getByRole('button', { name: /Eliminar/ })).toHaveCount(0)
    expect([404, 405]).toContain(await apiStatus('doctor', 'DELETE', `/api/v1/documents/${documentId}`))
    await page.reload()
    await page.getByRole('tab', { name: 'Documentos' }).click()
    await expect(page.getByRole('tabpanel', { name: 'Documentos' }).getByText(title)).toBeVisible()
  })

  test('the patient is notified generically and the deep link opens that document', async ({ page }) => {
    await switchRole(page.context(), 'patient')
    await page.goto('/patient/notificacoes')
    const notification = page.getByRole('listitem').filter({ hasText: 'Novo documento' }).first()
    // D4: generic text only; the title stays inside the access-controlled documents area.
    await expect(notification).not.toContainText(title)
    await notification.getByRole('link', { name: 'Abrir documento' }).click()

    await expect(page).toHaveURL(new RegExp(`/patient/documentos\\?document=${documentId}$`))
    const linked = page.locator('li[aria-current="true"]')
    await expect(linked).toContainText(title)
    await expect(linked).toBeFocused()
    await expect(page.getByRole('form', { name: 'Carregar documento' })).toHaveCount(0)
    await page.setViewportSize({ width: 320, height: 800 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  })

  test('another patient of the same clinic cannot download the document', async () => {
    expect(await apiStatus('other_patient', 'GET', `/api/v1/documents/${documentId}/download`)).toBe(404)
    expect(await apiStatus('patient', 'GET', `/api/v1/documents/${documentId}/download`)).toBe(200)
  })
})
