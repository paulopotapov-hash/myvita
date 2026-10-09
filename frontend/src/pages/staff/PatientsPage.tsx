import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '../../components/Button'
import { PatientInvitationsPanel } from '../../components/PatientInvitationsPanel'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { usePatientsPage } from '../../hooks/useClinicData'
import { toUserMessage } from '../../lib/errorMessages'
import { Link } from 'react-router-dom'
import { useSession } from '../../hooks/useSession'

/**
 * Percentage of a second to wait after the user stops typing before the
 * directory re-queries.
 *
 * The backend applies the search inside the authenticated clinic scope.
 * Keeping it in the URL makes browser back/forward restore the same query.
 */
const DEBOUNCE_MS = 300
const PAGE_SIZE = 20

/**
 * Compose filter state into the URL.
 */
function useFilterComposer() {
  const [params, setParams] = useSearchParams()

  const update = useCallback(
    (next: (current: URLSearchParams) => URLSearchParams) => {
      const nextParams = new URLSearchParams(params.toString())
      next(nextParams)
      setParams(nextParams, { replace: true })
    },
    [params, setParams],
  )

  return { params, update }
}

export function PatientsPage() {
  const { user } = useSession()
  const canOpenClinicalRecord = user?.role === 'staff' && (user.staff_role === 'doctor' || user.staff_role === 'nurse')
  // Same rule as POST /api/v1/invitations/patients (the backend enforces it).
  const canInvitePatients = user?.role === 'clinic_admin' || canOpenClinicalRecord

  const { params, update } = useFilterComposer()

  const pageFromUrl = Number(params.get('page'))
  const page = Number.isInteger(pageFromUrl) && pageFromUrl > 0 ? pageFromUrl : 1
  const urlSearch = params.get('search') ?? ''

  // The URL is the only source of truth for the current filter. This input
  // mirrors it, but only changes when the URL changes — typing does not
  // change the URL until the debounce settles.
  const [searchDraft, setSearchDraft] = useState<string | null>(null)
  const searchInput = searchDraft ?? urlSearch

  // Debounce the search.
  //
  // The URL value is what the query consumes. A local draft keeps typing
  // responsive until the timer writes the final value to the URL.
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingSearchRef = useRef<string | null>(null)
  useEffect(() => () => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
  }, [])

  const scheduleDebounce = (value: string) => {
    pendingSearchRef.current = value
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null
      const settledSearch = pendingSearchRef.current ?? ''
      update((next) => {
        if (settledSearch) next.set('search', settledSearch)
        else next.delete('search')
        next.delete('page')
        return next
      })
      setSearchDraft(null)
    }, DEBOUNCE_MS)
  }

  const patients = usePatientsPage(page, PAGE_SIZE, urlSearch)
  const rows = patients.data?.items
  const total = patients.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const goToPage = (nextPage: number) => {
    update((next) => {
      if (nextPage <= 1) next.delete('page')
      else next.set('page', String(nextPage))
      return next
    })
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">Pacientes</h1>

      <label className="flex max-w-md flex-col gap-1 text-sm font-medium text-slate-700">
        Pesquisar por nome
        <input
          type="search"
          aria-label="Pesquisar por nome"
          value={searchInput}
          onChange={(event) => {
            const next = event.target.value
            setSearchDraft(next)
            scheduleDebounce(next)
          }}
          maxLength={100}
          className="rounded-md border border-slate-300 px-3 py-2 font-normal outline-none focus:ring-2 focus:ring-teal-600"
        />
      </label>

      <section className="rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
        {patients.isLoading && <LoadingSpinner />}
        {patients.isError && (
          <ErrorState message={toUserMessage(patients.error)} onRetry={() => patients.refetch()} />
        )}
        {rows && rows.length === 0 && (
          <EmptyState
            title={urlSearch.trim() ? 'Nenhum paciente encontrado' : 'Sem pacientes'}
            description={
              urlSearch.trim()
                ? 'Nenhum paciente corresponde à pesquisa.'
                : 'Ainda não há pacientes registados nesta clínica.'
            }
          />
        )}
        {rows && rows.length > 0 && (
          // Fits a 320px screen: no minimum width, names wrap; the scroll container is only a fallback.
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-2 pr-3 font-medium">Nome</th>
                  <th className="py-2 pr-3 font-medium">Estado</th>
                  <th className="py-2 text-right font-medium">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((patient) => (
                  <tr key={patient.id}>
                    <td className="break-words py-2 pr-3 font-medium text-slate-900">{patient.full_name}</td>
                    <td className="py-2 pr-3 text-slate-600">{patient.is_active ? 'Ativo' : 'Inativo'}</td>
                    <td className="py-2 text-right">
                      {canOpenClinicalRecord && (
                        <Link
                          className="inline-flex whitespace-nowrap rounded-md border border-slate-300 px-3 py-1.5 font-medium text-teal-700 hover:bg-slate-50 focus-visible:outline-2"
                          to={{
                            pathname: `/app/pacientes/${patient.id}`,
                            search: page === 1 ? (urlSearch ? `?search=${encodeURIComponent(urlSearch)}` : '') : `?page=${page}${urlSearch ? `&search=${encodeURIComponent(urlSearch)}` : ''}`,
                          }}
                        >
                          Abrir ficha
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rows && total > PAGE_SIZE && (
          <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
            <Button variant="secondary" disabled={page === 1 || patients.isFetching} onClick={() => goToPage(page - 1)}>
              Anterior
            </Button>
            <p className="text-sm text-slate-500">Página {page} de {pageCount} · {total} pacientes</p>
            <Button variant="secondary" disabled={page >= pageCount || patients.isFetching} onClick={() => goToPage(page + 1)}>
              Seguinte
            </Button>
          </div>
        )}
      </section>

      {/* Below the list so the patients table stays the first thing on a small screen. */}
      {canInvitePatients && <PatientInvitationsPanel />}
    </div>
  )
}
