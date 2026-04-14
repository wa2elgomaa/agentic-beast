'use client'

import { OrchestratorResponse } from '@/types'
import SingleResultCard from './SingleResultCard'

interface QueryDocumentsViewProps {
    data: OrchestratorResponse['data']
    metadata: OrchestratorResponse['metadata']
}

export default function QueryDocumentsView({ data, metadata }: QueryDocumentsViewProps) {
    // Check if we have actual results from database
    const hasResults = data.results && Array.isArray(data.results) && data.results.length > 0

    return (
        <div className="mt-4 space-y-4">
            {hasResults && (
                <div className="space-y-4">
                    {(data.results || []).map((result: any, idx: number) => (
                        <SingleResultCard
                            key={result?.beast_uuid || result?.id || result?.content_id || idx}
                            result={result}
                            metadata={metadata}
                        />
                    ))}
                </div>
            )}

            {/* Refined Query / Answer */}
            {data.answer && !hasResults && (
                <div className="rounded-lg border border-gray-200 overflow-hidden">
                    {/* <div className="bg-gray-50 px-4 py-2 flex items-center justify-between border-b border-gray-200">
                        <div className="flex items-center gap-2">
                            <FileCode size={16} className="text-gray-600" />
                            <span className="text-sm font-semibold text-gray-700">
                                {isJsonAnswer ? 'Structured Query' : 'Refined Query'}
                            </span>
                            {metadata.refinement_type && (
                                <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                                    {metadata.refinement_type}
                                </span>
                            )}
                            {metadata.duration_ms && (
                                <span className="text-xs text-gray-500 flex items-center gap-1">
                                    <Clock size={12} />
                                    {metadata.duration_ms}ms
                                </span>
                            )}
                        </div>

                        <button
                            onClick={() => copyToClipboard(data.answer || '')}
                            className="text-xs px-2 py-1 bg-white hover:bg-gray-100 text-gray-700 rounded flex items-center gap-1 transition-colors"
                        >
                            <Copy size={12} />
                            {copied ? 'Copied!' : 'Copy'}
                        </button>
                    </div> */}

                    {/* <div className="p-4 bg-white">
                        {isJsonAnswer ? (
                            <pre className="text-xs font-mono text-gray-800 overflow-x-auto whitespace-pre-wrap">
                                {JSON.stringify(JSON.parse(data.answer), null, 2)}
                            </pre>
                        ) : (
                            <p className="text-sm text-gray-800">{data.answer}</p>
                        )}
                    </div> */}
                </div>
            )}

            {/* Note */}
            {data.note && (
                <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                    <p className="text-xs text-blue-800">
                        ℹ️ {data.note}
                    </p>
                </div>
            )}

            {/* Original Query (if different) */}
            {data.original_query && data.answer !== data.original_query && (
                <details className="text-xs text-gray-600">
                    <summary className="cursor-pointer hover:text-gray-900 font-medium">
                        Original Query
                    </summary>
                    <p className="mt-2 pl-4 border-l-2 border-gray-300">
                        {data.original_query}
                    </p>
                </details>
            )}
        </div>
    )
}
