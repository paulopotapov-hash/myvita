import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextAreaField } from '../../components/TextAreaField'
import { RequestPreferencesForm, type RequestPreferences } from '../../components/scheduling/RequestPreferencesForm'
import { SlotPicker } from '../../components/scheduling/SlotPicker'
import {
  useAppointmentTypes,
  useBook,
  useBookableProfessionals,
  useBookingSettings,
  useSlots,
  useSpecialties,
} from '../../hooks/useScheduling'
import { ApiError } from '../../lib/apiClient'
import { describePreferences } from '../../lib/appointmentRequests'
import { addDays, clinicToday, formatClinicDay, formatClinicTime } from '../../lib/clinicTime'
import { toUserMessage } from '../../lib/errorMessages'
import { appointmentRequestsService } from '../../services/appointmentRequests'
import type { AppointmentRequestCreate } from '../../types/api'
import type { AppointmentTypeOption, Slot } from '../../types/scheduling'

const STEPS = ['Tipo de consulta', 'Especialidade', 'Profissional', 'Horário', 'Confirmação'] as const
const REQUEST_STEPS = ['Tipo de consulta', 'Especialidade', 'Profissional', 'Preferências', 'Confirmação'] as const
const WINDOW_DAYS = 14
const ANY = 'any'

function OptionButton({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={`flex min-h-12 w-full flex-col items-start rounded-xl border px-4 py-3 text-left focus-visible:outline-2 focus-visible:outline-teal-700 ${selected ? 'border-teal-600 bg-teal-50' : 'border-slate-200 bg-white hover:border-teal-300'}`}
    >
      {children}
    </button>
  )
}

/**
 * "Marcar consulta" in five steps: type, specialty, professional (or "Qualquer
 * disponível", known professionals first), a free slot from the server, and a summary.
 * For a "Só por pedido" type, step 4 is a request with the patient's preferences instead,
 * and the clinic confirms or proposes a time. Nothing is shown as booked until the server
 * confirms it.
 */
