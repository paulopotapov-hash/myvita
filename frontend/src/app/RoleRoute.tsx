import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import type { UserRole } from '../types/api'

/**
 * Only ever rendered inside ProtectedRoute, so a session is guaranteed to
 * exist. If the current role isn't allowed, redirect to the dashboard
 * instead of showing a dead-end "forbidden" page — the nav itself never
 * offers a link a role can't use, so reaching this case means a typed-in
 * URL, not a broken flow.
 */
export function RoleRoute({ allow, children }: { allow: UserRole[]; children: ReactNode }) {
  const { user } = useSession()
  if (!user) return null
  if (!allow.includes(user.role)) {
    return (
      <section role="alert" className="mx-auto max-w-xl rounded-xl border border-amber-200 bg-amber-50 px-6 py-10 text-center">
        <h1 className="text-xl font-semibold text-slate-900">Acesso não autorizado</h1>
        <p className="mt-2 text-sm text-slate-600">Não tens permissão para aceder a esta área.</p>
        <Link
          to="/app"
          className="mt-5 inline-flex rounded-md bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
        >
          Voltar ao início
        </Link>
      </section>
    )
  }
  return <>{children}</>
}
