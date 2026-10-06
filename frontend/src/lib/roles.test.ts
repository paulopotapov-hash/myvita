import { describe, expect, it } from 'vitest'
import { isClinician } from './roles'
import type { UserPublic } from '../types/api'

const base: UserPublic = { id: 'u', email: 'a@b.pt', full_name: 'A', role: 'staff', clinic_id: 'c', staff_role: null, patient_id: null }

describe('isClinician', () => {
  it('matches only the roles the backend grants clinical actions', () => {
    expect(isClinician({ ...base, staff_role: 'doctor' })).toBe(true)
    expect(isClinician({ ...base, staff_role: 'nurse' })).toBe(true)
    expect(isClinician({ ...base, staff_role: 'physiotherapist' })).toBe(false)
    expect(isClinician({ ...base, staff_role: 'admin' })).toBe(false)
    expect(isClinician({ ...base, role: 'clinic_admin' })).toBe(false)
    expect(isClinician({ ...base, role: 'patient' })).toBe(false)
    expect(isClinician(null)).toBe(false)
  })
})
