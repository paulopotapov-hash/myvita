import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { apiAs, authState, expectNoHorizontalOverflow, loadSeed, switchRole } from './support'

// NIF, NISS and Nº de utente: masked by the server, "Mostrar" through the audited reveal endpoint,
// changed by the care team and administrative roles only; the patient edits phone and address.
// Synthetic identifiers only.
const seed = loadSeed()
const NIF = '123456789'
const NISS = '12345678902'
const SNS = '987654321'

async function expectNoViolations(page: Page, label: string): Promise<void> {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
  expect(violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`), label).toEqual([])
}

test.describe.serial('patient identifiers', () => {
  test.beforeAll(async () => {
    await apiAs('clinic_admin', 'POST', `/api/v1/patients/${seed.patientIds.patient}/care-team`, {
      staff_id: seed.staffIds.doctor,
    }, [409])
  })

  test('the clinic administrator fills them in from the identification page, with check-digit validation', async ({ page }) => {
    await switchRole(page.context(), 'clinic_admin')
    await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
    await expect(page.getByRole('heading', { level: 1, name: seed.names.patient })).toBeVisible()
    await expect(page.getByRole('tablist')).toHaveCount(0)
    const card = page.getByRole('region', { name: 'Dados identificativos' })

    await card.getByRole('button', { name: 'Editar dados identificativos' }).click()
    const form = card.getByRole('form', { name: 'Editar dados identificativos' })
    await form.getByLabel('NIF').fill('123456788')
    await form.getByRole('button', { name: 'Guardar' }).click()
    await expect(form.getByText('NIF inválido: confirma os 9 dígitos.')).toBeVisible()
    await expect(form.getByLabel('NIF')).toBeFocused()

    await form.getByLabel('NIF').fill(NIF)
    await form.getByLabel('NISS').fill(NISS)
    await form.getByLabel('Nº de utente').fill(SNS)
    await form.getByRole('button', { name: 'Guardar' }).click()
    await expect(card.getByRole('status')).toHaveText('Dados identificativos atualizados.')
    await expect(card).toContainText('••••••789')
    await expect(card).not.toContainText(NIF)

    await card.getByRole('button', { name: 'Mostrar dados identificativos' }).click()
    await expect(card).toContainText(NIF)
    await expect(card).toContainText(NISS)
    await expectNoViolations(page, 'administrative identification page')
    await card.getByRole('button', { name: 'Ocultar dados identificativos' }).click()
    await expect(card).not.toContainText(NIF)
  })

  test('a NIF already used in the clinic is refused with a clear message', async ({ page }) => {
    await switchRole(page.context(), 'clinic_admin')
    await page.goto(`/app/pacientes/${seed.patientIds.other_patient}`)
    const card = page.getByRole('region', { name: 'Dados identificativos' })
    await card.getByRole('button', { name: 'Editar dados identificativos' }).click()
    const form = card.getByRole('form', { name: 'Editar dados identificativos' })
    await form.getByLabel('NIF').fill(NIF)
    await form.getByRole('button', { name: 'Guardar' }).click()
    await expect(form.getByRole('alert')).toHaveText('Já existe um paciente nesta clínica com este NIF.')
  })

  test('the assigned doctor sees them masked in Dados pessoais and may edit them', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
    const panel = page.getByRole('tabpanel', { name: 'Dados pessoais' })
    const card = panel.getByRole('region', { name: 'Dados identificativos' })
    await expect(card).toContainText('••••••789')
    await expect(card).toContainText('••••••321')
    await expect(card.getByRole('button', { name: 'Editar dados identificativos' })).toBeVisible()
    await expect(panel.getByLabel('Código postal')).toBeVisible()
  })
})

test.describe('patient profile', () => {
  test.use({ storageState: authState('patient'), viewport: { width: 375, height: 812 } })

  test('the patient reveals but never edits identifiers, and edits the address', async ({ page }) => {
    await page.goto('/patient/perfil')
    const card = page.getByRole('region', { name: 'Dados identificativos' })
    await expect(card).toBeVisible()
    await expect(card.getByRole('button', { name: /Editar/ })).toHaveCount(0)
    await card.getByRole('button', { name: 'Mostrar dados identificativos' }).click()
    await expect(card.getByRole('button', { name: 'Ocultar dados identificativos' })).toBeVisible()

    await page.getByRole('button', { name: 'Editar morada' }).click()
    await page.getByLabel('Rua').fill('Rua Sintética E2E, 1')
    await page.getByLabel('Código postal').fill('1000001')
    await page.getByLabel('Localidade').fill('Lisboa')
    await page.getByRole('button', { name: 'Guardar morada' }).click()
    await expect(page.getByText('O código postal deve ter o formato 0000-000.')).toBeVisible()
    await page.getByLabel('Código postal').fill('1000-001')
    await page.getByRole('button', { name: 'Guardar morada' }).click()
    await expect(page.getByText('Morada atualizada.')).toBeVisible()
    await expect(page.getByText('Rua Sintética E2E, 1, 1000-001 Lisboa')).toBeVisible()
    await expectNoHorizontalOverflow(page, 'patient profile @ 375px')
    await expectNoViolations(page, 'patient profile with identifiers and address')
  })
})
