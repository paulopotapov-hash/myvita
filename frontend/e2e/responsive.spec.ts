import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import {
  authState,
  expectNoHorizontalOverflow,
  expectViewportOverflowDetectorWorks,
  findOverflowingElements,
  loadSeed,
  seedAppointment,
  seedClinicalContent,
} from './support'

const seed = loadSeed()
const VIEWPORTS = [
  { name: '320px', width: 320, height: 640 },
  { name: '375px', width: 375, height: 667 },
  { name: '390px', width: 390, height: 844 },
  { name: '768px', width: 768, height: 1024 },
  { name: 'desktop', width: 1280, height: 800 },
]
// Set E2E_SCREENSHOTS=1 to write full-page screenshots to test-results/screens for visual review.
const SCREENSHOTS = process.env.E2E_SCREENSHOTS === '1'

async function expectFits(page: Page, label: string): Promise<void> {
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
  await expect(page.getByText('A carregar')).toHaveCount(0)
  await expectNoHorizontalOverflow(page, label)
  expect(await findOverflowingElements(page), `${label}: elements wider than the viewport`).toEqual([])
}

async function capture(page: Page, name: string): Promise<void> {
  if (!SCREENSHOTS) return
  mkdirSync('test-results/screens', { recursive: true })
  await page.screenshot({ path: `test-results/screens/${name}.png`, fullPage: true })
}

test.beforeAll(async () => {
  await seedAppointment(41, 'Responsivo consulta com um motivo longo para testar a quebra de linha em ecrãs pequenos')
  await seedClinicalContent('responsivo')
})

test('the overflow detector itself flags a page that is too wide (canary)', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 })
  await expectViewportOverflowDetectorWorks(page)
})

for (const viewport of VIEWPORTS) {
  test.describe(`viewport ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } })

    test.describe('public pages', () => {
      for (const path of ['/login', '/registo', '/nova-clinica', '/recuperar-acesso']) {
        test(`${path} fits`, async ({ page }) => {
          await page.goto(path)
          await expectFits(page, `${path} @ ${viewport.name}`)
          await capture(page, `${viewport.name}${path.replaceAll('/', '_')}`)
        })
      }
    })

    test.describe('as a doctor', () => {
      test.use({ storageState: authState('doctor') })

      for (const path of ['/app', '/app/consultas', '/app/pacientes', '/app/notificacoes', '/app/seguranca', `/app/pacientes/${seed.patientIds.patient}`]) {
        test(`${path.replace(seed.patientIds.patient, ':id')} fits`, async ({ page }) => {
          await page.goto(path)
          await expectFits(page, `${path} @ ${viewport.name}`)
          await capture(page, `${viewport.name}_doctor${path.replaceAll('/', '_')}`)
        })
      }

      test('the appointment dialog stays inside the viewport and its actions are reachable', async ({ page }) => {
        await page.goto('/app/consultas')
        await page.getByRole('listitem').filter({ hasText: 'Responsivo consulta' }).getByRole('button', { name: 'Detalhes' }).click()
        const dialog = page.getByRole('dialog', { name: 'Detalhe da consulta' })
        await expect(dialog).toBeVisible()
        const box = await dialog.boundingBox()
        expect(box).not.toBeNull()
        expect(box!.x).toBeGreaterThanOrEqual(0)
        expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width)
        expect(box!.y).toBeGreaterThanOrEqual(0)
        expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height)
        expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
        const save = dialog.getByRole('button', { name: 'Guardar alterações' })
        await save.scrollIntoViewIfNeeded()
        await expect(save).toBeInViewport()
        await capture(page, `${viewport.name}_dialog`)
      })
    })

    test.describe('as the patient', () => {
      test.use({ storageState: authState('patient') })

      for (const path of ['/app', '/app/consultas', '/app/saude', '/app/perfil', '/app/notificacoes']) {
        test(`${path} fits`, async ({ page }) => {
          await page.goto(path)
          await expectFits(page, `${path} @ ${viewport.name}`)
          await capture(page, `${viewport.name}_patient${path.replaceAll('/', '_')}`)
        })
      }
    })

    test.describe('as the clinic administrator', () => {
      test.use({ storageState: authState('clinic_admin') })

      for (const path of ['/app', '/app/equipa', '/app/contas']) {
        test(`${path} fits`, async ({ page }) => {
          await page.goto(path)
          await expectFits(page, `${path} @ ${viewport.name}`)
          await capture(page, `${viewport.name}_admin${path.replaceAll('/', '_')}`)
        })
      }
    })
  })
}

test.describe('mobile navigation', () => {
  test.use({ storageState: authState('doctor'), viewport: { width: 375, height: 667 } })

  test('the sidebar is replaced by a menu button that opens, navigates and closes', async ({ page }) => {
    await page.goto('/app')
    const toggle = page.getByRole('button', { name: 'Menu de navegação' })
    await expect(toggle).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Navegação principal' })).toHaveCount(0)

    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await page.getByRole('navigation', { name: 'Navegação principal' }).getByRole('link', { name: 'Pacientes' }).click()
    await expect(page).toHaveURL(/\/app\/pacientes$/)
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByRole('heading', { name: 'Pacientes', level: 1 })).toBeVisible()

    await toggle.click()
    await page.keyboard.press('Escape')
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(toggle).toBeFocused()
  })

  test('primary actions are large enough to tap', async ({ page }) => {
    await page.goto('/app/consultas')
    for (const name of ['Marcar consulta', 'Menu de navegação', 'Sair']) {
      const box = await page.getByRole('button', { name }).first().boundingBox()
      expect(box, name).not.toBeNull()
      expect(box!.height, `${name} height`).toBeGreaterThanOrEqual(32)
      expect(box!.width, `${name} width`).toBeGreaterThanOrEqual(32)
    }
  })
})

test.describe('tables on a narrow screen', () => {
  test.use({ storageState: authState('doctor'), viewport: { width: 320, height: 640 } })

  test('the patients table shows every column without sideways scrolling', async ({ page }) => {
    await page.goto('/app/pacientes')
    await expect(page.getByRole('columnheader', { name: 'Nome' })).toBeInViewport()
    await expect(page.getByRole('columnheader', { name: 'Estado' })).toBeInViewport()
    await expect(page.getByRole('cell', { name: 'Ativo' }).first()).toBeInViewport()
  })
})

test.describe('desktop navigation', () => {
  test.use({ storageState: authState('doctor'), viewport: { width: 1280, height: 800 } })

  test('shows the sidebar and no menu button', async ({ page }) => {
    await page.goto('/app')
    await expect(page.getByRole('button', { name: 'Menu de navegação' })).toBeHidden()
    await expect(page.getByRole('navigation', { name: 'Navegação principal' }).getByRole('link', { name: 'Pacientes' })).toBeVisible()
  })
})
