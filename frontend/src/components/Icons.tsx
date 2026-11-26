import type { ReactNode } from 'react'

export type IconName =
  | 'home' | 'users' | 'school' | 'book' | 'settings' | 'logout' | 'online'
  | 'offline' | 'install' | 'plus' | 'edit' | 'check' | 'close' | 'shield'
  | 'chart' | 'key' | 'refresh' | 'menu' | 'spark' | 'chat'

const paths: Record<IconName, ReactNode> = {
  home: <path d="M3 10.5 12 3l9 7.5M5 9.5V21h14V9.5M9 21v-7h6v7" />,
  users: <><circle cx="9" cy="8" r="3" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 5.2A3 3 0 0 1 16 11M18 20c0-2.2-.8-4.2-2-5.6" /></>,
  school: <path d="M3 9 12 4l9 5-9 5-9-5Zm3 2.5V18c0 1 2.7 3 6 3s6-2 6-3v-6.5M21 9v6" />,
  book: <path d="M4 5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2V5Zm2 13h13M8 7h7" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" /></>,
  logout: <path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5m4-4 4-4-4-4m4 4H9" />,
  online: <><path d="M5 12.5a10 10 0 0 1 14 0M8 16a5 5 0 0 1 8 0" /><circle cx="12" cy="20" r="1" /></>,
  offline: <path d="m3 3 18 18M5.5 10.5a10 10 0 0 1 3-1.8M2 8.5a15 15 0 0 1 4-2.3M12 20h.01M8.5 16a5 5 0 0 1 2-.9M16 8.7a10 10 0 0 1 3 1.8M22 8.5a15 15 0 0 0-6-3" />,
  install: <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v3h16v-3" />,
  plus: <path d="M12 5v14M5 12h14" />,
  edit: <path d="m4 20 4-.8L20 7.2 16.8 4 4.8 16 4 20Zm10-14 4 4" />,
  check: <path d="m4 12 5 5L20 6" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  shield: <path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Zm-3 9 2 2 4-4" />,
  chart: <path d="M4 20V10m5 10V4m5 16v-7m5 7V8" />,
  key: <><circle cx="8" cy="15" r="4" /><path d="m11 12 9-9 2 2-2 2 2 2-3 3-2-2-2 2" /></>,
  refresh: <path d="M20 11a8 8 0 1 0-2 6m2-6V5m0 6h-6" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  spark: <><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" /><path d="M19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" /></>,
  chat: <><path d="M4 5h16v11H9l-5 4V5Z" /><path d="M8 9h8M8 12h5" /></>,
}

export function Icon({ name, className = 'h-5 w-5' }: { name: IconName; className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  )
}
