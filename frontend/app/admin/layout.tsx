import ProtectedRoute from '@/components/ProtectedRoute'
import AdminHeader from '@/components/admin/AdminHeader'
import AdminSidebar from '@/components/admin/AdminSidebar'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute requireAdmin>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        {/* Admin Header */}
        <AdminHeader />
        
        {/* Admin Sidebar + Content */}
        <div className="flex">
          {/* Sidebar */}
          <AdminSidebar />
          
          {/* Admin Content */}
          <main className="flex-1 lg:ml-64 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
            {children}
          </main>
        </div>
      </div>
    </ProtectedRoute>
  )
}
