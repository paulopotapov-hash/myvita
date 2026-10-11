import { Link } from 'react-router-dom'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { MedicalRecordsSection } from '../../components/MedicalRecordsSection'
import { useAppointments } from '../../hooks/useClinicData'
import { useMedications } from '../../hooks/useClinicalData'
import { useClinicalResults } from '../../hooks/useClinicalResults'
import { nextAppointment } from '../../lib/appointments'
import { RESULT_CATEGORY_LABELS } from '../../lib/clinicalResultForm'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDate, formatDateTime } from '../../lib/formatDate'
import { PatientSectionPage } from './PatientSectionPage'

const LATEST_RESULTS = 3

/** "Resumo de saúde": what matters now, then the clinical records shared with the patient. */
export function HealthSummaryPage() {
  return (
    <PatientSectionPage title="Resumo de saúde" intro="Um resumo da tua informação clínica nesta clínica.">
      {(patientId) => (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <CurrentMedication patientId={patientId} />
            <NextAppointment />
            <div className="sm:col-span-2"><LatestResults patientId={patientId} /></div>
          </div>
          <MedicalRecordsSection patientId={patientId} canWrite={false} />
        </>
      )}
    </PatientSectionPage>
  )
}

function SummaryCard({ id, title, link, children }: { id: string; title: string; link: { to: string; label: string }; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-5">
      <h2 id={id} className="text-base font-semibold text-slate-900">{title}</h2>
      <div className="flex-1 text-sm text-slate-700">{children}</div>
      <Link to={link.to} className="text-sm font-medium text-teal-700 hover:underline">{link.label}</Link>
    </section>
  )
}

function CurrentMedication({ patientId }: { patientId: string }) {
  const medications = useMedications(patientId)
  const active = (medications.data?.items ?? []).filter((item) => item.status === 'active')
  return (
    <SummaryCard id="summary-medication" title="Medicação atual" link={{ to: '/patient/medicacao', label: 'Ver toda a medicação' }}>
      {medications.isLoading && <LoadingSpinner />}
      {medications.isError && <ErrorState message={toUserMessage(medications.error)} onRetry={() => medications.refetch()} />}
      {medications.data && active.length === 0 && <p className="text-slate-500">Sem medicação ativa.</p>}
      {active.length > 0 && (
        <ul className="flex flex-col gap-1">
          {active.map((item) => <li key={item.id}><span className="font-medium">{item.name}</span> · {item.dosage}{item.frequency && ` · ${item.frequency}`}</li>)}
        </ul>
      )}
    </SummaryCard>
  )
}

function NextAppointment() {
  const appointments = useAppointments()
  const upcoming = appointments.data ? nextAppointment(appointments.data, new Date()) : undefined
  return (
    <SummaryCard
      id="summary-appointment"
      title="Próxima consulta"
      link={upcoming ? { to: `/patient/consultas?consulta=${upcoming.id}`, label: 'Ver detalhes' } : { to: '/patient/consultas', label: 'Ver as minhas consultas' }}
    >
      {appointments.isLoading && <LoadingSpinner />}
      {appointments.isError && <ErrorState message={toUserMessage(appointments.error)} onRetry={() => appointments.refetch()} />}
      {appointments.data && !upcoming && <p className="text-slate-500">Sem consultas marcadas.</p>}
      {upcoming && (
        <p>
          <span className="font-medium">{formatDateTime(upcoming.scheduled_at)}</span>
          {upcoming.view === 'patient' && upcoming.staff_name && <span className="block text-slate-500">{upcoming.staff_name}</span>}
        </p>
      )}
    </SummaryCard>
  )
}

function LatestResults({ patientId }: { patientId: string }) {
  const results = useClinicalResults(patientId, 1, LATEST_RESULTS)
  const items = results.data?.items ?? []
  return (
    <SummaryCard id="summary-results" title="Últimos resultados" link={{ to: '/patient/resultados', label: 'Ver todos os resultados' }}>
      {results.isLoading && <LoadingSpinner />}
      {results.isError && <ErrorState message={toUserMessage(results.error)} onRetry={() => results.refetch()} />}
      {results.data && items.length === 0 && <p className="text-slate-500">Sem resultados disponíveis.</p>}
      {items.length > 0 && (
        <ul className="flex flex-col gap-1">
          {items.map((item) => (
            <li key={item.id}>
              <Link to={`/patient/resultados?result=${item.id}`} className="font-medium text-slate-900 hover:underline">{item.title}</Link>
              <span className="text-slate-500"> · {RESULT_CATEGORY_LABELS[item.category]} · {formatDate(item.result_date)}</span>
            </li>
          ))}
        </ul>
      )}
    </SummaryCard>
  )
}
