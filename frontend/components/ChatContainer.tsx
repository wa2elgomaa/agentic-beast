'use client'

import { useState, useEffect } from 'react'
import Sidebar from './Sidebar'
import ChatArea from './ChatArea'
import { Message, Conversation, OperationType, AnalyticsResultDataItem } from '@/types'
import { getConversations, getConversation, deleteConversation, updateConversationTitle } from '@/lib/api'
import { useToast } from './Toast'

export default function ChatContainer() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isOpen, setIsOpen] = useState(true)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null)
  const [hasMoreConversations, setHasMoreConversations] = useState(false)
  const [hasMoreMessages, setHasMoreMessages] = useState(false)
  const [conversationsPage, setConversationsPage] = useState(1)
  const [messagesPage, setMessagesPage] = useState(1)
  const [isLoadingConversations, setIsLoadingConversations] = useState(false)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [isFirstMessage, setIsFirstMessage] = useState(true)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const { showToast } = useToast()

  // Load conversations on mount
  useEffect(() => {
    loadConversations()
  }, [])

  const tryParseContent = (value: unknown): Record<string, any> | null => {
    if (typeof value === 'object' && value !== null) return value as Record<string, any>
    if (typeof value !== 'string') return null

    const trimmed = value.trim()
    if (!trimmed) return null

    const candidates = [trimmed]
    if (
      (trimmed.startsWith('"{') && trimmed.endsWith('}"')) ||
      (trimmed.startsWith('"[') && trimmed.endsWith(']"'))
    ) {
      candidates.push(trimmed.slice(1, -1))
    }

    for (const candidate of candidates) {
      try {
        const parsed = JSON.parse(candidate)
        if (typeof parsed === 'string') {
          try {
            const nested = JSON.parse(parsed)
            if (typeof nested === 'object' && nested !== null) return nested as Record<string, any>
          } catch {
            // continue
          }
        }
        if (typeof parsed === 'object' && parsed !== null) return parsed as Record<string, any>
      } catch {
        // try next
      }
    }

    return null
  }

  const mapQueryTypeToOperation = (queryType?: string, fallback?: string): OperationType | undefined => {
    switch ((queryType || fallback || '').toLowerCase()) {
      case 'analytics':
      case 'query_documents':
        return 'query_documents'
      case 'tag_suggestion':
      case 'suggest_tags_for_article_id':
        return 'suggest_tags_for_article_id'
      case 'suggest_tags_for_article_body':
        return 'suggest_tags_for_article_body'
      default:
        return undefined
    }
  }

  const normalizeHistoryMessage = (msg: any): Message => {
    const base: Message = {
      ...msg,
      timestamp: new Date(msg.created_at || msg.timestamp),
      content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content ?? ''),
      operationData: msg.operation_data,
      operationMetadata: msg.operation_metadata,
      results: msg.operation_data?.results as any,
    }

    // Old assistant messages may only store JSON payload inside content.
    if (msg.role !== 'assistant') return base

    const parsedContent = tryParseContent(msg.content)
    if (!parsedContent) return base

    const queryType = parsedContent.query_type as string | undefined
    const operation = mapQueryTypeToOperation(queryType, msg.metadata?.operation)

    const normalizedResults =
      (Array.isArray(parsedContent.result_data) ? parsedContent.result_data : undefined) ||
      (Array.isArray(parsedContent.results) ? parsedContent.results : undefined)

    const operationData = {
      answer: parsedContent.insight_summary || parsedContent.answer || base.content,
      results: normalizedResults as AnalyticsResultDataItem[] | undefined,
      note: parsedContent.verification || parsedContent.resolved_context,
      query_type: queryType,
      resolved_context: parsedContent.resolved_context,
      verification: parsedContent.verification,
      analytics_content: queryType
        ? {
            query_type: queryType,
            resolved_context: parsedContent.resolved_context || '',
            result_data: Array.isArray(parsedContent.result_data) ? parsedContent.result_data : [],
            insight_summary: parsedContent.insight_summary || '',
            verification: parsedContent.verification || '',
          }
        : undefined,
    }

    return {
      ...base,
      content: operationData.answer,
      operation: operation || base.operation,
      operationData: base.operationData || operationData,
      operationMetadata: base.operationMetadata || msg.metadata || {},
      results: (base.operationData?.results as any) || (operationData.results as any),
    }
  }

  const loadConversations = async (page: number = 1) => {
    setIsLoadingConversations(true)
    try {
      const response = await getConversations(page, 20)
      if (page === 1) {
        setConversations(response.conversations)
      } else {
        setConversations(prev => [...prev, ...response.conversations])
      }
      setHasMoreConversations(response.has_more ?? false)
      setConversationsPage(page)
    } catch (error) {
      showToast('Failed to load conversations', 'error')
      console.error('Error loading conversations:', error)
    } finally {
      setIsLoadingConversations(false)
    }
  }

  const loadMoreConversations = () => {
    loadConversations(conversationsPage + 1)
  }

  const handleSelectConversation = async (conversationId: string) => {
    try {
      setIsLoadingMessages(true)
      const conversation = await getConversation(conversationId, 1, 50)

      const loadedMessages: Message[] = conversation.messages.map(normalizeHistoryMessage)

      setMessages(loadedMessages)
      setCurrentConversationId(conversationId)
      setHasMoreMessages(conversation.has_more ?? false)
      setMessagesPage(1)
      setIsFirstMessage(loadedMessages.length === 0)
    } catch (error) {
      showToast('Failed to load conversation', 'error')
      console.error('Error loading conversation:', error)
    } finally {
      setIsLoadingMessages(false)
    }
  }

  const loadMoreMessages = async () => {
    setHasMoreMessages(false)
  }

  const handleNewMessage = async (message: Message) => {
    const conversationId = currentConversationId ?? undefined

    // Update message with conversation_id when available
    message.conversation_id = conversationId

    setMessages(prev => [...prev, message])
    
    // Update message count in conversations list
    setConversations(prev => prev.map(c => 
      c.id === conversationId 
        ? { ...c, message_count: c.message_count + 1, updated_at: new Date().toISOString() } 
        : c
    ))
    
    // Auto-rename conversation on first user message
    if (isFirstMessage && message.role === 'user' && conversationId) {
      setIsFirstMessage(false)
      const title = message.content.slice(0, 50)
      try {
        await updateConversationTitle(conversationId, title)
        // Update in conversations list
        setConversations(prev => prev.map(c => 
          c.id === conversationId ? { ...c, title } : c
        ))
      } catch (error) {
        console.error('Error auto-renaming conversation:', error)
      }
    }
    
    // Return the conversation ID so ChatArea can use it
    return conversationId
  }

  const handleConversationReady = async (conversationId: string, firstUserMessage: string) => {
    if (!conversationId) return

    setCurrentConversationId(conversationId)
    setIsFirstMessage(false)
    setMessages(prev => prev.map(msg => (
      msg.conversation_id ? msg : { ...msg, conversation_id: conversationId }
    )))

    try {
      await updateConversationTitle(conversationId, firstUserMessage.slice(0, 50))
    } catch (error) {
      console.error('Error setting first conversation title:', error)
    }

    await loadConversations(1)
  }

  const handleClearChat = async () => {
    setMessages([])
    setCurrentConversationId(null)
    setIsFirstMessage(true)
    setPendingQuestion(null)
    setHasMoreMessages(false)
    showToast('New chat started', 'success')
  }

  const handleDeleteConversation = async (conversationId: string) => {
    try {
      await deleteConversation(conversationId)

      // Remove from list
      setConversations(prev => prev.filter(c => c.id !== conversationId))

      // If it was the current conversation, clear it
      if (conversationId === currentConversationId) {
        setMessages([])
        setCurrentConversationId(null)
      }

      showToast('Conversation deleted', 'success')
    } catch (error) {
      showToast('Failed to delete conversation', 'error')
      console.error('Error deleting conversation:', error)
    }
  }

  const handleUpdateConversationTitle = async (conversationId: string, newTitle: string) => {
    try {
      const updated = await updateConversationTitle(conversationId, newTitle)
      
      // Update in conversations list
      setConversations(prev => prev.map(c => 
        c.id === conversationId ? { ...c, title: updated.title } : c
      ))
      
      showToast('Conversation renamed', 'success')
    } catch (error) {
      showToast('Failed to rename conversation', 'error')
      console.error('Error updating conversation title:', error)
    }
  }

  const handleQuickQuestion = async (question: string) => {
    if (currentConversationId) {
      // If we have a conversation, dispatch the question immediately
      const event = new CustomEvent('quickQuestion', { detail: question })
      window.dispatchEvent(event)
      return
    }

    // No active conversation: clear local state and ask ChatArea to send immediately.
    setMessages([])
    setCurrentConversationId(null)
    setIsFirstMessage(true)
    setPendingQuestion(question)
  }

  return (
    <div className="flex h-screen bg-white">
      <Sidebar
        isOpen={isOpen}
        onToggle={() => setIsOpen(!isOpen)}
        onClearChat={handleClearChat}
        messageCount={messages.length}
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        onUpdateConversationTitle={handleUpdateConversationTitle}
        hasMoreConversations={hasMoreConversations}
        onLoadMoreConversations={loadMoreConversations}
        isLoadingConversations={isLoadingConversations}
        onQuickQuestion={handleQuickQuestion}
      />
      <ChatArea
        messages={messages}
        onNewMessage={handleNewMessage}
        onConversationReady={handleConversationReady}
        onUpdateMessage={(id, updates) => {
          setMessages(prev => prev.map(msg =>
            msg.id === id ? { ...msg, ...updates } : msg
          ))
        }}
        onAddMessage={(message) => {
          setMessages(prev => [...prev, message])
          // Update message count in conversations list
          if (message.conversation_id) {
            setConversations(prev => prev.map(c => 
              c.id === message.conversation_id 
                ? { ...c, message_count: c.message_count + 1, updated_at: new Date().toISOString() } 
                : c
            ))
          }
        }}
        currentConversationId={currentConversationId}
        hasMoreMessages={hasMoreMessages}
        onLoadMoreMessages={loadMoreMessages}
        isLoadingMore={isLoadingMessages}
        pendingQuestion={pendingQuestion}
        onQuestionProcessed={() => setPendingQuestion(null)}
      />
    </div>
  )
}