export function BookingFlowPage() {
  const navigate = useNavigate()
  const types = useAppointmentTypes()
  const specialties = useSpecialties()
  const settings = useBookingSettings()
  const book = useBook()
  const queryClient = useQueryClient()
  const ask = useMutation({
    mutationFn: (payload: AppointmentRequestCreate) => appointmentRequestsService.create(payload),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['appointment-requests'] }),
  })
  const [preferences, setPreferences] = useState<RequestPreferences | null>(null)
  const [step, setStep] = useState(0)
  const [typeName, setTypeName] = useState('')
  const [type, setType] = useState<AppointmentTypeOption | null>(null)
  const [staffId, setStaffId] = useState(ANY)
  const [windowEnd, setWindowEnd] = useState(() => addDays(clinicToday(), WINDOW_DAYS - 1))
  const [slot, setSlot] = useState<Slot | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const headingRef = useRef<HTMLHeadingElement>(null)
  const professionals = useBookableProfessionals(type?.id ?? '')
  const byRequest = type?.booking_mode === 'request'
  const stepLabels = byRequest ? REQUEST_STEPS : STEPS
  const today = clinicToday()
  const slots = useSlots(step >= 3 && type?.booking_mode === 'direct' ? type.id : '', today, windowEnd, staffId === ANY ? undefined : staffId)

  useEffect(() => {
    headingRef.current?.focus()
  }, [step])

  const activeTypes = types.data ?? []
  const names = [...new Set(activeTypes.map((item) => item.name))].sort((a, b) => a.localeCompare(b, 'pt'))
  const offering = activeTypes.filter((item) => item.name === typeName)
  const specialtyName = new Map((specialties.data ?? []).map((item) => [item.id, item.name]))
  const horizonEnd = settings.data ? addDays(today, settings.data.booking_horizon_days) : today
  const go = (next: number) => {
    setError('')
    setStep(next)
  }

  function confirm() {
    if (!type || !slot) return
    setError('')
    book.mutate(
      { appointment_type_id: type.id, starts_at: slot.starts_at, ...(staffId !== ANY ? { staff_id: staffId } : {}), ...(reason.trim() ? { reason: reason.trim() } : {}) },
      {
        onSuccess: (appointment) => navigate(`/patient/consultas/${appointment.id}`, { state: { booked: true } }),
        onError: (failure) => {
          if (failure instanceof ApiError && failure.status === 409) {
            // Taken between showing and confirming: back to the slots, refreshed.
            setSlot(null)
            setStep(3)
            setError(failure.detail ?? 'Este horário já não está disponível. Escolhe outro.')
            void slots.refetch()
          } else {
            setError(toUserMessage(failure))
          }
        },
      },
    )
  }

  function sendRequest() {
    if (!type || !preferences) return
    setError('')
    ask.mutate(
      { appointment_type_id: type.id, ...(staffId !== ANY ? { staff_id: staffId } : {}), ...preferences },
      {
        onSuccess: () => navigate('/patient/consultas', { state: { requested: true } }),
        onError: (failure) => setError(toUserMessage(failure)),
      },
    )
  }
  const chosenName = staffId === ANY ? 'Qualquer disponível' : professionals.data?.find((item) => item.id === staffId)?.full_name ?? '—'

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Marcar consulta</h1>
        <p className="text-sm text-slate-500" aria-live="polite">Passo {step + 1} de {stepLabels.length}</p>
        <ol aria-label="Passos" className="mt-2 flex gap-1">
          {stepLabels.map((label, index) => (
            <li key={label} className={`h-1.5 flex-1 rounded-full ${index <= step ? 'bg-teal-600' : 'bg-slate-200'}`}>
              <span className="sr-only">{label}{index === step ? ' (atual)' : index < step ? ' (concluído)' : ''}</span>
            </li>
          ))}
        </ol>
      </div>

      <section aria-labelledby="booking-step" className="flex flex-col gap-3">
        <h2 id="booking-step" ref={headingRef} tabIndex={-1} className="text-lg font-semibold text-slate-900 focus:outline-none">{stepLabels[step]}</h2>
        {error && <FormMessage kind="error">{error}</FormMessage>}

        {step === 0 && (
          <>
            {types.isLoading && <LoadingSpinner />}
            {types.isError && <ErrorState message={toUserMessage(types.error)} onRetry={() => types.refetch()} />}
            {types.data && names.length === 0 && <EmptyState title="Ainda não há consultas para marcar online" description="Contacta a clínica." />}
            <ul className="flex flex-col gap-2">
              {names.map((name) => {
                const options = activeTypes.filter((item) => item.name === name)
                return (
                  <li key={name}>
                    <OptionButton selected={typeName === name} onClick={() => { setTypeName(name); setType(options.length === 1 ? options[0] : null); setSlot(null); go(1) }}>
                      <span className="font-medium text-slate-900">{name}</span>
                      <span className="text-sm text-slate-500">{options[0].duration_minutes} minutos{options.every((item) => item.booking_mode === 'request') ? ' · só por pedido' : ''}</span>
                    </OptionButton>
                  </li>
                )
              })}
            </ul>
          </>
        )}

        {step === 1 && (
          <ul className="flex flex-col gap-2">
            {offering.map((item) => (
              <li key={item.id}>
                <OptionButton selected={type?.id === item.id} onClick={() => { setType(item); setStaffId(ANY); setSlot(null); go(2) }}>
                  <span className="font-medium text-slate-900">{specialtyName.get(item.specialty_id) ?? 'Especialidade'}</span>
                  {item.booking_mode === 'request' && <span className="text-sm text-slate-500">Só por pedido: a clínica confirma o horário</span>}
                </OptionButton>
              </li>
            ))}
          </ul>
        )}

        {step === 2 && byRequest && (
          <p className="text-sm text-slate-600">Esta consulta é marcada por pedido: indicas as tuas preferências e a clínica confirma ou propõe um horário.</p>
        )}

        {step === 2 && type && (
          <>
            {professionals.isLoading && <LoadingSpinner />}
            {professionals.isError && <ErrorState message={toUserMessage(professionals.error)} onRetry={() => professionals.refetch()} />}
            {professionals.data && professionals.data.length === 0 && !byRequest && (
              <EmptyState title="Sem profissionais disponíveis para esta consulta" description="Contacta a clínica ou escolhe outro tipo de consulta." />
            )}
            {professionals.data && (professionals.data.length > 0 || byRequest) && (
              <ul className="flex flex-col gap-2">
                <li>
                  <OptionButton selected={staffId === ANY} onClick={() => { setStaffId(ANY); setSlot(null); go(3) }}>
                    <span className="font-medium text-slate-900">Qualquer disponível</span>
                    <span className="text-sm text-slate-500">{byRequest ? 'A clínica escolhe o profissional' : 'Mostra os horários de todos os profissionais'}</span>
                  </OptionButton>
                </li>
                {professionals.data.map((professional) => (
                  <li key={professional.id}>
                    <OptionButton selected={staffId === professional.id} onClick={() => { setStaffId(professional.id); setSlot(null); go(3) }}>
                      <span className="font-medium text-slate-900">{professional.full_name}</span>
                      {professional.known && <span className="text-sm text-slate-500">Já tiveste consulta</span>}
                    </OptionButton>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {step === 3 && !byRequest && (
          <SlotPicker
            slots={slots}
            showStaff={staffId === ANY}
            onSelect={(item) => { setSlot(item); go(4) }}
            onMore={windowEnd < horizonEnd ? () => setWindowEnd((current) => (addDays(current, WINDOW_DAYS) > horizonEnd ? horizonEnd : addDays(current, WINDOW_DAYS))) : undefined}
          />
        )}

        {step === 3 && byRequest && (
          <RequestPreferencesForm
            maxDate={settings.data ? horizonEnd : undefined}
            submitLabel="Continuar"
            isPending={false}
            onSubmit={(values) => { setPreferences(values); go(4) }}
          />
        )}

        {step === 4 && byRequest && type && preferences && (
          <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4">
            <dl className="grid gap-2 text-sm sm:grid-cols-[10rem_1fr]">
              <dt className="text-slate-500">Consulta</dt><dd className="font-medium">{type.name} ({type.duration_minutes} min)</dd>
              <dt className="text-slate-500">Especialidade</dt><dd className="font-medium">{specialtyName.get(type.specialty_id) ?? '—'}</dd>
              <dt className="text-slate-500">Profissional</dt><dd className="font-medium">{chosenName}</dd>
              <dt className="text-slate-500">Preferências</dt>
              <dd className="font-medium">{describePreferences(preferences)}</dd>
              {preferences.reason && (<><dt className="text-slate-500">Motivo</dt><dd className="whitespace-pre-wrap">{preferences.reason}</dd></>)}
            </dl>
            <p className="text-sm text-slate-500">A clínica responde na app: confirma o pedido ou propõe um horário que podes aceitar ou recusar.</p>
            <Button isLoading={ask.isPending} onClick={sendRequest}>Enviar pedido</Button>
          </div>
        )}

        {step === 4 && !byRequest && type && slot && (
          <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4">
            <dl className="grid gap-2 text-sm sm:grid-cols-[10rem_1fr]">
              <dt className="text-slate-500">Consulta</dt><dd className="font-medium">{type.name} ({type.duration_minutes} min)</dd>
              <dt className="text-slate-500">Especialidade</dt><dd className="font-medium">{specialtyName.get(type.specialty_id) ?? '—'}</dd>
              <dt className="text-slate-500">Profissional</dt><dd className="font-medium">{slot.staff_name}</dd>
              <dt className="text-slate-500">Data</dt><dd className="font-medium first-letter:uppercase">{formatClinicDay(slot.starts_at)}</dd>
              <dt className="text-slate-500">Hora</dt><dd className="font-medium">{formatClinicTime(slot.starts_at)}–{formatClinicTime(slot.ends_at)}</dd>
              <dt className="text-slate-500">Local</dt><dd className="font-medium">{settings.data?.clinic_address ?? 'Na clínica'}</dd>
            </dl>
            <TextAreaField label="Motivo da consulta (opcional)" value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />
            {settings.data && (
              <p className="text-sm text-slate-500">Podes cancelar ou remarcar na app até {settings.data.cancellation_deadline_hours} horas antes.</p>
            )}
            <Button isLoading={book.isPending} onClick={confirm}>Confirmar marcação</Button>
          </div>
        )}
      </section>

      <div className="flex flex-wrap gap-3">
        {step > 0 && <Button variant="secondary" disabled={book.isPending || ask.isPending} onClick={() => go(step - 1)}>Voltar</Button>}
        <Link to="/patient/consultas" className="inline-flex min-h-11 items-center text-sm font-medium text-slate-600 underline">Cancelar e voltar às consultas</Link>
      </div>
    </div>
  )
}
