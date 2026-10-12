import { useState } from 'react'
import { initialsOf } from '../lib/initials'

const SIZES = { sm: 'h-8 w-8 text-xs', md: 'h-10 w-10 text-sm', lg: 'h-12 w-12 text-base', xl: 'h-20 w-20 text-2xl' } as const

/**
 * The person's approved profile photo when there is one, otherwise their initials.
 * Decorative: the name is always given next to it or in the control's label.
 */
export function Avatar({ name, size = 'md', photoUrl }: { name: string; size?: keyof typeof SIZES; photoUrl?: string | null }) {
  const [broken, setBroken] = useState<string | null>(null)
  if (photoUrl && broken !== photoUrl) {
    return <img src={photoUrl} alt="" aria-hidden="true" onError={() => setBroken(photoUrl)} className={`shrink-0 rounded-full object-cover ${SIZES[size]}`} />
  }
  return (
    <span aria-hidden="true" className={`inline-flex shrink-0 select-none items-center justify-center rounded-full bg-teal-700 font-semibold text-white ${SIZES[size]}`}>
      {initialsOf(name)}
    </span>
  )
}
