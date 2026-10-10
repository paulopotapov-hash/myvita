import { api } from '../lib/apiClient'
import type {
  ClinicalResultCorrectionRequest,
  ClinicalResultCreateRequest,
  ClinicalResultPublic,
  ClinicalResultStaffView,
  ClinicalResultStatus,
  ClinicalResultUpdateRequest,
} from '../types/api'

/** Mirrors backend schema limits; the backend still validates. */
export const RESULT_TITLE_MAX_LENGTH = 200
export const RESULT_VALUE_MAX_LENGTH = 200
export const RESULT_UNIT_MAX_LENGTH = 50
export const RESULT_REFERENCE_MAX_LENGTH = 100
export const RESULT_SUMMARY_MAX_LENGTH = 5000
export const CORRECTION_REASON_MIN_LENGTH = 5
export const CORRECTION_REASON_MAX_LENGTH = 1000

export const clinicalResultsService = {
  /** Patients only ever receive released results (enforced by the backend). */
  list: (patientId: string, page: number, pageSize: number, status?: ClinicalResultStatus, signal?: AbortSignal) => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (status) query.set('status', status)
    return api.getPage<ClinicalResultPublic>(`/api/v1/patients/${encodeURIComponent(patientId)}/results?${query}`, signal)
  },
  detail: (resultId: string, signal?: AbortSignal) =>
    api.get<ClinicalResultPublic>(`/api/v1/results/${encodeURIComponent(resultId)}`, signal),
  create: (patientId: string, payload: ClinicalResultCreateRequest) =>
    api.post<ClinicalResultStaffView>(`/api/v1/patients/${encodeURIComponent(patientId)}/results`, payload),
  update: (resultId: string, payload: ClinicalResultUpdateRequest) =>
    api.patch<ClinicalResultStaffView>(`/api/v1/results/${encodeURIComponent(resultId)}`, payload),
  /** A correction is a new result; the released original is never modified. */
  correct: (resultId: string, payload: ClinicalResultCorrectionRequest) =>
    api.post<ClinicalResultStaffView>(`/api/v1/results/${encodeURIComponent(resultId)}/corrections`, payload),
  release: (resultId: string) =>
    api.post<ClinicalResultStaffView>(`/api/v1/results/${encodeURIComponent(resultId)}/release`),
}
