import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { ClinicalResultsSection } from '../../components/ClinicalResultsSection'
import { DocumentsSection } from '../../components/DocumentsSection'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { useAppointments, usePatient, useUpdatePatient } from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDate, formatDateTime } from '../../lib/formatDate'
import type { PatientPublic } from '../../types/api'
import { ConsentSection } from '../../components/ConsentSection'
import { MedicalRecordsSection } from '../../components/MedicalRecordsSection'
import { MedicationsSection } from './MedicationsSection'

function PatientUpdateForm({ patient }: { patient: PatientPublic }) {
  const update = useUpdatePatient(patient.id)
  const [phone, setPhone] = useState(patient.phone ?? '')
  const [healthNumber, setHealthNumber] = useState(patient.national_health_number ?? '')
  const [message, setMessage] = useState('')

  return (
    <form
      className="mt-5 grid gap-4 border-t border-slate-100 pt-5 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault()
        setMessage('')
        update.mutate(
          { phone: phone || null, national_health_number: healthNumber || null },
          {
            onSuccess: () => setMessage('Dados atualizados com sucesso.'),
            onError: (error) => setMessage(toUserMessage(error)),
          },
        )
      }}
    >
      <TextField label="Telefone" value={phone} onChange={(event) => setPhone(event.target.value)} />
      <TextField label="Número de utente" value={healthNumber} onChange={(event) => setHealthNumber(event.target.value)} />
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <Button type="submit" isLoading={update.isPending}>Guardar dados</Button>
        {message && <p role="status" className="text-sm text-slate-600">{message}</p>}
      </div>
    </form>
  )
}

type PatientSection = 'personal' | 'appointments' | 'records' | 'results' | 'medications' | 'documents' | 'consents'

/** Staff patient file with tabs (patients have one page per section, see pages/patient). */
export function PatientDetailPage() {
  const { id: routeId = '' } = useParams()
  const location = useLocation()
  const { user } = useSession()
  const [activeSection, setActiveSection] = useState<PatientSection>('personal')
  const id = routeId
  const patientQuery = usePatient(id)
  const appointments = useAppointments()
  const patient = patientQuery.data
  const patientAppointments = (appointments.data ?? []).filter((item) => item.view === 'staff' && item.patient_id === id)
  const canWriteClinical = user?.role === 'staff' && (user.staff_role === 'doctor' || user.staff_role === 'nurse')
  const canReadClinical = canWriteClinical

  if (patientQuery.isLoading) return <LoadingSpinner label="A carregar paciente…" />
  if (patientQuery.isError) {
    return <ErrorState message={toUserMessage(patientQuery.error)} onRetry={() => patientQuery.refetch()} />
  }
  if (!patient) {
    return <ErrorState message="Paciente não encontrado ou sem acesso nesta clínica." />
  }

  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Breadcrumb" className="text-sm text-slate-500">
        <Link to={{ pathname: '/app/pacientes', search: location.search }} className="hover:text-teal-700 hover:underline">Voltar à lista de pacientes</Link>
        <span aria-hidden="true"> / </span>
        <span>{patient.full_name}</span>
      </nav>

      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{patient.full_name}</h1>
        <p className="text-sm text-slate-500">Ficha do paciente</p>
      </div>

      <nav role="tablist" aria-label="Secções da ficha" className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {([
          ['personal', 'Dados pessoais'], ['appointments', 'Consultas'],
          ...(canReadClinical ? [['records', 'Registos clínicos'], ['results', 'Resultados'], ['medications', 'Medicamentos'], ['documents', 'Documentos']] : []),
          ['consents', 'Consentimentos'],
        ] as Array<[typeof activeSection, string]>).map(([key, label]) => (
          <button key={key} id={`patient-tab-${key}`} type="button" role="tab" aria-controls={`patient-panel-${key}`} aria-selected={activeSection === key} onClick={() => setActiveSection(key)} className={`rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-2 ${activeSection === key ? 'bg-teal-50 text-teal-800' : 'text-slate-600 hover:bg-slate-100'}`}>
            {label}
          </button>
        ))}
      </nav>

      {activeSection === 'personal' && <section id="patient-panel-personal" role="tabpanel" aria-labelledby="patient-tab-personal" className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Dados pessoais</h2>
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Detail label="Data de nascimento" value={patient.birth_date ? formatDate(patient.birth_date) : '—'} />
          <Detail label="Telefone" value={patient.phone ?? '—'} />
          <Detail label="Número de utente" value={patient.national_health_number ?? '—'} />
          <Detail label="Estado" value={patient.is_active ? 'Ativo' : 'Inativo'} />
        </dl>
        <PatientUpdateForm patient={patient} />
      </section>}

      {activeSection === 'appointments' && <section id="patient-panel-appointments" role="tabpanel" aria-labelledby="patient-tab-appointments" className="rounded-xl border border-slate-200 bg-white p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-medium">Consultas</h2><Link to="/app/consultas" className="text-sm font-medium text-teal-700 hover:underline">Abrir agenda</Link></div>
        {appointments.isLoading && <LoadingSpinner />}
        {appointments.isError && (
          <ErrorState message={toUserMessage(appointments.error)} onRetry={() => appointments.refetch()} />
        )}
        {appointments.data && patientAppointments.length === 0 && <EmptyState title="Sem consultas" />}
        {patientAppointments.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {patientAppointments.map((appointment) => (
              <li key={appointment.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <p className="font-medium">{formatDateTime(appointment.scheduled_at)}</p>
                  <p className="text-sm text-slate-500">{appointment.reason ?? 'Sem motivo indicado'}</p>
                </div>
                <AppointmentStatusBadge status={appointment.status} />
              </li>
            ))}
          </ul>
        )}
      </section>}

      {canReadClinical && activeSection === 'records' && <div id="patient-panel-records" role="tabpanel" aria-labelledby="patient-tab-records"><MedicalRecordsSection patientId={patient.id} canWrite={canWriteClinical} /></div>}
      {canReadClinical && activeSection === 'results' && <div id="patient-panel-results" role="tabpanel" aria-labelledby="patient-tab-results"><ClinicalResultsSection patientId={patient.id} canManage={canWriteClinical} /></div>}
      {canReadClinical && activeSection === 'medications' && <div id="patient-panel-medications" role="tabpanel" aria-labelledby="patient-tab-medications"><MedicationsSection patientId={patient.id} canWrite={canWriteClinical} /></div>}
      {canReadClinical && activeSection === 'documents' && <div id="patient-panel-documents" role="tabpanel" aria-labelledby="patient-tab-documents"><DocumentsSection patientId={patient.id} canManage={canWriteClinical} patientName={patient.full_name} /></div>}
      {activeSection === 'consents' && <div id="patient-panel-consents" role="tabpanel" aria-labelledby="patient-tab-consents"><ConsentSection patientId={patient.id} canManage={false} /></div>}
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-sm text-slate-500">{label}</dt><dd className="font-medium text-slate-900">{value}</dd></div>
}
