import { describe, expect, it } from 'vitest'
import { badgeText, navigationFor } from './navItems'
import { initialsOf } from './initials'

const labels = (role: 'patient' | 'staff' | 'clinic_admin', staff_role: 'doctor' | 'nurse' | 'physiotherapist' | 'admin' | null = null) =>
  navigationFor({ role, staff_role }).items.map((item) => item.label)

describe('navigationFor', () => {
  it('gives the patient their own sections and account links', () => {
    const navigation = navigationFor({ role: 'patient', staff_role: null })
    expect(navigation.items.map((item) => item.label)).toEqual([
      'Início', 'Consultas', 'Mensagens', 'Resultados', 'Documentos', 'Dados clínicos', 'Consentimentos', 'Notificações',
    ])
    expect(navigation.items.every((item) => item.to.startsWith('/patient'))).toBe(true)
    expect(navigation.account).toEqual({ profile: '/patient/perfil', security: '/patient/seguranca' })
  })

  it('offers messages only to roles that may message (doctor, nurse)', () => {
    expect(labels('staff', 'doctor')).toContain('Mensagens')
    expect(labels('staff', 'nurse')).toContain('Mensagens')
    expect(labels('staff', 'physiotherapist')).not.toContain('Mensagens')
    expect(labels('staff', 'admin')).not.toContain('Mensagens')
  })

  it('gives clinic administrators team and account management, without clinical messaging', () => {
    expect(labels('clinic_admin')).toEqual(['Início', 'Consultas', 'Pacientes', 'Equipa', 'Contas', 'Notificações'])
    expect(labels('staff', 'doctor')).not.toContain('Equipa')
  })
})

describe('badgeText and initialsOf', () => {
  it('caps large counts and builds initials safely', () => {
    expect(badgeText(7)).toBe('7')
    expect(badgeText(100)).toBe('99+')
    expect(initialsOf('Ana Maria Silva')).toBe('AS')
    expect(initialsOf('  rui  ')).toBe('R')
    expect(initialsOf('')).toBe('?')
  })
})
