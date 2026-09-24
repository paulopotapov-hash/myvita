import { useMemo, useState } from 'react'
import { DashboardAppointments } from '../../components/dashboard/DashboardAppointments'
import { DashboardHeader, QuickActions } from '../../components/dashboard/DashboardChrome'
import { useStaff, useUpcomingAppointments } from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'

export function PatientDashboard() {
  const { user } = useSession()
  const [dashboardOpenedAt] = useState(() => new Date().toISOString())
  const appointments = useUpcomingAppointments(dashboardOpenedAt)
  const staff = useStaff()
  const staffNames = useMemo(
    () => new Map((staff.data ?? []).map((professional) => [professional.id, professional.full_name])),
    [staff.data],
  )

  if (!user) return null

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-7">
      <DashboardHeader
        name={user.full_name}
        context="Consulta os teus próximos cuidados e acede rapidamente à tua área pessoal."
      />
      <DashboardAppointments
        title="Próximas consultas"
        appointments={appointments.data}
        isLoading={appointments.isLoading}
        error={appointments.error}
        onRetry={() => appointments.refetch()}
        emptyTitle="Sem consultas futuras"
        emptyDescription="Não tens consultas agendadas neste momento."
        counterpartName={(appointment) => staffNames.get(appointment.staff_id) ?? 'Profissional de saúde'}
      />
      <QuickActions role="patient" />
    </div>
  )
}
