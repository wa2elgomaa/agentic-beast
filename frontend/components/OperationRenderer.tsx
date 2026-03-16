'use client'

import { OperationType, OrchestratorResponse } from '@/types'
import TagSuggestionsView from './TagSuggestionsView'
import QueryDocumentsView from './QueryDocumentsView'

interface OperationRendererProps {
  operation: OperationType
  data: OrchestratorResponse['data']
  metadata: OrchestratorResponse['metadata']
}

export default function OperationRenderer({ operation, data, metadata }: OperationRendererProps) {
  switch (operation) {
    case 'suggest_tags_for_article_id':
    case 'suggest_tags_for_article_body':
      return <TagSuggestionsView data={data} metadata={metadata} />
    
    case 'query_documents':
      return <QueryDocumentsView data={data} metadata={metadata} />
    
    case 'cache_get':
    case 'cache_put':
    case 'log_analytics':
      // These operations typically don't need visual representation
      return null
    
    default:
      return (
        <div className="text-xs text-gray-500 mt-2 p-3 bg-gray-50 rounded-lg">
          Operation: {operation}
        </div>
      )
  }
}
