import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { authState, loadSeed, openPatientFile } from './support'

const seed = loadSeed()

async function openPatient(page: Page) {
  await openPatientFile(page, seed.names.patient, 'Medicamentos')
  return page.getByRole('region', { name: 'Medicação' })
}

async function addMedication(section: ReturnType<Page['getByRole']>, name: string, extra: Record<string, string> = {}) {
  await section.getByLabel('Medicamento').fill(name)
  await section.getByLabel('Dosagem').fill('500 mg')
  await section.getByLabel('Data de início').fill('2026-01-15')
  for (const [label, value] of Object.entries(extra)) await section.getByLabel(label).fill(value)
  await section.getByRole('button', { name: 'Adicionar medicação' }).click()
}

test.describe.serial('medications', () => {
  test.describe('as a doctor', () => {
    test.use({ storageState: authState('doctor') })

    test('validates required fields and the date order', async ({ page }) => {
      const section = await openPatient(page)

      await section.getByRole('button', { name: 'Adicionar medicação' }).click()
      await expect(section.getByText('Indica o nome do medicamento.')).toBeVisible()
      await expect(section.getByText('Indica a dosagem.')).toBeVisible()
      await expect(section.getByText('Indica a data de início.')).toBeVisible()
      await expect(section.getByLabel('Medicamento')).toBeFocused()

      await section.getByLabel('Medicamento').fill('Inválida E2E')
      await section.getByLabel('Dosagem').fill('1 mg')
      await section.getByLabel('Data de início').fill('2026-02-10')
      await section.getByLabel('Data de fim (opcional)').fill('2026-02-01')
      await section.getByRole('button', { name: 'Adicionar medicação' }).click()
      await expect(section.getByText('A data de fim não pode ser anterior à data de início.')).toBeVisible()
      await expect(section.getByLabel('Data de fim (opcional)')).toBeFocused()
      await expect(section.getByRole('listitem').filter({ hasText: 'Inválida E2E' })).toHaveCount(0)
    })

    test('creates, views, edits and completes a medication', async ({ page }) => {
      const section = await openPatient(page)
      await addMedication(section, 'Amoxicilina E2E', {
        'Via de administração (opcional)': 'oral',
        'Frequência (opcional)': '8/8h',
        'Instruções (opcional)': 'Tomar após as refeições.',
      })
      await expect(section.getByRole('status').filter({ hasText: 'Medicação adicionada.' })).toBeVisible()

      const row = section.getByRole('listitem').filter({ hasText: 'Amoxicilina E2E' })
      await expect(row).toContainText('500 mg')
      await expect(row).toContainText('Ativa')
      await expect(row).toContainText('Via oral')
      await expect(row).toContainText('8/8h')
      await expect(row).toContainText('Tomar após as refeições.')

      await row.getByRole('button', { name: 'Editar' }).click()
      await expect(section.getByLabel('Medicamento')).toHaveValue('Amoxicilina E2E')
      await section.getByRole('button', { name: 'Guardar alterações' }).click()
      await expect(section.getByText('Não há alterações para guardar.')).toBeVisible()
      await section.getByLabel('Dosagem').fill('250 mg')
      await section.getByRole('button', { name: 'Guardar alterações' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Medicação atualizada.' })).toBeVisible()
      await expect(row).toContainText('250 mg')

      page.once('dialog', (confirm) => confirm.dismiss())
      await row.getByRole('button', { name: 'Concluir' }).click()
      await expect(row).toContainText('Ativa')

      page.once('dialog', (confirm) => confirm.accept())
      await row.getByRole('button', { name: 'Concluir' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Medicação concluída.' })).toBeVisible()
      await expect(row).toContainText('Concluída')
      await expect(row).toContainText('Fim')
      await expect(row.getByRole('button')).toHaveCount(0)
    })

    test('discontinues a medication', async ({ page }) => {
      const section = await openPatient(page)
      await addMedication(section, 'Ibuprofeno E2E')
      const row = section.getByRole('listitem').filter({ hasText: 'Ibuprofeno E2E' })
      page.once('dialog', (confirm) => confirm.accept())
      await row.getByRole('button', { name: 'Descontinuar' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Medicação descontinuada.' })).toBeVisible()
      await expect(row).toContainText('Descontinuada')
    })
  })

  test.describe('as the patient', () => {
    test.use({ storageState: authState('patient') })

    test('sees their medication without any way to change it', async ({ page }) => {
      // Merged UI: the patient's health data is /patient/saude, split into tabs.
      await page.goto('/patient/saude')
      await page.getByRole('tab', { name: 'Medicamentos' }).click()
      const section = page.getByRole('region', { name: 'Medicação' })
      await expect(section.getByRole('listitem').filter({ hasText: 'Amoxicilina E2E' })).toBeVisible()
      await expect(section.getByLabel('Medicamento')).toHaveCount(0)
      await expect(section.getByRole('button')).toHaveCount(0)
    })
  })
})
