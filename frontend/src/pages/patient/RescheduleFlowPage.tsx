import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button } from '../../components/Button'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { RequestPreferencesForm } from '../../components/scheduling/RequestPreferencesForm'
import { SlotPicker } from '../../components/scheduling/SlotPicker'
import { useAppointment } from '../../hooks/useClinicData'
import { useBookingSettings, useReschedule, useRescheduleSlots } from '../../hooks/useScheduling'
import { ApiError } from '../../lib/apiClient'
import { addDays, clinicToday, formatClinicDay, formatClinicTime } from '../../lib/clinicTime'
import { toUserMessage } from '../../lib/errorMessages'
import { appointmentRequestsService } from '../../services/appointmentRequests'
import type { AppointmentRequestCreate } from '../../types/api'
import type { Slot } from '../../types/scheduling'

const WINDOW_DAYS = 14
const STEPS = ['Profissional', 'Horário', 'Confirmação'] as const
type Who = 'same' | 'any'

/**
 * "Remarcar": a direct type moves to another free slot (same professional or any), in one
 * step on the server (the old appointment stays if the new slot was taken meanwhile). A
 * request type asks the clinic, with the patient's preferences; the appointment stays
 * until the clinic answers.
 */
export function RescheduleFlowPage() {
  const { appointmentId = '' } = useParams()
  const navigate = useNavigate()
  const appointment = useAppointment(appointmentId)
  const settings = useBookingSettings()
  const reschedule = useReschedule()
  const queryClient = useQueryClient()
  const ask = useMutation({
    mutationFn: (payload: AppointmentRequestCreate) => appointmentRequestsService.create(payload),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['appointment-requests'] }),
  })
  const [step, setStep] = useState(0)
  const [who, setWho] = useState<Who>('same')
  const [slot, setSlot] = useState<Slot | null>(null)
  const [error, setError] = useState('')
  const today = clinicToday()
  const [windowEnd, setWindowEnd] = useState(() => addDays(today, WINDOW_DAYS - 1))
  const headingRef = useRef<HTMLHeadingElement>(null)
  const data = appointment.data?.view === 'patient' ? appointment.data : null
  const direct = data?.booking_mode === 'direct'
  const slots = useRescheduleSlots(appointmentId, today, windowEnd, who, step >= 1 && direct && Boolean(data?.can_change))
  const horizonEnd = settings.data ? addDays(today, settings.data.booking_horizon_days) : today

  useEffect(() => {
    headingRef.current?.focus()
  }, [step])

  const go = (next: number) => {
    setError('')
    setStep(next)
  }

  function confirm() {
    if (!slot) return
    setError('')
    reschedule.mutate(
      { appointmentId, starts_at: slot.starts_at, ...(who === 'any' ? { staff_id: slot.staff_id } : {}) },
      {
        onSuccess: (moved) => navigate(`/patient/consultas/${moved.id}`, { replace: true, state: { rescheduled: true } }),
        onError: (failure) => {
          if (failure instanceof ApiError && failure.status === 409) {
            // Taken meanwhile (or the deadline passed): nothing changed; back to fresh slots.
            setSlot(null)
            setStep(1)
            setError(failure.detail ?? 'Este horário já não está disponível. Escolhe outro.')
            void slots.refetch()
          } else {
            setError(toUserMessage(failure))
          }
        },
      },
    )
  }

  const back = <Link to={`/patient/consultas/${appointmentId}`} className="inline-flex min-h-11 items-center text-sm font-medium text-slate-600 underline">Voltar à consulta</Link>

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <h1 className="text-2xl font-semibold text-slate-900">Remarcar consulta</h1>
      {appointment.isLoading && <LoadingSpinner label="A carregar a consulta…" />}
      {appointment.isError && <ErrorState message={toUserMessage(appointment.error)} onRetry={() => appointment.refetch()} />}
      {data && (
        <p className="text-sm text-slate-600">
          Consulta atual: {data.appointment_type}, <span className="first-letter:uppercase">{formatClinicDay(data.scheduled_at)}</span>, {formatClinicTime(data.scheduled_at)} · {data.staff_name}
        </p>
      )}

      {data && !data.can_change && (
        <FormMessage kind="error">
          Já não é possível remarcar esta consulta na app.{settings.data?.clinic_phone ? ` Liga para a clínica: ${settings.data.clinic_phone}.` : ' Contacta a clínica.'}
        </FormMessage>
      )}

      {data && data.can_change && !direct && (
        <section aria-labelledby="reschedule-request" className="flex flex-col gap-3">
          <h2 id="reschedule-request" className="text-lg font-semibold text-slate-900">Pedir outro horário</h2>
          <p className="text-sm text-slate-600">Indica quando te dá jeito. A clínica confirma ou propõe um horário; até lá, a consulta atual mantém-se.</p>
          <RequestPreferencesForm
            maxDate={settings.data ? horizonEnd : undefined}
            submitLabel="Enviar pedido de remarcação"
            isPending={ask.isPending}
            error={error}
            withReason={false}
            onSubmit={(preferences) => {
              setError('')
              ask.mutate(
                { reschedule_of_id: appointmentId, ...preferences },
                {
                  onSuccess: () => navigate(`/patient/consultas/${appointmentId}`, { replace: true, state: { rescheduleRequested: true } }),
                  onError: (failure) => setError(toUserMessage(failure)),
                },
              )
            }}
          />
        </section>
      )}

      {data && data.can_change && direct && (
        <section aria-labelledby="reschedule-step" className="flex flex-col gap-3">
          <p className="text-sm text-slate-500" aria-live="polite">Passo {step + 1} de {STEPS.length}</p>
          <h2 id="reschedule-step" ref={headingRef} tabIndex={-1} className="text-lg font-semibold text-slate-900 focus:outline-none">{STEPS[step]}</h2>
          {error && <FormMessage kind="error">{error}</FormMessage>}

          {step === 0 && (
            <ul className="flex flex-col gap-2">
              {([['same', `Com ${data.staff_name}`, 'O mesmo profissional'], ['any', 'Qualquer disponível', 'Mostra os horários de todos os profissionais']] as Array<[Who, string, string]>).map(([value, title, hint]) => (
                <li key={value}>
                  <button
                    type="button"
                    aria-pressed={who === value}
                    onClick={() => { setWho(value); setSlot(null); go(1) }}
                    className={`flex min-h-12 w-full flex-col items-start rounded-xl border px-4 py-3 text-left focus-visible:outline-2 focus-visible:outline-teal-700 ${who === value ? 'border-teal-600 bg-teal-50' : 'border-slate-200 bg-white hover:border-teal-300'}`}
                  >
                    <span className="font-medium text-slate-900">{title}</span>
                    <span className="text-sm text-slate-500">{hint}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {step === 1 && (
            <SlotPicker
              slots={slots}
              showStaff={who === 'any'}
              onSelect={(item) => { setSlot(item); go(2) }}
              onMore={windowEnd < horizonEnd ? () => setWindowEnd((current) => (addDays(current, WINDOW_DAYS) > horizonEnd ? horizonEnd : addDays(current, WINDOW_DAYS))) : undefined}
            />
          )}

          {step === 2 && slot && (
            <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4">
              <dl className="grid gap-2 text-sm sm:grid-cols-[10rem_1fr]">
                <dt className="text-slate-500">Passa de</dt>
                <dd className="font-medium"><span className="first-letter:uppercase">{formatClinicDay(data.scheduled_at)}</span>, {formatClinicTime(data.scheduled_at)} · {data.staff_name}</dd>
                <dt className="text-slate-500">Para</dt>
                <dd className="font-medium"><span className="first-letter:uppercase">{formatClinicDay(slot.starts_at)}</span>, {formatClinicTime(slot.starts_at)}–{formatClinicTime(slot.ends_at)} · {slot.staff_name}</dd>
              </dl>
              <p className="text-sm text-slate-500">A consulta atual é cancelada ao confirmar.</p>
              <Button isLoading={reschedule.isPending} onClick={confirm}>Confirmar remarcação</Button>
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            {step > 0 && <Button variant="secondary" disabled={reschedule.isPending} onClick={() => go(step - 1)}>Voltar</Button>}
          </div>
        </section>
      )}
      {back}
    </div>
  )
}
