import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { TextField } from '../../components/TextField'
import { useClinicOnboarding } from '../../hooks/useAuthMutations'
import { useSession } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { ApiError } from '../../lib/apiClient'
import { clinicOnboardingSchema, zodErrorsToRecord } from '../../lib/validation'
import { AuthLayout } from '../../layouts/AuthLayout'

const EMPTY_FORM = {
  clinic_name: '',
  nif: '',
  address: '',
  phone: '',
  admin_full_name: '',
  admin_email: '',
  admin_password: '',
}

export function ClinicOnboardingPage() {
  const { isAuthenticated } = useSession()
  const onboard = useClinicOnboarding()
  const [form, setForm] = useState(EMPTY_FORM)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  if (isAuthenticated) return <Navigate to="/app" replace />

  function update<K extends keyof typeof EMPTY_FORM>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const result = clinicOnboardingSchema.safeParse(form)
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    onboard.mutate(
      {
        ...result.data,
        nif: result.data.nif || undefined,
        address: result.data.address || undefined,
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
    <AuthLayout title="Criar conta da clínica" subtitle="Regista a tua clínica e a conta de administrador">
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <TextField
          label="Nome da clínica"
          value={form.clinic_name}
          onChange={(e) => update('clinic_name', e.target.value)}
          error={fieldErrors.clinic_name}
        />
        <TextField label="NIF (opcional)" value={form.nif} onChange={(e) => update('nif', e.target.value)} />
        <TextField
          label="Morada (opcional)"
          value={form.address}
          onChange={(e) => update('address', e.target.value)}
        />
        <TextField
          label="Telefone (opcional)"
          value={form.phone}
          onChange={(e) => update('phone', e.target.value)}
        />
        <hr className="my-2 border-slate-200" />
        <TextField
          label="O teu nome"
          value={form.admin_full_name}
          onChange={(e) => update('admin_full_name', e.target.value)}
          error={fieldErrors.admin_full_name}
        />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={form.admin_email}
          onChange={(e) => update('admin_email', e.target.value)}
          error={fieldErrors.admin_email}
        />
        <TextField
          label="Palavra-passe"
          type="password"
          autoComplete="new-password"
          value={form.admin_password}
          onChange={(e) => update('admin_password', e.target.value)}
          error={fieldErrors.admin_password}
        />
        {fieldErrors._root && (
          <p role="alert" className="text-sm text-red-600">
            {fieldErrors._root}
          </p>
        )}
        <Button type="submit" isLoading={onboard.isPending} className="mt-2 w-full">
          Criar clínica
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
