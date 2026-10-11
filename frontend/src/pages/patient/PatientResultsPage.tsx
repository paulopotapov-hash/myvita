import { ClinicalResultsSection } from '../../components/ClinicalResultsSection'
import { PatientSectionPage } from './PatientSectionPage'

export function PatientResultsPage() {
  return (
    <PatientSectionPage title="Os meus resultados" intro="Análises, exames e outros resultados disponibilizados pela tua equipa clínica.">
      {(patientId) => <ClinicalResultsSection patientId={patientId} canManage={false} patientArea />}
    </PatientSectionPage>
  )
}
