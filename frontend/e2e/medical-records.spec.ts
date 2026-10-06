import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { authState, loadSeed } from './support'

const seed = loadSeed()

async function openPatient(page: Page) {
  await page.goto('/app/pacientes')
  await page.getByRole('link', { name: seed.names.patient }).click()
  await expect(page.getByRole('heading', { name: seed.names.patient, level: 1 })).toBeVisible()
}

test.describe.serial('medical records', () => {
  test.describe('as a doctor', () => {
    test.use({ storageState: authState('doctor') })

    test('validates, creates, views and edits a record as a new version', async ({ page }) => {
      await openPatient(page)
      const section = page.getByRole('region', { name: 'Histórico clínico' })

      await section.getByRole('button', { name: 'Criar registo' }).click()
      await expect(section.getByText('Indica o título do registo.')).toBeVisible()
      await expect(section.getByText('Indica o conteúdo clínico.')).toBeVisible()
      await expect(section.getByLabel('Título do registo')).toBeFocused()

      await section.getByLabel('Título do registo').fill('Avaliação inicial E2E')
      await section.getByLabel('Conteúdo clínico').fill('Sem queixas relevantes.')
      await section.getByRole('button', { name: 'Criar registo' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Registo clínico guardado.' })).toBeVisible()

      const record = section.getByRole('listitem').filter({ hasText: 'Avaliação inicial E2E' })
      await expect(record).toContainText('Sem queixas relevantes.')
      await expect(record).toContainText('Versão 1')

      await record.getByRole('button', { name: 'Editar' }).click()
      await expect(section.getByLabel('Título do registo')).toHaveValue('Avaliação inicial E2E')
      await expect(record.getByText('Revisões')).toBeVisible()
      await section.getByLabel('Conteúdo clínico').fill('Queixas de cansaço.')
      await section.getByRole('button', { name: 'Guardar nova versão' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Registo clínico guardado.' })).toBeVisible()
      await expect(record).toContainText('Queixas de cansaço.')
      await expect(record).toContainText('Versão 2')
    })
  })

  test.describe('as the patient', () => {
    test.use({ storageState: authState('patient') })

    test('can read their record but not write it', async ({ page }) => {
      await page.goto('/app/saude')
      const section = page.getByRole('region', { name: 'Histórico clínico' })
      await expect(section.getByRole('listitem').filter({ hasText: 'Avaliação inicial E2E' })).toBeVisible()
      await expect(section.getByLabel('Título do registo')).toHaveCount(0)
      await expect(section.getByRole('button', { name: 'Editar' })).toHaveCount(0)
    })
  })

  test.describe('as the clinic administrator', () => {
    test.use({ storageState: authState('clinic_admin') })

    test('is refused the patient file and gets no clinical content', async ({ page }) => {
      await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
      // The backend answers 403 for the patient record; the page shows that instead of any clinical content.
      await expect(page.getByRole('alert')).toBeVisible()
      await expect(page.getByRole('region', { name: 'Histórico clínico' })).toHaveCount(0)
      await expect(page.getByText('Avaliação inicial E2E')).toHaveCount(0)
    })
  })
})
