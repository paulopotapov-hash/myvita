import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { useAppointments, usePatients } from '../../hooks/useClinicData'
import { useGrantConsent, usePatientConsents, useRevokeConsent } from '../../hooks/useConsents'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDate, formatDateTime } from '../../lib/formatDate'
import { consentCreateSchema, zodErrorsToRecord } from '../../lib/validation'
import type { ConsentType } from '../../types/api'

const CONSENT_LABELS: Record<ConsentType, string> = {
  treatment: 'Tratamento',
  data_processing: 'Tratamento de dados',
  communications: 'Comunicações',
  research: 'Investigação',
}

export function PatientDetailPage() {
  const { id = '' } = useParams()
  const patients = usePatients()
  const appointments = useAppointments()
  const patient = patients.data?.find((item) => item.id === id)
  const patientAppointments = (appointments.data ?? []).filter((item) => item.patient_id === id)

  if (patients.isLoading) return <LoadingSpinner label="A carregar paciente…" />
  if (patients.isError) {
    return <ErrorState message={toUserMessage(patients.error)} onRetry={() => patients.refetch()} />
  }
  if (!patient) {
    return <ErrorState message="Paciente não encontrado ou sem acesso nesta clínica." />
  }

  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Breadcrumb" className="text-sm text-slate-500">
        <Link to="/app/pacientes" className="hover:text-teal-700 hover:underline">Pacientes</Link>
        <span aria-hidden="true"> / </span>
        <span>{patient.full_name}</span>
      </nav>

      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{patient.full_name}</h1>
        <p className="text-sm text-slate-500">Ficha do paciente</p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Dados pessoais</h2>
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Detail label="Data de nascimento" value={patient.birth_date ? formatDate(patient.birth_date) : '—'} />
          <Detail label="Telefone" value={patient.phone ?? '—'} />
          <Detail label="Número de utente" value="Não disponível na API" />
          <Detail label="Estado" value="Não disponível na API" />
        </dl>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Consultas</h2>
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
      </section>

      <ConsentSection patientId={patient.id} />
    </div>
  )
}

function ConsentSection({ patientId }: { patientId: string }) {
  const consents = usePatientConsents(patientId)
  const grant = useGrantConsent(patientId)
  const revoke = useRevokeConsent(patientId)
  const [form, setForm] = useState({ consent_type: 'treatment' as ConsentType, purpose: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [success, setSuccess] = useState('')

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setSuccess('')
    const result = consentCreateSchema.safeParse(form)
    if (!result.success) {
      setErrors(zodErrorsToRecord(result.error))
      return
    }
    setErrors({})
    grant.mutate(result.data, {
      onSuccess: () => {
        setForm((current) => ({ ...current, purpose: '' }))
        setSuccess('Consentimento concedido e registado no histórico.')
      },
      onError: (error) => setErrors({ _root: toUserMessage(error) }),
    })
  }

  function confirmRevoke(consentId: string) {
    if (!window.confirm('Revogar este consentimento? O registo continuará visível no histórico.')) return
    setSuccess('')
    revoke.mutate(consentId, {
      onSuccess: () => setSuccess('Consentimento revogado. O histórico foi preservado.'),
      onError: (error) => setErrors({ _root: toUserMessage(error) }),
    })
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <div className="mb-5">
        <h2 className="text-lg font-medium">Consentimentos</h2>
        <p className="text-sm text-slate-500">A revogação preserva sempre o registo original no histórico.</p>
      </div>

      <form onSubmit={submit} className="mb-6 grid gap-4 border-b border-slate-200 pb-6 md:grid-cols-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="consent-type" className="text-sm font-medium text-slate-700">Tipo</label>
          <select
            id="consent-type"
            value={form.consent_type}
            onChange={(event) => setForm((current) => ({ ...current, consent_type: event.target.value as ConsentType }))}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            {Object.entries(CONSENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <TextField
          label="Finalidade"
          value={form.purpose}
          onChange={(event) => setForm((current) => ({ ...current, purpose: event.target.value }))}
          error={errors.purpose}
        />
        <div className="flex items-end"><Button type="submit" isLoading={grant.isPending}>Conceder</Button></div>
        {errors._root && <p role="alert" className="text-sm text-red-600 md:col-span-3">{errors._root}</p>}
        {success && <p role="status" className="text-sm text-teal-700 md:col-span-3">{success}</p>}
      </form>

      {consents.isLoading && <LoadingSpinner />}
      {consents.isError && <ErrorState message={toUserMessage(consents.error)} onRetry={() => consents.refetch()} />}
      {consents.data?.length === 0 && <EmptyState title="Sem consentimentos" description="Ainda não existem decisões registadas." />}
      {consents.data && consents.data.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {consents.data.map((consent) => (
            <li key={consent.id} className="flex flex-wrap items-start justify-between gap-3 py-4">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium">{CONSENT_LABELS[consent.consent_type]}</p>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${consent.status === 'granted' ? 'bg-teal-50 text-teal-800' : 'bg-slate-100 text-slate-700'}`}>
                    {consent.status === 'granted' ? 'Concedido' : 'Revogado'}
                  </span>
                </div>
                <p className="text-sm text-slate-600">{consent.purpose}</p>
                <p className="mt-1 text-xs text-slate-500">Concedido em {formatDateTime(consent.granted_at)}{consent.revoked_at ? ` · Revogado em ${formatDateTime(consent.revoked_at)}` : ''}</p>
              </div>
              {consent.status === 'granted' && (
                <Button variant="secondary" disabled={revoke.isPending} onClick={() => confirmRevoke(consent.id)}>Revogar</Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-sm text-slate-500">{label}</dt><dd className="font-medium text-slate-900">{value}</dd></div>
}
