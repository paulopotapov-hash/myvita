import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useSession } from '../../hooks/useSession'
import { useOwnClinicName } from '../../hooks/useOwnClinicName'
import { usePatient } from '../../hooks/useClinicData'
import { formatDate } from '../../lib/formatDate'

const ROLE_LABELS = {
  patient: 'Paciente',
  staff: 'Profissional de saúde',
  clinic_admin: 'Administrador da clínica',
} as const

export function PatientProfilePage() {
  const { user } = useSession()
  const clinicName = useOwnClinicName()
  const patient = usePatient(user?.patient_id ?? '')

  if (!user) return null

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">O meu perfil</h1>
      {!user.patient_id && <ErrorState message="A sessão não contém uma identidade de paciente válida." />}
      {patient.isLoading && <LoadingSpinner label="A carregar dados do perfil…" />}
      {patient.isError && <ErrorState message="Não foi possível carregar os dados do perfil clínico." onRetry={() => patient.refetch()} />}
      {patient.data && <dl className="max-w-md divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
        <Row label="Nome" value={user.full_name} />
        <Row label="Email" value={user.email} />
        <Row label="Tipo de conta" value={ROLE_LABELS[user.role]} />
        <Row label="Clínica" value={clinicName ?? '—'} />
        <Row label="Data de nascimento" value={patient.data?.birth_date ? formatDate(patient.data.birth_date) : '—'} />
        <Row label="Telefone" value={patient.data?.phone ?? '—'} />
      </dl>}
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
