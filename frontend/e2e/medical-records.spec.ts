import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { apiStatus, authState, loadSeed, openPatientFile } from './support'

const seed = loadSeed()

// Merged UI: Parent A's standalone records section was dead code and is deleted; the live
// section is the inline one in the "Registos clínicos" tab of the patient file.
async function openPatient(page: Page) {
  await openPatientFile(page, seed.names.patient, 'Registos clínicos')
}

function recordsPanel(page: Page) {
  return page.getByRole('tabpanel', { name: 'Registos clínicos' })
}

test.describe.serial('medical records', () => {
  test.describe('as a doctor', () => {
    test.use({ storageState: authState('doctor') })

    test('validates, creates, views and edits a record as a new version', async ({ page }) => {
      await openPatient(page)
      const section = recordsPanel(page)

      await section.getByRole('button', { name: 'Criar registo' }).click()
      await expect(section.getByRole('alert')).toHaveText('Preenche o título e o conteúdo clínico.')
      // Accessibility requirement kept from Parent A: focus moves to the first invalid field.
      await expect(section.getByLabel('Título do registo')).toBeFocused()

      await section.getByLabel('Título do registo').fill('Avaliação inicial E2E')
      await section.getByLabel('Conteúdo clínico').fill('Sem queixas relevantes.')
      // P2.5: shared explicitly; records are internal notes by default.
      await section.getByRole('checkbox', { name: /Partilhar com o paciente/ }).check()
      await section.getByRole('button', { name: 'Criar registo' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Registo clínico guardado.' })).toBeVisible()

      const record = section.getByRole('listitem').filter({ hasText: 'Avaliação inicial E2E' })
      await expect(record).toContainText('Sem queixas relevantes.')
      await expect(record).toContainText('Versão 1')

      await record.getByRole('button', { name: 'Editar' }).click()
      await expect(section.getByLabel('Título do registo')).toHaveValue('Avaliação inicial E2E')
      await expect(record.getByText('Revisões')).toBeVisible()
      await section.getByLabel('Conteúdo clínico').fill('Queixas de cansaço.')
      await section.getByRole('button', { name: 'Guardar alterações' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Registo clínico guardado.' })).toBeVisible()
      await expect(record).toContainText('Queixas de cansaço.')
      await expect(record).toContainText('Versão 2')
      await expect(record).toContainText('Partilhado com o paciente')
    })

    test('keeps an internal note away from the patient', async ({ page }) => {
      await openPatient(page)
      const section = recordsPanel(page)
      await section.getByLabel('Título do registo').fill('Nota interna E2E')
      await section.getByLabel('Conteúdo clínico').fill('Observação só para a equipa.')
      await section.getByRole('button', { name: 'Criar registo' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Registo clínico guardado.' })).toBeVisible()
      await expect(section.getByRole('listitem').filter({ hasText: 'Nota interna E2E' })).toContainText('Nota interna')
    })
  })

  test.describe('sharing decisions', () => {
    test.use({ storageState: authState('doctor') })

    test('shares an internal note explicitly after confirmation, then withdraws it', async ({ page }) => {
      await openPatient(page)
      const section = recordsPanel(page)
      const note = section.getByRole('listitem').filter({ hasText: 'Nota interna E2E' })
      await note.getByRole('button', { name: 'Partilhar com o paciente' }).click()
      const dialog = page.getByRole('alertdialog', { name: 'Partilhar com o paciente' })
      await expect(dialog).toContainText('notificação genérica')
      await dialog.getByRole('button', { name: 'Partilhar' }).click()
      await expect(section.getByRole('status')).toHaveText('Registo partilhado com o paciente.')
      await expect(note).toContainText('Partilhado com o paciente')
      expect(await apiStatus('patient', 'GET', `/api/v1/patients/${seed.patientIds.patient}/medical-records`)).toBe(200)

      await note.getByRole('button', { name: 'Deixar de partilhar' }).click()
      await page.getByRole('alertdialog', { name: 'Deixar de partilhar' }).getByRole('button', { name: 'Deixar de partilhar' }).click()
      await expect(section.getByRole('status')).toHaveText('O paciente deixou de ter acesso a este registo.')
      await expect(note).toContainText('Nota interna')
    })
  })

  test.describe('as the patient', () => {
    test.use({ storageState: authState('patient') })

    test('can read the shared record but not write it, and never sees internal notes', async ({ page }) => {
      // Shared records are part of the patient's "Resumo de saúde" page.
      await page.goto('/patient/saude')
      await expect(page.getByRole('heading', { level: 1, name: 'Resumo de saúde' })).toBeVisible()
      const section = page.getByRole('region', { name: 'Registos clínicos' })
      await expect(section.getByRole('listitem').filter({ hasText: 'Avaliação inicial E2E' })).toBeVisible()
      await expect(section.getByText('Nota interna E2E')).toHaveCount(0)
      await expect(section.getByText('Observação só para a equipa.')).toHaveCount(0)
      await expect(section.getByLabel('Título do registo')).toHaveCount(0)
      await expect(section.getByRole('button', { name: 'Editar' })).toHaveCount(0)
      await expect(section).not.toContainText('Versão')
    })
  })

  test.describe('as the clinic administrator', () => {
    test.use({ storageState: authState('clinic_admin') })

    test('gets only the patient identification, never clinical content', async ({ page }) => {
      await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
      // Administrative roles see the name and identifiers only; the clinical file stays closed (403 in the API).
      await expect(page.getByRole('heading', { level: 1, name: seed.names.patient })).toBeVisible()
      await expect(page.getByRole('region', { name: 'Dados identificativos' })).toBeVisible()
      expect(await apiStatus('clinic_admin', 'GET', `/api/v1/patients/${seed.patientIds.patient}/medical-records`)).toBe(403)
      await expect(page.getByRole('tab', { name: 'Registos clínicos' })).toHaveCount(0)
      await expect(recordsPanel(page)).toHaveCount(0)
      await expect(page.getByText('Avaliação inicial E2E')).toHaveCount(0)
    })
  })
})
