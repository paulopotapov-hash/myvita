import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <p className="text-lg font-semibold text-teal-700">myVita</p>
      <h1 className="text-2xl font-semibold text-slate-900">Página não encontrada</h1>
      <Link to="/" className="text-teal-700 hover:underline">
        Voltar ao início
      </Link>
    </div>
  )
}
