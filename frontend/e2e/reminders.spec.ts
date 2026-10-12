import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'
import { apiAs, authState, loadSeed } from './support'

// Scheduling, step 7: the background job sends an in-app reminder linked to the
// appointment, and the patient confirms they will come. Synthetic data only.
const seed = loadSeed()
const backend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../backend')

/** One pass of `python -m app.jobs` against the E2E database (same defaults as start-backend.sh). */
function runJobsOnce(): string {
  return execFileSync(process.env.E2E_PYTHON ?? '.venv/bin/python', ['-m', 'app.jobs', '--once'], {
    cwd: backend,
    env: { ...process.env, DATABASE_URL: process.env.E2E_DATABASE_URL ?? 'postgresql+psycopg://myvita:myvita@localhost:5432/myvita_e2e_test' },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
}

test.describe('appointment reminders', () => {
  test.use({ storageState: authState('other_patient'), viewport: { width: 375, height: 812 } })

  test('the reminder opens the appointment and the patient confirms', async ({ page }) => {
    const soon = new Date(Date.now() + 3 * 3_600_000)
    soon.setUTCMinutes(0, 0, 0)
    const created = await apiAs<{ id: string }>('clinic_admin', 'POST', '/api/v1/appointments', {
      patient_id: seed.patientIds.other_patient,
      staff_id: seed.staffIds.nurse,
      scheduled_at: soon.toISOString(),
      duration_minutes: 15,
    })
    runJobsOnce()

    await page.goto('/patient/notificacoes')
    const reminder = page.getByRole('listitem').filter({ hasText: 'Lembrete de consulta' }).first()
    await expect(reminder).toBeVisible()
    await reminder.getByRole('link', { name: 'Abrir consulta' }).click()
    await expect(page).toHaveURL(new RegExp(`/patient/consultas/${created!.id}$`))

    const presence = page.getByRole('region', { name: 'Presença' })
    await presence.getByRole('button', { name: 'Confirmar presença' }).click()
    await expect(presence).toContainText('Presença confirmada')
    // Within 24 hours of the start: no change in the app, the clinic's contact instead.
    await expect(page.getByRole('region', { name: 'Alterar a consulta' })).toContainText('Já não é possível cancelar ou remarcar')
  })
})
