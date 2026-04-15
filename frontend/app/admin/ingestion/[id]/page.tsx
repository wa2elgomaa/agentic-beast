'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { IngestionTask, IngestionTaskRun, TaskSchemaMapping, PreviewEmail } from '@/types'
import {
    cancelIngestionTaskRun,
    getGmailTaskAuthUrl,
    getIngestionTask,
    getIngestionTaskRuns,
    getTaskSchemaMapping,
    triggerIngestionTaskRun,
    previewEmailsForTask,
    runTaskWithSelections,
} from '@/lib/api'
import SchemaMapper from '@/components/admin/SchemaMapper'
import TaskRunHistory from '@/components/admin/TaskRunHistory'
import TaskSettingsForm from '@/components/admin/TaskSettingsForm'
import GmailCredentialStatus from '@/components/admin/GmailCredentialStatus'
import { EmailSelectionModal } from '@/components/admin/ingestion/EmailSelectionModal'
import { AlertCircle, Link as LinkIcon, Play, Settings, Lock } from 'lucide-react'
import Link from 'next/link'

export default function TaskDetailPage() {
    const params = useParams()
    const router = useRouter()
    const taskId = params.id as string

    const [task, setTask] = useState<IngestionTask | null>(null)
    const [schemaMapping, setSchemaMapping] = useState<TaskSchemaMapping | null>(null)
    const [runs, setRuns] = useState<IngestionTaskRun[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [isRunning, setIsRunning] = useState(false)
    const [cancelingRunId, setCancelingRunId] = useState<string | null>(null)
    const [isLinkingGmail, setIsLinkingGmail] = useState(false)
    const [activeTab, setActiveTab] = useState<'schema' | 'runs' | 'settings' | 'gmail-credentials' | 'failed-emails'>('schema')
    const [showPendingRunsModal, setShowPendingRunsModal] = useState(false)
    const [showEmailSelection, setShowEmailSelection] = useState(false)
    const [emailsForSelection, setEmailsForSelection] = useState<PreviewEmail[]>([])
    const [isLoadingEmails, setIsLoadingEmails] = useState(false)
    const [emailLoadError, setEmailLoadError] = useState<string | null>(null)
    const [previewPage, setPreviewPage] = useState(1)
    const [previewLimit, setPreviewLimit] = useState(10)
    const [previewCurrentToken, setPreviewCurrentToken] = useState<string | null>(null)
    const [previewNextToken, setPreviewNextToken] = useState<string | null>(null)
    const [previewTokenStack, setPreviewTokenStack] = useState<Array<string | null>>([])

    useEffect(() => {
        loadData()
    }, [taskId])

    const loadData = async () => {
        try {
            setIsLoading(true)
            setError(null)

            const [taskData, mappingData, runsData] = await Promise.all([
                getIngestionTask(taskId),
                getTaskSchemaMapping(taskId),
                getIngestionTaskRuns(taskId)
            ])

            setTask(taskData)
            setSchemaMapping(mappingData)
            setRuns(runsData || [])
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load task details')
        } finally {
            setIsLoading(false)
        }
    }

    const runTaskNow = async () => {
        try {
            setIsRunning(true)
            setShowPendingRunsModal(false)

            // For Gmail tasks, show email selection instead of running immediately
            if (task?.adaptor_type === 'gmail') {
                setIsLoadingEmails(true)
                setEmailLoadError(null)
                try {
                    const previewSize = (task?.adaptor_config as any)?.preview_page_size || 10
                    const result = await previewEmailsForTask(taskId, previewSize, null)
                    setPreviewLimit(previewSize)
                    setPreviewPage(1)
                    setPreviewCurrentToken(result.current_page_token ?? null)
                    setPreviewNextToken(result.next_page_token ?? null)
                    setPreviewTokenStack([])
                    setEmailsForSelection(result.emails)
                    setShowEmailSelection(true)
                } catch (err) {
                    setEmailLoadError(err instanceof Error ? err.message : 'Failed to load emails')
                }
                setIsLoadingEmails(false)
            } else {
                // For non-Gmail tasks, use existing flow
                await triggerIngestionTaskRun(taskId)
                // Reload runs
                setTimeout(() => loadData(), 1000)
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to trigger task')
        } finally {
            setIsRunning(false)
        }
    }

    const handlePreviewNextPage = async () => {
        if (!previewNextToken) return
        try {
            setIsLoadingEmails(true)
            setEmailLoadError(null)
            const result = await previewEmailsForTask(taskId, previewLimit, previewNextToken)
            setPreviewTokenStack((prev) => [previewCurrentToken, ...prev])
            setPreviewCurrentToken(result.current_page_token ?? null)
            setPreviewNextToken(result.next_page_token ?? null)
            setPreviewPage((p) => p + 1)
            setEmailsForSelection(result.emails)
        } catch (err) {
            setEmailLoadError(err instanceof Error ? err.message : 'Failed to load next page')
        } finally {
            setIsLoadingEmails(false)
        }
    }

    const handlePreviewPrevPage = async () => {
        if (previewTokenStack.length === 0) return
        const prevToken = previewTokenStack[0]
        try {
            setIsLoadingEmails(true)
            setEmailLoadError(null)
            const result = await previewEmailsForTask(taskId, previewLimit, prevToken)
            setPreviewTokenStack((prev) => prev.slice(1))
            setPreviewCurrentToken(result.current_page_token ?? null)
            setPreviewNextToken(result.next_page_token ?? null)
            setPreviewPage((p) => Math.max(1, p - 1))
            setEmailsForSelection(result.emails)
        } catch (err) {
            setEmailLoadError(err instanceof Error ? err.message : 'Failed to load previous page')
        } finally {
            setIsLoadingEmails(false)
        }
    }

    const handleEmailSelectionConfirm = async (selectedIds: string[]) => {
        try {
            setIsRunning(true)
            setShowEmailSelection(false)
            await runTaskWithSelections(taskId, selectedIds)
            // Reload runs
            setTimeout(() => {
                loadData()
                setActiveTab('runs')
            }, 1000)
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start task with selected emails')
        } finally {
            setIsRunning(false)
        }
    }

    const handleRunTask = async () => {
        const activeRuns = runs.filter((run) => run.status === 'pending' || run.status === 'running')
        if (activeRuns.length > 0) {
            setShowPendingRunsModal(true)
            return
        }

        await runTaskNow()
    }

    const handleCancelRun = async (runId: string) => {
        try {
            setCancelingRunId(runId)
            setError(null)
            await cancelIngestionTaskRun(taskId, runId)
            await loadData()
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to stop run')
        } finally {
            setCancelingRunId(null)
        }
    }

    const handleConnectGmail = async () => {
        try {
            setIsLinkingGmail(true)
            setError(null)
            const redirectUri = `${window.location.origin}/admin/ingestion/gmail-callback`
            const result = await getGmailTaskAuthUrl(taskId, { redirect_uri: redirectUri })
            window.location.href = result.auth_url
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start Gmail authorization')
            setIsLinkingGmail(false)
        }
    }

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="text-gray-500 dark:text-gray-400">Loading task details...</div>
            </div>
        )
    }

    if (!task) {
        return (
            <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Task not found</h3>
                <Link href="/admin/ingestion" className="text-blue-600 hover:text-blue-700">
                    Back to tasks
                </Link>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <Link href="/admin/ingestion" className="text-blue-600 hover:text-blue-700">
                All tasks
            </Link>
            {/* Header */}
            <div className="flex items-center justify-between bg-white dark:bg-gray-800 p-6 rounded-lg border border-gray-200 dark:border-gray-700">
                <div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{task.name}</h2>
                    <div className="flex items-center gap-3 mt-2">
                        <span className="px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-xs font-medium capitalize">
                            {task.adaptor_type}
                        </span>
                        <span className={`px-3 py-1 rounded-full text-xs font-medium capitalize ${task.status === 'active'
                                ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
                                : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
                            }`}>
                            {task.status}
                        </span>
                        {task.adaptor_type === 'gmail' && task.adaptor_config?.gmail_account_email && (
                            <span className="px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 dark:bg-emerald-900 text-emerald-800 dark:text-emerald-200">
                                Linked: {task.adaptor_config.gmail_account_email}
                            </span>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {task.adaptor_type === 'gmail' && (
                        <button
                            onClick={handleConnectGmail}
                            disabled={isLinkingGmail}
                            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg transition-colors font-medium"
                        >
                            <LinkIcon size={16} />
                            {isLinkingGmail ? 'Linking...' : 'Connect Gmail'}
                        </button>
                    )}
                    <button
                        onClick={handleRunTask}
                        disabled={isRunning}
                        className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 text-white rounded-lg transition-colors font-medium"
                    >
                        <Play size={16} />
                        {isRunning ? 'Running...' : 'Run Task'}
                    </button>
                </div>
            </div>

            {/* Error Alert */}
            {error && (
                <div className="flex items-center gap-3 px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900 rounded-lg">
                    <AlertCircle size={18} className="text-red-600 dark:text-red-400 flex-shrink-0" />
                    <p className="text-red-800 dark:text-red-200">{error}</p>
                </div>
            )}

            {showPendingRunsModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
                    <div className="w-full max-w-md rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 shadow-2xl">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Active Runs Detected</h3>
                        <p className="mt-3 text-sm text-gray-600 dark:text-gray-300">
                            This task currently has {runs.filter((run) => run.status === 'pending' || run.status === 'running').length} active run(s). Running it again will queue another run.
                        </p>
                        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                            You can stop those runs from the Run History tab, or ignore them and continue.
                        </p>
                        <div className="mt-6 flex justify-end gap-3">
                            <button
                                onClick={() => setShowPendingRunsModal(false)}
                                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={runTaskNow}
                                disabled={isRunning}
                                className="px-4 py-2 rounded-lg bg-orange-600 text-white hover:bg-orange-700 disabled:opacity-50"
                            >
                                {isRunning ? 'Running...' : 'Ignore & Run'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Email Selection Modal for Gmail tasks */}
            <EmailSelectionModal
                isOpen={showEmailSelection}
                isLoading={isLoadingEmails}
                emails={emailsForSelection}
                currentPage={previewPage}
                hasPrevPage={previewTokenStack.length > 0}
                hasNextPage={Boolean(previewNextToken)}
                error={emailLoadError || undefined}
                onClose={() => {
                    setShowEmailSelection(false)
                    setEmailsForSelection([])
                    setEmailLoadError(null)
                    setPreviewPage(1)
                    setPreviewCurrentToken(null)
                    setPreviewNextToken(null)
                    setPreviewTokenStack([])
                }}
                onSelect={handleEmailSelectionConfirm}
                onPrevPage={handlePreviewPrevPage}
                onNextPage={handlePreviewNextPage}
                taskAdaptorType={task?.adaptor_type}
            />

            {/* Tabs */}
            <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
                <button
                    onClick={() => setActiveTab('schema')}
                    className={`px-4 py-3 font-medium border-b-2 transition-colors ${activeTab === 'schema'
                            ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                            : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-300'
                        }`}
                >
                    Schema Mapping
                </button>
                <button
                    onClick={() => setActiveTab('runs')}
                    className={`px-4 py-3 font-medium border-b-2 transition-colors ${activeTab === 'runs'
                            ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                            : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-300'
                        }`}
                >
                    Run History
                </button>
                <button
                    onClick={() => setActiveTab('settings')}
                    className={`flex items-center gap-1.5 px-4 py-3 font-medium border-b-2 transition-colors ${activeTab === 'settings'
                            ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                            : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-300'
                        }`}
                >
                    <Settings size={14} />
                    Settings
                </button>
                {task?.adaptor_type === 'gmail' && (
                    <button
                        onClick={() => setActiveTab('gmail-credentials')}
                        className={`flex items-center gap-1.5 px-4 py-3 font-medium border-b-2 transition-colors ${activeTab === 'gmail-credentials'
                            ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                            : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-300'
                        }`}
                    >
                        <Lock size={14} />
                        Gmail Credentials
                    </button>
                )}
            </div>

            {/* Content */}
            {activeTab === 'schema' ? (
                <SchemaMapper task={task} initialMapping={schemaMapping} onUpdated={loadData} />
            ) : activeTab === 'runs' ? (
                <TaskRunHistory runs={runs} onRefresh={loadData} onCancelRun={handleCancelRun} cancelingRunId={cancelingRunId} />
            ) : activeTab === 'settings' ? (
                <TaskSettingsForm task={task} onUpdated={loadData} />
            ) : activeTab === 'gmail-credentials' ? (
                <GmailCredentialStatus taskId={taskId} />
            ) : null}
        </div>
    )
}
