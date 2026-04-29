'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  CogIcon,
  FolderIcon,
  TagIcon,
  BarChart2Icon,
  BarChart3Icon,
} from 'lucide-react'

interface NavItem {
  href: string
  label: string
  icon: React.ReactNode
  description?: string
}

const navItems: NavItem[] = [
  {
    href: '/admin/ingestion',
    label: 'Ingestion Tasks',
    icon: <BarChart2Icon className="w-5 h-5" />,
    description: 'Manage data ingestion tasks',
  },
  {
    href: '/admin/settings',
    label: 'Settings',
    icon: <CogIcon className="w-5 h-5" />,
    description: 'Application & provider settings',
  },
  {
    href: '/admin/datasets',
    label: 'Datasets',
    icon: <FolderIcon className="w-5 h-5" />,
    description: 'Manage documents and data',
  },
  {
    href: '/admin/tags',
    label: 'Tags',
    icon: <TagIcon className="w-5 h-5" />,
    description: 'Manage content tags',
  },
]

export default function AdminSidebar() {
  const pathname = usePathname()

  return (
    <aside className="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-40 lg:block lg:w-64 lg:bg-white lg:dark:bg-gray-800 lg:border-r lg:border-gray-200 lg:dark:border-gray-700 pt-20">
      <div className="h-full overflow-y-auto px-4 py-6">
        <nav className="space-y-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(item.href + '/')

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50'
                }`}
              >
                <span className={isActive ? 'text-blue-600 dark:text-blue-400' : 'text-gray-500 dark:text-gray-400'}>
                  {item.icon}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{item.label}</div>
                  {item.description && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{item.description}</p>
                  )}
                </div>
              </Link>
            )
          })}
        </nav>
      </div>
    </aside>
  )
}
