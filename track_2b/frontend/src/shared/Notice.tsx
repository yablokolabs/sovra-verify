import type { ReactNode } from 'react'

export type NoticeTone = 'info' | 'warning' | 'error' | 'success'

interface NoticeProps {
  tone?: NoticeTone
  title?: string
  children: ReactNode
}

/**
 * An inline notice placed next to the control it describes. It is deliberately
 * never rendered as a trailing page section.
 */
export function Notice({ tone = 'info', title, children }: NoticeProps) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {title ? <p className="notice-title">{title}</p> : null}
      <div className="notice-body">{children}</div>
    </div>
  )
}

interface ListNoticeProps {
  tone?: NoticeTone
  title: string
  items: string[]
}

export function ListNotice({ tone = 'warning', title, items }: ListNoticeProps) {
  if (items.length === 0) return null
  return (
    <Notice tone={tone} title={title}>
      <ul className="notice-list">
        {items.map((item, index) => (
          <li key={`${index}-${item.slice(0, 24)}`}>{item}</li>
        ))}
      </ul>
    </Notice>
  )
}
