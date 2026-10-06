import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { MfaEnrolment } from '../../components/MfaEnrolment'
import { TextField } from '../../components/TextField'
import { useLogout } from '../../hooks/useAuthMutations'
import { SESSION_QUERY_KEY } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { passwordChangeSchema, zodErrorsToRecord } from '../../lib/validation'
import { AuthLayout } from '../../layouts/AuthLayout'
import { authService } from '../../services/auth'
import type { PasswordChangeRequest, PendingAccountAction } from '../../types/api'
import { useFocusFirstInvalid } from '../../hooks/useFocusFirstInvalid'

const TITLES: Record<PendingAccountAction, { title: string; subtitle: string }> = {
  password_change: {
    title: 'Alterar palavra-passe',
    subtitle: 'Antes de continuar, define uma nova palavra-passe só tua.',
  },
  mfa_setup: {
    title: 'Ativar autenticação de dois fatores',
    subtitle: 'O teu perfil exige um segundo fator para aceder a dados clínicos.',
  },
  mfa_verification: {
    title: 'Verificação necessária',
    subtitle: 'Esta sessão ainda não foi validada com o segundo fator.',
  },
}

/**
 * Shown by ProtectedRoute instead of the app while the account has a pending
 * obligation. The backend refuses every other endpoint meanwhile
 * (403 + X-Account-Action-Required), so this page only uses the endpoints
 * it still allows — and logging out is always possible, so nobody is stuck.
 */
export function AccountSetupPage({ action }: { action: PendingAccountAction }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const logout = useLogout()
  const refreshSession = () => queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY })

  function signOut() {
    logout.mutate(undefined, { onSettled: () => navigate('/login', { replace: true }) })
  }

  return (
    <AuthLayout {...TITLES[action]}>
      {action === 'password_change' && <ForcedPasswordChange onDone={refreshSession} />}
      {action === 'mfa_setup' && <MfaEnrolment onDone={refreshSession} />}
      {action === 'mfa_verification' && (
        <p className="text-sm text-slate-700">Termina a sessão e entra novamente para introduzir o código de verificação.</p>
      )}
      <Button variant="secondary" className="mt-6 w-full" onClick={signOut} isLoading={logout.isPending}>
        Terminar sessão
      </Button>
    </AuthLayout>
  )
}

function ForcedPasswordChange({ onDone }: { onDone: () => void }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const formRef = useFocusFirstInvalid(fieldErrors)
  const change = useMutation({ mutationFn: (payload: PasswordChangeRequest) => authService.changePassword(payload) })

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
      { onSuccess: onDone, onError: (error) => setFieldErrors({ _root: toUserMessage(error) }) },
    )
  }

  return (
    <form ref={formRef} onSubmit={submit} noValidate className="flex flex-col gap-4">
      <TextField label="Palavra-passe atual" required type="password" autoComplete="current-password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} error={fieldErrors.current_password} />
      <TextField label="Nova palavra-passe" required type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} error={fieldErrors.new_password} />
      <TextField label="Confirmar nova palavra-passe" required type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} error={fieldErrors.confirm_password} />
      {fieldErrors._root && <p role="alert" className="text-sm text-red-600">{fieldErrors._root}</p>}
      <Button type="submit" isLoading={change.isPending}>Alterar palavra-passe</Button>
    </form>
  )
}
