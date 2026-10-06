import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { ErrorState } from '../../components/ErrorState'
import { SelectField } from '../../components/SelectField'
import { TextField } from '../../components/TextField'
import { usePatientRegister } from '../../hooks/useAuthMutations'
import { useClinics } from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import { usePublicConfig } from '../../hooks/usePublicConfig'
import { formErrorsFrom, toUserMessage } from '../../lib/errorMessages'
import { patientRegisterSchema, zodErrorsToRecord } from '../../lib/validation'
import { AuthLayout } from '../../layouts/AuthLayout'
import { useFocusFirstInvalid } from '../../hooks/useFocusFirstInvalid'

const EMPTY_FORM = { clinic_id: '', full_name: '', email: '', password: '', birth_date: '', phone: '' }

export function PatientRegisterPage() {
  const { isAuthenticated } = useSession()
  const clinics = useClinics()
  const register = usePatientRegister()
  const publicConfig = usePublicConfig()
  const [form, setForm] = useState(EMPTY_FORM)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const formRef = useFocusFirstInvalid(fieldErrors)

  if (isAuthenticated) return <Navigate to="/app" replace />
  if (publicConfig.isSuccess && !publicConfig.data.patient_registration_enabled) {
    return <Navigate to="/login" replace />
  }

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
        onError: (error) =>
          setFieldErrors(formErrorsFrom(error, ['clinic_id', 'full_name', 'email', 'password', 'birth_date', 'phone'])),
      },
    )
  }

  return (
    <AuthLayout title="Criar conta" subtitle="Regista-te como paciente numa clínica myVita">
      <form ref={formRef} onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        {clinics.isLoading && <p role="status" className="text-sm text-slate-500">A carregar clínicas…</p>}
        {clinics.isError && <ErrorState message={toUserMessage(clinics.error)} onRetry={() => clinics.refetch()} />}
        {clinics.data && (
          <SelectField label="Clínica" required value={form.clinic_id} onChange={(e) => update('clinic_id', e.target.value)} error={fieldErrors.clinic_id}>
            <option value="">Escolhe a tua clínica…</option>
            {clinics.data.map((clinic) => (
              <option key={clinic.id} value={clinic.id}>
                {clinic.name}
              </option>
            ))}
          </SelectField>
        )}
        <TextField
          label="Nome completo" required
          value={form.full_name}
          onChange={(e) => update('full_name', e.target.value)}
          error={fieldErrors.full_name}
        />
        <TextField
          label="Email" required
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={(e) => update('email', e.target.value)}
          error={fieldErrors.email}
        />
        <TextField
          label="Palavra-passe" required
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
