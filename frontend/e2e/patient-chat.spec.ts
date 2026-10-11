import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { apiAs, authState, expectNoHorizontalOverflow, loadSeed } from './support'

// Patient messages, chat style, at 375px: composer fixed at the bottom, newest message in view.
const seed = loadSeed()
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
const newest = 'Última mensagem da equipa E2E.'
let conversationId = ''

test.describe('patient chat', () => {
  test.use({ storageState: authState('patient'), viewport: { width: 375, height: 667 } })

  test.beforeAll(async () => {
    await apiAs('clinic_admin', 'POST', `/api/v1/patients/${seed.patientIds.patient}/care-team`, { staff_id: seed.staffIds.doctor }, [409])
    const opened = await apiAs<{ id: string }>('doctor', 'POST', '/api/v1/conversations', { patient_id: seed.patientIds.patient })
    conversationId = opened!.id
    // A doctor-closed thread from another spec would be read-only: reopen it if needed.
    await apiAs('doctor', 'POST', `/api/v1/conversations/${conversationId}/status`, { status: 'open' }, [200, 403])
    for (let index = 1; index <= 14; index += 1) {
      await apiAs('doctor', 'POST', `/api/v1/conversations/${conversationId}/messages`, { body: `Mensagem de teste ${index} com algum texto para ocupar espaço no ecrã.` })
    }
    await apiAs('doctor', 'POST', `/api/v1/conversations/${conversationId}/messages`, { body: newest })
  })

  test('opens at the newest message with the composer fixed at the bottom', async ({ page }) => {
    await page.goto('/patient/mensagens')
    const row = page.getByRole('list', { name: 'Conversas' }).getByRole('link').filter({ hasText: seed.names.doctor }).first()
    await row.click()
    await expect(page.getByText(newest)).toBeInViewport()
    const composer = page.getByRole('form', { name: 'Enviar mensagem' })
    await expect(composer).toBeInViewport()
    await expect(page.getByText('Hoje')).toBeVisible()

    // Scrolling back through the history keeps the composer at the bottom of the screen.
    await page.mouse.wheel(0, -3000)
    await expect(page.getByText(newest)).not.toBeInViewport()
    const box = (await composer.boundingBox())!
    expect(Math.round(box.y + box.height)).toBeGreaterThanOrEqual(667 - 2)

    await page.getByLabel('Mensagem', { exact: true }).fill('Obrigado pela informação.')
    await page.getByRole('button', { name: 'Enviar' }).click()
    await expect(page.getByRole('article', { name: 'Mensagem enviada por si' }).last()).toContainText('Obrigado pela informação.')
    await expect(page.getByText('Obrigado pela informação.')).toBeInViewport()
    await expectNoHorizontalOverflow(page, 'patient chat @ 375px')
  })

  test('the chat, its ⋮ menu and the list have no accessibility violations', async ({ page }) => {
    await page.goto(`/patient/mensagens/${conversationId}`)
    await expect(page.getByText(newest)).toBeVisible()
    await page.getByRole('button', { name: 'Mais opções' }).click()
    await expect(page.getByRole('region', { name: 'Estado da conversa' })).toBeVisible()
    for (const label of ['chat with ⋮ menu', 'conversation list']) {
      await page.waitForFunction(() =>
        document.getAnimations().every((animation) => animation.playState !== 'running' || animation.effect?.getComputedTiming().iterations === Infinity),
      )
      const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze()
      expect(violations.map((violation) => `${violation.id}: ${violation.help}`), label).toEqual([])
      if (label === 'chat with ⋮ menu') {
        await page.getByRole('link', { name: 'Voltar às mensagens' }).click()
        await expect(page.getByRole('heading', { level: 1, name: 'Mensagens' })).toBeVisible()
      }
    }
  })
})
