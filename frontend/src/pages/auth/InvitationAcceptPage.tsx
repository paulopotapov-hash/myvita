import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { SESSION_QUERY_KEY } from '../../hooks/useSession'
import { ApiError } from '../../lib/apiClient'
import { homePathForRole } from '../../lib/navigation'
import { toUserMessage } from '../../lib/errorMessages'
import { invitationAcceptSchema, zodErrorsToRecord } from '../../lib/validation'
import { AuthLayout } from '../../layouts/AuthLayout'
import { invitationsService } from '../../services/invitations'
import { useFocusFirstInvalid } from '../../hooks/useFocusFirstInvalid'

export function InvitationAcceptPage() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '')
  const queryClient = useQueryClient()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const formRef = useFocusFirstInvalid(fieldErrors)
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, '', '/convite')
  }, [])
  const accept = useMutation({
    mutationFn: () => invitationsService.accept({ token, password }),
    onSuccess: (user) => {
      queryClient.clear()
      queryClient.setQueryData(SESSION_QUERY_KEY, user)
    },
  })
  // Once accepted the token is spent: a refetch (e.g. after the cache is cleared above) would
  // answer 410 and show "already used" next to the success message.
  const preview = useQuery({
    queryKey: ['invitation-preview', token],
    queryFn: ({ signal }) => invitationsService.preview(token, signal),
    enabled: Boolean(token) && !accept.isSuccess,
    retry: false,
  })

  if (!token) {
    return <Navigate to="/login" replace />
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const result = invitationAcceptSchema.safeParse({ password, confirm_password: confirmPassword })
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    accept.mutate(undefined, {
      onError: (error) => setFieldErrors({ _root: toUserMessage(error) }),
    })
  }

  return (
    <AuthLayout title="Aceitar convite" subtitle="Define a tua palavra-passe para ativar a conta">
      {preview.isLoading && <LoadingSpinner />}
      {preview.isError && (
        // 404/410/422 are final (unknown, used, revoked or expired): retrying cannot help.
        preview.error instanceof ApiError && [404, 410, 422].includes(preview.error.status) ? (
          <div role="alert" className="flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <p className="font-medium">{preview.error.status === 410 ? toUserMessage(preview.error) : 'Este convite não é válido.'}</p>
            <p>Peça à clínica um novo convite. Se já ativou a conta, inicie sessão.</p>
            <Link className="font-medium underline" to="/login">Ir para o início de sessão</Link>
          </div>
        ) : (
          <ErrorState message={toUserMessage(preview.error)} onRetry={() => preview.refetch()} />
        )
      )}
      {preview.data && !accept.isSuccess && (
        <>
          <div className="mb-5 rounded-md bg-slate-50 p-3 text-sm text-slate-700">
            <p className="font-medium">{preview.data.clinic_name}</p>
            <p>{preview.data.full_name} · {preview.data.email}</p>
          </div>
          <form ref={formRef} onSubmit={submit} noValidate className="flex flex-col gap-4">
            <TextField label="Nova palavra-passe" required type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={fieldErrors.password} />
            <TextField label="Confirmar palavra-passe" required type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} error={fieldErrors.confirm_password} />
            {fieldErrors._root && <p role="alert" className="text-sm text-red-600">{fieldErrors._root}</p>}
            <Button type="submit" isLoading={accept.isPending}>Ativar conta</Button>
          </form>
        </>
      )}
      {accept.isSuccess && (
        <p className="text-sm text-teal-700">Conta ativada. <Link className="font-medium underline" to={homePathForRole(accept.data.role)}>Continuar</Link></p>
      )}
    </AuthLayout>
  )
}
