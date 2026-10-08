import { Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './app/ProtectedRoute'
import { RoleRoute } from './app/RoleRoute'
import { RootRedirect } from './app/RootRedirect'
import { AppLayout } from './layouts/AppLayout'
import { PatientLayout } from './layouts/PatientLayout'
import { ClinicOnboardingPage } from './pages/auth/ClinicOnboardingPage'
import { LoginPage } from './pages/auth/LoginPage'
import { InvitationAcceptPage } from './pages/auth/InvitationAcceptPage'
import { PatientRegisterPage } from './pages/auth/PatientRegisterPage'
import { DashboardPage } from './pages/DashboardPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PatientProfilePage } from './pages/patient/PatientProfilePage'
import { AppointmentsPage } from './pages/staff/AppointmentsPage'
import { PatientsPage } from './pages/staff/PatientsPage'
import { PatientDetailPage } from './pages/staff/PatientDetailPage'
import { NotificationsPage } from './pages/NotificationsPage'
import { StaffManagementPage } from './pages/admin/StaffManagementPage'
import { AccountSecurityPage } from './pages/AccountSecurityPage'
import { AccountProfilePage } from './pages/AccountProfilePage'
import { PatientDashboard } from './pages/patient/PatientDashboard'
import { MessagesInboxPage } from './pages/messages/MessagesInboxPage'
import { ConversationPage } from './pages/messages/ConversationPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/registo" element={<PatientRegisterPage />} />
      <Route path="/nova-clinica" element={<ClinicOnboardingPage />} />
      <Route path="/convite" element={<InvitationAcceptPage />} />

      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <RoleRoute allow={['staff', 'clinic_admin']}>
              <AppLayout />
            </RoleRoute>
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="consultas" element={<AppointmentsPage />} />
        <Route path="notificacoes" element={<NotificationsPage />} />
        <Route path="mensagens" element={<MessagesInboxPage />} />
        <Route path="mensagens/:conversationId" element={<ConversationPage />} />
        <Route path="perfil" element={<AccountProfilePage />} />
        <Route path="seguranca" element={<AccountSecurityPage />} />
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

      <Route
        path="/patient"
        element={
          <ProtectedRoute>
            <RoleRoute allow={['patient']}>
              <PatientLayout />
            </RoleRoute>
          </ProtectedRoute>
        }
      >
        <Route index element={<PatientDashboard />} />
        <Route path="consultas" element={<AppointmentsPage />} />
        <Route path="perfil" element={<PatientProfilePage />} />
        <Route path="consentimentos" element={<PatientDetailPage own section="consents" />} />
        <Route path="seguranca" element={<AccountSecurityPage />} />
        <Route path="saude" element={<PatientDetailPage own />} />
        <Route path="notificacoes" element={<NotificationsPage />} />
        <Route path="mensagens" element={<MessagesInboxPage />} />
        <Route path="mensagens/:conversationId" element={<ConversationPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
