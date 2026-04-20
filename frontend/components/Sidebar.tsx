'use client'

import { MessageSquare, Plus, Trash2, TrendingUp, Menu, X, Clock, LogOut, Edit2, Check, XIcon, Settings } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import LogoIcon from './Logo'
import { Conversation } from '@/types'
import { formatDistanceToNow } from 'date-fns'
import { useAuth } from '@/contexts/AuthContext'
import { useState } from 'react'

interface SidebarProps {
  isOpen: boolean
  onToggle: () => void
  onClearChat: () => void
  messageCount: number
  conversations: Conversation[]
  currentConversationId: string | null
  onSelectConversation: (id: string) => void
  onDeleteConversation: (id: string) => void
  onUpdateConversationTitle: (id: string, title: string) => void
  onQuickQuestion: (question: string) => void
  hasMoreConversations: boolean
  onLoadMoreConversations: () => void
  isLoadingConversations: boolean
}

const quickQuestions = [
  { id: 1, text: 'What are the top 5 viewed videos', icon: '🎥' },
  { id: 2, text: 'Instagram reels with most impressions', icon: '📸' },
  // { id: 3, text: 'Instagram reels with most impressions', icon: '📸' },
  // { id: 4, text: 'What is the average completion rate for TikTok videos this month', icon: '📘' },
  // { id: 5, text: 'Compare TikTok vs Instagram', icon: '📊' },
]

