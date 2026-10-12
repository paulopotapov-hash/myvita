import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { loadSeed, switchRole } from './support'

// Scheduling, step 3: the clinic configures specialties, appointment types and a doctor's
// weekly schedule; the doctor blocks an absence and the free slots shrink accordingly.
const seed = loadSeed()

async function expectNoViolations(page: Page, label: string): Promise<void> {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
  expect(violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`), label).toEqual([])
}

function nextMonday(): string {
  const day = new Date()
  day.setDate(day.getDate() + 7)
  while (day.getDay() !== 1) day.setDate(day.getDate() + 1)
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
}

test.describe.serial('scheduling configuration', () => {
  test('the clinic administrator configures a specialty, a type and the doctor weekly schedule', async ({ page }) => {
    await switchRole(page.context(), 'clinic_admin')
    await page.goto('/app/agendas')
    await expect(page.getByRole('heading', { level: 1, name: 'Agendas e marcações' })).toBeVisible()

    const specialties = page.getByRole('region', { name: 'Especialidades' })
    await specialties.getByLabel('Nova especialidade').fill('Medicina Geral E2E')
    await specialties.getByRole('button', { name: 'Adicionar especialidade' }).click()
    await expect(specialties.getByText('Medicina Geral E2E')).toBeVisible()

    const typeForm = page.getByRole('form', { name: 'Novo tipo de consulta' })
    await typeForm.getByLabel('Nome do tipo').fill('Consulta de rotina E2E')
    await typeForm.getByLabel('Duração (minutos)').fill('30')
    await typeForm.getByLabel('Especialidade').selectOption({ label: 'Medicina Geral E2E' })
    await typeForm.getByRole('button', { name: 'Adicionar tipo de consulta' }).click()
    await expect(page.getByRole('region', { name: 'Tipos de consulta' }).getByRole('cell', { name: 'Consulta de rotina E2E', exact: true })).toBeVisible()

    const professionals = page.getByRole('region', { name: 'Profissionais e agenda semanal' })
    await professionals.getByLabel('Profissional').selectOption({ label: seed.names.doctor })
    const profile = professionals.getByRole('form', { name: 'Perfil de marcação' })
    await profile.getByLabel('Especialidade do profissional').selectOption({ label: 'Medicina Geral E2E' })
    await profile.getByRole('button', { name: 'Guardar perfil' }).click()
    await expect(profile.getByText('Perfil guardado.')).toBeVisible()

    const schedule = professionals.getByRole('form', { name: 'Agenda semanal' })
    await schedule.getByRole('button', { name: 'Adicionar bloco' }).click()
    await expect(schedule.getByRole('checkbox', { name: 'Consulta de rotina E2E' })).toBeChecked()
    await schedule.getByRole('button', { name: 'Guardar agenda semanal' }).click()
    await expect(schedule.getByText('Agenda semanal guardada.')).toBeVisible()
    await expectNoViolations(page, 'scheduling admin page')
  })

  test('the doctor sees their week and blocks an absence that removes free slots', async ({ page }) => {
    await switchRole(page.context(), 'doctor')
    const monday = nextMonday()
    const types = await (await page.request.get('/api/v1/scheduling/appointment-types')).json() as Array<{ id: string; name: string }>
    const typeId = types.find((type) => type.name === 'Consulta de rotina E2E')!.id
    const slotsUrl = `/api/v1/scheduling/slots?appointment_type_id=${typeId}&from=${monday}&to=${monday}&staff_id=${seed.staffIds.doctor}`
    const before = await (await page.request.get(slotsUrl)).json() as unknown[]
    expect(before).toHaveLength(6)

    await page.goto('/app/agenda')
    await expect(page.getByRole('heading', { level: 1, name: 'A minha agenda' })).toBeVisible()
    await page.getByLabel('Início').fill(`${monday}T09:00`)
    await page.getByLabel('Fim').fill(`${monday}T10:00`)
    await page.getByRole('button', { name: 'Bloquear' }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Ausência registada.' })).toBeVisible()
    await expectNoViolations(page, 'my agenda page')

    const after = await (await page.request.get(slotsUrl)).json() as unknown[]
    expect(after).toHaveLength(4)
  })
})
