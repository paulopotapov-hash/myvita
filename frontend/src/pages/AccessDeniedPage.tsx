import { Link } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import { homePathForRole } from '../lib/navigation'

export function AccessDeniedPage() {
  const { user } = useSession()
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="text-2xl font-semibold text-slate-900">Acesso não permitido</h1>
      <p className="max-w-md text-slate-600">A tua conta não tem permissão para abrir esta página.</p>
      <Link to={user ? homePathForRole(user.role) : '/login'} className="rounded-md bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2">
        {user ? 'Voltar à página inicial' : 'Iniciar sessão'}
      </Link>
    </main>
  )
}
