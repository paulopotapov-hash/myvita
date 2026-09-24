import { Link } from 'react-router-dom'
import type { UserRole } from '../../types/api'

const ACTIONS: Record<UserRole, Array<{ to: string; label: string; description: string }>> = {
  patient: [
    { to: '/app/consultas', label: 'Consultas', description: 'Consulta os teus agendamentos' },
    { to: '/app/perfil', label: 'Perfil', description: 'Revê os teus dados pessoais' },
  ],
  staff: [
    { to: '/app/consultas', label: 'Consultas', description: 'Consulta e gere a agenda' },
    { to: '/app/pacientes', label: 'Pacientes', description: 'Acede ao diretório da clínica' },
  ],
  clinic_admin: [
    { to: '/app/consultas', label: 'Consultas', description: 'Acompanha a agenda da clínica' },
    { to: '/app/pacientes', label: 'Pacientes', description: 'Consulta os pacientes' },
    { to: '/app/equipa', label: 'Equipa', description: 'Gere os profissionais' },
  ],
}

export function DashboardHeader({ name, context }: { name: string; context: string }) {
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Bom dia' : hour < 19 ? 'Boa tarde' : 'Boa noite'
  return (
    <header>
      <p className="text-sm font-medium text-teal-700">Visão geral</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
        {greeting}, {name}
      </h1>
      <p className="mt-2 max-w-2xl text-slate-600">{context}</p>
    </header>
  )
}

export function QuickActions({ role }: { role: UserRole }) {
  return (
    <section aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="mb-3 text-lg font-semibold text-slate-900">
        Acesso rápido
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {ACTIONS[role].map((action) => (
          <Link
            key={action.to}
            to={action.to}
            className="rounded-xl border border-slate-200 bg-white p-4 transition hover:border-teal-300 hover:bg-teal-50/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
          >
            <span className="font-medium text-slate-900">{action.label}</span>
            <span className="mt-1 block text-sm text-slate-500">{action.description}</span>
          </Link>
        ))}
      </div>
    </section>
  )
}