export default function Sidebar({
  isOpen,
  onToggle,
  onClearChat,
  messageCount,
  conversations,
  currentConversationId,
  onSelectConversation,
  onDeleteConversation,
  onUpdateConversationTitle,
  onQuickQuestion,
  hasMoreConversations,
  onLoadMoreConversations,
  isLoadingConversations
}: SidebarProps) {
  const { logout, user } = useAuth()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  const handleQuestionClick = (question: string) => {
    onQuickQuestion(question)
  }

  const startEditing = (conv: Conversation) => {
    setEditingId(conv.id)
    setEditTitle(conv.title)
  }

  const saveEdit = (convId: string) => {
    if (editTitle.trim()) {
      onUpdateConversationTitle(convId, editTitle.trim())
    }
    setEditingId(null)
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditTitle('')
  }

  const formatTime = (dateString: string) => {
    try {
      return formatDistanceToNow(new Date(dateString), { addSuffix: true })
    } catch {
      return 'recently'
    }
  }

  return (
    <>
      {/* Mobile Toggle Button */}
      <button
        onClick={onToggle}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 rounded-lg bg-white hover:bg-gray-50 text-gray-900 border border-gray-200 shadow-sm"
      >
        {isOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      <AnimatePresence>
        {isOpen && (
          <>
            {/* Overlay for mobile */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onToggle}
              className="lg:hidden fixed inset-0 bg-black/50 z-40"
            />

            {/* Sidebar */}
            <motion.aside
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: 'spring', damping: 20 }}
              className="fixed lg:relative z-40 w-[280px] bg-[#f9fafb] h-screen flex flex-col border-r border-gray-200"
            >
              {/* Header */}
              <div className="p-4 border-b border-gray-200">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm">
                    <LogoIcon color='#004E79' />
                  </div>
                  <span className="font-semibold text-gray-900">The Beast AI</span>
                </div>
                <button
                  onClick={onClearChat}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border border-gray-200 hover:bg-gray-100 transition-colors text-sm text-gray-900"
                >
                  <Plus size={16} />
                  New Chat
                </button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-4">
                {/* Conversation History */}
                {conversations.length > 0 && (
                  <div className="mb-6">
                    <div className='flex items-center justify-between gap-2 text-xs text-gray-400 uppercase tracking-wider mb-3 w-full'>
                      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                        <Clock size={14} />
                        Recent Conversations
                      </h3>
                      <button
                        onClick={onClearChat}
                        className="px-2 py-2.5 rounded-lg hover:bg-red-100 hover:text-red-600 transition-colors text-sm text-gray-600"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <div className="space-y-1">
                      {conversations.map((conv) => (
                        <div
                          key={conv.id}
                          className={`group relative rounded-lg transition-colors ${conv.id === currentConversationId
                            ? 'bg-blue-50 border border-blue-200'
                            : 'hover:bg-gray-100 border border-transparent'
                            }`}
                        >
                          {editingId === conv.id ? (
                            <div className="flex items-center gap-2 px-3 py-2.5">
                              <MessageSquare
                                size={14}
                                className="mt-0.5 flex-shrink-0 text-blue-600"
                              />
                              <input
                                type="text"
                                value={editTitle}
                                onChange={(e) => setEditTitle(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') saveEdit(conv.id)
                                  if (e.key === 'Escape') cancelEdit()
                                }}
                                className="flex-1 min-w-0 px-2 py-1 text-sm border border-blue-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                                autoFocus
                                maxLength={50}
                              />
                              <button
                                onClick={() => saveEdit(conv.id)}
                                className="p-1 rounded hover:bg-green-100 text-green-600"
                                title="Save"
                              >
                                <Check size={14} />
                              </button>
                              <button
                                onClick={cancelEdit}
                                className="p-1 rounded hover:bg-gray-200 text-gray-600"
                                title="Cancel"
                              >
                                <XIcon size={14} />
                              </button>
                            </div>
                          ) : (
                            <>
                              <button
                                onClick={() => onSelectConversation(conv.id)}
                                className="w-full text-left px-3 py-2.5 text-sm"
                              >
                                <div className="flex items-start gap-2">
                                  <MessageSquare
                                    size={14}
                                    className={`mt-0.5 flex-shrink-0 ${conv.id === currentConversationId ? 'text-blue-600' : 'text-gray-400'
                                      }`}
                                  />
                                  <div className="flex-1 min-w-0 pr-16">
                                    <div className={`font-medium truncate ${conv.id === currentConversationId ? 'text-blue-900' : 'text-gray-900'
                                      }`}>
                                      {conv.title}
                                    </div>
                                    <div className="text-xs text-gray-500 mt-0.5">
                                      {conv.message_count} messages · {formatTime(conv.updated_at)}
                                    </div>
                                  </div>
                                </div>
                              </button>
                              <div className="absolute right-2 top-2.5 flex gap-1 opacity-0 group-hover:opacity-100">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    startEditing(conv)
                                  }}
                                  className="p-1 rounded hover:bg-blue-100 text-gray-400 hover:text-blue-600 transition-all"
                                  title="Rename conversation"
                                >
                                  <Edit2 size={14} />
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    onDeleteConversation(conv.id)
                                  }}
                                  className="p-1 rounded hover:bg-red-100 text-gray-400 hover:text-red-600 transition-all"
                                  title="Delete conversation"
                                >
                                  <Trash2 size={14} />
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      ))}
                    </div>

                    {/* Load More Conversations */}
                    {hasMoreConversations && (
                      <button
                        onClick={onLoadMoreConversations}
                        disabled={isLoadingConversations}
                        className="w-full mt-2 px-3 py-2 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
                      >
                        {isLoadingConversations ? 'Loading...' : 'Load More'}
                      </button>
                    )}
                  </div>
                )}

                {/* Quick Questions */}
                <div>
                  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                    <TrendingUp size={14} />
                    Quick Questions
                  </h3>
                  <div className="space-y-2">
                    {quickQuestions.map((q) => (
                      <button
                        key={q.id}
                        title={q.text}
                        aria-label={q.text}
                        onClick={() => handleQuestionClick(q.text)}
                        className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-gray-100 transition-colors text-sm text-gray-700 hover:text-gray-900 flex items-center gap-2 group"
                      >
                        <span className="text-base">{q.icon}</span>
                        <span className="flex-1 truncate">{q.text}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Stats */}
                {messageCount > 0 && currentConversationId && (
                  <div className="mt-6 p-3 rounded-lg bg-gray-100 border border-gray-200">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-600">Current Chat Messages</span>
                      <span className="font-semibold text-gray-900">{messageCount}</span>
                    </div>
                  </div>
                )}


              </div>

              {/* Footer */}
              <div className="p-4 border-t border-gray-200">
                {/* Admin Section */}
                {/* {user?.is_admin && (
                  <div className="px-4 py-2 text-xs text-gray-600 border-b border-gray-200 pb-3 mb-2">
                    <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                      <Settings size={14} />
                      Admin
                    </h3>
                    <a
                      href="/admin/ingestion"
                      className="w-full flex items-center gap-3 py-2.5 rounded-lg transition-colors text-sm text-gray-700 hover:text-orange-700 hover:font-medium"
                    >
                      <TrendingUp size={16} className="text-orange-600" />
                      <span>Data Ingestion</span>
                    </a>
                  </div>
                )} */}
                {user && (
                  <div className="px-4 py-2 text-xs text-gray-600 border-b border-gray-200 pb-3 mb-2">
                    <div className="font-medium text-gray-900">{user.username}</div>
                    <div className="text-gray-500 truncate">{user.email}</div>
                    <div className='mt-4 flex items-center justify-between gap-2 text-xs text-gray-400 uppercase tracking-wider mt-2'>

                      {user.is_admin && <a
                        href="/admin/ingestion"
                        className=" flex gap-2 items-center text-orange-600 font-medium text-xs mt-1">
                        <Settings size={14} />
                        Admin
                      </a>}
                      <button
                        onClick={logout}
                        className="flex items-center gap-3 p-2 rounded-lg hover:bg-red-50 transition-colors text-sm text-gray-600 hover:text-red-600"
                      >
                        <LogOut size={16} />
                        Sign out
                      </button>
                    </div>

                  </div>
                )}
                {/* <button
                  onClick={onClearChat}
                  className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg hover:bg-gray-100 transition-colors text-sm text-gray-600 hover:text-gray-900"
                >
                  <Trash2 size={16} />
                  Clear conversations
                </button> */}
                {/* <button
                  onClick={logout}
                  className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg hover:bg-red-50 transition-colors text-sm text-gray-600 hover:text-red-600"
                >
                  <LogOut size={16} />
                  Sign out
                </button> */}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence >
    </>
  )
}
