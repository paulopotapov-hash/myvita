import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import type { BrowserContext } from '@playwright/test'
import { apiAs, authState, loadSeed } from './support'

const seed = loadSeed()
const title = 'Instruções pós-operatórias E2E'

async function switchRole(context: BrowserContext, role: 'doctor' | 'patient' | 'other_patient') {
  const state = JSON.parse(readFileSync(authState(role), 'utf-8')) as { cookies: Parameters<BrowserContext['addCookies']>[0] }
  await context.clearCookies()
  await context.addCookies(state.cookies)
}

test.describe.serial('clinical documents', () => {
  test.beforeAll(async () => {
    await apiAs('clinic_admin', 'POST', `/api/v1/patients/${seed.patientIds.patient}/care-team`, {
      staff_id: seed.staffIds.doctor,
    }, [409])
  })

  test('staff publishes a note, patient opens the notification and sees the current version', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
    const section = page.getByRole('region', { name: 'Documentos' })
    await section.getByLabel('Título da nota').fill(title)
    await section.getByLabel('Conteúdo').fill('Descansar e seguir o plano acordado.')
    await section.getByRole('button', { name: 'Guardar nota' }).click()
    await expect(section.getByText('Descansar e seguir o plano acordado.')).toBeVisible()

    await switchRole(page.context(), 'patient')
    await page.goto('/app/notificacoes')
    await page.getByRole('link', { name: 'Ver documento' }).last().click()
    const patientDocuments = page.getByRole('region', { name: 'Documentos' })
    await expect(patientDocuments.getByText(title)).toBeVisible()
    await expect(patientDocuments.getByText('Descansar e seguir o plano acordado.').first()).toBeVisible()
    await expect(patientDocuments.getByRole('button', { name: 'Nova versão' })).toHaveCount(0)
    await page.setViewportSize({ width: 320, height: 800 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  })

  test('versioning preserves history and an unrelated patient cannot access the document', async ({ page }) => {
    const versionedTitle = `${title} - histórico`
    const created = await apiAs<{ id: string }>('doctor', 'POST', `/api/v1/patients/${seed.patientIds.patient}/documents/notes`, {
      title: versionedTitle,
      content: 'Versão inicial.',
    })
    expect(created?.id).toBeTruthy()
    const docId = created!.id

    await switchRole(page.context(), 'doctor')
    await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
    const section = page.getByRole('region', { name: 'Documentos' })
    await section.getByRole('button', { name: 'Nova versão' }).last().click()
    await section.getByLabel('Conteúdo').fill('Versão atualizada.')
    await section.getByRole('button', { name: 'Guardar nota' }).click()
    await expect(section.getByText('Nota guardada como nova versão.')).toBeVisible()
    await expect(section.getByText('Versão atualizada.')).toBeVisible()
    await section.getByRole('button', { name: `Ver versões de ${versionedTitle}` }).click()
    await expect(section.getByText('Versão inicial.')).toBeVisible()
    await expect(section.getByText('Versão atualizada.')).toBeVisible()

    await switchRole(page.context(), 'other_patient')
    const status = await page.evaluate(async (id) => (await fetch(`/api/v1/documents/${id}`)).status, docId)
    expect(status).toBe(404)
  })
})
