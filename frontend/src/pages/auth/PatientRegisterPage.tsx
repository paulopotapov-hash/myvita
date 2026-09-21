import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { ErrorState } from '../../components/ErrorState'
import { TextField } from '../../components/TextField'
import { usePatientRegister } from '../../hooks/useAuthMutations'
import { useClinics } from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import { ApiError } from '../../lib/apiClient'
import { toUserMessage } from '../../lib/errorMessages'
import { patientRegisterSchema, zodErrorsToRecord } from '../../lib/validation'
import { AuthLayout } from '../../layouts/AuthLayout'

const EMPTY_FORM = { clinic_id: '', full_name: '', email: '', password: '', birth_date: '', phone: '' }

export function PatientRegisterPage() {
  const { isAuthenticated } = useSession()
  const clinics = useClinics()
  const register = usePatientRegister()
  const [form, setForm] = useState(EMPTY_FORM)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  if (isAuthenticated) return <Navigate to="/app" replace />

  function update<K extends keyof typeof EMPTY_FORM>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const result = patientRegisterSchema.safeParse(form)
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    register.mutate(
      {
        ...result.data,
        birth_date: result.data.birth_date || undefined,
        phone: result.data.phone || undefined,
      },
      {
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
    <AuthLayout title="Criar conta" subtitle="Regista-te como paciente numa clínica myVita">
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="clinic" className="text-sm font-medium text-slate-700">
            Clínica
          </label>
          {clinics.isLoading && <p className="text-sm text-slate-500">A carregar clínicas…</p>}
          {clinics.isError && <ErrorState message={toUserMessage(clinics.error)} onRetry={() => clinics.refetch()} />}
          {clinics.data && (
            <select
              id="clinic"
              value={form.clinic_id}
              onChange={(e) => update('clinic_id', e.target.value)}
              aria-invalid={Boolean(fieldErrors.clinic_id)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600"
            >
              <option value="">Escolhe a tua clínica…</option>
              {clinics.data.map((clinic) => (
                <option key={clinic.id} value={clinic.id}>
                  {clinic.name}
                </option>
              ))}
            </select>
          )}
          {fieldErrors.clinic_id && (
            <p role="alert" className="text-sm text-red-600">
              {fieldErrors.clinic_id}
            </p>
          )}
        </div>
        <TextField
          label="Nome completo"
          value={form.full_name}
          onChange={(e) => update('full_name', e.target.value)}
          error={fieldErrors.full_name}
        />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={(e) => update('email', e.target.value)}
          error={fieldErrors.email}
        />
        <TextField
          label="Palavra-passe"
          type="password"
          autoComplete="new-password"
          value={form.password}
          onChange={(e) => update('password', e.target.value)}
          error={fieldErrors.password}
        />
        <TextField
          label="Data de nascimento (opcional)"
          type="date"
          value={form.birth_date}
          onChange={(e) => update('birth_date', e.target.value)}
        />
        <TextField
          label="Telefone (opcional)"
          value={form.phone}
          onChange={(e) => update('phone', e.target.value)}
        />
        {fieldErrors._root && (
          <p role="alert" className="text-sm text-red-600">
            {fieldErrors._root}
          </p>
        )}
        <Button type="submit" isLoading={register.isPending} className="mt-2 w-full">
          Criar conta
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-500">
        Já tens conta?{' '}
        <Link to="/login" className="font-medium text-teal-700 hover:underline">
          Inicia sessão
        </Link>
      </p>
    </AuthLayout>
  )
}
