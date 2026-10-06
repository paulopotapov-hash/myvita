import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { SelectField } from '../../components/SelectField'
import { TextField } from '../../components/TextField'
import { useStaff } from '../../hooks/useClinicData'
import { formErrorsFrom, toUserMessage } from '../../lib/errorMessages'
import { staffCreateSchema, zodErrorsToRecord } from '../../lib/validation'
import { invitationsService } from '../../services/invitations'
import type { StaffRole } from '../../types/api'

const STAFF_ROLE_LABELS: Record<StaffRole, string> = {
  doctor: 'Médico(a)',
  nurse: 'Enfermeiro(a)',
  physiotherapist: 'Fisioterapeuta',
  admin: 'Administrativo(a)',
}

const EMPTY_FORM = { full_name: '', email: '', staff_role: 'doctor' as StaffRole, specialty: '' }

export function StaffManagementPage() {
  const staff = useStaff()
  const createStaff = useMutation({ mutationFn: invitationsService.inviteStaff })
  const [form, setForm] = useState(EMPTY_FORM)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [invitationLink, setInvitationLink] = useState('')

  function update<K extends keyof typeof EMPTY_FORM>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (createStaff.isPending) return
    setInvitationLink('')
    const result = staffCreateSchema.safeParse(form)
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    createStaff.mutate(
      { ...result.data, specialty: result.data.specialty || undefined },
      {
        onSuccess: (invitation) => {
          setForm(EMPTY_FORM)
          setInvitationLink(`${window.location.origin}/convite#token=${encodeURIComponent(invitation.token)}`)
        },
        onError: (error) => setFieldErrors(formErrorsFrom(error, ['full_name', 'email', 'staff_role', 'specialty'])),
      },
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">Equipa</h1>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium text-slate-900">Convidar profissional</h2>
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
          <SelectField label="Função" value={form.staff_role} onChange={(e) => update('staff_role', e.target.value)} error={fieldErrors.staff_role}>
            {Object.entries(STAFF_ROLE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </SelectField>
          <TextField
            label="Especialidade (opcional)"
            value={form.specialty}
            onChange={(e) => update('specialty', e.target.value)}
            error={fieldErrors.specialty}
          />
          <div className="sm:col-span-2">
            {fieldErrors._root && <FormMessage kind="error" className="mb-2">{fieldErrors._root}</FormMessage>}
            {invitationLink && (
              <div className="mb-3 rounded-md bg-teal-50 p-3 text-sm text-teal-900">
                <p className="font-medium">Convite criado. Partilha uma única vez por um canal privado aprovado.</p>
                <p className="mt-1 break-all select-all">{invitationLink}</p>
              </div>
            )}
            <Button type="submit" isLoading={createStaff.isPending}>
              Criar convite
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
