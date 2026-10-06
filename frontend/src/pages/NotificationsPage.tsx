import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { FormMessage } from '../components/FormMessage'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { useMarkNotificationRead, useNotifications } from '../hooks/useClinicalData'
import { toUserMessage } from '../lib/errorMessages'
import { formatDateTime } from '../lib/formatDate'

export function NotificationsPage() {
  const [page, setPage] = useState(1)
  const [error, setError] = useState('')
  const pageSize = 20
  const notifications = useNotifications(page, pageSize)
  const markRead = useMarkNotificationRead()
  const total = notifications.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / pageSize))

  function read(id: string) {
    if (markRead.isPending) return
    setError('')
    markRead.mutate(id, { onError: (failure) => setError(toUserMessage(failure)) })
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Notificações</h1>
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        {error && <FormMessage kind="error" className="mb-3">{error}</FormMessage>}
        {notifications.isLoading && <LoadingSpinner />}
        {notifications.isError && <ErrorState message={toUserMessage(notifications.error)} onRetry={() => notifications.refetch()} />}
        {notifications.data?.items.length === 0 && <EmptyState title="Sem notificações" description="Não existem notificações para mostrar." />}
        {notifications.data && notifications.data.items.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {notifications.data.items.map((notification) => (
              <li key={notification.id} className={`flex flex-wrap items-start justify-between gap-3 py-4 ${notification.is_read ? 'opacity-70' : ''}`}>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-medium">{notification.title}</p>
                    {!notification.is_read && <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs text-teal-800">Nova</span>}
                  </div>
                  <p className="text-sm text-slate-600">{notification.message}</p>
                  <p className="mt-1 text-xs text-slate-500">{formatDateTime(notification.created_at)}</p>
                </div>
                {!notification.is_read && (
                  <Button
                    variant="secondary"
                    disabled={markRead.isPending}
                    isLoading={markRead.isPending && markRead.variables === notification.id}
                    onClick={() => read(notification.id)}
                  >
                    Marcar como lida
                  </Button>
                )}
                {notification.target_type === 'document' && notification.target_id && (
                  <Link className="rounded-md border border-teal-700 px-3 py-2 text-sm font-medium text-teal-800 hover:bg-teal-50 focus:outline-none focus:ring-2 focus:ring-teal-700" to={`/app/saude?document=${notification.target_id}`}>
                    Ver documento
                  </Link>
                )}
                {notification.target_type === 'conversation' && notification.conversation_target_id && (
                  <Link className="rounded-md border border-teal-700 px-3 py-2 text-sm font-medium text-teal-800 hover:bg-teal-50 focus:outline-none focus:ring-2 focus:ring-teal-700" to={`/app/mensagens?conversationTargetId=${notification.conversation_target_id}`}>
                    Ver mensagem
                  </Link>
                )}
              </li>
            ))}
          </ul>
        )}
        {total > pageSize && (
          <div className="mt-5 flex items-center justify-between">
            <Button variant="secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</Button>
            <span className="text-sm text-slate-500">Página {page} de {pages}</span>
            <Button variant="secondary" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Seguinte</Button>
          </div>
        )}
      </section>
    </div>
  )
}
