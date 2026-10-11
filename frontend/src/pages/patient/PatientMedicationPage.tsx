import { MedicationsSection } from '../staff/MedicationsSection'
import { PatientSectionPage } from './PatientSectionPage'

export function PatientMedicationPage() {
  return (
    <PatientSectionPage title="A minha medicação" intro="Medicação registada pela tua equipa clínica.">
      {(patientId) => <MedicationsSection patientId={patientId} canWrite={false} />}
    </PatientSectionPage>
  )
}
