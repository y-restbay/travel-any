import { Link, NavLink } from 'react-router-dom'
import { Compass, SlidersHorizontal } from 'lucide-react'

export default function ShellNav() {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    [
      'inline-flex items-center gap-2 rounded-3xl px-4 py-2 text-sm transition',
      isActive ? 'bg-paper text-ink shadow-quiet' : 'text-muted hover:bg-paper/70 hover:text-ink',
    ].join(' ')

  return (
    <header className="fixed left-0 right-0 top-0 z-30 flex justify-center px-4 py-4">
      <nav className="flex w-full max-w-5xl items-center justify-between rounded-4xl bg-[#F8F6F1]/80 px-3 py-2 shadow-quiet backdrop-blur-xl">
        <Link to="/" className="flex items-center gap-3 rounded-3xl px-3 py-2 text-ink">
          <span className="grid h-9 w-9 place-items-center rounded-3xl bg-clay text-ink">
            <Compass size={18} />
          </span>
          <span className="leading-tight">
            <span className="block font-display text-lg">WanderBot</span>
            <span className="block text-xs text-muted">漫游指南</span>
          </span>
        </Link>
        <div className="flex items-center gap-1">
          <NavLink to="/" className={linkClass}>
            <Compass size={16} />
            对话
          </NavLink>
          <NavLink to="/admin" className={linkClass}>
            <SlidersHorizontal size={16} />
            管理
          </NavLink>
        </div>
      </nav>
    </header>
  )
}
