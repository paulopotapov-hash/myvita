/**
 * Inline SVG icons (no icon dependency). Always decorative: the control or
 * text next to an icon carries the accessible name.
 */
const PATHS = {
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'M6 6l12 12M18 6L6 18',
  home: 'M3 11.5L12 4l9 7.5M5.5 10v9.5h4.5V14h4v5.5h4.5V10',
  calendar: 'M7 3v3M17 3v3M4 8.5h16M5 5.5h14a1 1 0 011 1V19a1 1 0 01-1 1H5a1 1 0 01-1-1V6.5a1 1 0 011-1z',
  chat: 'M20 12a7.5 7.5 0 01-11.2 6.5L4 20l1.5-4.6A7.5 7.5 0 1120 12z',
  results: 'M9 3h6M10 3v6.5L5 18a1.6 1.6 0 001.4 2.5h11.2A1.6 1.6 0 0019 18l-5-8.5V3M7.5 14.5h9',
  document: 'M14 3H7a1 1 0 00-1 1v16a1 1 0 001 1h10a1 1 0 001-1V7l-4-4zM14 3v4h4M9 12h6M9 16h6',
  clipboard: 'M9 4h6a1 1 0 011 1v1H8V5a1 1 0 011-1zM8 5H6a1 1 0 00-1 1v14a1 1 0 001 1h12a1 1 0 001-1V6a1 1 0 00-1-1h-2M12 10v6M9 13h6',
  check: 'M12 3l7 3v5.5c0 4.3-3 7.8-7 9-4-1.2-7-4.7-7-9V6l7-3zM8.5 12l2.5 2.5 4.5-5',
  bell: 'M6 16V11a6 6 0 1112 0v5l1.5 2h-15L6 16zM10 20.5a2 2 0 004 0',
  users: 'M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM2.5 20a6.5 6.5 0 0113 0M16 4.3a3.5 3.5 0 010 6.4M18 14.5a6.5 6.5 0 013.5 5.5',
  team: 'M12 11a3 3 0 100-6 3 3 0 000 6zM6.5 20a5.5 5.5 0 0111 0M5 10.5a2.5 2.5 0 100-5M19 10.5a2.5 2.5 0 110-5M1.5 18a4 4 0 014-3.5M22.5 18a4 4 0 00-4-3.5',
  key: 'M14.5 9.5a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM13 13l7.5 7.5M17 17l2-2M19 19l1.5-1.5',
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0',
  shield: 'M12 3l7 3v5.5c0 4.3-3 7.8-7 9-4-1.2-7-4.7-7-9V6l7-3z',
  logout: 'M15 4h3a1 1 0 011 1v14a1 1 0 01-1 1h-3M10 16l-4-4 4-4M6 12h10',
} as const

export type IconName = keyof typeof PATHS

export function Icon({ name, className = 'h-6 w-6' }: { name: IconName; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  )
}
