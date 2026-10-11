import { expect, test } from '@playwright/test'
import { authState, expectNoHorizontalOverflow, loadSeed, seedAppointment } from './support'

// Patient home (mobile first): greeting, shortcut grid and highlight cards, at 375px.
const seed = loadSeed()

test.describe('patient home', () => {
  test.use({ storageState: authState('patient'), viewport: { width: 375, height: 812 } })

  test.beforeAll(async () => {
    await seedAppointment(2, 'Consulta inicial E2E')
  })

  test('greets by first name and lays the six shortcuts out three per row', async ({ page }) => {
    await page.goto('/patient')
    await expect(page.getByRole('heading', { level: 1, name: `Olá, ${seed.names.patient.split(' ')[0]}!` })).toBeVisible()
    const tiles = page.getByRole('navigation', { name: 'Atalhos' }).getByRole('link')
    await expect(tiles).toHaveCount(6)
    const tops = await Promise.all((await tiles.all()).map(async (tile) => Math.round((await tile.boundingBox())!.y)))
    expect(new Set(tops.slice(0, 3)).size).toBe(1)
    expect(new Set(tops.slice(3)).size).toBe(1)
    expect(tops[3]).toBeGreaterThan(tops[0])
    for (const tile of await tiles.all()) {
      const box = (await tile.boundingBox())!
      expect(box.height).toBeGreaterThanOrEqual(44)
    }
    await expectNoHorizontalOverflow(page, 'patient home @ 375px')
  })

  test('shows the next appointment and opens its detail', async ({ page }) => {
    await page.goto('/patient')
    const card = page.getByRole('region', { name: 'Próxima consulta' })
    await expect(card).toContainText(`Com ${seed.names.doctor}`)
    await card.getByRole('link', { name: 'Ver detalhes' }).click()
    await expect(page).toHaveURL(/\/patient\/consultas\?consulta=/)
    await expect(page.getByRole('dialog')).toContainText(seed.names.doctor)
  })

  test('Marcar consulta lands on the request form, and Medicação on the medication list', async ({ page }) => {
    await page.goto('/patient')
    await page.getByRole('navigation', { name: 'Atalhos' }).getByRole('link', { name: 'Marcar consulta' }).click()
    await expect(page.getByLabel('Data e hora pretendidas')).toBeFocused()

    await page.goto('/patient')
    await page.getByRole('navigation', { name: 'Atalhos' }).getByRole('link', { name: 'Medicação' }).click()
    await expect(page).toHaveURL(/\/patient\/medicacao$/)
    await expect(page.getByRole('heading', { level: 1, name: 'A minha medicação' })).toBeVisible()
  })
})
