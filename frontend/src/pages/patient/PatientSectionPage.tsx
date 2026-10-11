import type { ReactNode } from 'react'
import { ErrorState } from '../../components/ErrorState'
import { useSession } from '../../hooks/useSession'

/**
 * Shell for one page of the patient area (one page per section, MyChart style):
 * the page's own title, a short intro and the content for the signed-in patient.
 * Each route renders its own page, so the content always matches the URL.
 */
export function PatientSectionPage({ title, intro, children }: { title: string; intro?: string; children: (patientId: string) => ReactNode }) {
  const { user } = useSession()
  const patientId = user?.patient_id ?? ''
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {intro && <p className="mt-1 text-sm text-slate-500">{intro}</p>}
      </div>
      {patientId ? children(patientId) : <ErrorState message="A sessão não contém uma identidade de paciente válida." />}
    </div>
  )
}
