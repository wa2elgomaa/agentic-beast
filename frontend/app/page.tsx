'use client'

import ChatContainer from '@/components/ChatContainer'
import ProtectedRoute from '@/components/ProtectedRoute'

export default function Home() {
  return (
    <ProtectedRoute>
      <ChatContainer />
    </ProtectedRoute>
  )
}
