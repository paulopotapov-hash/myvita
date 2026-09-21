import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { usePatients } from '../../hooks/useClinicData'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDate } from '../../lib/formatDate'

export function PatientsPage() {
  const patients = usePatients()

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">Pacientes</h1>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        {patients.isLoading && <LoadingSpinner />}
        {patients.isError && (
          <ErrorState message={toUserMessage(patients.error)} onRetry={() => patients.refetch()} />
        )}
        {patients.data && patients.data.length === 0 && (
          <EmptyState title="Sem pacientes" description="Ainda não há pacientes registados nesta clínica." />
        )}
        {patients.data && patients.data.length > 0 && (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="py-2 font-medium">Nome</th>
                <th className="py-2 font-medium">Data de nascimento</th>
                <th className="py-2 font-medium">Telefone</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {patients.data.map((patient) => (
                <tr key={patient.id}>
                  <td className="py-2 font-medium text-slate-900">{patient.full_name}</td>
                  <td className="py-2 text-slate-600">{patient.birth_date ? formatDate(patient.birth_date) : '—'}</td>
                  <td className="py-2 text-slate-600">{patient.phone ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
