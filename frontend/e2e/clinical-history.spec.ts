import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { apiAs, expectNoHorizontalOverflow, loadSeed, openPatientFile, switchRole } from './support'

// Commit 3: clinical history by category, with origin ("Confirmado pelo profissional" /
// "Declarado pelo paciente"), partial dates, hiding from the patient with a reason, and
// the patient's own declarations (history and medication). Synthetic data only.
const seed = loadSeed()

async function expectNoViolations(page: Page, label: string): Promise<void> {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
  expect(violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`), label).toEqual([])
}

async function openHistory(page: Page) {
  await openPatientFile(page, seed.names.patient, 'Histórico')
  return page.getByRole('tabpanel', { name: 'Histórico' })
}

test.describe.serial('clinical history', () => {
  test.beforeAll(async () => {
    await apiAs('clinic_admin', 'POST', `/api/v1/patients/${seed.patientIds.patient}/care-team`, {
      staff_id: seed.staffIds.doctor,
    }, [409])
  })

  test('the doctor records an allergy and a condition with a partial date, confirmed at once', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    const panel = await openHistory(page)

    const allergies = panel.getByRole('region', { name: 'Alergias' })
    await allergies.getByRole('button', { name: 'Adicionar alergia' }).click()
    await allergies.getByLabel('Substância', { exact: true }).fill('Penicilina E2E')
    await allergies.getByLabel('Reação (opcional)').fill('Urticária')
    await allergies.getByLabel('Gravidade').selectOption({ label: 'Grave' })
    await allergies.getByRole('button', { name: 'Adicionar alergia' }).click()
    const allergy = allergies.getByRole('listitem').filter({ hasText: 'Penicilina E2E' })
    await expect(allergy).toContainText('Confirmado pelo profissional')

    const conditions = panel.getByRole('region', { name: 'Doenças e problemas de saúde' })
    await conditions.getByRole('button', { name: 'Adicionar doença ou problema' }).click()
    await conditions.getByLabel('Doença ou problema', { exact: true }).fill('Asma E2E')
    await conditions.getByLabel('Estado').selectOption({ label: 'Ativa' })
    await conditions.getByLabel('Início: precisão').selectOption({ label: 'Mês e ano' })
    await conditions.getByLabel('Início: mês').fill('2010-03')
    await conditions.getByRole('button', { name: 'Adicionar doença ou problema' }).click()
    await expect(conditions.getByRole('listitem').filter({ hasText: 'Asma E2E' })).toContainText('Início março 2010')
    await expectNoViolations(page, 'staff history tab')
  })

  test('the patient sees them, declares a vaccine and medication, at 375px', async ({ page }) => {
    await switchRole(page.context(), 'patient')
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/patient/saude')
    await expect(page.getByRole('region', { name: 'Alergias conhecidas' })).toContainText('Penicilina E2E · Grave')
    await expect(page.getByRole('region', { name: 'Doenças e problemas de saúde' })).toContainText('Asma E2E')

    const vaccines = page.getByRole('region', { name: 'Vacinas' })
    await vaccines.getByRole('button', { name: 'Declarar vacina' }).click()
    await vaccines.getByLabel('Vacina', { exact: true }).fill('Gripe E2E')
    await vaccines.getByLabel('Data: ano').fill('2024')
    await vaccines.getByRole('button', { name: 'Declarar vacina' }).click()
    const vaccine = vaccines.getByRole('listitem').filter({ hasText: 'Gripe E2E' })
    await expect(vaccine).toContainText('2024')
    await expect(vaccine).toContainText('Declarado pelo paciente')
    await expect(vaccine.getByRole('button', { name: 'Editar' })).toBeVisible()
    // Nothing the professional confirmed can be changed by the patient.
    await expect(page.getByRole('region', { name: 'Alergias' }).getByRole('button', { name: 'Editar' })).toHaveCount(0)
    await expectNoHorizontalOverflow(page, 'health summary @ 375px')
    await expectNoViolations(page, 'patient health summary with history')

    await page.goto('/patient/medicacao')
    const medication = page.getByRole('region', { name: 'Medicação' })
    await medication.getByLabel('Medicamento').fill('Vitamina D E2E')
    // Only the year is known: it stays "2025", never a fabricated 01/01/2025.
    await medication.getByLabel('Data de início: ano').fill('2025')
    await medication.getByRole('button', { name: 'Declarar medicação' }).click()
    await expect(medication.getByRole('status')).toContainText('Medicação declarada')
    const declared = medication.getByRole('listitem').filter({ hasText: 'Vitamina D E2E' })
    await expect(declared).toContainText('Declarado pelo paciente')
    await expect(declared).toContainText('Início 2025')
  })

  test('the doctor confirms the declarations (completing the dose) and hides an entry with a reason', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    const panel = await openHistory(page)
    const vaccine = panel.getByRole('region', { name: 'Vacinas' }).getByRole('listitem').filter({ hasText: 'Gripe E2E' })
    await vaccine.getByRole('button', { name: 'Confirmar' }).click()
    await expect(vaccine).toContainText('Confirmado pelo profissional')

    const condition = panel.getByRole('region', { name: 'Doenças e problemas de saúde' }).getByRole('listitem').filter({ hasText: 'Asma E2E' })
    await condition.getByRole('button', { name: 'Ocultar ao paciente' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Ocultar ao paciente' })
    await dialog.getByRole('button', { name: 'Ocultar' }).click()
    await expect(dialog.getByText('Indica o motivo.')).toBeVisible()
    await dialog.getByLabel('Motivo').fill('Aguarda conversa presencial E2E')
    await dialog.getByRole('button', { name: 'Ocultar' }).click()
    await expect(condition).toContainText('Oculto ao paciente')
    await expect(condition).toContainText('Motivo para ocultar: Aguarda conversa presencial E2E')

    await page.getByRole('tab', { name: 'Medicamentos' }).click()
    const declared = page.getByRole('region', { name: 'Medicação' }).getByRole('listitem').filter({ hasText: 'Vitamina D E2E' })
    await declared.getByRole('button', { name: 'Confirmar' }).click()
    const confirm = page.getByRole('alertdialog', { name: 'Confirmar medicação' })
    await confirm.getByLabel('Dosagem (opcional)').fill('1000 UI')
    await confirm.getByLabel(/Data de início completa \(opcional\), declarada: 2025/).fill('2025-02-03')
    await confirm.getByRole('button', { name: 'Confirmar' }).click()
    await expect(declared).toContainText('Vitamina D E2E · 1000 UI')
    await expect(declared).toContainText('Início 03/02/2025')
    await expect(declared).toContainText('Confirmado pelo profissional')
  })

  test('the hidden entry disappears for the patient, and the confirmed vaccine is no longer editable', async ({ page }) => {
    await switchRole(page.context(), 'patient')
    await page.goto('/patient/saude')
    await expect(page.getByRole('region', { name: 'Vacinas' })).toContainText('Confirmado pelo profissional')
    await expect(page.getByRole('region', { name: 'Vacinas' }).getByRole('button', { name: 'Editar' })).toHaveCount(0)
    await expect(page.getByRole('region', { name: 'Doenças e problemas de saúde' })).not.toContainText('Asma E2E')
    await expect(page.getByText('Aguarda conversa presencial E2E')).toHaveCount(0)
  })
})
