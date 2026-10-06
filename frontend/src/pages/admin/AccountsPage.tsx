import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useSession } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { passwordResetLink, usersService } from '../../services/users'
import type { AccountSummary } from '../../types/api'

const ACCOUNTS_QUERY_KEY = ['users', 'accounts'] as const

const ROLE_LABELS: Record<AccountSummary['role'], string> = {
  patient: 'Paciente',
  staff: 'Profissional',
  clinic_admin: 'Administrador',
}

/**
 * Clinic-admin account recovery: issue a one-time reset link (handed over
 * out of band), require a password change, reset a lost MFA device and
 * deactivate/reactivate. The backend enforces every rule (own clinic only,
 * never the admin's own account, never another admin's credentials).
 */
export function AccountsPage() {
  const { user } = useSession()
  const queryClient = useQueryClient()
  const [issuedLink, setIssuedLink] = useState<{ name: string; link: string; expiresAt: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const accounts = useQuery({ queryKey: ACCOUNTS_QUERY_KEY, queryFn: ({ signal }) => usersService.list(signal) })

  const action = useMutation({
    mutationFn: async ({ kind, account }: { kind: AccountAction; account: AccountSummary }) => {
      if (kind === 'reset-link') {
        const issued = await usersService.issuePasswordReset(account.id)
        setIssuedLink({ name: account.full_name, link: passwordResetLink(issued.token), expiresAt: issued.expires_at })
        return
      }
      await ACTIONS[kind].run(account.id)
    },
    onMutate: () => setError(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY }),
    onError: (failure) => setError(toUserMessage(failure)),
  })

  function run(kind: AccountAction, account: AccountSummary) {
    if (!window.confirm(`${ACTIONS[kind].confirm} (${account.full_name})`)) return
    setIssuedLink(null)
    action.mutate({ kind, account })
  }

  if (accounts.isLoading) return <LoadingSpinner />
  if (accounts.isError) return <ErrorState message={toUserMessage(accounts.error)} onRetry={() => accounts.refetch()} />
  const items = accounts.data?.items ?? []

  return (
    <div className="max-w-5xl">
      <h1 className="mb-2 text-2xl font-semibold text-slate-900">Contas</h1>
      <p className="mb-6 text-sm text-slate-500">
        Recuperação de acesso da equipa e dos pacientes desta clínica. A recuperação de outro administrador é feita
        pelo operador da plataforma.
      </p>
      {error && <p role="alert" className="mb-4 text-sm text-red-600">{error}</p>}
      {issuedLink && (
        <div role="status" className="mb-6 rounded-xl border border-teal-200 bg-teal-50 p-4 text-sm">
          <p className="font-medium text-teal-900">Ligação de redefinição para {issuedLink.name}</p>
          <p className="mt-1 text-teal-800">
            Mostrada apenas agora. Entrega-a pessoalmente ou por um canal seguro; expira em{' '}
            {new Date(issuedLink.expiresAt).toLocaleString('pt-PT')}.
          </p>
          <p className="mt-2 break-all rounded bg-white p-2 font-mono text-xs">{issuedLink.link}</p>
          <div className="mt-2 flex gap-2">
            <Button variant="secondary" onClick={() => void navigator.clipboard?.writeText(issuedLink.link)}>Copiar</Button>
            <Button variant="secondary" onClick={() => setIssuedLink(null)}>Fechar</Button>
          </div>
        </div>
      )}
      {items.length === 0 ? (
        <EmptyState title="Sem contas" description="Ainda não existem contas nesta clínica." />
      ) : (
        <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
          {items.map((account) => {
            const isSelf = account.id === user?.id
            const isOtherAdmin = account.role === 'clinic_admin' && !isSelf
            return (
              <li key={account.id} className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{account.full_name}{isSelf && ' (tu)'}</p>
                  <p className="text-sm text-slate-500">
                    {ROLE_LABELS[account.role]}
                    {account.email && ` · ${account.email}`}
                    {' · '}{account.is_active ? 'Ativa' : 'Desativada'}
                    {account.mfa_enabled && ' · 2FA ativa'}
                    {account.must_change_password && ' · alteração de palavra-passe pendente'}
                  </p>
                </div>
                {!isSelf && (
                  <div className="flex flex-wrap gap-2">
                    {account.is_active && !isOtherAdmin && (
                      <>
                        <Button variant="secondary" onClick={() => run('reset-link', account)} disabled={action.isPending}>Ligação de redefinição</Button>
                        {!account.must_change_password && (
                          <Button variant="secondary" onClick={() => run('require-change', account)} disabled={action.isPending}>Exigir nova palavra-passe</Button>
                        )}
                        {account.mfa_enabled && (
                          <Button variant="secondary" onClick={() => run('reset-mfa', account)} disabled={action.isPending}>Repor 2FA</Button>
                        )}
                      </>
                    )}
                    {account.is_active ? (
                      <Button variant="secondary" onClick={() => run('deactivate', account)} disabled={action.isPending}>Desativar</Button>
                    ) : (
                      <Button variant="secondary" onClick={() => run('reactivate', account)} disabled={action.isPending}>Reativar</Button>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

type AccountAction = 'reset-link' | 'require-change' | 'reset-mfa' | 'deactivate' | 'reactivate'

const ACTIONS: Record<AccountAction, { confirm: string; run: (id: string) => Promise<unknown> }> = {
  'reset-link': { confirm: 'Emitir uma ligação de redefinição de palavra-passe? Ligações anteriores deixam de funcionar.', run: usersService.issuePasswordReset },
  'require-change': { confirm: 'Exigir que esta pessoa altere a palavra-passe no próximo acesso?', run: usersService.requirePasswordChange },
  'reset-mfa': { confirm: 'Repor a autenticação de dois fatores? A pessoa perde todas as sessões e terá de a configurar de novo.', run: usersService.resetMfa },
  deactivate: { confirm: 'Desativar esta conta? Todas as sessões terminam imediatamente; nenhum dado é apagado.', run: usersService.deactivate },
  reactivate: { confirm: 'Reativar esta conta?', run: usersService.reactivate },
}
