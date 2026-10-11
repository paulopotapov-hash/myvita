import { useState } from 'react'
import { Button } from '../../components/Button'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PatientIdentifiersCard } from '../../components/PatientIdentifiersCard'
import { TextField } from '../../components/TextField'
import { useSession } from '../../hooks/useSession'
import { useOwnClinicName } from '../../hooks/useOwnClinicName'
import { usePatient, useUpdatePatient } from '../../hooks/useClinicData'
import { formatAddress } from '../../lib/address'
import { ApiError } from '../../lib/apiClient'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDate } from '../../lib/formatDate'
import { addressSchema, zodErrorsToRecord } from '../../lib/validation'
import type { PatientPublic } from '../../types/api'

const ROLE_LABELS = {
  patient: 'Paciente',
  staff: 'Profissional de saúde',
  clinic_admin: 'Administrador da clínica',
} as const

/**
 * Account and personal data of the signed-in patient. Email is read-only; the patient edits
 * phone and address. Identifiers (NIF, NISS, Nº de utente) are masked, with an audited
 * "Mostrar"; only the care team and administrative staff change them.
 */
export function PatientProfilePage() {
  const { user } = useSession()
  const clinicName = useOwnClinicName()
  const patient = usePatient(user?.patient_id ?? '')

  if (!user) return null

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
      <h1 className="text-2xl font-semibold text-slate-900">O meu perfil</h1>
      {!user.patient_id && <ErrorState message="A sessão não contém uma identidade de paciente válida." />}
      <section aria-labelledby="profile-account" className="rounded-xl border border-slate-200 bg-white">
        <h2 id="profile-account" className="px-5 pt-4 text-base font-semibold text-slate-900">Conta</h2>
        <dl className="divide-y divide-slate-100">
          <Row label="Nome" value={user.full_name} />
          <Row label="Email" value={user.email} />
          <Row label="Tipo de conta" value={ROLE_LABELS[user.role]} />
          <Row label="Clínica" value={clinicName ?? '—'} />
        </dl>
      </section>
      {patient.isLoading && <LoadingSpinner label="A carregar dados do perfil…" />}
      {patient.isError && <ErrorState message="Não foi possível carregar os dados do perfil clínico." onRetry={() => patient.refetch()} />}
      {patient.data && <PersonalData patient={patient.data} />}
      {patient.data && <PatientIdentifiersCard patientId={patient.data.id} />}
    </div>
  )
}

function PersonalData({ patient }: { patient: PatientPublic }) {
  return (
    <section aria-labelledby="profile-personal" className="rounded-xl border border-slate-200 bg-white">
      <h2 id="profile-personal" className="px-5 pt-4 text-base font-semibold text-slate-900">Dados pessoais</h2>
      <dl className="divide-y divide-slate-100">
        <Row label="Data de nascimento" value={patient.birth_date ? formatDate(patient.birth_date) : '—'} />
        <PhoneRow patient={patient} />
        <AddressRow patient={patient} />
      </dl>
    </section>
  )
}

function PhoneRow({ patient }: { patient: PatientPublic }) {
  const update = useUpdatePatient(patient.id)
  const [editing, setEditing] = useState(false)
  const [phone, setPhone] = useState(patient.phone ?? '')
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)

  if (!editing) {
    return (
      <div className="flex items-center justify-between gap-3 px-5 py-3">
        <dt className="text-sm text-slate-500">Telefone</dt>
        <dd className="flex flex-col items-end gap-2 text-sm font-medium text-slate-900">
          <span className="flex items-center gap-3">
            {patient.phone ?? '—'}
            <Button variant="secondary" aria-label="Editar telefone" onClick={() => { setPhone(patient.phone ?? ''); setMessage(null); setEditing(true) }}>Editar</Button>
          </span>
          {message && <FormMessage kind={message.kind}>{message.text}</FormMessage>}
        </dd>
      </div>
    )
  }

  return (
    <div className="px-5 py-3">
      <dt className="sr-only">Telefone</dt>
      <dd>
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            update.mutate({ phone: phone.trim() || null }, {
              onSuccess: () => { setEditing(false); setMessage({ kind: 'success', text: 'Telefone atualizado.' }) },
              onError: (error) => setMessage({ kind: 'error', text: toUserMessage(error) }),
            })
          }}
        >
          <TextField label="Telefone" type="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} maxLength={30} />
          {message?.kind === 'error' && <FormMessage kind="error">{message.text}</FormMessage>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" isLoading={update.isPending}>Guardar</Button>
            <Button variant="secondary" disabled={update.isPending} onClick={() => { setEditing(false); setMessage(null) }}>Cancelar</Button>
          </div>
        </form>
      </dd>
    </div>
  )
}

function AddressRow({ patient }: { patient: PatientPublic }) {
  const update = useUpdatePatient(patient.id)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ street: '', postal_code: '', locality: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  if (!editing) {
    return (
      <div className="flex items-center justify-between gap-3 px-5 py-3">
        <dt className="text-sm text-slate-500">Morada</dt>
        <dd className="flex flex-col items-end gap-2 text-right text-sm font-medium text-slate-900">
          <span className="flex items-center gap-3">
            {formatAddress(patient.address) ?? '—'}
            <Button
              variant="secondary"
              aria-label="Editar morada"
              onClick={() => {
                setForm({ street: patient.address.street ?? '', postal_code: patient.address.postal_code ?? '', locality: patient.address.locality ?? '' })
                setErrors({})
                setSaved(false)
                setEditing(true)
              }}
            >
              Editar
            </Button>
          </span>
          {saved && <FormMessage kind="success">Morada atualizada.</FormMessage>}
        </dd>
      </div>
    )
  }

  return (
    <div className="px-5 py-3">
      <dt className="sr-only">Morada</dt>
      <dd>
        <form
          noValidate
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault()
            const parsed = addressSchema.safeParse(form)
            if (!parsed.success) {
              setErrors(zodErrorsToRecord(parsed.error))
              return
            }
            update.mutate(
              {
                address_street: parsed.data.street || null,
                address_postal_code: parsed.data.postal_code || null,
                address_locality: parsed.data.locality || null,
              },
              {
                onSuccess: () => { setEditing(false); setSaved(true) },
                onError: (error) => {
                  const fields = error instanceof ApiError ? error.fieldErrors : null
                  setErrors(fields
                    ? { street: fields.address_street, postal_code: fields.address_postal_code, locality: fields.address_locality }
                    : { _root: toUserMessage(error) })
                },
              },
            )
          }}
        >
          <div className="sm:col-span-2">
            <TextField label="Rua" autoComplete="street-address" value={form.street} onChange={(event) => setForm({ ...form, street: event.target.value })} error={errors.street} maxLength={200} />
          </div>
          <TextField label="Código postal" placeholder="0000-000" inputMode="numeric" autoComplete="postal-code" value={form.postal_code} onChange={(event) => setForm({ ...form, postal_code: event.target.value })} error={errors.postal_code} maxLength={8} />
          <TextField label="Localidade" autoComplete="address-level2" value={form.locality} onChange={(event) => setForm({ ...form, locality: event.target.value })} error={errors.locality} maxLength={100} />
          {errors._root && <FormMessage kind="error" className="sm:col-span-2">{errors._root}</FormMessage>}
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <Button type="submit" isLoading={update.isPending}>Guardar morada</Button>
            <Button variant="secondary" disabled={update.isPending} onClick={() => setEditing(false)}>Cancelar</Button>
          </div>
        </form>
      </dd>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 px-5 py-3">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="text-right text-sm font-medium text-slate-900">{value}</dd>
    </div>
  )
}
