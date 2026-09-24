import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { Button } from '../../components/Button'
import { TextField } from '../../components/TextField'
import { useLogin } from '../../hooks/useAuthMutations'
import { useSession } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { loginSchema, zodErrorsToRecord } from '../../lib/validation'
import { AuthLayout } from '../../layouts/AuthLayout'
import { safeReturnTo } from '../../lib/authSession'

export function LoginPage() {
  const { isAuthenticated } = useSession()
  const location = useLocation()
  const login = useLogin()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  // Already logged in (e.g. opened /login in a second tab) — go straight in.
  if (isAuthenticated) {
    const redirectTo = safeReturnTo((location.state as { from?: unknown } | null)?.from)
    return <Navigate to={redirectTo} replace />
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const result = loginSchema.safeParse({ email, password })
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    login.mutate(result.data, {
      onError: (error) => {
        setFieldErrors({ _root: toUserMessage(error) })
      },
    })
  }

  return (
    <AuthLayout title="Iniciar sessão" subtitle="Acede à tua conta myVita">
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
        />
        <TextField
          label="Palavra-passe"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
        />
        {fieldErrors._root && (
          <p role="alert" className="text-sm text-red-600">
            {fieldErrors._root}
          </p>
        )}
        <Button type="submit" isLoading={login.isPending} className="mt-2 w-full">
          Entrar
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-500">
        Ainda não tens conta?{' '}
        <Link to="/registo" className="font-medium text-teal-700 hover:underline">
          Regista-te como paciente
        </Link>
      </p>
      <p className="mt-2 text-center text-sm text-slate-500">
        Tens uma clínica?{' '}
        <Link to="/nova-clinica" className="font-medium text-teal-700 hover:underline">
          Cria a conta da tua clínica
        </Link>
      </p>
    </AuthLayout>
  )
}
