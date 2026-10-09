import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { Button } from '../../components/Button'
import { TextField } from '../../components/TextField'
import { useLogin, useVerifyMfa } from '../../hooks/useAuthMutations'
import { useFocusFirstInvalid } from '../../hooks/useFocusFirstInvalid'
import { useSession } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { safePostLoginPath } from '../../lib/navigation'
import { loginSchema, mfaVerificationCodeSchema, zodErrorsToRecord } from '../../lib/validation'
import { AuthLayout } from '../../layouts/AuthLayout'
import { isMfaChallenge } from '../../types/api'

export function LoginPage() {
  const { user } = useSession()
  const location = useLocation()
  const login = useLogin()
  const verifyMfa = useVerifyMfa()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const formRef = useFocusFirstInvalid(fieldErrors)
  const [step, setStep] = useState<'credentials' | 'mfa'>('credentials')
  const [code, setCode] = useState('')

  // Already logged in (e.g. opened /login in a second tab) — go straight in.
  if (user) {
    const redirectTo = safePostLoginPath(location.state, user.role)
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
      onSuccess: (response) => {
        if (isMfaChallenge(response)) {
          setPassword('')
          setStep('mfa')
        }
      },
      onError: (error) => {
        setFieldErrors({ _root: toUserMessage(error) })
      },
    })
  }

  function handleCodeSubmit(event: React.FormEvent) {
    event.preventDefault()
    const parsed = mfaVerificationCodeSchema.safeParse(code)
    if (!parsed.success) {
      setFieldErrors({ code: parsed.error.issues[0].message })
      return
    }
    setFieldErrors({})
    verifyMfa.mutate(parsed.data, {
      onError: (error) => {
        setCode('')
        setFieldErrors({ _root: toUserMessage(error) })
      },
    })
  }

  if (step === 'mfa') {
    return (
      <AuthLayout title="Verificação em dois passos" subtitle="Introduz o código da tua aplicação autenticadora">
        <form ref={formRef} onSubmit={handleCodeSubmit} noValidate className="flex flex-col gap-4">
          <TextField
            label="Código de verificação"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value)}
            error={fieldErrors.code}
          />
          <p className="text-xs text-slate-500">Sem acesso ao dispositivo? Usa um dos teus códigos de recuperação.</p>
          {fieldErrors._root && (
            <p role="alert" className="text-sm text-red-600">
              {fieldErrors._root}
            </p>
          )}
          <Button type="submit" isLoading={verifyMfa.isPending} className="mt-2 w-full">
            Verificar
          </Button>
          <Button variant="secondary" onClick={() => { setStep('credentials'); setCode(''); setFieldErrors({}) }}>
            Voltar
          </Button>
        </form>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Iniciar sessão" subtitle="Acede à tua conta myVita">
      <form ref={formRef} onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
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
      <p className="mt-4 text-center text-sm">
        <Link to="/recuperar-acesso" className="font-medium text-teal-700 hover:underline">
          Esqueceste-te da palavra-passe?
        </Link>
      </p>
    </AuthLayout>
  )
}
