import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import type { BrowserContext } from '@playwright/test'
import { apiAs, authState, loadSeed } from './support'

const seed = loadSeed()
const subject = 'Acompanhamento clínico E2E'

async function switchRole(context: BrowserContext, role: 'doctor' | 'nurse' | 'patient') {
  const state = JSON.parse(readFileSync(authState(role), 'utf-8')) as { cookies: Parameters<BrowserContext['addCookies']>[0] }
  await context.clearCookies()
  await context.addCookies(state.cookies)
}

test.describe('clinical messaging', () => {
  test.beforeAll(async () => {
    for (const staffId of [seed.staffIds.doctor, seed.staffIds.nurse]) {
      await apiAs('clinic_admin', 'POST', `/api/v1/patients/${seed.patientIds.patient}/care-team`, { staff_id: staffId }, [409])
    }
  })

  test('team initiates, patient replies, nurse responds and patient sees sender identity', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    await page.goto('/app/mensagens')
    await page.getByRole('button', { name: 'Nova conversa' }).click()
    await page.getByLabel('Paciente').selectOption(seed.patientIds.patient)
    await page.getByLabel('Assunto').fill(subject)
    await page.getByLabel('Primeira mensagem').fill('Queremos saber como tem corrido a recuperação.')
    await page.getByRole('button', { name: 'Enviar ao paciente' }).click()
    await expect(page.getByText('Queremos saber como tem corrido a recuperação.')).toBeVisible()

    await switchRole(page.context(), 'patient')
    await page.goto('/app/notificacoes')
    await page.getByRole('link', { name: 'Ver mensagem' }).click()
    await expect(page.getByRole('heading', { name: subject })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Nova conversa' })).toHaveCount(0)
    await page.getByLabel('Responder à equipa clínica').fill('A recuperação está a correr bem.')
    await page.getByRole('button', { name: 'Enviar resposta' }).click()

    await switchRole(page.context(), 'nurse')
    await page.goto('/app/mensagens')
    await page.getByRole('button', { name: new RegExp(subject) }).click()
    await expect(page.getByText('A recuperação está a correr bem.')).toBeVisible()
    await expect(page.getByText('Paciente', { exact: true })).toBeVisible()
    await page.getByLabel('Responder à equipa clínica').fill('Obrigada pela atualização. Continuamos disponíveis.')
    await page.getByRole('button', { name: 'Enviar resposta' }).click()

    await switchRole(page.context(), 'patient')
    await page.goto('/app/notificacoes')
    await page.getByRole('link', { name: 'Ver mensagem' }).last().click()
    await expect(page.getByText('Obrigada pela atualização. Continuamos disponíveis.')).toBeVisible()
    await expect(page.getByText(seed.names.nurse)).toBeVisible()
    await expect(page.getByText('Enfermeiro', { exact: true }).last()).toBeVisible()
  })
})
