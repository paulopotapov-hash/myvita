import { expect, test } from '@playwright/test'
import { authState, futureSlot, loadSeed } from './support'

const seed = loadSeed()

async function fillAppointment(page: import('@playwright/test').Page, slot: string, reason: string) {
  await page.getByLabel('Paciente').selectOption({ label: seed.names.patient })
  await page.getByLabel('Profissional').selectOption({ label: seed.names.doctor })
  await page.getByLabel('Data e hora').fill(slot)
  await page.getByLabel('Motivo (opcional)').fill(reason)
}

test.describe.serial('appointments', () => {
  test.describe('as a doctor', () => {
    test.use({ storageState: authState('doctor') })

    test('shows validation errors next to the fields and focuses the first invalid one', async ({ page }) => {
      await page.goto('/app/consultas')
      await page.getByRole('button', { name: 'Marcar consulta' }).click()

      await expect(page.getByText('Escolhe um paciente.')).toBeVisible()
      await expect(page.getByText('Escolhe um profissional.')).toBeVisible()
      await expect(page.getByText('Escolhe data e hora.')).toBeVisible()
      await expect(page.getByLabel('Paciente')).toBeFocused()
      await expect(page.getByLabel('Paciente')).toHaveAccessibleDescription('Escolhe um paciente.')

      await fillAppointment(page, futureSlot(30), 'E2E validação')
      await page.getByLabel('Duração (minutos)').fill('3')
      await page.getByRole('button', { name: 'Marcar consulta' }).click()
      await expect(page.getByText('A duração mínima é de 5 minutos.')).toBeVisible()
      await expect(page.getByLabel('Duração (minutos)')).toBeFocused()
    })

    test('creates, views, updates and cancels an appointment', async ({ page }) => {
      const reason = 'E2E consulta anual'
      await page.goto('/app/consultas')
      await fillAppointment(page, futureSlot(30), reason)
      await page.getByRole('button', { name: 'Marcar consulta' }).click()
      await expect(page.getByRole('status').filter({ hasText: 'Consulta marcada com sucesso.' })).toBeVisible()

      const row = page.getByRole('listitem').filter({ hasText: reason })
      await expect(row).toBeVisible()
      await expect(row.getByText('Agendada')).toBeVisible()

      // View and update
      await row.getByRole('button', { name: 'Detalhes' }).click()
      const dialog = page.getByRole('dialog', { name: 'Detalhe da consulta' })
      await expect(dialog).toBeFocused()
      await expect(dialog.getByText(seed.names.patient)).toBeVisible()
      await dialog.getByLabel('Duração (minutos)').fill('2')
      await dialog.getByRole('button', { name: 'Guardar alterações' }).click()
      await expect(dialog.getByText('A duração mínima é de 5 minutos.')).toBeVisible()
      await dialog.getByLabel('Duração (minutos)').fill('45')
      await dialog.getByRole('button', { name: 'Guardar alterações' }).click()
      await expect(dialog).toBeHidden()
      await expect(page.getByRole('status').filter({ hasText: 'Consulta atualizada.' })).toBeVisible()
      await expect(row.getByRole('button', { name: 'Detalhes' })).toBeFocused()

      await row.getByRole('button', { name: 'Detalhes' }).click()
      await expect(page.getByRole('dialog').getByLabel('Duração (minutos)')).toHaveValue('45')

      // Cancel (confirmation required)
      page.once('dialog', (confirm) => confirm.accept())
      await page.getByRole('dialog').getByRole('button', { name: 'Cancelar consulta' }).click()
      await expect(page.getByRole('status').filter({ hasText: 'Consulta cancelada.' })).toBeVisible()
      await expect(row.getByText('Cancelada')).toBeVisible()
      await row.getByRole('button', { name: 'Detalhes' }).click()
      await expect(page.getByRole('button', { name: 'Cancelar consulta' })).toHaveCount(0)
    })

    test('reports a double booking with the backend message and keeps the form', async ({ page }) => {
      await page.goto('/app/consultas')
      await fillAppointment(page, futureSlot(31), 'E2E primeira')
      await page.getByRole('button', { name: 'Marcar consulta' }).click()
      await expect(page.getByRole('status').filter({ hasText: 'Consulta marcada com sucesso.' })).toBeVisible()

      await fillAppointment(page, futureSlot(31, 9, 15), 'E2E sobreposta')
      await page.getByRole('button', { name: 'Marcar consulta' }).click()
      await expect(page.getByRole('alert').filter({ hasText: 'consulta sobreposta' })).toBeVisible()
      await expect(page.getByLabel('Motivo (opcional)')).toHaveValue('E2E sobreposta')
    })
  })

  test.describe('as the patient', () => {
    test.use({ storageState: authState('patient') })

    test('sees only their own appointments and cannot create or change them', async ({ page }) => {
      await page.goto('/app/consultas')
      await expect(page.getByRole('heading', { name: 'Consultas', level: 1 })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Marcar consulta' })).toHaveCount(0)
      const row = page.getByRole('listitem').filter({ hasText: 'E2E primeira' })
      await expect(row).toBeVisible()

      await row.getByRole('button', { name: 'Detalhes' }).click()
      const dialog = page.getByRole('dialog', { name: 'Detalhe da consulta' })
      await expect(dialog.getByRole('button', { name: 'Guardar alterações' })).toHaveCount(0)
      await expect(dialog.getByRole('button', { name: 'Cancelar consulta' })).toHaveCount(0)
      await page.keyboard.press('Escape')
      await expect(dialog).toBeHidden()
    })
  })
})
