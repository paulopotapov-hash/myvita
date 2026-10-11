import { MedicationsSection } from '../staff/MedicationsSection'
import { PatientSectionPage } from './PatientSectionPage'

export function PatientMedicationPage() {
  return (
    <PatientSectionPage title="A minha medicação" intro="A medicação registada pela tua equipa clínica e a que declaraste.">
      {(patientId) => <MedicationsSection patientId={patientId} canWrite={false} canDeclare />}
    </PatientSectionPage>
  )
}
