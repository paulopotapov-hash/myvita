import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { useAppointments, usePatient, useUpdatePatient } from '../../hooks/useClinicData'
import { useCreateMedicalRecord, useCreateMedication, useMedicalRecords, useMedicalRecordRevisions, useMedications, useUpdateMedicalRecord, useUpdateMedication } from '../../hooks/useClinicalData'
import { useGrantConsent, usePatientConsents, useRevokeConsent } from '../../hooks/useConsents'
import { useSession } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDate, formatDateTime } from '../../lib/formatDate'
import { consentCreateSchema, zodErrorsToRecord } from '../../lib/validation'
import type { ConsentType, MedicalRecordPublic, PatientPublic } from '../../types/api'

const CONSENT_LABELS: Record<ConsentType, string> = {
  treatment: 'Tratamento',
  data_processing: 'Tratamento de dados',
  communications: 'Comunicações',
  research: 'Investigação',
}

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
      <div className="flex items-center gap-3 sm:col-span-2">
        <Button type="submit" isLoading={update.isPending}>Guardar dados</Button>
        {message && <p role="status" className="text-sm text-slate-600">{message}</p>}
      </div>
    </form>
  )
}

function MedicalRecordsSection({ patientId, canWrite }: { patientId: string; canWrite: boolean }) {
  const records = useMedicalRecords(patientId)
  const create = useCreateMedicalRecord(patientId)
  const update = useUpdateMedicalRecord(patientId)
  const [selected, setSelected] = useState<MedicalRecordPublic | null>(null)
  const revisions = useMedicalRecordRevisions(selected?.id ?? '')
  const [form, setForm] = useState({ title: '', content: '' })
  const [message, setMessage] = useState('')

  function save(event: React.FormEvent) {
    event.preventDefault()
    setMessage('')
    if (!form.title.trim() || !form.content.trim()) {
      setMessage('Preenche o título e o conteúdo clínico.')
      return
    }
    const options = {
      onSuccess: () => {
        setSelected(null)
        setForm({ title: '', content: '' })
        setMessage('Registo clínico guardado.')
      },
      onError: (error: unknown) => setMessage(toUserMessage(error)),
    }
    if (selected) update.mutate({ id: selected.id, payload: form }, options)
    else create.mutate(form, options)
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-medium">Histórico clínico</h2>
      {canWrite && (
        <form className="mb-6 grid gap-3 border-b border-slate-100 pb-5" onSubmit={save}>
          <TextField label="Título do registo" value={form.title} onChange={(event) => setForm((value) => ({ ...value, title: event.target.value }))} />
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">Conteúdo clínico
            <textarea className="min-h-28 rounded-md border border-slate-300 px-3 py-2 font-normal" value={form.content} onChange={(event) => setForm((value) => ({ ...value, content: event.target.value }))} maxLength={20000} />
          </label>
          <div className="flex items-center gap-3"><Button type="submit" isLoading={create.isPending || update.isPending}>{selected ? 'Guardar nova versão' : 'Criar registo'}</Button>{selected && <Button variant="secondary" onClick={() => { setSelected(null); setForm({ title: '', content: '' }) }}>Cancelar edição</Button>}</div>
          {message && <p role="status" className="text-sm text-slate-600">{message}</p>}
        </form>
      )}
      {records.isLoading && <LoadingSpinner />}
      {records.isError && <ErrorState message={toUserMessage(records.error)} onRetry={() => records.refetch()} />}
      {records.data?.length === 0 && <EmptyState title="Sem registos clínicos" />}
      {records.data && records.data.length > 0 && <ul className="divide-y divide-slate-100">{records.data.map((record) => <li key={record.id} className="py-4"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{record.title}</p><p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{record.content}</p><p className="mt-1 text-xs text-slate-500">Versão {record.version} · {formatDateTime(record.updated_at)}</p></div>{canWrite && <Button variant="secondary" onClick={() => { setSelected(record); setForm({ title: record.title, content: record.content }) }}>Editar</Button>}</div>{selected?.id === record.id && <div className="mt-3 rounded-lg bg-slate-50 p-3"><p className="text-sm font-medium">Revisões</p>{revisions.isLoading && <LoadingSpinner />}{revisions.data?.map((revision) => <p key={revision.id} className="mt-1 text-xs text-slate-600">Versão {revision.version} · {formatDateTime(revision.created_at)}</p>)}</div>}</li>)}</ul>}
    </section>
  )
}

function MedicationsSection({ patientId, canWrite }: { patientId: string; canWrite: boolean }) {
  const medications = useMedications(patientId)
  const create = useCreateMedication(patientId)
  const update = useUpdateMedication(patientId)
  const [form, setForm] = useState({ name: '', dosage: '', start_date: '' })
  const [message, setMessage] = useState('')
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-medium">Medicação</h2>
      {canWrite && <form className="mb-6 grid gap-3 border-b border-slate-100 pb-5 sm:grid-cols-3" onSubmit={(event) => { event.preventDefault(); setMessage(''); create.mutate(form, { onSuccess: () => { setForm({ name: '', dosage: '', start_date: '' }); setMessage('Medicação adicionada.') }, onError: (error) => setMessage(toUserMessage(error)) }) }}>
        <TextField label="Medicamento" value={form.name} onChange={(event) => setForm((value) => ({ ...value, name: event.target.value }))} />
        <TextField label="Dosagem" value={form.dosage} onChange={(event) => setForm((value) => ({ ...value, dosage: event.target.value }))} />
        <TextField label="Data de início" type="date" value={form.start_date} onChange={(event) => setForm((value) => ({ ...value, start_date: event.target.value }))} />
        <div className="sm:col-span-3"><Button type="submit" isLoading={create.isPending}>Adicionar medicação</Button></div>
        {message && <p role="status" className="text-sm text-slate-600 sm:col-span-3">{message}</p>}
      </form>}
      {medications.isLoading && <LoadingSpinner />}
      {medications.isError && <ErrorState message={toUserMessage(medications.error)} onRetry={() => medications.refetch()} />}
      {medications.data?.length === 0 && <EmptyState title="Sem medicação" />}
      {medications.data && medications.data.length > 0 && <ul className="divide-y divide-slate-100">{medications.data.map((medication) => <li key={medication.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div><p className="font-medium">{medication.name} · {medication.dosage}</p><p className="text-sm text-slate-500">{medication.status === 'active' ? 'Ativa' : medication.status === 'completed' ? 'Concluída' : 'Descontinuada'} · início {formatDate(medication.start_date)}</p></div>{canWrite && medication.status === 'active' && <Button variant="secondary" disabled={update.isPending} onClick={() => update.mutate({ id: medication.id, payload: { status: 'discontinued' } }, { onError: (error) => setMessage(toUserMessage(error)) })}>Terminar</Button>}</li>)}</ul>}
    </section>
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
        <PatientUpdateForm patient={patient} />
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
    setErrors({})
    revoke.mutate(consentId, {
      onSuccess: () => {
        setErrors({})
        setSuccess('Consentimento revogado. O histórico foi preservado.')
      },
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
            onChange={(event) => {
              const parsed = consentCreateSchema.shape.consent_type.safeParse(event.target.value)
              if (parsed.success) setForm((current) => ({ ...current, consent_type: parsed.data }))
            }}
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
