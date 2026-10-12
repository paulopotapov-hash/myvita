import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { apiAs, apiGet, authState, expectNoHorizontalOverflow, loadSeed, seedNurseBooking } from './support'

// Scheduling, step 5: the patient reschedules and cancels on a phone; a "só por pedido"
// type goes as a request with preferences, the clinic proposes a time and the patient
// accepts it. Synthetic data only.
const seed = loadSeed()
const REQUEST_TYPE = 'Primeira consulta E2E'

async function expectNoViolations(page: Page, label: string): Promise<void> {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
  expect(violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`), label).toEqual([])
}

function lisbonInput(daysAhead: number, hour: number): string {
  const day = new Date(Date.now() + daysAhead * 86_400_000)
  while (day.getUTCDay() === 0 || day.getUTCDay() === 6) day.setUTCDate(day.getUTCDate() + 1)
  return `${day.toISOString().slice(0, 10)}T${String(hour).padStart(2, '0')}:00`
}

test.describe('patient changes and requests', () => {
  test.use({ storageState: authState('patient'), viewport: { width: 375, height: 812 } })
  let typeId = ''

  test.beforeAll(async () => {
    typeId = await seedNurseBooking()
    const specialties = await apiGet<Array<{ id: string; name: string }>>('clinic_admin', '/api/v1/scheduling/specialties')
    const specialtyId = specialties.find((item) => item.name === 'Enfermagem E2E')!.id
    await apiAs('clinic_admin', 'POST', '/api/v1/scheduling/appointment-types', {
      name: REQUEST_TYPE, duration_minutes: 30, specialty_id: specialtyId, booking_mode: 'request',
    }, [409])
  })

  test('reschedules with the same professional, then cancels', async ({ page }) => {
    const today = new Date().toISOString().slice(0, 10)
    const until = new Date(Date.now() + 20 * 86_400_000).toISOString().slice(0, 10)
    const slots = await apiGet<Array<{ starts_at: string }>>(
      'patient', `/api/v1/scheduling/slots?appointment_type_id=${typeId}&from=${today}&to=${until}&staff_id=${seed.staffIds.nurse}`,
    )
    // Far from "now" and from the other booking spec's slot (the last one shown).
    const booked = await apiAs<{ id: string }>('patient', 'POST', '/api/v1/scheduling/bookings', {
      appointment_type_id: typeId, staff_id: seed.staffIds.nurse, starts_at: slots[Math.floor(slots.length / 2)].starts_at,
    })

    await page.goto(`/patient/consultas/${booked!.id}`)
    const actions = page.getByRole('region', { name: 'Alterar a consulta' })
    await expect(actions).toContainText('Podes cancelar ou remarcar na app até')
    await expectNoViolations(page, 'detail with actions')
    await actions.getByRole('link', { name: 'Remarcar' }).click()

    await expect(page.getByRole('heading', { level: 1, name: 'Remarcar consulta' })).toBeVisible()
    await page.getByRole('button', { name: new RegExp(`Com ${seed.names.nurse}`) }).click()
    // A slot well beyond the 24-hour deadline, so the moved appointment can still be cancelled.
    const slot = page.getByRole('button', { name: /, \d{2}:\d{2}/ }).last()
    await expect(slot).toBeVisible()
    await expectNoHorizontalOverflow(page, 'reschedule slots @ 375px')
    await slot.click()
    await expect(page.getByText('A consulta atual é cancelada ao confirmar.')).toBeVisible()
    await page.getByRole('button', { name: 'Confirmar remarcação' }).click()

    await expect(page.getByText('Consulta remarcada. A anterior foi cancelada.')).toBeVisible()
    await expect(page).not.toHaveURL(new RegExp(booked!.id))
    await page.getByRole('region', { name: 'Alterar a consulta' }).getByRole('button', { name: 'Cancelar consulta' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Cancelar a consulta?' })
    await dialog.getByRole('button', { name: 'Cancelar consulta' }).click()
    await expect(page.getByText('Consulta cancelada. O horário ficou livre.')).toBeVisible()
    await expect(page.getByRole('region', { name: 'Detalhes da consulta' })).toContainText('Cancelada')
    await expect(page.getByRole('region', { name: 'Alterar a consulta' })).toHaveCount(0)
  })

  test('requests a "só por pedido" type, the clinic proposes and the patient accepts', async ({ page, browser }) => {
    await page.goto('/patient/consultas/marcar')
    await page.getByRole('button', { name: new RegExp(REQUEST_TYPE) }).click()
    await page.getByRole('button', { name: /Enfermagem E2E/ }).click()
    await page.getByRole('button', { name: /Qualquer disponível/ }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'Preferências' })).toBeVisible()
    await page.getByRole('radio', { name: 'Manhã' }).check()
    await expectNoViolations(page, 'request preferences')
    await expectNoHorizontalOverflow(page, 'request preferences @ 375px')
    await page.getByRole('button', { name: 'Continuar' }).click()
    await page.getByRole('button', { name: 'Enviar pedido' }).click()
    await expect(page.getByText('Pedido enviado. A clínica responde na app')).toBeVisible()
    await expect(page.getByRole('list', { name: 'Pedidos em curso' })).toContainText(REQUEST_TYPE)

    // The clinic proposes a time, from its own screen.
    const clinic = await browser.newContext({ storageState: authState('clinic_admin') })
    const staffPage = await clinic.newPage()
    await staffPage.goto('/app/consultas')
    const pending = staffPage.getByRole('list', { name: 'Pedidos de consulta pendentes' }).getByRole('listitem').filter({ hasText: REQUEST_TYPE }).first()
    await pending.getByRole('button', { name: 'Propor horário…' }).click()
    const form = staffPage.getByRole('form', { name: `Propor horário a ${seed.names.patient}` })
    await form.getByLabel('Profissional').selectOption(seed.staffIds.nurse)
    await form.getByLabel('Data e hora').fill(lisbonInput(25, 16))
    await form.getByRole('button', { name: 'Enviar proposta' }).click()
    await expect(staffPage.getByRole('list', { name: 'Propostas à espera do paciente' })).toContainText(REQUEST_TYPE)
    await clinic.close()

    await page.reload()
    const open = page.getByRole('list', { name: 'Pedidos em curso' })
    await expect(open).toContainText('A clínica propõe:')
    await expect(open).toContainText(seed.names.nurse)
    await expectNoViolations(page, 'proposal')
    await open.getByRole('button', { name: 'Aceitar proposta' }).first().click()
    await expect(page.getByText(/Pedidos anteriores/)).toBeVisible()
    await expect(page.getByRole('tabpanel').getByRole('link').filter({ hasText: REQUEST_TYPE }).first()).toBeVisible()
  })
})
