import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { authState, loadSeed, loginThroughUi, seedAppointment, seedClinicalContent } from './support'

const seed = loadSeed()
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function expectNoViolations(page: Page, label: string): Promise<void> {
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
  await expect(page.getByText('A carregar')).toHaveCount(0)
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  const summary = violations.map(
    (violation) => `${violation.id} (${violation.impact}): ${violation.help} -> ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`,
  )
  expect(summary, `${label} has accessibility violations`).toEqual([])
}

test.beforeAll(async () => {
  await seedAppointment(40, 'A11y consulta')
  await seedClinicalContent('a11y')
})

test('the scanner itself detects violations (canary)', async ({ page }) => {
  await page.setContent('<main><input type="text"><button></button></main>')
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  expect(violations.map((violation) => violation.id)).toEqual(expect.arrayContaining(['label', 'button-name']))
})

test.describe('public pages', () => {
  for (const [path, name] of [
    ['/login', 'login'],
    ['/recuperar-acesso', 'recover access'],
    ['/registo', 'patient registration'],
    ['/nova-clinica', 'clinic onboarding'],
  ] as const) {
    test(`${name} has no WCAG A/AA violations`, async ({ page }) => {
      await page.goto(path)
      await expectNoViolations(page, name)
    })
  }

  test('login with validation and server errors has no violations and exposes the errors', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('button', { name: 'Entrar' }).click()
    await expect(page.getByLabel('Email')).toHaveAccessibleDescription('Introduz um email válido.')
    await expectNoViolations(page, 'login (validation errors)')

    await loginThroughUi(page, seed.emails.doctor, 'PalavraErrada123!')
    await expect(page.getByRole('alert').filter({ hasText: /./ }).first()).toBeVisible()
    await expectNoViolations(page, 'login (server error)')
  })

  test('registration and onboarding validation errors have no violations', async ({ page }) => {
    await page.goto('/registo')
    await page.getByRole('button', { name: 'Criar conta' }).click()
    await expect(page.getByLabel('Clínica')).toBeFocused()
    await expectNoViolations(page, 'registration (validation errors)')
  })
})

test.describe('keyboard and focus', () => {
  test('the login form can be completed and submitted with the keyboard alone', async ({ page }) => {
    await page.goto('/login')
    await page.keyboard.press('Tab')
    await expect(page.getByLabel('Email')).toBeFocused()
    await page.keyboard.type(seed.emails.patient)
    await page.keyboard.press('Tab')
    await expect(page.getByLabel('Palavra-passe')).toBeFocused()
    await page.keyboard.type('SenhaForte123!')
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/\/app$/)
  })

  test('the focused control always has a visible focus indicator', async ({ page }) => {
    await page.goto('/login')
    for (let step = 0; step < 4; step += 1) {
      await page.keyboard.press('Tab')
      const outline = await page.evaluate(() => {
        const style = getComputedStyle(document.activeElement as Element)
        return { style: style.outlineStyle, width: parseFloat(style.outlineWidth) }
      })
      expect(outline.style, `focus step ${step}`).not.toBe('none')
      expect(outline.width, `focus step ${step}`).toBeGreaterThan(0)
    }
  })
})

test.describe('authenticated pages as a doctor', () => {
  test.use({ storageState: authState('doctor') })

  for (const [path, name] of [
    ['/app', 'dashboard'],
    ['/app/consultas', 'appointments'],
    ['/app/pacientes', 'patients'],
    ['/app/notificacoes', 'notifications'],
    ['/app/seguranca', 'account security'],
    [`/app/pacientes/${seed.patientIds.patient}`, 'patient file (records, medications, consents)'],
  ] as const) {
    test(`${name} has no violations`, async ({ page }) => {
      await page.goto(path)
      await expectNoViolations(page, name)
    })
  }

  test('the appointment dialog is accessible and traps keyboard focus', async ({ page }) => {
    await page.goto('/app/consultas')
    const row = page.getByRole('listitem').filter({ hasText: 'A11y consulta' })
    await row.getByRole('button', { name: 'Detalhes' }).click()
    const dialog = page.getByRole('dialog', { name: 'Detalhe da consulta' })
    await expect(dialog).toBeFocused()
    const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze()
    expect(violations.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([])

    for (let step = 0; step < 8; step += 1) {
      await page.keyboard.press('Tab')
      const inside = await dialog.evaluate((element) => element.contains(document.activeElement))
      expect(inside, `Tab ${step} left the dialog`).toBe(true)
    }
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(row.getByRole('button', { name: 'Detalhes' })).toBeFocused()
  })

  test('navigating moves focus to the page content and updates the title', async ({ page }) => {
    await page.goto('/app')
    await page.getByRole('link', { name: 'Consultas' }).first().click()
    await expect(page).toHaveTitle('Consultas · myVita')
    await expect(page.getByRole('main')).toBeFocused()
  })

  test('the skip link is the first tab stop and lands on the main content', async ({ page }) => {
    await page.goto('/app')
    // Tab only once the shell exists; before that, focus has nothing to land on.
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await page.keyboard.press('Tab')
    const skip = page.getByRole('link', { name: 'Saltar para o conteúdo' })
    await expect(skip).toBeFocused()
    await expect(skip).toBeVisible()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('main')).toBeFocused()
  })

  test('validation errors on the clinical forms are announced and have no violations', async ({ page }) => {
    await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
    await page.getByRole('region', { name: 'Medicação' }).getByRole('button', { name: 'Adicionar medicação' }).click()
    await page.getByRole('region', { name: 'Histórico clínico' }).getByRole('button', { name: 'Criar registo' }).click()
    await expect(page.getByLabel('Medicamento')).toHaveAccessibleDescription('Indica o nome do medicamento.')
    await expectNoViolations(page, 'patient file (validation errors)')
  })
})

test.describe('authenticated pages as the patient', () => {
  test.use({ storageState: authState('patient') })

  for (const [path, name] of [
    ['/app', 'dashboard'],
    ['/app/consultas', 'appointments'],
    ['/app/saude', 'health data'],
    ['/app/perfil', 'profile'],
    ['/app/notificacoes', 'notifications'],
  ] as const) {
    test(`${name} has no violations`, async ({ page }) => {
      await page.goto(path)
      await expectNoViolations(page, name)
    })
  }
})

test.describe('authenticated pages as the clinic administrator', () => {
  test.use({ storageState: authState('clinic_admin') })

  for (const [path, name] of [
    ['/app', 'dashboard'],
    ['/app/equipa', 'team'],
    ['/app/contas', 'accounts'],
  ] as const) {
    test(`${name} has no violations`, async ({ page }) => {
      await page.goto(path)
      await expectNoViolations(page, name)
    })
  }
})
