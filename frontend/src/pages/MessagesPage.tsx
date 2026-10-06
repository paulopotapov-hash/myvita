import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { FormMessage } from '../components/FormMessage'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { TextAreaField } from '../components/TextAreaField'
import { TextField } from '../components/TextField'
import { usePatients } from '../hooks/useClinicData'
import {
  useConversation,
  useConversationInbox,
  useEscalateConversation,
  useReplyToConversation,
  useStartConversation,
  useUpdateConversationStatus,
} from '../hooks/useMessaging'
import { useSession } from '../hooks/useSession'
import { toUserMessage } from '../lib/errorMessages'
import { formatDateTime } from '../lib/formatDate'
import type { ConversationStatus } from '../types/api'

const STATUS_LABELS: Record<ConversationStatus, string> = {
  open: 'Aberta',
  waiting_for_patient: 'A aguardar resposta do paciente',
  waiting_for_team: 'A aguardar resposta da equipa',
  closed: 'Encerrada',
}

const ROLE_LABELS = { patient: 'Paciente', doctor: 'Médico', nurse: 'Enfermeiro' } as const

export function MessagesPage() {
  const { user } = useSession()
  const isPatient = user?.role === 'patient'
  const isDoctor = user?.role === 'staff' && user.staff_role === 'doctor'
  const isNurse = user?.role === 'staff' && user.staff_role === 'nurse'
  const canUseMessages = isPatient || isDoctor || isNurse
  const inbox = useConversationInbox(canUseMessages)
  const patients = usePatients(isDoctor || isNurse)
  const start = useStartConversation()
  const reply = useReplyToConversation()
  const setStatus = useUpdateConversationStatus()
  const escalate = useEscalateConversation()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('conversation') ?? ''
  const selected = useConversation(selectedId)
  const [patientId, setPatientId] = useState('')
  const [subject, setSubject] = useState('')
  const [firstMessage, setFirstMessage] = useState('')
  const [replyBody, setReplyBody] = useState('')
  const [composing, setComposing] = useState(false)
  const [error, setError] = useState('')
  const busy = start.isPending || reply.isPending || setStatus.isPending || escalate.isPending

  useEffect(() => {
    const deepLink = searchParams.get('conversationTargetId')
    if (deepLink && !selectedId) setSearchParams({ conversation: deepLink }, { replace: true })
  }, [searchParams, selectedId, setSearchParams])

  function submitStart(event: React.FormEvent) {
    event.preventDefault()
    if (!patientId || !subject.trim() || !firstMessage.trim()) {
      setError('Seleciona um paciente e indica o assunto e a primeira mensagem.')
      return
    }
    setError('')
    start.mutate({ patientId, subject: subject.trim(), body: firstMessage.trim() }, {
      onSuccess: (conversation) => {
        setSubject('')
        setFirstMessage('')
        setComposing(false)
        setSearchParams({ conversation: conversation.id })
      },
      onError: (failure) => setError(toUserMessage(failure)),
    })
  }

  function submitReply(event: React.FormEvent) {
    event.preventDefault()
    if (!selectedId || !replyBody.trim() || busy) return
    setError('')
    reply.mutate({ id: selectedId, body: replyBody.trim() }, {
      onSuccess: () => setReplyBody(''),
      onError: (failure) => setError(toUserMessage(failure)),
    })
  }

  function updateStatus(status: ConversationStatus) {
    if (!selectedId) return
    setStatus.mutate({ id: selectedId, status }, { onError: (failure) => setError(toUserMessage(failure)) })
  }

  if (!canUseMessages) {
    return <ErrorState message="A tua função não tem acesso às mensagens clínicas." />
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{isPatient ? 'Mensagens' : 'Inbox da equipa'}</h1>
          <p className="mt-1 text-sm text-slate-600">Comunicação privada com a equipa clínica autorizada.</p>
        </div>
        {!isPatient && <Button onClick={() => setComposing((value) => !value)}>{composing ? 'Cancelar' : 'Nova conversa'}</Button>}
      </header>

      {error && <FormMessage kind="error">{error}</FormMessage>}
      {composing && !isPatient && (
        <form className="grid gap-3 rounded-xl border border-slate-200 bg-white p-5 md:grid-cols-2" onSubmit={submitStart}>
          <h2 className="font-medium md:col-span-2">Iniciar conversa clínica</h2>
          <label className="grid gap-1 text-sm font-medium text-slate-700">Paciente
            <select value={patientId} onChange={(event) => setPatientId(event.target.value)} required className="rounded-md border border-slate-300 px-3 py-2">
              <option value="">Seleciona um paciente</option>
              {(patients.data ?? []).map((patient) => <option key={patient.id} value={patient.id}>{patient.full_name}</option>)}
            </select>
          </label>
          <TextField label="Assunto" required maxLength={200} value={subject} onChange={(event) => setSubject(event.target.value)} />
          <div className="md:col-span-2"><TextAreaField label="Primeira mensagem" required maxLength={10000} value={firstMessage} onChange={(event) => setFirstMessage(event.target.value)} /></div>
          <Button type="submit" disabled={busy} isLoading={start.isPending}>Enviar ao paciente</Button>
        </form>
      )}

      <div className="grid min-h-[32rem] gap-4 lg:grid-cols-[minmax(18rem,0.8fr)_minmax(0,1.7fr)]">
        <section aria-label="Lista de conversas" className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-medium">{isPatient ? 'As minhas conversas' : 'Conversas da equipa'}</h2>
            <Button variant="secondary" onClick={() => void inbox.refetch()}>Atualizar</Button>
          </div>
          {inbox.isLoading && <LoadingSpinner />}
          {inbox.isError && <ErrorState message={toUserMessage(inbox.error)} onRetry={() => void inbox.refetch()} />}
          {!inbox.isLoading && inbox.data?.length === 0 && <EmptyState title="Sem conversas" description={isPatient ? 'A equipa clínica pode iniciar uma conversa contigo.' : 'As conversas dos pacientes autorizados aparecerão aqui.'} />}
          {!!inbox.data?.length && (
            <ul className="divide-y divide-slate-100">
              {inbox.data.map((conversation) => (
                <li key={conversation.id}>
                  <button type="button" onClick={() => setSearchParams({ conversation: conversation.id })} className={`w-full rounded-md px-3 py-3 text-left hover:bg-slate-50 ${selectedId === conversation.id ? 'bg-teal-50' : ''}`}>
                    <span className="flex items-start justify-between gap-2">
                      <span className="break-words font-medium text-slate-900">{conversation.subject}</span>
                      {conversation.unread && <span aria-label="Não lida" className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-teal-700" />}
                    </span>
                    {!isPatient && <span className="block text-xs text-slate-600">{conversation.patient_name}</span>}
                    <span className="mt-1 block text-xs text-slate-500">{conversation.last_message.sender_role === 'patient' ? 'Paciente respondeu' : 'Equipa respondeu'} · {formatDateTime(conversation.updated_at)}</span>
                    {conversation.needs_doctor_review && <span className="mt-1 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">Requer revisão médica</span>}
                    <span className="mt-1 block text-xs text-slate-500">{STATUS_LABELS[conversation.status]}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label="Conversa selecionada" className="flex min-h-[32rem] flex-col rounded-xl border border-slate-200 bg-white p-4">
          {!selectedId && <EmptyState title="Seleciona uma conversa" description="As mensagens aparecerão aqui." />}
          {selected.isLoading && <LoadingSpinner />}
          {selected.isError && <ErrorState message={toUserMessage(selected.error)} onRetry={() => void selected.refetch()} />}
          {selected.data && (
            <>
              <div className="border-b border-slate-100 pb-3">
                <h2 className="break-words text-lg font-semibold">{selected.data.subject}</h2>
                {!isPatient && <p className="text-sm text-slate-600">Paciente: {selected.data.patient_name}</p>}
                <p className="text-sm text-slate-500">{STATUS_LABELS[selected.data.status]} · Atualizada {formatDateTime(selected.data.updated_at)}</p>
                {selected.data.needs_doctor_review && <p className="mt-1 text-sm font-medium text-amber-800">Requer revisão médica</p>}
              </div>
              <ol aria-label="Mensagens da conversa" className="my-4 flex-1 space-y-3 overflow-y-auto">
                {selected.data.messages.map((message) => (
                  <li key={message.id} className="rounded-lg bg-slate-50 p-3">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <p className="font-medium text-slate-900">{message.sender_name}</p>
                      <span className="text-xs text-slate-600">{ROLE_LABELS[message.sender_role]}</span>
                    </div>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate-800">{message.body}</p>
                    <time className="mt-2 block text-xs text-slate-500" dateTime={message.created_at}>{formatDateTime(message.created_at)}</time>
                  </li>
                ))}
              </ol>
              {!isPatient && (
                <div className="mb-3 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-3">
                  <label className="grid gap-1 text-sm font-medium text-slate-700">Estado
                    <select value={selected.data.status} onChange={(event) => updateStatus(event.target.value as ConversationStatus)} disabled={busy || (isNurse && selected.data.status === 'closed')} className="rounded-md border border-slate-300 px-3 py-2">
                      {(Object.keys(STATUS_LABELS) as ConversationStatus[]).map((status) => <option key={status} value={status} disabled={isNurse && status === 'closed'}>{STATUS_LABELS[status]}</option>)}
                    </select>
                  </label>
                  {isNurse && !selected.data.needs_doctor_review && selected.data.status !== 'closed' && <Button variant="secondary" disabled={busy} isLoading={escalate.isPending} onClick={() => escalate.mutate(selectedId, { onError: (failure) => setError(toUserMessage(failure)) })}>Escalar a médico</Button>}
                </div>
              )}
              {selected.data.status !== 'closed' && (
                <form className="grid gap-2 border-t border-slate-100 pt-3" onSubmit={submitReply}>
                  <TextAreaField label="Responder à equipa clínica" required maxLength={10000} value={replyBody} onChange={(event) => setReplyBody(event.target.value)} />
                  <Button type="submit" disabled={busy || !replyBody.trim()} isLoading={reply.isPending}>Enviar resposta</Button>
                </form>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
