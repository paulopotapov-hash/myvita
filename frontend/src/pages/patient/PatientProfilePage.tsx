import { useSession } from '../../hooks/useSession'
import { useOwnClinicName } from '../../hooks/useOwnClinicName'

const ROLE_LABELS = {
  patient: 'Paciente',
  staff: 'Profissional de saúde',
  clinic_admin: 'Administrador da clínica',
} as const

export function PatientProfilePage() {
  const { user } = useSession()
  const clinicName = useOwnClinicName()

  if (!user) return null

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">O meu perfil</h1>
      <dl className="max-w-md divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
        <Row label="Nome" value={user.full_name} />
        <Row label="Email" value={user.email} />
        <Row label="Tipo de conta" value={ROLE_LABELS[user.role]} />
        <Row label="Clínica" value={clinicName ?? '—'} />
      </dl>
      <p className="max-w-md text-sm text-slate-500">
        Data de nascimento e telefone ainda não podem ser consultados aqui — a API atual só os devolve no
        momento do registo. Assim que existir um endpoint para o perfil clínico completo, esta página passa a
        mostrá-los.
      </p>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between px-5 py-3">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="text-sm font-medium text-slate-900">{value}</dd>
    </div>
  )
}
