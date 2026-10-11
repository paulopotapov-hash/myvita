import { expect, test } from '@playwright/test'
import { authState, expectNoHorizontalOverflow } from './support'

// Patient area, one page per section (MyChart style): every URL opens its own page with its
// own title, directly and after navigating in the app. The tabbed patient file is staff-only.
const PAGES = [
  ['/patient/consultas', 'As minhas consultas'],
  ['/patient/resultados', 'Os meus resultados'],
  ['/patient/medicacao', 'A minha medicação'],
  ['/patient/documentos', 'Os meus documentos'],
  ['/patient/saude', 'Resumo de saúde'],
  ['/patient/consentimentos', 'Os meus consentimentos'],
] as const

test.describe('patient section pages', () => {
  test.use({ storageState: authState('patient'), viewport: { width: 375, height: 812 } })

  for (const [path, title] of PAGES) {
    test(`opening ${path} directly shows "${title}"`, async ({ page }) => {
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(title)
      await expect(page).toHaveTitle(`${title} · myVita`)
      await expect(page.getByRole('tablist')).toHaveCount(0)
      await expectNoHorizontalOverflow(page, `${path} @ 375px`)
    })
  }

  test('the menu keeps the page in sync with the URL (Consentimentos → Resultados → Dados clínicos)', async ({ page }) => {
    await page.goto('/patient/consentimentos')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Os meus consentimentos')

    await page.getByRole('button', { name: 'Menu de navegação' }).click()
    await page.getByRole('dialog', { name: 'Menu' }).getByRole('link', { name: 'Resultados' }).click()
    await expect(page).toHaveURL(/\/patient\/resultados$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Os meus resultados')
    await expect(page.getByRole('heading', { name: 'Consentimentos' })).toHaveCount(0)

    await page.getByRole('button', { name: 'Menu de navegação' }).click()
    await page.getByRole('dialog', { name: 'Menu' }).getByRole('link', { name: 'Dados clínicos' }).click()
    await expect(page).toHaveURL(/\/patient\/saude$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Resumo de saúde')

    await page.goBack()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Os meus resultados')
  })

  test('personal data live in the profile; the email and health number are read-only', async ({ page }) => {
    await page.goto('/patient/perfil')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('O meu perfil')
    const personal = page.getByRole('region', { name: 'Dados pessoais' })
    await expect(personal).toContainText('Número de utente')
    await expect(page.getByRole('button', { name: /Editar/ })).toHaveCount(1)
    await expect(page.getByRole('button', { name: 'Editar telefone' })).toBeVisible()
  })

  test('the old records link opens the health summary', async ({ page }) => {
    await page.goto('/patient/registos')
    await expect(page).toHaveURL(/\/patient\/saude$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Resumo de saúde')
  })
})
