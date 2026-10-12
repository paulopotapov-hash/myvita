import AxeBuilder from '@axe-core/playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { authState, expectNoHorizontalOverflow, loadSeed } from './support'

// Profile photo with approval: the patient crops and sends a photo on a phone, it shows as
// pending, the associated doctor approves it in the patient file, and it becomes the
// patient's avatar and the file's header image. Synthetic image only.
const seed = loadSeed()
const photo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'fixtures/synthetic-photo.jpg')

async function expectNoViolations(page: Page, label: string): Promise<void> {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
  expect(violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`), label).toEqual([])
}

test.describe('profile photo', () => {
  test.use({ storageState: authState('patient'), viewport: { width: 375, height: 812 } })

  test('sent by the patient, pending, approved by the doctor, then shown', async ({ page, browser }) => {
    await page.goto('/patient/perfil')
    const section = page.getByRole('region', { name: 'Foto de perfil' })
    await expect(section).toContainText('A cores.')
    await expectNoViolations(page, 'profile photo')
    await expectNoHorizontalOverflow(page, 'profile photo @ 375px')

    await page.getByTestId('photo-gallery-input').setInputFiles(photo)
    const dialog = page.getByRole('dialog', { name: 'Recortar a foto' })
    await expect(dialog.getByRole('img', { name: /Pré-visualização do recorte/ })).toBeVisible()
    await dialog.getByLabel('Zoom').fill('1.5')
    await dialog.getByRole('img', { name: /Pré-visualização do recorte/ }).press('ArrowLeft')
    await dialog.getByRole('button', { name: 'Enviar para aprovação' }).click()
    await expect(section).toContainText('Foto enviada. Fica pendente até o teu médico a aprovar.')
    await expect(section.getByText('Pendente de aprovação')).toBeVisible()

    // The associated doctor sees the pending photo in the patient's file and approves it.
    const clinic = await browser.newContext({ storageState: authState('doctor') })
    const staffPage = await clinic.newPage()
    await staffPage.goto(`/app/pacientes/${seed.patientIds.patient}`)
    const card = staffPage.getByRole('region', { name: 'Foto de perfil por aprovar' })
    await expect(card).toBeVisible()
    await expectNoViolations(staffPage, 'photo review card')
    await card.getByRole('button', { name: 'Aprovar' }).click()
    await expect(card).toHaveCount(0)
    const header = staffPage.locator('h1', { hasText: seed.names.patient }).locator('xpath=../..')
    await expect(header.locator('img')).toHaveAttribute('src', /\/api\/v1\/patient-photos\/[0-9a-f-]{36}\/image$/)
    await clinic.close()

    await page.reload()
    await expect(section.getByText('Foto atual')).toBeVisible()
    await expect(section.getByText('Pendente de aprovação')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Menu da conta' }).locator('img')).toBeVisible()
  })
})
