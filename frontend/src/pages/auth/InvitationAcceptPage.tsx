import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { Button } from '../../components/Button'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { SESSION_QUERY_KEY } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { invitationAcceptSchema, zodErrorsToRecord } from '../../lib/validation'
import { AuthLayout } from '../../layouts/AuthLayout'
import { invitationsService } from '../../services/invitations'

export function InvitationAcceptPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const queryClient = useQueryClient()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const preview = useQuery({
    queryKey: ['invitation-preview', token],
    queryFn: ({ signal }) => invitationsService.preview(token, signal),
    enabled: Boolean(token),
    retry: false,
  })
  const accept = useMutation({
    mutationFn: () => invitationsService.accept({ token, password }),
    onSuccess: (user) => {
      queryClient.clear()
      queryClient.setQueryData(SESSION_QUERY_KEY, user)
    },
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
      {preview.isError && <ErrorState message={toUserMessage(preview.error)} onRetry={() => preview.refetch()} />}
      {preview.data && !accept.isSuccess && (
        <>
          <div className="mb-5 rounded-md bg-slate-50 p-3 text-sm text-slate-700">
            <p className="font-medium">{preview.data.clinic_name}</p>
            <p>{preview.data.full_name} · {preview.data.email}</p>
          </div>
          <form onSubmit={submit} noValidate className="flex flex-col gap-4">
            <TextField label="Nova palavra-passe" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={fieldErrors.password} />
            <TextField label="Confirmar palavra-passe" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} error={fieldErrors.confirm_password} />
            {fieldErrors._root && <p role="alert" className="text-sm text-red-600">{fieldErrors._root}</p>}
            <Button type="submit" isLoading={accept.isPending}>Ativar conta</Button>
          </form>
        </>
      )}
      {accept.isSuccess && (
        <p className="text-sm text-teal-700">Conta ativada. <Link className="font-medium underline" to="/app">Continuar</Link></p>
      )}
    </AuthLayout>
  )
}
