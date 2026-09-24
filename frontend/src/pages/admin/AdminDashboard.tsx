import { Link } from 'react-router-dom'
import { useAppointments, usePatients, useStaff } from '../../hooks/useClinicData'
import { useOwnClinicName } from '../../hooks/useOwnClinicName'
import { useSession } from '../../hooks/useSession'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { toUserMessage } from '../../lib/errorMessages'

export function AdminDashboard() {
  const { user } = useSession()
  const clinicName = useOwnClinicName()
  const patients = usePatients()
  const staff = useStaff()
  const appointments = useAppointments()
  const firstError = patients.error ?? staff.error ?? appointments.error
  const isLoading = patients.isLoading || staff.isLoading || appointments.isLoading

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Olá, {user?.full_name}</h1>
        <p className="text-slate-500">{clinicName ?? 'A tua clínica'}</p>
      </div>

      {isLoading && <LoadingSpinner label="A carregar resumo da clínica…" />}
      {firstError && (
        <ErrorState
          message={toUserMessage(firstError)}
          onRetry={() => {
            patients.refetch()
            staff.refetch()
            appointments.refetch()
          }}
        />
      )}
      {!isLoading && !firstError && (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Pacientes" value={patients.data?.length} />
          <StatCard label="Equipa" value={staff.data?.length} />
          <StatCard label="Consultas" value={appointments.data?.length} />
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <Link
          to="/app/equipa"
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Gerir equipa
        </Link>
        <Link
          to="/app/pacientes"
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Ver pacientes
        </Link>
        <Link
          to="/app/consultas"
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Ver consultas
        </Link>
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-semibold text-slate-900">{value ?? '—'}</p>
    </div>
  )
}
