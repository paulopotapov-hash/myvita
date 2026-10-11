import { initialsOf } from '../lib/initials'

const SIZES = { sm: 'h-8 w-8 text-xs', md: 'h-10 w-10 text-sm', lg: 'h-12 w-12 text-base' } as const

/** Initials avatar (there are no profile photos). Decorative: the name is always given next to it or in the control's label. */
export function Avatar({ name, size = 'md' }: { name: string; size?: keyof typeof SIZES }) {
  return (
    <span aria-hidden="true" className={`inline-flex shrink-0 select-none items-center justify-center rounded-full bg-teal-700 font-semibold text-white ${SIZES[size]}`}>
      {initialsOf(name)}
    </span>
  )
}
