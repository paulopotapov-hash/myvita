import { describe, expect, it } from 'vitest'
import { digitsOnly, isValidNif, isValidNiss, isValidPostalCode, isValidSnsNumber } from './ptIdentifiers'

// Synthetic values only, the same ones the backend tests use.
describe('Portuguese identifiers', () => {
  it('checks the NIF check digit', () => {
    expect(isValidNif('123456789')).toBe(true)
    expect(isValidNif('234567899')).toBe(true)
    expect(isValidNif('500000000')).toBe(true)
    for (const value of ['123456788', '12345678', '1234567890', '12345678a', '']) expect(isValidNif(value)).toBe(false)
  })

  it('checks the NISS check digit and prefix', () => {
    expect(isValidNiss('12345678902')).toBe(true)
    expect(isValidNiss('12345678900')).toBe(false)
    expect(isValidNiss('32345678902')).toBe(false)
    expect(isValidNiss('1234567890')).toBe(false)
  })

  it('checks the SNS number format, the postal code format and normalises spaces', () => {
    expect(isValidSnsNumber('987654321')).toBe(true)
    expect(isValidSnsNumber('98765432')).toBe(false)
    expect(isValidPostalCode('1000-001')).toBe(true)
    for (const value of ['1000001', '1000-01', '100-0001']) expect(isValidPostalCode(value)).toBe(false)
    expect(digitsOnly(' 123 456 789 ')).toBe('123456789')
  })
})
