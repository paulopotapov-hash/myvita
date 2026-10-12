import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { authState, expectNoHorizontalOverflow, loadSeed, seedNurseBooking } from './support'

// Scheduling, step 4: the patient books a free slot in five steps on a phone, and only
// sees it as booked after the server confirms it. Synthetic data only.
const seed = loadSeed()

async function expectNoViolations(page: Page, label: string): Promise<void> {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
  expect(violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`), label).toEqual([])
}

test.describe('patient booking', () => {
  test.use({ storageState: authState('patient'), viewport: { width: 375, height: 812 } })

  test.beforeAll(async () => {
    await seedNurseBooking()
  })

  test('books a free slot in five steps and sees it confirmed', async ({ page }) => {
    await page.goto('/patient')
    await page.getByRole('navigation', { name: 'Atalhos' }).getByRole('link', { name: 'Marcar consulta' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Marcar consulta' })).toBeVisible()
    await expect(page.getByText('Passo 1 de 5')).toBeVisible()
    await expectNoViolations(page, 'booking step 1')

    await page.getByRole('button', { name: /Consulta de enfermagem E2E/ }).click()
    await page.getByRole('button', { name: /Enfermagem E2E/ }).click()
    await expect(page.getByText('Passo 3 de 5')).toBeVisible()
    await page.getByRole('button', { name: new RegExp(seed.names.nurse) }).click()
    await expect(page.getByText('Passo 4 de 5')).toBeVisible()
    // The last slot shown (about two weeks ahead), so other specs' "next appointment" stays theirs.
    const firstSlot = page.getByRole('button', { name: /, \d{2}:\d{2}/ }).last()
    await expect(firstSlot).toBeVisible()
    await expectNoViolations(page, 'booking slots')
    await expectNoHorizontalOverflow(page, 'booking slots @ 375px')
    await firstSlot.click()

    await expect(page.getByText('Passo 5 de 5')).toBeVisible()
    await expect(page.getByText(seed.names.nurse)).toBeVisible()
    await page.getByLabel('Motivo da consulta (opcional)').fill('Penso E2E')
    await page.getByRole('button', { name: 'Confirmar marcação' }).click()

    await expect(page).toHaveURL(/\/patient\/consultas\/[0-9a-f-]{36}$/)
    await expect(page.getByText('Consulta marcada e confirmada.')).toBeVisible()
    await expect(page.getByRole('heading', { level: 1, name: 'Consulta de enfermagem E2E' })).toBeVisible()
    const details = page.getByRole('region', { name: 'Detalhes da consulta' })
    await expect(details).toContainText('Confirmada')
    await expect(details).toContainText('Penso E2E')
    await expectNoViolations(page, 'appointment detail')

    await page.getByRole('link', { name: 'As minhas consultas' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'As minhas consultas' })).toBeVisible()
    await expect(page.getByRole('tabpanel').getByRole('link').filter({ hasText: 'Consulta de enfermagem E2E' }).first()).toBeVisible()
    await expectNoViolations(page, 'my appointments')
    await expectNoHorizontalOverflow(page, 'my appointments @ 375px')
  })
})
