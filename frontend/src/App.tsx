import { Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './app/ProtectedRoute'
import { RoleRoute } from './app/RoleRoute'
import { RootRedirect } from './app/RootRedirect'
import { AppLayout } from './layouts/AppLayout'
import { ClinicOnboardingPage } from './pages/auth/ClinicOnboardingPage'
import { LoginPage } from './pages/auth/LoginPage'
import { PatientRegisterPage } from './pages/auth/PatientRegisterPage'
import { DashboardPage } from './pages/DashboardPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PatientProfilePage } from './pages/patient/PatientProfilePage'
import { AppointmentsPage } from './pages/staff/AppointmentsPage'
import { PatientsPage } from './pages/staff/PatientsPage'
import { PatientDetailPage } from './pages/staff/PatientDetailPage'
import { StaffManagementPage } from './pages/admin/StaffManagementPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/registo" element={<PatientRegisterPage />} />
      <Route path="/nova-clinica" element={<ClinicOnboardingPage />} />

      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="consultas" element={<AppointmentsPage />} />
        <Route
          path="perfil"
          element={
            <RoleRoute allow={['patient']}>
              <PatientProfilePage />
            </RoleRoute>
          }
        />
        <Route
          path="pacientes"
          element={
            <RoleRoute allow={['staff', 'clinic_admin']}>
              <PatientsPage />
            </RoleRoute>
          }
        />
        <Route
          path="pacientes/:id"
          element={
            <RoleRoute allow={['staff', 'clinic_admin']}>
              <PatientDetailPage />
            </RoleRoute>
          }
        />
        <Route
          path="equipa"
          element={
            <RoleRoute allow={['clinic_admin']}>
              <StaffManagementPage />
            </RoleRoute>
          }
        />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
