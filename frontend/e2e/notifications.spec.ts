import { expect, test } from '@playwright/test'
import { authState } from './support'

test.describe.serial('notifications', () => {
  test.describe('as the patient', () => {
    test.use({ storageState: authState('patient') })

    test('lists unread notifications and marks one as read', async ({ page }) => {
      await page.goto('/patient/notificacoes')
      await expect(page.getByRole('heading', { name: 'Notificações', level: 1 })).toBeVisible()

      // Other flows (documents, messaging) also notify this patient; assert on the seeded entries only.
      const items = page.getByRole('listitem')
      for (const title of ['Consulta confirmada', 'Resultados disponíveis']) {
        await expect(items.filter({ hasText: title })).toHaveCount(1)
        await expect(items.filter({ hasText: title }).getByText('Nova', { exact: true })).toBeVisible()
      }

      const first = items.filter({ hasText: 'Consulta confirmada' })
      await first.getByRole('button', { name: 'Marcar como lida' }).click()
      await expect(first.getByText('Nova', { exact: true })).toHaveCount(0)
      await expect(first.getByRole('button', { name: 'Marcar como lida' })).toHaveCount(0)

      const second = items.filter({ hasText: 'Resultados disponíveis' })
      await expect(second.getByText('Nova', { exact: true })).toBeVisible()
      await expect(second.getByRole('button', { name: 'Marcar como lida' })).toBeEnabled()
    })

    test('keeps the read state after a reload', async ({ page }) => {
      await page.goto('/patient/notificacoes')
      const items = page.getByRole('listitem')
      await expect(items.filter({ hasText: 'Consulta confirmada' }).getByText('Nova', { exact: true })).toHaveCount(0)
      await expect(items.filter({ hasText: 'Consulta confirmada' }).getByRole('button', { name: 'Marcar como lida' })).toHaveCount(0)
      await expect(
        page.getByRole('listitem').filter({ hasText: 'Resultados disponíveis' }).getByText('Nova', { exact: true }),
      ).toBeVisible()
    })
  })

  test.describe('as a doctor', () => {
    test.use({ storageState: authState('doctor') })

    test("never sees another user's notifications", async ({ page }) => {
      await page.goto('/app/notificacoes')
      await expect(page.getByRole('heading', { name: 'Notificações', level: 1 })).toBeVisible()
      await expect(page.getByText('A carregar')).toHaveCount(0)
      // The doctor may have their own (messaging) notifications; the patient's never appear.
      await expect(page.getByText('Consulta confirmada')).toHaveCount(0)
      await expect(page.getByText('Resultados disponíveis')).toHaveCount(0)
    })
  })
})
