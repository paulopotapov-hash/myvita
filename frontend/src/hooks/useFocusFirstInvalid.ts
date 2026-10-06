import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

/**
 * After a failed submit, moves keyboard/screen-reader focus to the first
 * invalid field of the form that owns `errors`. Attach the returned ref to the
 * <form>. Root-level errors (`_root`) are announced by their own alert instead.
 */
export function useFocusFirstInvalid(errors: Record<string, string>): RefObject<HTMLFormElement | null> {
  const formRef = useRef<HTMLFormElement>(null)
  useEffect(() => {
    if (!Object.keys(errors).some((field) => field !== '_root')) return
    formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()
  }, [errors])
  return formRef
}
