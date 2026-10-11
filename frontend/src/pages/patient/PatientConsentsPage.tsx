import { ConsentSection } from '../../components/ConsentSection'
import { PatientSectionPage } from './PatientSectionPage'

export function PatientConsentsPage() {
  return (
    <PatientSectionPage title="Os meus consentimentos" intro="Concede ou revoga as autorizações para o tratamento dos teus dados.">
      {(patientId) => <ConsentSection patientId={patientId} canManage />}
    </PatientSectionPage>
  )
}
