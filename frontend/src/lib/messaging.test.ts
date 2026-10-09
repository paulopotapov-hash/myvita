import { describe, expect, it } from 'vitest'
import { canUseMessaging, messagesBasePath } from './messaging'

describe('canUseMessaging', () => {
  it('mirrors the backend participant rule', () => {
    expect(canUseMessaging({ role: 'patient', staff_role: null })).toBe(true)
    expect(canUseMessaging({ role: 'staff', staff_role: 'doctor' })).toBe(true)
    expect(canUseMessaging({ role: 'staff', staff_role: 'nurse' })).toBe(true)
    expect(canUseMessaging({ role: 'staff', staff_role: 'admin' })).toBe(false)
    expect(canUseMessaging({ role: 'clinic_admin', staff_role: null })).toBe(false)
    expect(canUseMessaging(null)).toBe(false)
  })

  it('routes each role to its own messages area', () => {
    expect(messagesBasePath({ role: 'patient' })).toBe('/patient/mensagens')
    expect(messagesBasePath({ role: 'staff' })).toBe('/app/mensagens')
  })
})
