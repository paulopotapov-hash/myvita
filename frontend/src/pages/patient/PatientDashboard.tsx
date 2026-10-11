import { ErrorState } from '../../components/ErrorState'
import { HighlightCard } from '../../components/HighlightCard'
import { HomeTile } from '../../components/HomeTile'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { REQUEST_FORM_ANCHOR } from '../../components/AppointmentRequestsPanel'
import { useAppointments } from '../../hooks/useClinicData'
import { UNREAD_CONVERSATIONS_SCAN, useConversations } from '../../hooks/useMessages'
import { useUnopenedResultIds } from '../../hooks/useResultNotifications'
import { useSession } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDateTime, formatLongDate, formatTime } from '../../lib/formatDate'
import { firstNameOf } from '../../lib/initials'
import type { AppointmentView } from '../../types/api'

const UPCOMING_STATUSES = new Set(['scheduled', 'confirmed'])

function nextAppointment(appointments: AppointmentView[], now: Date): AppointmentView | undefined {
  return appointments
    .filter((appointment) => UPCOMING_STATUSES.has(appointment.status) && new Date(appointment.scheduled_at) >= now)
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))[0]
}

/** Patient home (mobile first, MyChart style): greeting, shortcut grid, highlight cards. */
export function PatientDashboard() {
  const { user } = useSession()
  const appointments = useAppointments()
  const conversations = useConversations(1, UNREAD_CONVERSATIONS_SCAN)
  const unopenedResults = useUnopenedResultIds()

  const unreadConversations = (conversations.data?.items ?? [])
    .filter((conversation) => conversation.unread_count > 0)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  const latestUnread = unreadConversations[0]
  const upcoming = appointments.data ? nextAppointment(appointments.data, new Date()) : undefined
  const resultsLink =
    unopenedResults.length === 1 ? `/patient/resultados?result=${encodeURIComponent(unopenedResults[0])}` : '/patient/resultados'

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">Olá, {firstNameOf(user?.full_name ?? '')}!</h1>

      <nav aria-label="Atalhos">
        <ul className="grid grid-cols-3 gap-3 sm:gap-4 lg:grid-cols-6">
          <li><HomeTile to={`/patient/consultas#${REQUEST_FORM_ANCHOR}`} label="Marcar consulta" icon="calendarPlus" /></li>
          <li>
            <HomeTile
              to="/patient/mensagens"
              label="Mensagens"
              icon="chat"
              badge={unreadConversations.length}
              badgeLabel={unreadConversations.length === 1 ? '1 conversa por ler' : `${unreadConversations.length} conversas por ler`}
            />
          </li>
          <li>
            <HomeTile
              to="/patient/resultados"
              label="Resultados"
              icon="results"
              badge={unopenedResults.length}
              badgeLabel={unopenedResults.length === 1 ? '1 resultado por abrir' : `${unopenedResults.length} resultados por abrir`}
            />
          </li>
          <li><HomeTile to="/patient/medicacao" label="Medicação" icon="pill" /></li>
          <li><HomeTile to="/patient/documentos" label="Documentos" icon="document" /></li>
          <li><HomeTile to="/patient/consultas" label="Consultas" icon="calendar" /></li>
        </ul>
      </nav>

      <div className="flex flex-col gap-4">
        {appointments.isLoading && <LoadingSpinner label="A carregar a próxima consulta…" />}
        {appointments.isError && (
          <ErrorState message={toUserMessage(appointments.error)} onRetry={() => appointments.refetch()} />
        )}
        {appointments.data && upcoming && (
          <HighlightCard
            id="next-appointment"
            title="Próxima consulta"
            icon="calendar"
            actionLabel="Ver detalhes"
            actionTo={`/patient/consultas?consulta=${encodeURIComponent(upcoming.id)}`}
          >
            <p className="font-medium text-slate-900 first-letter:uppercase">{formatLongDate(upcoming.scheduled_at)}</p>
            <p>às {formatTime(upcoming.scheduled_at)}</p>
            {upcoming.view === 'patient' && <p className="text-slate-600">Com {upcoming.staff_name}</p>}
          </HighlightCard>
        )}
        {appointments.data && !upcoming && (
          <HighlightCard
            id="next-appointment"
            title="Sem consultas marcadas"
            icon="calendar"
            actionLabel="Marcar consulta"
            actionTo={`/patient/consultas#${REQUEST_FORM_ANCHOR}`}
          >
            <p>Peça uma consulta e a clínica confirma o dia e a hora.</p>
          </HighlightCard>
        )}

        {latestUnread && (
          <HighlightCard
            id="unread-message"
            title="Mensagem por ler"
            icon="chat"
            actionLabel="Ver mensagem"
            actionTo={`/patient/mensagens/${encodeURIComponent(latestUnread.id)}`}
          >
            <p className="font-medium text-slate-900">Conversa com {latestUnread.staff_name}</p>
            <p className="text-slate-600">
              {latestUnread.unread_count === 1 ? '1 mensagem nova' : `${latestUnread.unread_count} mensagens novas`} ·{' '}
              <time dateTime={latestUnread.updated_at}>{formatDateTime(latestUnread.updated_at)}</time>
            </p>
          </HighlightCard>
        )}

        {unopenedResults.length > 0 && (
          <HighlightCard id="new-results" title="Resultados por abrir" icon="results" actionLabel="Ver resultados" actionTo={resultsLink}>
            <p>
              {unopenedResults.length === 1
                ? 'Tem 1 resultado novo, revisto pela sua equipa clínica.'
                : `Tem ${unopenedResults.length} resultados novos, revistos pela sua equipa clínica.`}
            </p>
          </HighlightCard>
        )}
      </div>
    </div>
  )
}
