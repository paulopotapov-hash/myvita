import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { usePatient, useUpdatePatient } from '../../hooks/usePatientRecord'
import { ApiError } from '../../lib/apiClient'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDate, formatDateTime } from '../../lib/formatDate'
import { patientUpdateSchema, zodErrorsToRecord, type PatientUpdateFormValues } from '../../lib/validation'
import type { PatientPublic } from '../../types/api'

function valuesFrom(patient: PatientPublic): PatientUpdateFormValues {
  return {
    full_name: patient.full_name,
    birth_date: patient.birth_date ?? '',
    phone: patient.phone ?? '',
    national_health_number: patient.national_health_number ?? '',
  }
}

export function PatientRecordPage() {
  const { patientId } = useParams()
  const patient = usePatient(patientId)

  if (patient.isLoading) return <LoadingSpinner label="A carregar ficha do paciente…" />
  if (patient.isError) return <PatientLoadError error={patient.error} onRetry={() => patient.refetch()} />
  if (!patient.data || !patientId) return <EmptyState title="Paciente não encontrado" />

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <Link to="/app/pacientes" className="w-fit rounded-sm text-sm font-medium text-teal-700 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700">
        ← Voltar aos pacientes
      </Link>
      <PatientRecord patient={patient.data} />
    </div>
  )
}

function PatientLoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (error instanceof ApiError && error.status === 403) {
    return <ErrorState message="Não tens permissão para consultar esta ficha de paciente." />
  }
  if (error instanceof ApiError && error.status === 404) {
    return <EmptyState title="Paciente não encontrado" description="O paciente não existe ou não está disponível para a tua clínica." />
  }
  return <ErrorState message={toUserMessage(error)} onRetry={onRetry} />
}

function PatientRecord({ patient }: { patient: PatientPublic }) {
  const [editing, setEditing] = useState(false)

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-teal-700">Ficha do paciente</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">{patient.full_name}</h1>
          <p className="mt-2 text-sm text-slate-500">Informação protegida · acesso sujeito a auditoria</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-sm font-medium ${patient.is_active === false ? 'bg-slate-200 text-slate-700' : 'bg-emerald-100 text-emerald-800'}`}>
          {patient.is_active === false ? 'Paciente inativo' : 'Paciente ativo'}
        </span>
      </header>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6" aria-labelledby="patient-details-title">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="patient-details-title" className="text-lg font-semibold text-slate-900">Dados pessoais</h2>
          {!editing && <Button variant="secondary" onClick={() => setEditing(true)}>Editar dados</Button>}
        </div>
        {editing ? (
          <PatientEditForm patient={patient} onClose={() => setEditing(false)} />
        ) : (
          <PatientDetails patient={patient} />
        )}
      </section>
    </>
  )
}

function PatientDetails({ patient }: { patient: PatientPublic }) {
  return (
    <dl className="mt-6 grid gap-x-8 gap-y-6 sm:grid-cols-2">
      <Datum label="Nome completo" value={patient.full_name} />
      <Datum label="Data de nascimento" value={patient.birth_date ? formatDate(patient.birth_date) : 'Não indicada'} />
      <Datum label="Telefone" value={patient.phone || 'Não indicado'} />
      <Datum label="Número de utente" value={patient.national_health_number || 'Não indicado'} />
      <Datum label="Estado da conta" value={patient.is_active === false ? 'Inativa' : 'Ativa'} />
      <Datum label="Ficha atualizada" value={patient.updated_at ? formatDateTime(patient.updated_at) : 'Não disponível'} />
    </dl>
  )
}

function PatientEditForm({ patient, onClose }: { patient: PatientPublic; onClose: () => void }) {
  const initialValues = useMemo(() => valuesFrom(patient), [patient])
  const [form, setForm] = useState(initialValues)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState('')
  const update = useUpdatePatient()
  const dirty = JSON.stringify(form) !== JSON.stringify(initialValues)

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  function cancel() {
    setForm(initialValues)
    setFieldErrors({})
    setFormError('')
    onClose()
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setFormError('')
    const parsed = patientUpdateSchema.safeParse(form)
    if (!parsed.success) {
      setFieldErrors(zodErrorsToRecord(parsed.error))
      return
    }
    setFieldErrors({})
    update.mutate(
      {
        patientId: patient.id,
        payload: {
          full_name: parsed.data.full_name,
          birth_date: parsed.data.birth_date || null,
          phone: parsed.data.phone || null,
          national_health_number: parsed.data.national_health_number || null,
        },
      },
      {
        onSuccess: onClose,
        onError: (error) => {
          if (error instanceof ApiError && error.fieldErrors) setFieldErrors(error.fieldErrors)
          setFormError(toUserMessage(error))
        },
      },
    )
  }

  return (
    <form onSubmit={submit} className="mt-6 grid gap-4 sm:grid-cols-2" noValidate>
      <TextField label="Nome completo" autoComplete="name" maxLength={255} value={form.full_name} error={fieldErrors.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} />
      <TextField label="Data de nascimento" type="date" value={form.birth_date} error={fieldErrors.birth_date} onChange={(event) => setForm({ ...form, birth_date: event.target.value })} />
      <TextField label="Telefone" type="tel" autoComplete="tel" maxLength={30} value={form.phone} error={fieldErrors.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} />
      <TextField label="Número de utente" maxLength={30} value={form.national_health_number} error={fieldErrors.national_health_number} onChange={(event) => setForm({ ...form, national_health_number: event.target.value })} />
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        {formError && <p role="alert" className="w-full text-sm text-red-700">{formError}</p>}
        <Button type="submit" isLoading={update.isPending} disabled={!dirty}>Guardar</Button>
        <Button variant="secondary" onClick={cancel} disabled={update.isPending}>Cancelar</Button>
      </div>
    </form>
  )
}

function Datum({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 break-words text-sm font-medium text-slate-900">{value}</dd></div>
}
