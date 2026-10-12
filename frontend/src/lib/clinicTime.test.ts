import { describe, expect, it } from 'vitest'
import { addDays, clinicDateKey, clinicLocalToIso, formatClinicTime, mondayOf } from './clinicTime'

describe('clinic time (Europe/Lisbon)', () => {
  it('turns Lisbon wall-clock times into instants across daylight saving', () => {
    expect(clinicLocalToIso('2027-03-26T09:00')).toBe('2027-03-26T09:00:00.000Z') // WET, UTC+0
    expect(clinicLocalToIso('2027-04-02T09:00')).toBe('2027-04-02T08:00:00.000Z') // WEST, UTC+1
    expect(clinicLocalToIso('2027-10-29T23:30')).toBe('2027-10-29T22:30:00.000Z')
  })

  it('shows instants in Lisbon time whatever the browser time zone is', () => {
    expect(formatClinicTime('2027-04-02T08:00:00Z')).toBe('09:00')
    expect(clinicDateKey('2027-04-01T23:30:00Z')).toBe('2027-04-02')
  })

  it('does calendar arithmetic on date keys', () => {
    expect(addDays('2027-02-27', 2)).toBe('2027-03-01')
    expect(mondayOf('2027-04-04')).toBe('2027-03-29')
    expect(mondayOf('2027-03-29')).toBe('2027-03-29')
  })
})
