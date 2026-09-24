import { useMemo } from 'react'
import { DashboardAppointments } from '../../components/dashboard/DashboardAppointments'
import { DashboardHeader, QuickActions } from '../../components/dashboard/DashboardChrome'
import { useAppointments, usePatients, useUpcomingAppointments } from '../../hooks/useClinicData'
import { useOwnClinicName } from '../../hooks/useOwnClinicName'
import { useSession } from '../../hooks/useSession'
import { endOfTodayIso, startOfTodayIso, startOfTomorrowIso } from '../../lib/dashboardDates'

export function AdminDashboard() {
  const { user } = useSession()
  const clinicName = useOwnClinicName()
  const today = useAppointments({ start_date: startOfTodayIso(), end_date: endOfTodayIso(), limit: 50 })
  const future = useUpcomingAppointments(startOfTomorrowIso())
  const patients = usePatients()
  const patientNames = useMemo(
    () => new Map((patients.data ?? []).map((patient) => [patient.id, patient.full_name])),
    [patients.data],
  )

  if (!user) return null

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-7">
      <DashboardHeader
        name={user.full_name}
        context={`Visão operacional de ${clinicName ?? 'a tua clínica'} para hoje e próximos dias.`}
      />
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <DashboardAppointments
          title="Atividade de hoje"
          appointments={today.data}
          isLoading={today.isLoading}
          error={today.error}
          onRetry={() => today.refetch()}
          emptyTitle="Sem consultas hoje"
          emptyDescription="Não existem consultas na agenda de hoje."
          counterpartName={(appointment) => patientNames.get(appointment.patient_id) ?? 'Paciente'}
        />
        <DashboardAppointments
          title="Próximas consultas"
          appointments={future.data}
          isLoading={future.isLoading}
          error={future.error}
          onRetry={() => future.refetch()}
          emptyTitle="Sem consultas futuras"
          emptyDescription="Não existem consultas futuras agendadas."
          counterpartName={(appointment) => patientNames.get(appointment.patient_id) ?? 'Paciente'}
        />
      </div>
      <QuickActions role="clinic_admin" />
    </div>
  )
}
