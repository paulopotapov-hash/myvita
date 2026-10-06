import { expect, test } from '@playwright/test'
import { authState } from './support'

test.describe.serial('notifications', () => {
  test.describe('as the patient', () => {
    test.use({ storageState: authState('patient') })

    test('lists unread notifications and marks one as read', async ({ page }) => {
      await page.goto('/app/notificacoes')
      await expect(page.getByRole('heading', { name: 'Notificações', level: 1 })).toBeVisible()

      const items = page.getByRole('listitem')
      await expect(items).toHaveCount(2)
      await expect(page.getByText('Nova', { exact: true })).toHaveCount(2)

      const first = items.filter({ hasText: 'Consulta confirmada' })
      await first.getByRole('button', { name: 'Marcar como lida' }).click()
      await expect(first.getByText('Nova', { exact: true })).toHaveCount(0)
      await expect(first.getByRole('button', { name: 'Marcar como lida' })).toHaveCount(0)

      const second = items.filter({ hasText: 'Resultados disponíveis' })
      await expect(second.getByText('Nova', { exact: true })).toBeVisible()
      await expect(second.getByRole('button', { name: 'Marcar como lida' })).toBeEnabled()
    })

    test('keeps the read state after a reload', async ({ page }) => {
      await page.goto('/app/notificacoes')
      await expect(page.getByRole('listitem')).toHaveCount(2)
      await expect(page.getByText('Nova', { exact: true })).toHaveCount(1)
      await expect(
        page.getByRole('listitem').filter({ hasText: 'Resultados disponíveis' }).getByText('Nova', { exact: true }),
      ).toBeVisible()
    })
  })

  test.describe('as a doctor', () => {
    test.use({ storageState: authState('doctor') })

    test("never sees another user's notifications", async ({ page }) => {
      await page.goto('/app/notificacoes')
      await expect(page.getByText('Sem notificações')).toBeVisible()
      await expect(page.getByText('Consulta confirmada')).toHaveCount(0)
    })
  })
})
