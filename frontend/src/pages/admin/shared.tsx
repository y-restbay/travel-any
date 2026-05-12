import { motion, AnimatePresence } from 'framer-motion'
import { Loader2, X } from 'lucide-react'
import type { ReactNode } from 'react'

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="modal-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto bg-black/30 px-4 backdrop-blur-lg"
          onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
        >
          <motion.div
            key="modal-panel"
            initial={{ opacity: 0, scale: 0.96, y: 24 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 24 }}
            transition={{ type: 'spring', duration: 0.35, bounce: 0.12 }}
            className="relative mt-[8vh] w-full max-w-2xl rounded-4xl bg-paper p-6 shadow-soft md:p-7"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={onClose}
              className="absolute right-5 top-5 grid h-8 w-8 place-items-center rounded-xl text-muted transition hover:bg-clay/30 hover:text-ink"
            >
              <X size={17} />
            </button>
            <h3 className="pr-8 text-xl font-semibold text-ink">{title}</h3>
            {subtitle && <p className="mt-1.5 text-sm leading-6 text-muted">{subtitle}</p>}
            <div className="mt-6">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function ModuleCard({
  title,
  desc,
  icon,
  actions,
  children,
}: {
  title: string
  desc: string
  icon: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      className="rounded-4xl bg-paper/90 p-5 shadow-soft backdrop-blur md:p-6"
    >
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-3xl bg-sage text-moss">
            {icon}
          </span>
          <div>
            <h2 className="text-lg font-semibold">{title}</h2>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">{desc}</p>
          </div>
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
      {children}
    </motion.section>
  )
}

export function Field({
  label,
  hint,
  className = '',
  children,
}: {
  label: string
  hint?: string
  className?: string
  children: ReactNode
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-2 block px-1 text-sm font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="mt-2 block px-1 text-xs leading-5 text-muted/80">{hint}</span>}
    </label>
  )
}

export function SoftButton({
  children,
  onClick,
  type = 'button',
  disabled = false,
  tone = 'quiet',
  className = '',
  intent,
}: {
  children: ReactNode
  onClick?: () => void
  type?: 'button' | 'submit'
  disabled?: boolean
  tone?: 'primary' | 'quiet' | 'danger' | 'success'
  className?: string
  intent?: string
}) {
  const toneClass = {
    primary: 'bg-ink text-paper shadow-quiet hover:-translate-y-0.5',
    quiet: 'bg-[#F8F6F1] text-ink hover:bg-clay/40',
    danger: 'bg-red-50 text-red-700 hover:bg-red-100',
    success: 'bg-sage text-moss hover:bg-sage/80',
  }[tone]

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      data-intent={intent}
      className={`inline-flex items-center justify-center gap-2 rounded-3xl px-4 py-2.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-55 ${toneClass} ${className}`}
    >
      {children}
    </button>
  )
}

export function IconButton({
  title,
  children,
  onClick,
  disabled = false,
  danger = false,
}: {
  title: string
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  danger?: boolean
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`grid h-9 w-9 place-items-center rounded-2xl transition disabled:cursor-not-allowed disabled:opacity-40 ${
        danger ? 'text-muted hover:bg-red-100 hover:text-red-700' : 'text-muted hover:bg-clay/40 hover:text-ink'
      }`}
    >
      {children}
    </button>
  )
}

export function LoadingState({ label = '加载中...' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center rounded-3xl bg-[#F8F6F1] py-10 text-sm text-muted">
      <Loader2 className="mr-2 animate-spin" size={18} />
      {label}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-3xl border border-dashed border-line px-6 py-10 text-center text-sm leading-6 text-muted">
      {children}
    </div>
  )
}

export function InlineNotice({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'success' | 'error'
  children: ReactNode
}) {
  const toneClass = {
    neutral: 'bg-[#F8F6F1] text-muted',
    success: 'bg-green-50 text-green-800',
    error: 'bg-red-50 text-red-800',
  }[tone]

  return <div className={`rounded-3xl px-4 py-3 text-sm leading-6 ${toneClass}`}>{children}</div>
}
