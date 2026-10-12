import { Link } from 'react-router-dom'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { MedicalRecordsSection } from '../../components/MedicalRecordsSection'
import { ClinicalHistorySection } from '../../components/clinicalHistory/ClinicalHistorySection'
import { EntryBadges } from '../../components/clinicalHistory/EntryBadges'
import { useAppointments } from '../../hooks/useClinicData'
import { useMedications } from '../../hooks/useClinicalData'
import { useClinicalHistory } from '../../hooks/useClinicalHistory'
import { useClinicalResults } from '../../hooks/useClinicalResults'
import { nextAppointment } from '../../lib/appointments'
import { SEVERITY_LABELS } from '../../lib/clinicalHistoryLabels'
import { RESULT_CATEGORY_LABELS } from '../../lib/clinicalResultForm'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDate, formatDateTime } from '../../lib/formatDate'
import { formatPartialDate } from '../../lib/partialDate'
import { PatientSectionPage } from './PatientSectionPage'

const LATEST_RESULTS = 3

/**
 * "Resumo de saúde": what matters now (current medication, allergies, next appointment,
 * latest results), then the clinical history by category, then the shared clinical records.
 */
export function HealthSummaryPage() {
  return (
    <PatientSectionPage title="Resumo de saúde" intro="Um resumo da tua informação clínica nesta clínica.">
      {(patientId) => (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <CurrentMedication patientId={patientId} />
            <Allergies patientId={patientId} />
            <NextAppointment />
            <LatestResults patientId={patientId} />
          </div>
          <ClinicalHistorySection patientId={patientId} mode="patient" medicationSlot={<MedicationCategory patientId={patientId} />} />
          <MedicalRecordsSection patientId={patientId} canWrite={false} />
        </>
      )}
    </PatientSectionPage>
  )
}

function Allergies({ patientId }: { patientId: string }) {
  const history = useClinicalHistory(patientId)
  const allergies = (history.data ?? []).filter((entry) => entry.category === 'allergy')
  return (
    <SummaryCard id="summary-allergies" title="Alergias conhecidas" link={{ to: '#history-allergy', label: 'Ver ou declarar alergias' }}>
      {history.isLoading && <LoadingSpinner />}
      {history.isError && <ErrorState message={toUserMessage(history.error)} onRetry={() => history.refetch()} />}
      {history.data && allergies.length === 0 && <p className="text-slate-500">Sem alergias registadas.</p>}
      {allergies.length > 0 && (
        <ul className="flex flex-col gap-1">
          {allergies.map((entry) => (
            <li key={entry.id}>
              <span className="font-medium">{entry.name}</span>
              {entry.severity && <span className="text-slate-500"> · {SEVERITY_LABELS[entry.severity]}</span>}
            </li>
          ))}
        </ul>
      )}
    </SummaryCard>
  )
}

/** The medication category of the history: current and past, managed on "A minha medicação". */
function MedicationCategory({ patientId }: { patientId: string }) {
  const medications = useMedications(patientId)
  const items = medications.data?.items ?? []
  const groups = [
    { label: 'Atual', items: items.filter((item) => item.status === 'active') },
    { label: 'Histórico', items: items.filter((item) => item.status !== 'active') },
  ]
  return (
    <section aria-labelledby="history-medication" className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="history-medication" className="text-base font-semibold text-slate-900">Medicação</h2>
        <Link to="/patient/medicacao" className="text-sm font-medium text-teal-700 hover:underline">Ver, declarar ou alterar</Link>
      </div>
      {medications.isLoading && <LoadingSpinner />}
      {medications.isError && <ErrorState message={toUserMessage(medications.error)} onRetry={() => medications.refetch()} />}
      {medications.data && items.length === 0 && <p className="mt-2 text-sm text-slate-500">Sem registos.</p>}
      {groups.filter((group) => group.items.length > 0).map((group) => (
        <div key={group.label} className="mt-2">
          <h3 className="text-sm font-semibold text-slate-700">{group.label}</h3>
          <ul className="divide-y divide-slate-100">
            {group.items.map((item) => (
              <li key={item.id} className="py-2 text-sm">
                <span className="font-medium">{item.name}</span>
                {item.dosage && ` · ${item.dosage}`}
                {item.frequency && ` · ${item.frequency}`}
                <span className="text-slate-500">
                  {item.start_date && ` · desde ${formatPartialDate(item.start_date)}`}
                  {item.end_date && ` até ${formatDate(item.end_date)}`}
                </span>
                <div className="mt-1"><EntryBadges confirmed={item.confirmed} /></div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  )
}

function SummaryCard({ id, title, link, children }: { id: string; title: string; link: { to: string; label: string }; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-5">
      <h2 id={id} className="text-base font-semibold text-slate-900">{title}</h2>
      <div className="flex-1 text-sm text-slate-700">{children}</div>
      {link.to.startsWith('#') ? (
        // Same page: a plain anchor lets the browser scroll to the category.
        <a href={link.to} className="text-sm font-medium text-teal-700 hover:underline">{link.label}</a>
      ) : (
        <Link to={link.to} className="text-sm font-medium text-teal-700 hover:underline">{link.label}</Link>
      )}
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
          {active.map((item) => <li key={item.id}><span className="font-medium">{item.name}</span>{item.dosage && ` · ${item.dosage}`}{item.frequency && ` · ${item.frequency}`}</li>)}
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
      link={upcoming ? { to: `/patient/consultas/${upcoming.id}`, label: 'Ver detalhes' } : { to: '/patient/consultas/marcar', label: 'Marcar consulta' }}
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
