import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { apiAs, apiGet, authState, expectNoHorizontalOverflow, loadSeed, seedNurseBooking } from './support'

// Scheduling, step 6: a patient joins the waiting list on a phone; when an earlier slot is
// freed they are offered it and take it, and the old appointment is cancelled. Synthetic data only.
const seed = loadSeed()

async function expectNoViolations(page: Page, label: string): Promise<void> {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
  expect(violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`), label).toEqual([])
}

test.describe('waiting list', () => {
  test.use({ storageState: authState('other_patient'), viewport: { width: 375, height: 812 } })

  test('joins, is offered an earlier slot when someone cancels, and takes it', async ({ page }) => {
    const typeId = await seedNurseBooking()
    const today = new Date().toISOString().slice(0, 10)
    const until = new Date(Date.now() + 20 * 86_400_000).toISOString().slice(0, 10)
    const slots = await apiGet<Array<{ starts_at: string }>>(
      'other_patient', `/api/v1/scheduling/slots?appointment_type_id=${typeId}&from=${today}&to=${until}&staff_id=${seed.staffIds.nurse}`,
    )
    const late = await apiAs<{ id: string }>('other_patient', 'POST', '/api/v1/scheduling/bookings', {
      appointment_type_id: typeId, staff_id: seed.staffIds.nurse, starts_at: slots[slots.length - 3].starts_at,
    })

    await page.goto(`/patient/consultas/${late!.id}`)
    const section = page.getByRole('region', { name: 'Lista de espera' })
    await section.getByRole('button', { name: 'Entrar na lista de espera' }).click()
    await expect(section).toContainText('Estás na lista de espera')
    await expectNoViolations(page, 'waiting list joined')

    // Someone else's earlier appointment with the same nurse is cancelled.
    const earlier = await apiAs<{ id: string }>('patient', 'POST', '/api/v1/scheduling/bookings', {
      appointment_type_id: typeId, staff_id: seed.staffIds.nurse, starts_at: slots[slots.length - 6].starts_at,
    })
    await apiAs('patient', 'POST', `/api/v1/scheduling/bookings/${earlier!.id}/cancel`)

    await page.goto('/patient/consultas')
    const offers = page.getByRole('list', { name: 'Vagas oferecidas' })
    await expect(offers).toContainText(seed.names.nurse)
    await expectNoViolations(page, 'waiting list offer')
    await expectNoHorizontalOverflow(page, 'waiting list offer @ 375px')
    await offers.getByRole('button', { name: 'Aceitar vaga' }).click()

    await expect(page.getByText('Consulta antecipada. A anterior foi cancelada.')).toBeVisible()
    await expect(page).not.toHaveURL(new RegExp(late!.id))
    await page.goto(`/patient/consultas/${late!.id}`)
    await expect(page.getByRole('region', { name: 'Detalhes da consulta' })).toContainText('Cancelada')
  })
})
