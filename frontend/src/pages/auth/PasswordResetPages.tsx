import { useMutation } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/Button'
import { TextField } from '../../components/TextField'
import { toUserMessage } from '../../lib/errorMessages'
import { invitationAcceptSchema, loginSchema, zodErrorsToRecord } from '../../lib/validation'
import { AuthLayout } from '../../layouts/AuthLayout'
import { authService } from '../../services/auth'
import { useFocusFirstInvalid } from '../../hooks/useFocusFirstInvalid'

/**
 * Self-service entry point. No delivery channel is approved yet, so the
 * backend never issues a link here: it records the request for the clinic
 * and always answers the same way (no account enumeration).
 */
export function PasswordResetRequestPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const formRef = useFocusFirstInvalid(useMemo<Record<string, string>>(() => Object.fromEntries(error ? [['email', error]] : []), [error]))
  const request = useMutation({ mutationFn: (email: string) => authService.requestPasswordReset(email) })

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const result = loginSchema.shape.email.safeParse(email)
    if (!result.success) {
      setError(result.error.issues[0].message)
      return
    }
    setError(null)
    request.mutate(result.data, { onError: (failure) => setError(toUserMessage(failure)) })
  }

  return (
    <AuthLayout title="Recuperar acesso" subtitle="A redefinição é feita pelo administrador da tua clínica">
      {request.data ? (
        <p role="status" className="text-sm text-slate-700">{request.data.detail}</p>
      ) : (
        <form ref={formRef} onSubmit={submit} noValidate className="flex flex-col gap-4">
          <TextField label="Email" required type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} error={error ?? undefined} />
          <Button type="submit" isLoading={request.isPending}>Pedir ajuda</Button>
        </form>
      )}
      <p className="mt-6 text-center text-sm">
        <Link to="/login" className="font-medium text-teal-700 hover:underline">Voltar ao início de sessão</Link>
      </p>
    </AuthLayout>
  )
}

/** Opens a link issued by a clinic admin (token in the URL fragment). */
export function PasswordResetConfirmPage() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const confirmFormRef = useFocusFirstInvalid(fieldErrors)
  const confirm = useMutation({ mutationFn: () => authService.confirmPasswordReset(token, password) })

  // Drop the token from the address bar/history as soon as it is read.
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, '', '/redefinir-palavra-passe')
  }, [])

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const result = invitationAcceptSchema.safeParse({ password, confirm_password: confirmPassword })
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    confirm.mutate(undefined, { onError: (error) => setFieldErrors({ _root: toUserMessage(error) }) })
  }

  return (
    <AuthLayout title="Redefinir palavra-passe" subtitle="Escolhe uma nova palavra-passe">
      {!token && <p role="alert" className="text-sm text-red-600">Ligação de redefinição inválida ou incompleta.</p>}
      {token && !confirm.isSuccess && (
        <form ref={confirmFormRef} onSubmit={submit} noValidate className="flex flex-col gap-4">
          <TextField label="Nova palavra-passe" required type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={fieldErrors.password} />
          <TextField label="Confirmar palavra-passe" required type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} error={fieldErrors.confirm_password} />
          {fieldErrors._root && <p role="alert" className="text-sm text-red-600">{fieldErrors._root}</p>}
          <Button type="submit" isLoading={confirm.isPending}>Guardar palavra-passe</Button>
        </form>
      )}
      {confirm.isSuccess && (
        <p role="status" className="text-sm text-teal-700">
          Palavra-passe alterada e sessões anteriores terminadas.{' '}
          <Link className="font-medium underline" to="/login">Iniciar sessão</Link>
        </p>
      )}
    </AuthLayout>
  )
}
