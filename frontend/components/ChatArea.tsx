'use client'

import { useEffect, useRef, useState } from 'react'
import { Aggregation, ContentResult, Message, OrchestratorResponse, QuerySuggestion } from '@/types'
import ChatMessage from './ChatMessage'
import MessageInput from './MessageInput'
import WelcomeScreen from './WelcomeScreen'
import { queryContent, chat } from '@/lib/api'

interface ChatAreaProps {
  messages: Message[]
  onNewMessage: (message: Message) => Promise<string | undefined>
  onConversationReady?: (conversationId: string, firstUserMessage: string) => Promise<void> | void
  onUpdateMessage: (id: string, updates: Partial<Message>) => void
  onAddMessage: (message: Message) => void
  currentConversationId: string | null
  hasMoreMessages: boolean
  onLoadMoreMessages: () => void
  isLoadingMore: boolean
  pendingQuestion?: string | null
  onQuestionProcessed?: () => void
}

export default function ChatArea({
  messages,
  onNewMessage,
  onConversationReady,
  onUpdateMessage,
  onAddMessage,
  currentConversationId,
  hasMoreMessages,
  onLoadMoreMessages,
  isLoadingMore,
  pendingQuestion,
  onQuestionProcessed
}: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [isLoading, setIsLoading] = useState(false)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Handle pending quick question
  useEffect(() => {
    if (pendingQuestion && !isLoading) {
      handleSendMessage(pendingQuestion)
      onQuestionProcessed?.()
    }
  }, [pendingQuestion, currentConversationId, isLoading])

  useEffect(() => {
    const handleQuickQuestion = (event: Event) => {
      const customEvent = event as CustomEvent<string>
      handleSendMessage(customEvent.detail)
    }

    window.addEventListener('quickQuestion', handleQuickQuestion)
    return () => window.removeEventListener('quickQuestion', handleQuickQuestion)
  }, [currentConversationId])  // Add dependency to update when conversation changes

  const handleSendMessage = async (content: string) => {
    if (!content.trim() || isLoading) return

    // Add user message and get the conversation ID
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    }
    const conversationId = await onNewMessage(userMessage)

    // Add loading assistant message directly with the conversation ID
    const assistantMessageId = (Date.now() + 1).toString()
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
      conversation_id: conversationId,
    }
    // Add assistant message directly without creating a conversation
    onAddMessage(assistantMessage)

    setIsLoading(true)

    try {
      // Use new orchestrator API with conversation ID
      const response: OrchestratorResponse = await chat(
        content,
        conversationId,
        true,  // include context
        2      // context window (last 2 messages)
      )

      const resolvedConversationId = response.data.conversation_id || conversationId
      if (!conversationId && resolvedConversationId) {
        await onConversationReady?.(resolvedConversationId, content)
      }

      if (!response.success) {
        // Handle error response
        onUpdateMessage(assistantMessageId, {
          content: `Error: ${response.data.error || 'Operation failed'}`,
          isLoading: false,
        })
        return
      }

      // Generate content based on operation type
      let messageContent = ''

      switch (response.operation) {
        case 'suggest_tags_for_article_id':
        case 'suggest_tags_for_article_body':
          const tagCount = response.data.results?.length || 0
          messageContent = `Found ${tagCount} relevant tags${response.data.article_id ? ` for article ${response.data.article_id}` : ''}.`
          break

        case 'query_documents':
          messageContent = response.data.answer || response.data.refined_query || response.data.note || 'Query processed successfully.'
          break

        default:
          messageContent = response.data.note || 'Operation completed successfully.'
      }

      // Update assistant message with operation data
      onUpdateMessage(assistantMessageId, {
        content: messageContent,
        operation: response.operation,
        operationData: response.data,
        operationMetadata: response.metadata,
        // Expose chart/code interpreter output via typed metadata field
        metadata: response.metadata.chart_b64 || response.metadata.code_output ? {
          chart_b64: response.metadata.chart_b64,
          code_output: response.metadata.code_output,
          generated_sql: response.metadata.generated_sql,
        } : undefined,
        conversation_id: resolvedConversationId,
        isLoading: false,
      })
    } catch (error) {
      onUpdateMessage(assistantMessageId, {
        content: `Error: ${error instanceof Error ? error.message : 'Unknown error occurred'}`,
        isLoading: false,
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleSuggestionClick = async (suggestion: QuerySuggestion) => {
    if (isLoading || !currentConversationId) return

    // Add user message with the suggestion question
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: suggestion.question,
      timestamp: new Date(),
      conversation_id: currentConversationId,
    }
    await onNewMessage(userMessage)

    // Add assistant message with instant results (no AI call)
    const assistantMessageId = (Date.now() + 1).toString()
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
      conversation_id: currentConversationId,
    }
    onAddMessage(assistantMessage)

    setIsLoading(true)

    try {
      // Execute the pre-generated SQL directly using chat
      const data: OrchestratorResponse = await chat(
        suggestion.question,
        currentConversationId,
        false,  // No need for context since SQL is pre-generated
        2,
        suggestion.sql  // Pass pre-generated SQL
      )

      if (!data.success) {
        onUpdateMessage(assistantMessageId, {
          content: `Error: ${data.data.error || 'Operation failed'}`,
          isLoading: false,
        })
        return
      }

      const messageContent = data.data.answer || 'Query processed successfully.'

      onUpdateMessage(assistantMessageId, {
        content: messageContent,
        operation: data.operation,
        operationData: data.data,
        operationMetadata: data.metadata,
        metadata: data.metadata.chart_b64 || data.metadata.code_output ? {
          chart_b64: data.metadata.chart_b64,
          code_output: data.metadata.code_output,
          generated_sql: data.metadata.generated_sql,
        } : undefined,
        isLoading: false,
      })
    } catch (error) {
      onUpdateMessage(assistantMessageId, {
        content: `Error: ${error instanceof Error ? error.message : 'Unknown error occurred'}`,
        isLoading: false,
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex-1 flex flex-col h-screen">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <WelcomeScreen onSendMessage={handleSendMessage} />
        ) : (
          <div className="max-w-4xl mx-auto px-4 py-8">
            {/* Load More Messages Button */}
            {hasMoreMessages && (
              <div className="flex justify-center mb-4">
                <button
                  onClick={onLoadMoreMessages}
                  disabled={isLoadingMore}
                  className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                >
                  {isLoadingMore ? 'Loading...' : 'Load More Messages'}
                </button>
              </div>
            )}

            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                onSelectSuggestion={handleSuggestionClick}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input Area */}
      <MessageInput onSendMessage={handleSendMessage} isLoading={isLoading} />
    </div>
  )
}
