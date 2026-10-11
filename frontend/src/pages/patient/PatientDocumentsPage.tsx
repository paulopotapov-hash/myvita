import { DocumentsSection } from '../../components/DocumentsSection'
import { PatientSectionPage } from './PatientSectionPage'

export function PatientDocumentsPage() {
  return (
    <PatientSectionPage title="Os meus documentos" intro="Relatórios e outros documentos partilhados contigo.">
      {(patientId) => <DocumentsSection patientId={patientId} canManage={false} />}
    </PatientSectionPage>
  )
}
