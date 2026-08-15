'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { BarChart3, BriefcaseBusiness, FileText, FolderOpen, LogOut, Menu, Settings, UserRound, X } from 'lucide-react'
import { useAuth } from './auth-provider'

const links = [
  { href: '/', label: 'Job search', icon: BriefcaseBusiness },
  { href: '/open-jobs', label: 'Open jobs', icon: FolderOpen },
  { href: '/applied-jobs', label: 'Applied jobs', icon: BriefcaseBusiness },
  { href: '/cvs', label: 'My CVs', icon: FileText },
  { href: '/preferences', label: 'Job preferences', icon: Settings },
  { href: '/stats', label: 'Stats', icon: BarChart3 },
  { href: '/account', label: 'Account', icon: UserRound },
]

export default function Navigation() {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const [isOpen, setIsOpen] = useState(false)

  return (
    <aside className={`border-b border-gray-200 bg-white transition-[width] duration-200 md:min-h-screen md:shrink-0 md:border-b-0 md:border-r ${isOpen ? 'md:w-64' : 'md:w-14'}`}>
      <div className={`sticky top-0 p-3 md:flex md:min-h-screen md:flex-col ${isOpen ? 'md:p-5' : 'md:items-center'}`}>
        <div className={`flex items-center ${isOpen ? 'justify-between' : 'justify-center'}`}>
          {isOpen && <Link href="/" className="text-xl font-bold tracking-tight text-gray-900">CareerMatch</Link>}
          <button type="button" onClick={() => setIsOpen((current) => !current)} aria-label={isOpen ? 'Collapse navigation' : 'Expand navigation'} className="rounded-md p-2 text-gray-600 hover:bg-gray-100 hover:text-gray-900">
            {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
        {isOpen && <p className="mt-1 truncate text-xs text-gray-500">{user?.email}</p>}

        {isOpen && <nav className="mt-5 flex gap-2 overflow-x-auto md:block md:space-y-1" aria-label="Main navigation">
          {links.map(({ href, label, icon: Icon }) => {
            const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
            return (
              <Link
                key={href}
                href={href}
                className={`flex shrink-0 items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition md:w-full ${active ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'}`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            )
          })}
        </nav>}

        {isOpen && <button type="button" onClick={() => void logout()} className="mt-4 flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-gray-500 hover:bg-gray-50 hover:text-gray-900 md:mt-auto md:w-full">
          <LogOut className="h-4 w-4" /> Sign out
        </button>}
      </div>
    </aside>
  )
}