import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { SelectField } from '../../components/SelectField'
import { TextField } from '../../components/TextField'
import { useAppointments, usePatient, useUpdatePatient } from '../../hooks/useClinicData'
import { useGrantConsent, usePatientConsents, useRevokeConsent } from '../../hooks/useConsents'
import { useSession } from '../../hooks/useSession'
import { formErrorsFrom, toUserMessage } from '../../lib/errorMessages'
import { formatDate, formatDateTime } from '../../lib/formatDate'
import { consentCreateSchema, patientUpdateSchema, zodErrorsToRecord } from '../../lib/validation'
import type { ConsentType, PatientPublic } from '../../types/api'
import { MedicalRecordsSection } from './MedicalRecordsSection'
import { MedicationsSection } from './MedicationsSection'

const CONSENT_LABELS: Record<ConsentType, string> = {
  treatment: 'Tratamento',
  data_processing: 'Tratamento de dados',
  communications: 'Comunicações',
  research: 'Investigação',
}

function PatientUpdateForm({ patient, patientOwnRecord }: { patient: PatientPublic; patientOwnRecord: boolean }) {
  const update = useUpdatePatient(patient.id)
  const [phone, setPhone] = useState(patient.phone ?? '')
  const [healthNumber, setHealthNumber] = useState(patient.national_health_number ?? '')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [success, setSuccess] = useState('')

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (update.isPending) return
    setSuccess('')
    const result = patientUpdateSchema.safeParse({ phone, national_health_number: healthNumber })
    if (!result.success) {
      setErrors(zodErrorsToRecord(result.error))
      return
    }
    setErrors({})
    const { phone: cleanPhone, national_health_number: cleanHealthNumber } = result.data
    update.mutate(
      patientOwnRecord
        ? { phone: cleanPhone || null }
        : { phone: cleanPhone || null, national_health_number: cleanHealthNumber || null },
      {
        onSuccess: () => setSuccess('Dados atualizados com sucesso.'),
        onError: (error) => setErrors(formErrorsFrom(error, ['phone', 'national_health_number'])),
      },
    )
  }

  return (
    <form className="mt-5 grid gap-4 border-t border-slate-100 pt-5 sm:grid-cols-2" onSubmit={submit} noValidate>
      <TextField label="Telefone" value={phone} onChange={(event) => setPhone(event.target.value)} error={errors.phone} maxLength={30} />
      {!patientOwnRecord && (
        <TextField label="Número de utente" value={healthNumber} onChange={(event) => setHealthNumber(event.target.value)} error={errors.national_health_number} maxLength={30} />
      )}
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <Button type="submit" isLoading={update.isPending}>Guardar dados</Button>
        {errors._root && <FormMessage kind="error">{errors._root}</FormMessage>}
        {success && <FormMessage kind="success">{success}</FormMessage>}
      </div>
    </form>
  )
}

export function PatientDetailPage({ own = false }: { own?: boolean }) {
  const { id: routeId = '' } = useParams()
  const { user } = useSession()
  const id = own ? (user?.patient_id ?? '') : routeId
  const patientQuery = usePatient(id)
  const appointments = useAppointments()
  const patient = patientQuery.data
  const patientAppointments = (appointments.data ?? []).filter((item) => item.patient_id === id)
  const canWriteClinical = user?.role === 'staff' && (user.staff_role === 'doctor' || user.staff_role === 'nurse')
  const canReadClinical = user?.role === 'patient' || canWriteClinical

  if (!id) return <ErrorState message="A sessão não contém uma identidade de paciente válida." />
  if (patientQuery.isLoading) return <LoadingSpinner label="A carregar paciente…" />
  if (patientQuery.isError) {
    return <ErrorState message={toUserMessage(patientQuery.error)} onRetry={() => patientQuery.refetch()} />
  }
  if (!patient) {
    return <ErrorState message="Paciente não encontrado ou sem acesso nesta clínica." />
  }

  return (
    <div className="flex flex-col gap-6">
      {!own && <nav aria-label="Breadcrumb" className="text-sm text-slate-500">
        <Link to="/app/pacientes" className="hover:text-teal-700 hover:underline">Pacientes</Link>
        <span aria-hidden="true"> / </span>
        <span>{patient.full_name}</span>
      </nav>}

      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{patient.full_name}</h1>
        <p className="text-sm text-slate-500">Ficha do paciente</p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Dados pessoais</h2>
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Detail label="Data de nascimento" value={patient.birth_date ? formatDate(patient.birth_date) : '—'} />
          <Detail label="Telefone" value={patient.phone ?? '—'} />
          <Detail label="Número de utente" value={patient.national_health_number ?? '—'} />
          <Detail label="Estado" value={patient.is_active ? 'Ativo' : 'Inativo'} />
        </dl>
        <PatientUpdateForm patient={patient} patientOwnRecord={user?.role === 'patient'} />
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

      {canReadClinical && <MedicalRecordsSection patientId={patient.id} canWrite={canWriteClinical} />}
      {canReadClinical && <MedicationsSection patientId={patient.id} canWrite={canWriteClinical} />}

      {/* The backend answers 403 on consents to administrative roles, so the section is not offered to them. */}
      {canReadClinical && <ConsentSection patientId={patient.id} canManage={user?.role === 'patient'} />}
    </div>
  )
}

function ConsentSection({ patientId, canManage }: { patientId: string; canManage: boolean }) {
  const consents = usePatientConsents(patientId)
  const grant = useGrantConsent(patientId)
  const revoke = useRevokeConsent(patientId)
  const [form, setForm] = useState({ consent_type: 'treatment' as ConsentType, purpose: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [success, setSuccess] = useState('')
  const busy = grant.isPending || revoke.isPending

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return
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
      onError: (error) => setErrors(formErrorsFrom(error, ['consent_type', 'purpose'])),
    })
  }

  function confirmRevoke(consentId: string) {
    if (busy) return
    if (!window.confirm('Revogar este consentimento? O registo continuará visível no histórico.')) return
    setSuccess('')
    setErrors({})
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

      {canManage && (
        <form onSubmit={submit} noValidate className="mb-6 grid gap-4 border-b border-slate-200 pb-6 md:grid-cols-3">
          <SelectField
            label="Tipo"
            value={form.consent_type}
            error={errors.consent_type}
            onChange={(event) => {
              const parsed = consentCreateSchema.shape.consent_type.safeParse(event.target.value)
              if (parsed.success) setForm((current) => ({ ...current, consent_type: parsed.data }))
            }}
          >
            {Object.entries(CONSENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </SelectField>
          <TextField
            label="Finalidade"
            value={form.purpose}
            onChange={(event) => setForm((current) => ({ ...current, purpose: event.target.value }))}
            error={errors.purpose}
            maxLength={500}
          />
          <div className="flex items-end"><Button type="submit" isLoading={grant.isPending} disabled={busy}>Conceder</Button></div>
        </form>
      )}
      {errors._root && <FormMessage kind="error" className="mb-3">{errors._root}</FormMessage>}
      {success && <FormMessage kind="success" className="mb-3">{success}</FormMessage>}

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
              {canManage && consent.status === 'granted' && (
                <Button
                  variant="secondary"
                  disabled={busy}
                  isLoading={revoke.isPending && revoke.variables === consent.id}
                  onClick={() => confirmRevoke(consent.id)}
                >
                  Revogar
                </Button>
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
