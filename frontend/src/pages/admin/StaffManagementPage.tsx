import { useState } from 'react'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { useCreateStaff, useStaff } from '../../hooks/useClinicData'
import { ApiError } from '../../lib/apiClient'
import { toUserMessage } from '../../lib/errorMessages'
import { staffCreateSchema, zodErrorsToRecord } from '../../lib/validation'
import type { StaffRole } from '../../types/api'

const STAFF_ROLE_LABELS: Record<StaffRole, string> = {
  doctor: 'Médico(a)',
  nurse: 'Enfermeiro(a)',
  admin: 'Administrativo(a)',
}

const EMPTY_FORM = { full_name: '', email: '', password: '', staff_role: 'doctor' as StaffRole, specialty: '' }

export function StaffManagementPage() {
  const staff = useStaff()
  const createStaff = useCreateStaff()
  const [form, setForm] = useState(EMPTY_FORM)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [justCreated, setJustCreated] = useState(false)

  function update<K extends keyof typeof EMPTY_FORM>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setJustCreated(false)
    const result = staffCreateSchema.safeParse(form)
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    createStaff.mutate(
      { ...result.data, specialty: result.data.specialty || undefined },
      {
        onSuccess: () => {
          setForm(EMPTY_FORM)
          setJustCreated(true)
        },
        onError: (error) => {
          if (error instanceof ApiError && error.fieldErrors) {
            setFieldErrors(error.fieldErrors)
          } else {
            setFieldErrors({ _root: toUserMessage(error) })
          }
        },
      },
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">Equipa</h1>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium text-slate-900">Adicionar profissional</h2>
        <form onSubmit={handleSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Nome completo"
            value={form.full_name}
            onChange={(e) => update('full_name', e.target.value)}
            error={fieldErrors.full_name}
          />
          <TextField
            label="Email"
            type="email"
            value={form.email}
            onChange={(e) => update('email', e.target.value)}
            error={fieldErrors.email}
          />
          <TextField
            label="Palavra-passe inicial"
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => update('password', e.target.value)}
            error={fieldErrors.password}
          />
          <div className="flex flex-col gap-1">
            <label htmlFor="staff_role" className="text-sm font-medium text-slate-700">
              Função
            </label>
            <select
              id="staff_role"
              value={form.staff_role}
              onChange={(e) => update('staff_role', e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600"
            >
              {Object.entries(STAFF_ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <TextField
            label="Especialidade (opcional)"
            value={form.specialty}
            onChange={(e) => update('specialty', e.target.value)}
          />
          <div className="sm:col-span-2">
            {fieldErrors._root && (
              <p role="alert" className="mb-2 text-sm text-red-600">
                {fieldErrors._root}
              </p>
            )}
            {justCreated && <p className="mb-2 text-sm text-teal-700">Profissional adicionado com sucesso.</p>}
            <Button type="submit" isLoading={createStaff.isPending}>
              Adicionar
            </Button>
          </div>
        </form>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium text-slate-900">Equipa atual</h2>
        {staff.isLoading && <LoadingSpinner />}
        {staff.isError && <ErrorState message={toUserMessage(staff.error)} onRetry={() => staff.refetch()} />}
        {staff.data && staff.data.length === 0 && <EmptyState title="Sem profissionais registados" />}
        {staff.data && staff.data.length > 0 && (
          <ul className="flex flex-col divide-y divide-slate-100">
            {staff.data.map((member) => (
              <li key={member.id} className="flex items-center justify-between py-3">
                <div>
                  <p className="font-medium text-slate-900">{member.full_name}</p>
                  {member.specialty && <p className="text-sm text-slate-500">{member.specialty}</p>}
                </div>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-600">
                  {STAFF_ROLE_LABELS[member.staff_role]}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
