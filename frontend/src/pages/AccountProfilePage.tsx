import { Link } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import { useOwnClinicName } from '../hooks/useOwnClinicName'
import type { UserRole } from '../types/api'

const ROLE_LABELS: Record<UserRole, string> = {
  patient: 'Paciente',
  staff: 'Profissional de saúde',
  clinic_admin: 'Administrador da clínica',
}

export function AccountProfilePage() {
  const { user } = useSession()
  const clinicName = useOwnClinicName()
  if (!user) return null

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">Perfil da conta</h1>
      <dl className="max-w-xl divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
        <Row label="Nome" value={user.full_name} />
        <Row label="Email" value={user.email} />
        <Row label="Tipo de conta" value={ROLE_LABELS[user.role]} />
        <Row label="Clínica" value={clinicName ?? '—'} />
      </dl>
      <Link to={user.role === 'patient' ? '/patient/seguranca' : '/app/seguranca'} className="w-fit rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-teal-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-teal-700">
        Gerir segurança da conta
      </Link>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex flex-wrap justify-between gap-2 px-5 py-3"><dt className="text-sm text-slate-500">{label}</dt><dd className="break-all text-sm font-medium text-slate-900">{value}</dd></div>
}
