import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '../components/Button'
import { MfaEnrolment } from '../components/MfaEnrolment'
import { SESSION_QUERY_KEY, useSession } from '../hooks/useSession'
import { TextField } from '../components/TextField'
import { toUserMessage } from '../lib/errorMessages'
import { passwordChangeSchema, zodErrorsToRecord } from '../lib/validation'
import { authService } from '../services/auth'

export function AccountSecurityPage() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const change = useMutation({ mutationFn: authService.changePassword })
  const { user } = useSession()
  const queryClient = useQueryClient()

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const result = passwordChangeSchema.safeParse({
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
    })
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    change.mutate(
      { current_password: result.data.current_password, new_password: result.data.new_password },
      {
        onSuccess: () => {
          setCurrentPassword('')
          setNewPassword('')
          setConfirmPassword('')
        },
        onError: (error) => setFieldErrors({ _root: toUserMessage(error) }),
      },
    )
  }

  return (
    <div className="max-w-xl">
      <h1 className="mb-6 text-2xl font-semibold text-slate-900">Segurança da conta</h1>
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Alterar palavra-passe</h2>
        <form onSubmit={submit} noValidate className="flex flex-col gap-4">
          <TextField label="Palavra-passe atual" type="password" autoComplete="current-password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} error={fieldErrors.current_password} />
          <TextField label="Nova palavra-passe" type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} error={fieldErrors.new_password} />
          <TextField label="Confirmar nova palavra-passe" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} error={fieldErrors.confirm_password} />
          {fieldErrors._root && <p role="alert" className="text-sm text-red-600">{fieldErrors._root}</p>}
          {change.isSuccess && <p className="text-sm text-teal-700">Palavra-passe alterada e sessões anteriores revogadas.</p>}
          <Button type="submit" isLoading={change.isPending}>Alterar palavra-passe</Button>
        </form>
      </section>
      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Autenticação de dois fatores</h2>
        {user?.mfa_enabled ? (
          <p className="text-sm text-teal-700">Ativa. Se perderes o dispositivo, usa um código de recuperação ou pede ao administrador da clínica para a repor.</p>
        ) : (
          <MfaEnrolment onDone={() => queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY })} />
        )}
      </section>
    </div>
  )
}
