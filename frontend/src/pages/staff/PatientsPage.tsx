import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useState } from 'react'
import { Button } from '../../components/Button'
import { usePatientsPage } from '../../hooks/useClinicData'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDate } from '../../lib/formatDate'
import { Link } from 'react-router-dom'

export function PatientsPage() {
  const [page, setPage] = useState(1)
  const pageSize = 20
  const patients = usePatientsPage(page, pageSize)
  const rows = patients.data?.items
  const total = patients.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">Pacientes</h1>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        {patients.isLoading && <LoadingSpinner />}
        {patients.isError && (
          <ErrorState message={toUserMessage(patients.error)} onRetry={() => patients.refetch()} />
        )}
        {rows && rows.length === 0 && (
          <EmptyState title="Sem pacientes" description="Ainda não há pacientes registados nesta clínica." />
        )}
        {rows && rows.length > 0 && (
          <div className="overflow-x-auto">
          <table className="w-full min-w-xl text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="py-2 font-medium">Nome</th>
                <th className="py-2 font-medium">Data de nascimento</th>
                <th className="py-2 font-medium">Telefone</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((patient) => (
                <tr key={patient.id}>
                  <td className="py-2 font-medium text-slate-900">
                    <Link className="text-teal-700 hover:underline" to={`/app/pacientes/${patient.id}`}>
                      {patient.full_name}
                    </Link>
                  </td>
                  <td className="py-2 text-slate-600">{patient.birth_date ? formatDate(patient.birth_date) : '—'}</td>
                  <td className="py-2 text-slate-600">{patient.phone ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
        {rows && total > pageSize && (
          <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
            <Button variant="secondary" disabled={page === 1 || patients.isFetching} onClick={() => setPage((value) => value - 1)}>Anterior</Button>
            <p className="text-sm text-slate-500">Página {page} de {pageCount} · {total} pacientes</p>
            <Button variant="secondary" disabled={page >= pageCount || patients.isFetching} onClick={() => setPage((value) => value + 1)}>Seguinte</Button>
          </div>
        )}
      </section>
    </div>
  )
}
