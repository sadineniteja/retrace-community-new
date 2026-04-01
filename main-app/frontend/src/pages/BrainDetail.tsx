import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Loader2, ArrowLeft, Play, Pause, Trash2, Settings, Zap,
  Activity, ListChecks, Eye, Link2, BarChart3, Send,
  CheckCircle2, XCircle, Clock, AlertTriangle, Star,
  Monitor, Wifi, WifiOff, RotateCw,
  Globe, MousePointer,
} from 'lucide-react'
import { brainApi } from '@/utils/api'
import type { BrainTask, BrainActivity as BrainActivityType, PipelineItem, ConnectedAccount, BrainMonitor, BrainStats } from '@/types/brain'
import { BRAIN_ICONS, TASK_STATUS_COLORS } from '@/types/brain'

type Tab = 'activity' | 'tasks' | 'pipeline' | 'monitors' | 'accounts' | 'settings' | 'live'

export default function BrainDetail() {
  const { brainId } = useParams<{ brainId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<Tab>('activity')
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [newTaskInstructions, setNewTaskInstructions] = useState('')
  const [showNewTask, setShowNewTask] = useState(false)

  const { data: stats, isLoading } = useQuery<BrainStats>({
    queryKey: ['brain-stats', brainId],
    queryFn: () => brainApi.brainStats(brainId!),
    enabled: !!brainId,
    refetchInterval: 15000,
  })

  const brain = stats?.brain

  const { data: activities } = useQuery<BrainActivityType[]>({
    queryKey: ['brain-activity', brainId],
    queryFn: () => brainApi.listActivity(brainId!),
    enabled: !!brainId && activeTab === 'activity',
  })

  const { data: tasks } = useQuery<BrainTask[]>({
    queryKey: ['brain-tasks', brainId],
    queryFn: () => brainApi.listTasks(brainId!),
    enabled: !!brainId && activeTab === 'tasks',
  })

  const { data: pipeline } = useQuery<PipelineItem[]>({
    queryKey: ['brain-pipeline', brainId],
    queryFn: () => brainApi.listPipeline(brainId!),
    enabled: !!brainId && activeTab === 'pipeline',
  })

  const { data: monitors } = useQuery<BrainMonitor[]>({
    queryKey: ['brain-monitors', brainId],
    queryFn: () => brainApi.listMonitors(brainId!),
    enabled: !!brainId && activeTab === 'monitors',
  })

  const { data: accounts } = useQuery<ConnectedAccount[]>({
    queryKey: ['brain-accounts', brainId],
    queryFn: () => brainApi.listAccounts(brainId!),
    enabled: !!brainId && activeTab === 'accounts',
  })

  const activateMutation = useMutation({
    mutationFn: () => brainApi.activateBrain(brainId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['brain-stats', brainId] }),
  })

  const pauseMutation = useMutation({
    mutationFn: () => brainApi.pauseBrain(brainId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['brain-stats', brainId] }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => brainApi.deleteBrain(brainId!),
    onSuccess: () => navigate('/brains'),
  })

  const createTaskMutation = useMutation({
    mutationFn: () => brainApi.createTask(brainId!, { title: newTaskTitle, instructions: newTaskInstructions }),
    onSuccess: () => {
      setShowNewTask(false)
      setNewTaskTitle('')
      setNewTaskInstructions('')
      queryClient.invalidateQueries({ queryKey: ['brain-tasks', brainId] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh] gap-3 text-rt-text-muted">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    )
  }

  if (!brain) {
    return (
      <div className="px-12 pt-8">
        <p className="text-rt-text-muted">Brain not found.</p>
      </div>
    )
  }

  const tabs: { key: Tab; label: string; icon: React.ReactNode; count?: number }[] = [
    { key: 'activity', label: 'Activity', icon: <Activity className="w-4 h-4" />, count: stats?.total_activities },
    { key: 'tasks', label: 'Tasks', icon: <ListChecks className="w-4 h-4" />, count: stats?.tasks.total },
    { key: 'live', label: 'Live View', icon: <Monitor className="w-4 h-4" /> },
    { key: 'pipeline', label: 'Pipeline', icon: <BarChart3 className="w-4 h-4" />, count: stats?.pipeline.total },
    { key: 'monitors', label: 'Monitors', icon: <Eye className="w-4 h-4" />, count: stats?.active_monitors },
    { key: 'accounts', label: 'Accounts', icon: <Link2 className="w-4 h-4" />, count: stats?.connected_accounts },
    { key: 'settings', label: 'Settings', icon: <Settings className="w-4 h-4" /> },
  ]

  return (
    <div className="px-12 pb-20 pt-8">
      {/* Header */}
      <div className="flex items-center gap-2 mb-6">
        <Link to="/brains" className="text-rt-text-muted hover:text-rt-primary transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <span className="text-rt-text-muted text-sm">/ Brains /</span>
      </div>

      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start justify-between mb-8"
      >
        <div className="flex items-center gap-4">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center text-3xl"
            style={{ backgroundColor: (brain.color || '#6366f1') + '20' }}
          >
            {BRAIN_ICONS[brain.brain_type] || '🧠'}
          </div>
          <div>
            <h1 className="text-3xl font-headline font-bold">{brain.name}</h1>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-sm text-rt-text-muted capitalize">{brain.brain_type.replace('_', ' ')}</span>
              <span className="text-rt-border">·</span>
              <span className={`text-sm font-medium capitalize ${
                brain.status === 'active' ? 'text-green-500' : brain.status === 'paused' ? 'text-yellow-500' : 'text-gray-400'
              }`}>
                {brain.status === 'active' && <span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1.5 animate-pulse" />}
                {brain.status}
              </span>
              <span className="text-rt-border">·</span>
              <span className="text-xs text-rt-text-muted capitalize px-2 py-0.5 bg-rt-bg-lighter rounded-full">
                {brain.autonomy_level.replace('_', ' ')}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {brain.status === 'active' ? (
            <button
              onClick={() => pauseMutation.mutate()}
              disabled={pauseMutation.isPending}
              className="px-4 py-2 rounded-xl border border-yellow-200 text-yellow-600 hover:bg-yellow-50 transition-colors flex items-center gap-2 text-sm"
            >
              <Pause className="w-4 h-4" /> Pause
            </button>
          ) : brain.setup_status === 'ready' ? (
            <button
              onClick={() => activateMutation.mutate()}
              disabled={activateMutation.isPending}
              className="px-4 py-2 rounded-xl bg-green-500 text-white hover:bg-green-600 transition-colors flex items-center gap-2 text-sm"
            >
              <Play className="w-4 h-4" /> Activate
            </button>
          ) : (
            <Link
              to={`/brains/${brainId}/setup`}
              className="px-4 py-2 rounded-xl bg-rt-primary text-white hover:opacity-90 transition-opacity flex items-center gap-2 text-sm"
            >
              Complete Setup
            </Link>
          )}
          <button
            onClick={() => {
              if (confirm('Delete this brain and all its data?')) deleteMutation.mutate()
            }}
            disabled={deleteMutation.isPending}
            className="px-3 py-2 rounded-xl border border-rt-border text-rt-text-muted hover:text-red-500 hover:border-red-200 transition-colors"
            title="Delete Brain"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </motion.div>

      {/* Quick Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <MiniStat label="Tasks Today" value={brain.tasks_today} />
        <MiniStat label="Cost Today" value={`$${(brain.cost_today_cents / 100).toFixed(2)}`} />
        <MiniStat label="Pipeline Items" value={stats?.pipeline.total || 0} />
        <MiniStat label="Connected Accounts" value={stats?.connected_accounts || 0} />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-rt-border overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === tab.key
                ? 'border-rt-primary text-rt-primary'
                : 'border-transparent text-rt-text-muted hover:text-rt-text'
            }`}
          >
            {tab.icon} {tab.label}
            {tab.count != null && tab.count > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-rt-bg-lighter">{tab.count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'activity' && (
        <div className="space-y-3">
          {activities?.length === 0 && <EmptyTab message="No activity yet. Activate your Brain to start." />}
          {activities?.map((a) => (
            <div key={a.activity_id} className="flex items-start gap-3 p-4 rounded-xl border border-rt-border bg-rt-surface">
              <SeverityIcon severity={a.severity} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{a.title}</p>
                {a.description && <p className="text-xs text-rt-text-muted mt-0.5">{a.description}</p>}
              </div>
              {a.created_at && (
                <span className="text-[10px] text-rt-text-muted whitespace-nowrap">
                  {new Date(a.created_at).toLocaleString()}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {activeTab === 'tasks' && (
        <div>
          {brain.status === 'active' && (
            <div className="mb-4">
              {showNewTask ? (
                <div className="p-4 rounded-xl border border-rt-border bg-rt-surface space-y-3">
                  <input
                    value={newTaskTitle}
                    onChange={(e) => setNewTaskTitle(e.target.value)}
                    placeholder="Task title..."
                    className="w-full px-3 py-2 rounded-lg bg-rt-bg border border-rt-border text-sm"
                  />
                  <textarea
                    value={newTaskInstructions}
                    onChange={(e) => setNewTaskInstructions(e.target.value)}
                    placeholder="Instructions..."
                    rows={3}
                    className="w-full px-3 py-2 rounded-lg bg-rt-bg border border-rt-border text-sm resize-none"
                  />
                  <div className="flex gap-2 justify-end">
                    <button onClick={() => setShowNewTask(false)} className="px-3 py-1.5 text-sm text-rt-text-muted">Cancel</button>
                    <button
                      onClick={() => createTaskMutation.mutate()}
                      disabled={!newTaskTitle.trim() || !newTaskInstructions.trim() || createTaskMutation.isPending}
                      className="px-4 py-1.5 text-sm bg-rt-primary text-white rounded-lg disabled:opacity-50 flex items-center gap-1"
                    >
                      {createTaskMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                      Create Task
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowNewTask(true)}
                  className="text-sm text-rt-primary hover:underline flex items-center gap-1"
                >
                  <Zap className="w-3 h-3" /> Create a manual task
                </button>
              )}
            </div>
          )}
          <div className="space-y-2">
            {tasks?.length === 0 && <EmptyTab message="No tasks yet." />}
            {tasks?.map((t) => (
              <div key={t.task_id} className="flex items-center gap-3 p-4 rounded-xl border border-rt-border bg-rt-surface">
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${TASK_STATUS_COLORS[t.status] || ''}`}>
                  {t.status}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{t.title}</p>
                  {t.result_summary && <p className="text-xs text-rt-text-muted truncate">{t.result_summary}</p>}
                  {t.error && <p className="text-xs text-red-500 truncate">{t.error}</p>}
                </div>
                <span className="text-[10px] text-rt-text-muted capitalize">{t.trigger}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Live View Tab ── */}
      {activeTab === 'live' && brainId && (
        <BrainLiveView brainId={brainId} />
      )}

      {activeTab === 'pipeline' && (
        <div className="space-y-2">
          {pipeline?.length === 0 && <EmptyTab message="Pipeline is empty. Your Brain will populate it as it works." />}
          {pipeline?.map((item) => (
            <div key={item.item_id} className="flex items-center gap-3 p-4 rounded-xl border border-rt-border bg-rt-surface">
              {item.is_starred && <Star className="w-4 h-4 text-yellow-400 fill-yellow-400 flex-shrink-0" />}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{item.title}</p>
                <p className="text-xs text-rt-text-muted">{item.pipeline_type}</p>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-rt-bg-lighter text-rt-text-muted font-medium capitalize">
                {item.stage}
              </span>
              {item.external_url && (
                <a href={item.external_url} target="_blank" rel="noopener" className="text-rt-primary hover:underline text-xs">
                  Open
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      {activeTab === 'monitors' && (
        <div className="space-y-2">
          {monitors?.length === 0 && <EmptyTab message="No monitors configured." />}
          {monitors?.map((m) => (
            <div key={m.monitor_id} className="flex items-center gap-3 p-4 rounded-xl border border-rt-border bg-rt-surface">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${m.is_active ? 'bg-green-500' : 'bg-gray-300'}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{m.name}</p>
                <p className="text-xs text-rt-text-muted">{m.monitor_type} · every {m.check_interval_minutes}min · {m.trigger_count} triggers</p>
              </div>
              <span className="text-xs text-rt-text-muted capitalize">{m.trigger_action}</span>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'accounts' && brainId && (
        <BrainAccountsTab
          brainId={brainId}
          accounts={accounts || []}
          onAccountChange={() => queryClient.invalidateQueries({ queryKey: ['brain-accounts', brainId] })}
          onSwitchToLive={() => setActiveTab('live')}
        />
      )}

      {activeTab === 'settings' && (
        <div className="max-w-lg space-y-6">
          <div>
            <label className="text-sm font-medium block mb-2">Autonomy Level</label>
            <select
              value={brain.autonomy_level}
              onChange={async (e) => {
                await brainApi.updateBrain(brainId!, { autonomy_level: e.target.value })
                queryClient.invalidateQueries({ queryKey: ['brain-stats', brainId] })
              }}
              className="w-full px-4 py-2.5 rounded-xl bg-rt-bg border border-rt-border text-sm"
            >
              <option value="supervised">Supervised — approve every action</option>
              <option value="semi_auto">Semi-Auto — approve important actions</option>
              <option value="full_auto">Full Auto — Brain acts independently</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium block mb-2">Max Daily Tasks</label>
            <input
              type="number"
              defaultValue={brain.max_daily_tasks}
              onBlur={async (e) => {
                await brainApi.updateBrain(brainId!, { max_daily_tasks: parseInt(e.target.value) })
                queryClient.invalidateQueries({ queryKey: ['brain-stats', brainId] })
              }}
              className="w-full px-4 py-2.5 rounded-xl bg-rt-bg border border-rt-border text-sm"
            />
          </div>
          <div>
            <label className="text-sm font-medium block mb-2">Max Daily Cost (cents)</label>
            <input
              type="number"
              defaultValue={brain.max_daily_cost_cents}
              onBlur={async (e) => {
                await brainApi.updateBrain(brainId!, { max_daily_cost_cents: parseInt(e.target.value) })
                queryClient.invalidateQueries({ queryKey: ['brain-stats', brainId] })
              }}
              className="w-full px-4 py-2.5 rounded-xl bg-rt-bg border border-rt-border text-sm"
            />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Brain Live View Component ─────────────────────────────────────────

function BrainLiveView({ brainId }: { brainId: string }) {
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [currentUrl, setCurrentUrl] = useState('')
  const [currentTitle, setCurrentTitle] = useState('')
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null)
  const [urlInput, setUrlInput] = useState('')
  // Human intervention alert state
  const [alert, setAlert] = useState<{ type: string; message: string } | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/brain-browser/${brainId}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      setStatusMessage('Connected — launching browser...')
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        switch (msg.type) {
          case 'brain_screenshot':
            setScreenshot(msg.data)
            if (msg.url) {
              setCurrentUrl(msg.url)
              setUrlInput(msg.url)
            }
            if (msg.title) setCurrentTitle(msg.title)
            if (msg.task_id) setCurrentTaskId(msg.task_id)
            if (msg.status) setStatusMessage(msg.status)
            break
          case 'brain_alert':
            // Human intervention needed — captcha, login, block, etc.
            setAlert({ type: msg.alert_type, message: msg.message })
            setStatusMessage(msg.message)
            break
          case 'brain_status':
            setStatusMessage(msg.message || '')
            if (msg.url) setCurrentUrl(msg.url)
            if (msg.task_id) setCurrentTaskId(msg.task_id)
            if (msg.message === 'launching_browser') {
              setStatusMessage('Launching browser...')
            }
            // Clear alert when brain resumes
            if (msg.message?.includes('Resuming') || msg.message?.includes('resolved')) {
              setAlert(null)
            }
            break
          case 'brain_browser_closed':
            setScreenshot(null)
            setStatusMessage('Browser session ended')
            break
          case 'action_result':
            if (msg.result?.url) {
              setCurrentUrl(msg.result.url)
              setUrlInput(msg.result.url)
            }
            break
          case 'pong':
            break
        }
      } catch { /* ignore */ }
    }

    ws.onclose = () => {
      setIsConnected(false)
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => {
      setStatusMessage('Connection error — retrying...')
    }
  }, [brainId])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
      return true
    }
    return false
  }, [])

  const handleImageClick = useCallback((e: React.MouseEvent<HTMLImageElement>) => {
    const img = imgRef.current
    if (!img) return
    const rect = img.getBoundingClientRect()
    const scaleX = img.naturalWidth / rect.width
    const scaleY = img.naturalHeight / rect.height
    const x = Math.round((e.clientX - rect.left) * scaleX)
    const y = Math.round((e.clientY - rect.top) * scaleY)
    send({ type: 'click', x, y })
  }, [send])

  const handleNavigate = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if (!urlInput.trim()) return
    let url = urlInput.trim()
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      if (url.includes('.') && !url.includes(' ')) {
        url = `https://${url}`
      } else {
        url = `https://www.google.com/search?q=${encodeURIComponent(url)}`
      }
    }
    setUrlInput(url)
    send({ type: 'navigate', url })
  }, [urlInput, send])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const direction = e.deltaY > 0 ? 'down' : 'up'
    send({ type: 'scroll', direction, amount: Math.min(Math.abs(e.deltaY), 500) })
  }, [send])

  const handleResume = useCallback(() => {
    send({ type: 'resume' })
    setAlert(null)
    setStatusMessage('Resuming...')
  }, [send])

  return (
    <div className="rounded-2xl border border-rt-border bg-rt-surface overflow-hidden">
      {/* Browser toolbar */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-rt-bg border-b border-rt-border">
        <button
          onClick={() => send({ type: 'navigate', url: 'about:blank' })}
          className="p-1.5 rounded-lg hover:bg-rt-bg-lighter text-rt-text-muted"
          title="Refresh"
        >
          <RotateCw className="w-3.5 h-3.5" />
        </button>

        {/* URL bar */}
        <form onSubmit={handleNavigate} className="flex-1">
          <div className="flex items-center gap-2 bg-rt-bg-lighter rounded-full px-4 py-1.5 focus-within:ring-2 ring-rt-primary/30">
            <Globe className="w-3.5 h-3.5 text-rt-text-muted flex-shrink-0" />
            <input
              type="text"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              placeholder="Brain is browsing..."
              className="flex-1 bg-transparent text-xs focus:outline-none placeholder:text-rt-text-muted/50"
            />
          </div>
        </form>

        {/* Status */}
        <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider">
          {isConnected ? (
            <span className="flex items-center gap-1.5 text-green-500">
              <Wifi className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Live</span>
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-rt-text-muted">
              <WifiOff className="w-3.5 h-3.5" />
            </span>
          )}
        </div>
      </div>

      {/* Task info bar */}
      {currentTaskId && (
        <div className="px-4 py-1.5 bg-blue-50 border-b border-blue-100 text-xs text-blue-700 flex items-center gap-2">
          <Zap className="w-3 h-3" />
          <span>Task running: {currentTaskId.slice(0, 8)}...</span>
        </div>
      )}

      {/* Human intervention alert banner */}
      {alert && (
        <div className={`px-4 py-3 border-b flex items-center gap-3 ${
          alert.type === 'captcha'
            ? 'bg-orange-50 border-orange-200'
            : alert.type === 'login_required'
            ? 'bg-red-50 border-red-200'
            : alert.type === 'blocked'
            ? 'bg-red-50 border-red-200'
            : alert.type === 'verification'
            ? 'bg-yellow-50 border-yellow-200'
            : 'bg-yellow-50 border-yellow-200'
        }`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
            alert.type === 'captcha' ? 'bg-orange-100' :
            alert.type === 'login_required' ? 'bg-red-100' :
            alert.type === 'blocked' ? 'bg-red-100' :
            'bg-yellow-100'
          }`}>
            <AlertTriangle className={`w-4 h-4 ${
              alert.type === 'captcha' ? 'text-orange-600' :
              alert.type === 'login_required' ? 'text-red-600' :
              alert.type === 'blocked' ? 'text-red-600' :
              'text-yellow-600'
            }`} />
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-sm font-semibold ${
              alert.type === 'captcha' ? 'text-orange-800' :
              alert.type === 'login_required' ? 'text-red-800' :
              alert.type === 'blocked' ? 'text-red-800' :
              'text-yellow-800'
            }`}>
              {alert.type === 'captcha' && 'CAPTCHA Detected'}
              {alert.type === 'login_required' && 'Login Required'}
              {alert.type === 'blocked' && 'Account Blocked / Rate Limited'}
              {alert.type === 'verification' && 'Verification Required'}
              {alert.type === 'error' && 'Error Detected'}
            </p>
            <p className="text-xs text-rt-text-muted mt-0.5">{alert.message}</p>
          </div>
          <button
            onClick={handleResume}
            className={`px-4 py-2 rounded-xl text-white text-sm font-semibold flex items-center gap-1.5 hover:opacity-90 transition-opacity flex-shrink-0 ${
              alert.type === 'captcha' ? 'bg-orange-500' :
              alert.type === 'login_required' ? 'bg-red-500' :
              alert.type === 'blocked' ? 'bg-red-500' :
              'bg-yellow-500'
            }`}
          >
            <Play className="w-3.5 h-3.5" /> Resume
          </button>
        </div>
      )}

      {/* Browser viewport — constrained height with scroll */}
      <div className="relative bg-white overflow-hidden" style={{ maxHeight: '520px' }}>
        {screenshot ? (
          <img
            ref={imgRef}
            src={`data:image/jpeg;base64,${screenshot}`}
            alt={currentTitle || 'Brain browser view'}
            className="w-full h-auto cursor-crosshair"
            style={{ maxHeight: '520px', objectFit: 'contain' }}
            onClick={handleImageClick}
            onWheel={handleWheel}
            draggable={false}
          />
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-20 h-20 rounded-2xl bg-rt-primary-fixed/20 flex items-center justify-center mb-6">
              <Monitor className="w-8 h-8 text-rt-primary" />
            </div>
            <h3 className="text-lg font-headline font-bold mb-2">Brain Live View</h3>
            <p className="text-sm text-rt-text-muted max-w-md leading-relaxed mb-4">
              {statusMessage?.includes('launching') || statusMessage?.includes('Launching')
                ? 'Starting up the browser — this takes a few seconds...'
                : statusMessage || 'Watch your Brain work in real-time. The browser is launching automatically.'}
            </p>
            {(!isConnected || (isConnected && !screenshot)) && (
              <div className="flex items-center gap-2 text-xs text-rt-text-muted">
                <Loader2 className="w-3 h-3 animate-spin" />
                {!isConnected ? 'Connecting...' : 'Starting Chromium...'}
              </div>
            )}
          </div>
        )}

        {/* Floating status */}
        {statusMessage && screenshot && (
          <div className="absolute bottom-3 left-3 right-3 flex items-center gap-2 bg-black/70 backdrop-blur-sm rounded-full px-4 py-2 text-xs text-white">
            {statusMessage.includes('...') && <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />}
            {statusMessage.includes('Click') && <MousePointer className="w-3 h-3 flex-shrink-0" />}
            <span className="truncate">{statusMessage}</span>
          </div>
        )}
      </div>

      {/* Page info footer */}
      {currentTitle && currentTitle !== 'about:blank' && (
        <div className="px-4 py-2 bg-rt-bg border-t border-rt-border text-[10px] text-rt-text-muted truncate">
          {currentTitle} — {currentUrl}
        </div>
      )}
    </div>
  )
}

// ── Accounts Tab with Browser Login ───────────────────────────────────

const PROVIDERS = [
  { id: 'linkedin', name: 'LinkedIn', icon: '💼', color: '#0A66C2' },
  { id: 'indeed', name: 'Indeed', icon: '🔍', color: '#2164F3' },
  { id: 'glassdoor', name: 'Glassdoor', icon: '🏢', color: '#0CAA41' },
  { id: 'github', name: 'GitHub', icon: '🐙', color: '#333' },
  { id: 'twitter', name: 'Twitter / X', icon: '🐦', color: '#1DA1F2' },
  { id: 'google', name: 'Google', icon: '📧', color: '#4285F4' },
]

function BrainAccountsTab({
  brainId,
  accounts,
  onAccountChange,
  onSwitchToLive,
}: {
  brainId: string
  accounts: ConnectedAccount[]
  onAccountChange: () => void
  onSwitchToLive: () => void
}) {
  const [loginProvider, setLoginProvider] = useState<string | null>(null)
  const [loginStatus, setLoginStatus] = useState<'idle' | 'opening' | 'waiting' | 'capturing' | 'done' | 'error'>('idle')
  const [loginMessage, setLoginMessage] = useState('')

  const connectedProviders = new Set(accounts.map(a => a.provider.toLowerCase()))

  const startBrowserLogin = async (provider: string) => {
    setLoginProvider(provider)
    setLoginStatus('opening')
    setLoginMessage(`Opening ${provider} login page...`)

    try {
      const result = await brainApi.browserLoginStart(brainId, provider)
      setLoginStatus('waiting')
      setLoginMessage(result.message || `Log into ${provider} via the Live View tab, then click "Save Login" below.`)
    } catch (err: any) {
      setLoginStatus('error')
      setLoginMessage(err?.response?.data?.detail || 'Failed to start browser login')
    }
  }

  const captureLogin = async () => {
    setLoginStatus('capturing')
    setLoginMessage('Capturing session cookies...')

    try {
      const result = await brainApi.browserLoginCapture(brainId)
      setLoginStatus('done')
      setLoginMessage(`${result.provider} connected successfully! (${result.cookies_count} cookies saved)`)
      onAccountChange()
      // Auto-reset after 3 seconds
      setTimeout(() => {
        setLoginProvider(null)
        setLoginStatus('idle')
        setLoginMessage('')
      }, 3000)
    } catch (err: any) {
      setLoginStatus('error')
      setLoginMessage(err?.response?.data?.detail || 'Failed to capture login. Make sure you completed the sign-in.')
    }
  }

  const cancelLogin = () => {
    setLoginProvider(null)
    setLoginStatus('idle')
    setLoginMessage('')
  }

  return (
    <div className="space-y-6">
      {/* Browser login flow */}
      {loginProvider && loginStatus !== 'idle' && (
        <div className={`p-5 rounded-2xl border-2 ${
          loginStatus === 'done' ? 'border-green-200 bg-green-50' :
          loginStatus === 'error' ? 'border-red-200 bg-red-50' :
          'border-blue-200 bg-blue-50'
        }`}>
          <div className="flex items-start gap-4">
            <div className="text-3xl">
              {PROVIDERS.find(p => p.id === loginProvider)?.icon || '🔗'}
            </div>
            <div className="flex-1">
              <h3 className={`text-sm font-bold ${
                loginStatus === 'done' ? 'text-green-800' :
                loginStatus === 'error' ? 'text-red-800' :
                'text-blue-800'
              }`}>
                {loginStatus === 'opening' && `Opening ${loginProvider}...`}
                {loginStatus === 'waiting' && `Log into ${loginProvider}`}
                {loginStatus === 'capturing' && 'Saving login...'}
                {loginStatus === 'done' && 'Connected!'}
                {loginStatus === 'error' && 'Connection Failed'}
              </h3>
              <p className={`text-xs mt-1 ${
                loginStatus === 'done' ? 'text-green-700' :
                loginStatus === 'error' ? 'text-red-700' :
                'text-blue-700'
              }`}>
                {loginMessage}
              </p>

              <div className="flex gap-2 mt-3">
                {loginStatus === 'waiting' && (
                  <>
                    <button
                      onClick={onSwitchToLive}
                      className="px-4 py-2 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors flex items-center gap-1.5"
                    >
                      <Monitor className="w-3.5 h-3.5" /> Open Live View
                    </button>
                    <button
                      onClick={captureLogin}
                      className="px-4 py-2 rounded-xl bg-green-600 text-white text-sm font-medium hover:bg-green-700 transition-colors flex items-center gap-1.5"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" /> Save Login
                    </button>
                    <button
                      onClick={cancelLogin}
                      className="px-3 py-2 rounded-xl border border-blue-200 text-blue-600 text-sm hover:bg-blue-100 transition-colors"
                    >
                      Cancel
                    </button>
                  </>
                )}
                {loginStatus === 'error' && (
                  <>
                    <button
                      onClick={() => startBrowserLogin(loginProvider)}
                      className="px-4 py-2 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors"
                    >
                      Try Again
                    </button>
                    <button
                      onClick={cancelLogin}
                      className="px-3 py-2 rounded-xl border border-red-200 text-red-600 text-sm hover:bg-red-100 transition-colors"
                    >
                      Cancel
                    </button>
                  </>
                )}
                {loginStatus === 'opening' || loginStatus === 'capturing' ? (
                  <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                ) : null}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Connected accounts list */}
      {accounts.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-rt-text-muted uppercase tracking-wide font-medium">Connected</p>
          {accounts.map((a) => (
            <div key={a.account_id} className="flex items-center gap-3 p-4 rounded-xl border border-rt-border bg-rt-surface">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${a.status === 'active' ? 'bg-green-500' : 'bg-red-400'}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{a.provider_display_name}</p>
                <p className="text-xs text-rt-text-muted">{a.account_identifier || a.auth_type}</p>
              </div>
              <span className={`text-xs capitalize ${a.status === 'active' ? 'text-green-500' : 'text-red-400'}`}>
                {a.status}
              </span>
              <button
                onClick={async () => {
                  if (confirm(`Disconnect ${a.provider_display_name}?`)) {
                    await brainApi.disconnectAccount(brainId, a.account_id)
                    onAccountChange()
                  }
                }}
                className="p-1.5 rounded-lg text-rt-text-muted hover:text-red-500 hover:bg-red-50 transition-colors"
                title="Disconnect"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Available providers to connect */}
      <div className="space-y-2">
        <p className="text-xs text-rt-text-muted uppercase tracking-wide font-medium">
          {accounts.length > 0 ? 'Add more accounts' : 'Connect an account'}
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {PROVIDERS.map((provider) => {
            const isConnected = connectedProviders.has(provider.id)
            return (
              <button
                key={provider.id}
                onClick={() => !isConnected && startBrowserLogin(provider.id)}
                disabled={isConnected || (loginProvider !== null && loginStatus !== 'idle')}
                className={`flex items-center gap-3 p-4 rounded-xl border-2 transition-all text-left ${
                  isConnected
                    ? 'border-green-200 bg-green-50/50 cursor-default'
                    : 'border-rt-border hover:border-rt-primary/50 hover:shadow-sm cursor-pointer'
                } disabled:opacity-60`}
              >
                <span className="text-2xl">{provider.icon}</span>
                <div className="flex-1">
                  <p className="text-sm font-medium">{provider.name}</p>
                  <p className="text-[10px] text-rt-text-muted">
                    {isConnected ? '✓ Connected' : 'Browser login'}
                  </p>
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Helper Components ─────────────────────────────────────────────────

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="p-4 rounded-xl border border-rt-border bg-rt-surface">
      <p className="text-[10px] text-rt-text-muted uppercase tracking-wide mb-1">{label}</p>
      <p className="text-xl font-bold">{value}</p>
    </div>
  )
}

function SeverityIcon({ severity }: { severity: string }) {
  switch (severity) {
    case 'success': return <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
    case 'warning': return <AlertTriangle className="w-4 h-4 text-yellow-500 flex-shrink-0 mt-0.5" />
    case 'error': return <XCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
    default: return <Clock className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
  }
}

function EmptyTab({ message }: { message: string }) {
  return (
    <div className="text-center py-12 text-rt-text-muted text-sm">{message}</div>
  )
}
