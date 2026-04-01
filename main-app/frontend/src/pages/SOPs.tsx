import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ClipboardList, Loader2, Trash2, CheckCircle2,
  Package, ChevronDown, ChevronRight, Play, Send,
  CalendarClock, Edit2, History, XCircle, Timer, Layers,
  Zap, Clock, BarChart3, Shield, Search,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import toast from 'react-hot-toast'
import { productApi, agentApi, AGENT_GENERAL_SCOPE } from '@/utils/api'
import { Product } from '@/types'

export default function SOPs() {
  const [sopsByProduct, setSopsByProduct] = useState<Record<string, any[]>>({})
  const [isLoading, setIsLoading] = useState(false)
  const [expandedProducts, setExpandedProducts] = useState<Set<string>>(new Set())
  const [expandedSopId, setExpandedSopId] = useState<string | null>(null)
  const [expandedSection, setExpandedSection] = useState<'steps' | 'logs' | 'schedule' | null>('steps')
  const [runLogs, setRunLogs] = useState<Record<string, any[]>>({})
  const [loadingLogs, setLoadingLogs] = useState<string | null>(null)
  const [runningManual, setRunningManual] = useState<string | null>(null)
  const [showLogsDropdown, setShowLogsDropdown] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const [editingSopId, setEditingSopId] = useState<string | null>(null)
  const [editInstructions, setEditInstructions] = useState('')
  const [isEditingSop, setIsEditingSop] = useState(false)
  const [streamingSop, setStreamingSop] = useState<string | null>(null)

  const [editingScheduleId, setEditingScheduleId] = useState<string | null>(null)
  const [scheduleType, setScheduleType] = useState('none')
  const [scheduleConfig, setScheduleConfig] = useState<Record<string, any>>({})

  const { data: products = [] } = useQuery({
    queryKey: ['products'],
    queryFn: () => productApi.list(),
  })

  const trainedProducts = products.filter((p: Product) =>
    p.folder_groups?.some(g => g.training_status === 'completed') === true
  )

  const loadAllSOPs = useCallback(async () => {
    setIsLoading(true)
    try {
      const allSops = await agentApi.listSOPs('__all__')
      const grouped: Record<string, any[]> = {}
      for (const sop of (Array.isArray(allSops) ? allSops : [])) {
        const key = sop.product_id || AGENT_GENERAL_SCOPE
        if (!grouped[key]) grouped[key] = []
        grouped[key].push(sop)
      }
      setSopsByProduct(grouped)
    } catch {
      toast.error('Failed to load automations')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAllSOPs()
  }, [loadAllSOPs])

  const handleDelete = useCallback(async (sopId: string, productId: string) => {
    try {
      await agentApi.deleteSOP(sopId)
      setSopsByProduct(prev => ({
        ...prev,
        [productId]: (prev[productId] || []).filter(s => s.sop_id !== sopId),
      }))
      toast.success('Automation deleted')
    } catch {
      toast.error('Failed to delete automation')
    }
  }, [])

  const handleApprove = useCallback(async (sopId: string, productId: string) => {
    try {
      await agentApi.approveSOP(sopId)
      setSopsByProduct(prev => ({
        ...prev,
        [productId]: (prev[productId] || []).map(s =>
          s.sop_id === sopId ? { ...s, status: 'approved' } : s
        ),
      }))
      toast.success('Automation approved!')
    } catch {
      toast.error('Failed to approve automation')
    }
  }, [])

  const handleManualRun = useCallback(async (sopId: string) => {
    setRunningManual(sopId)
    try {
      await agentApi.manualRun(sopId)
      toast.success('Automation run started!')
      setTimeout(() => loadRunLogs(sopId), 2000)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to start run')
    } finally {
      setRunningManual(null)
    }
  }, [])

  const loadRunLogs = useCallback(async (sopId: string) => {
    setLoadingLogs(sopId)
    try {
      const logs = await agentApi.listRuns(sopId)
      setRunLogs(prev => ({ ...prev, [sopId]: logs }))
    } catch {
      toast.error('Failed to load run history')
    } finally {
      setLoadingLogs(null)
    }
  }, [])

  const handleSaveSchedule = useCallback(async (sopId: string, productId: string) => {
    try {
      const result = await agentApi.updateSchedule(sopId, scheduleType, scheduleType !== 'none' ? scheduleConfig : undefined)
      setSopsByProduct(prev => ({
        ...prev,
        [productId]: (prev[productId] || []).map(s => s.sop_id === sopId ? { ...s, ...result } : s),
      }))
      setEditingScheduleId(null)
      toast.success('Schedule updated!')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to update schedule')
    }
  }, [scheduleType, scheduleConfig])

  const handleEditSop = useCallback(async (sopId: string, productId: string) => {
    if (!editInstructions.trim()) return
    setIsEditingSop(true)
    try {
      const response = await fetch('/api/v1/agent/edit-sop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sop_id: sopId, edit_instructions: editInstructions.trim() }),
      })
      if (!response.ok) throw new Error(await response.text())
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No stream reader')
      const decoder = new TextDecoder()
      let buffer = ''
      let editResult: { sop_markdown: string; title: string } = { sop_markdown: '', title: '' }
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) { currentEvent = line.slice(7).trim() }
          else if (line.startsWith('data: ') && currentEvent) {
            try {
              const eventData = JSON.parse(line.slice(6))
              if (currentEvent === 'sop_chunk') {
                setStreamingSop(eventData.chunk)
              } else if (currentEvent === 'sop_done') {
                editResult = { sop_markdown: eventData.sop_markdown, title: eventData.title }
                setStreamingSop(null)
              } else if (currentEvent === 'sop_error') {
                setStreamingSop(null)
                throw new Error(eventData.detail || 'Edit failed')
              }
            } catch (e) { if (e instanceof Error && e.message !== 'Edit failed') { /* ignore */ } else throw e }
            currentEvent = ''
          }
        }
      }
      setSopsByProduct(prev => ({
        ...prev,
        [productId]: (prev[productId] || []).map(s =>
          s.sop_id === sopId ? { ...s, sop_markdown: editResult.sop_markdown, title: editResult.title } : s
        ),
      }))
      setEditingSopId(null)
      setEditInstructions('')
      toast.success('Automation updated!')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err?.message || 'Failed to edit automation')
      setStreamingSop(null)
    } finally {
      setIsEditingSop(false)
    }
  }, [editInstructions])

  // Compute stats
  const allSops = Object.values(sopsByProduct).flat()
  const totalSOPs = allSops.length
  const approvedCount = allSops.filter(s => s.status === 'approved').length
  const scheduledCount = allSops.filter(s => s.schedule_type && s.schedule_type !== 'none').length
  const draftCount = totalSOPs - approvedCount

  const generalSopsList = sopsByProduct[AGENT_GENERAL_SCOPE] || []
  const productMap = new Map(products.map((p: Product) => [p.product_id, p.product_name]))
  const displaySopSections: { sectionId: string; sectionName: string; isGeneral: boolean }[] = []
  if (generalSopsList.length > 0) {
    displaySopSections.push({ sectionId: AGENT_GENERAL_SCOPE, sectionName: 'General', isGeneral: true })
  }
  // Show all product sections that have SOPs (including orphaned products)
  for (const [key, sops] of Object.entries(sopsByProduct)) {
    if (key === AGENT_GENERAL_SCOPE || sops.length === 0) continue
    displaySopSections.push({
      sectionId: key,
      sectionName: productMap.get(key) || 'Deleted Product',
      isGeneral: false,
    })
  }

  const toggleProduct = (productId: string) => {
    setExpandedProducts(prev => {
      const next = new Set(prev)
      if (next.has(productId)) next.delete(productId)
      else next.add(productId)
      return next
    })
  }

  const handleExpand = (sopId: string) => {
    if (expandedSopId === sopId) {
      setExpandedSopId(null)
    } else {
      setExpandedSopId(sopId)
      setExpandedSection('steps')
      if (!runLogs[sopId]) loadRunLogs(sopId)
    }
  }

  // Filter SOPs by search query
  const filterSops = (sops: any[]) => {
    if (!searchQuery.trim()) return sops
    const q = searchQuery.toLowerCase()
    return sops.filter(s => s.title?.toLowerCase().includes(q) || s.goal?.toLowerCase().includes(q))
  }

  return (
    <div className="h-full flex flex-col bg-rt-bg">
      {/* Enterprise Header */}
      <div className="px-12 pt-10 pb-8 border-b border-rt-border/50">
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
          <div className="flex items-start justify-between mb-6">
            <div>
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-rt-primary-container/30 to-rt-primary-container/10 flex items-center justify-center">
                  <Zap className="w-5 h-5 text-rt-primary-container" />
                </div>
                <div>
                  <h1 className="text-3xl font-headline font-bold tracking-tight">Automations</h1>
                  <p className="text-sm text-on-surface-variant mt-0.5">Orchestrate intelligent workflows across your products</p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-rt-text-muted" />
                <input
                  type="text"
                  placeholder="Search automations..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 pr-3 py-2.5 bg-rt-surface/60 border border-rt-border text-rt-text rounded-xl text-xs w-60 focus:outline-none focus:border-rt-primary-container focus:bg-rt-bg transition-colors placeholder:text-rt-text-muted"
                />
              </div>
            </div>
          </div>

          {/* Stats Row */}
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: 'Total', value: totalSOPs, icon: ClipboardList, color: 'text-rt-primary-container', bg: 'bg-rt-primary-container/10' },
              { label: 'Approved', value: approvedCount, icon: Shield, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
              { label: 'Scheduled', value: scheduledCount, icon: Clock, color: 'text-blue-400', bg: 'bg-blue-500/10' },
              { label: 'Drafts', value: draftCount, icon: Edit2, color: 'text-rt-text-muted', bg: 'bg-rt-surface/50' },
            ].map(stat => (
              <div key={stat.label} className="flex items-center gap-3 px-4 py-3 rounded-xl border border-rt-border/40 bg-rt-surface/20">
                <div className={`w-9 h-9 rounded-lg ${stat.bg} flex items-center justify-center`}>
                  <stat.icon className={`w-4 h-4 ${stat.color}`} />
                </div>
                <div>
                  <p className="text-xl font-bold font-headline tracking-tight">{stat.value}</p>
                  <p className="text-[10px] font-medium text-rt-text-muted uppercase tracking-wider">{stat.label}</p>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto px-12 py-8">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center gap-4 text-rt-text-muted py-20">
            <div className="w-12 h-12 rounded-full bg-rt-primary-container/10 flex items-center justify-center">
              <Loader2 className="w-6 h-6 animate-spin text-rt-primary-container" />
            </div>
            <span className="text-sm">Loading automations...</span>
          </div>
        ) : displaySopSections.length === 0 ? (
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="text-center py-24">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-rt-primary-container/20 to-rt-primary-container/5 flex items-center justify-center">
              <Zap className="w-10 h-10 text-rt-primary-container/60" />
            </div>
            <h3 className="text-2xl font-headline font-bold mb-3">No automations yet</h3>
            <p className="text-on-surface-variant max-w-md mx-auto text-sm leading-relaxed mb-6">
              Automations are created from Agent conversations. Ask the agent a question, then use <strong className="text-rt-primary-container">Build Automation</strong> to turn it into a repeatable workflow.
            </p>
            <div className="flex items-center justify-center gap-6 text-xs text-rt-text-muted">
              <div className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Approve & deploy</div>
              <div className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-blue-400" /> Schedule recurring runs</div>
              <div className="flex items-center gap-1.5"><BarChart3 className="w-3.5 h-3.5 text-rt-primary-container" /> Track execution history</div>
            </div>
          </motion.div>
        ) : (
          <div className="max-w-6xl space-y-6">
            {displaySopSections.map((section) => {
              const productSOPs = filterSops(sopsByProduct[section.sectionId] || [])
              if (searchQuery.trim() && productSOPs.length === 0) return null
              const isExpanded = expandedProducts.has(section.sectionId)
              return (
                <motion.div key={section.sectionId} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  {/* Section header */}
                  <button
                    type="button"
                    onClick={() => toggleProduct(section.sectionId)}
                    className="w-full flex items-center gap-3 px-6 py-4 rounded-xl hover:bg-rt-surface/40 transition-all mb-3 group bg-rt-surface/20 border border-rt-border/30"
                  >
                    <ChevronDown className={`w-4 h-4 text-rt-text-muted transition-transform duration-200 ${isExpanded ? '' : '-rotate-90'}`} />
                    {section.isGeneral ? (
                      <div className="w-9 h-9 rounded-lg bg-amber-500/10 flex items-center justify-center">
                        <Layers className="w-3.5 h-3.5 text-amber-400" />
                      </div>
                    ) : (
                      <div className="w-9 h-9 rounded-lg bg-rt-primary/10 flex items-center justify-center">
                        <Package className="w-3.5 h-3.5 text-rt-primary" />
                      </div>
                    )}
                    <span className="text-base font-bold">{section.sectionName}</span>
                    <span className="px-3 py-1 rounded-lg text-xs font-bold bg-rt-surface/60 text-rt-text-muted border border-rt-border/30">
                      {productSOPs.length}
                    </span>
                    <div className="ml-auto flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <span className="text-[10px] text-rt-text-muted">
                        {productSOPs.filter(s => s.status === 'approved').length} approved
                      </span>
                    </div>
                  </button>

                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="pl-4 space-y-3">
                          {productSOPs.map(sop => (
                            <div key={sop.sop_id} className="rounded-xl border border-rt-border/50 bg-rt-surface/10 overflow-hidden hover:border-rt-border/70 hover:bg-rt-surface/20 transition-all duration-200">
                              <div
                                className="flex items-center gap-4 px-6 py-5 cursor-pointer transition-colors"
                                onClick={() => handleExpand(sop.sop_id)}
                              >
                                <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                                  sop.status === 'approved' ? 'bg-emerald-500/10' : 'bg-rt-surface/50'
                                }`}>
                                  <ClipboardList className={`w-4 h-4 ${sop.status === 'approved' ? 'text-emerald-400' : 'text-rt-text-muted'}`} />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                                    <span className="text-base font-semibold truncate">{sop.title}</span>
                                    {(sop.status || 'draft') === 'approved' ? (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                        <CheckCircle2 className="w-2.5 h-2.5" />
                                        Approved
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold bg-rt-surface/60 text-rt-text-muted border border-rt-border/30">
                                        Draft
                                      </span>
                                    )}
                                    {sop.schedule_type && sop.schedule_type !== 'none' && (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                                        <Timer className="w-2.5 h-2.5" />
                                        {scheduleLabel(sop.schedule_type, sop.schedule_config)}
                                      </span>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-3 flex-wrap">
                                    <p className="text-sm text-rt-text-muted truncate max-w-md">{sop.goal}</p>
                                    {sop.last_run_at && (
                                      <span className="text-[10px] text-rt-text-muted/60 flex items-center gap-1">
                                        <Clock className="w-2.5 h-2.5" />
                                        Last: {new Date(sop.last_run_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                      </span>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-1 flex-shrink-0">
                                  <span className="text-[10px] text-rt-text-muted/50 mr-3">
                                    {sop.created_at ? new Date(sop.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : ''}
                                  </span>
                                  {(sop.status || 'draft') !== 'approved' && (
                                    <button
                                      onClick={(e) => { e.stopPropagation(); handleApprove(sop.sop_id, section.sectionId) }}
                                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 transition-colors"
                                      title="Approve"
                                    >
                                      <CheckCircle2 className="w-3.5 h-3.5" />
                                      Approve
                                    </button>
                                  )}
                                  <button
                                    onClick={(e) => { e.stopPropagation(); setEditingSopId(editingSopId === sop.sop_id ? null : sop.sop_id); setEditInstructions('') }}
                                    className="p-2.5 rounded-lg hover:bg-rt-surface/60 text-rt-text-muted hover:text-blue-400 transition-colors"
                                    title="Edit"
                                  >
                                    <Edit2 className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      if (showLogsDropdown === sop.sop_id) setShowLogsDropdown(null)
                                      else { setShowLogsDropdown(sop.sop_id); if (!runLogs[sop.sop_id]) loadRunLogs(sop.sop_id) }
                                    }}
                                    className="p-2.5 rounded-lg hover:bg-rt-surface/60 text-rt-text-muted hover:text-indigo-400 transition-colors relative"
                                    title="Execution logs"
                                  >
                                    <History className="w-3.5 h-3.5" />
                                    {runLogs[sop.sop_id]?.length > 0 && (
                                      <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-indigo-500 rounded-full text-[8px] text-white flex items-center justify-center font-bold">
                                        {runLogs[sop.sop_id].length > 9 ? '9+' : runLogs[sop.sop_id].length}
                                      </span>
                                    )}
                                  </button>
                                  {sop.status === 'approved' && sop.sop_json && (
                                    <button
                                      onClick={(e) => { e.stopPropagation(); handleManualRun(sop.sop_id) }}
                                      disabled={runningManual === sop.sop_id}
                                      className="p-2.5 rounded-lg hover:bg-emerald-500/10 text-rt-text-muted hover:text-emerald-400 transition-colors disabled:opacity-50"
                                      title="Run now"
                                    >
                                      {runningManual === sop.sop_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                                    </button>
                                  )}
                                  {sop.status === 'approved' && (
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        setEditingScheduleId(editingScheduleId === sop.sop_id ? null : sop.sop_id)
                                        setScheduleType(sop.schedule_type || 'none')
                                        setScheduleConfig(sop.schedule_config || {})
                                        if (expandedSopId !== sop.sop_id) handleExpand(sop.sop_id)
                                        setExpandedSection('schedule')
                                      }}
                                      className="p-2.5 rounded-lg hover:bg-rt-surface/60 text-rt-text-muted hover:text-purple-400 transition-colors"
                                      title="Schedule"
                                    >
                                      <CalendarClock className="w-3.5 h-3.5" />
                                    </button>
                                  )}
                                  <button
                                    onClick={(e) => { e.stopPropagation(); handleDelete(sop.sop_id, section.sectionId) }}
                                    className="p-2.5 rounded-lg hover:bg-red-500/10 text-rt-text-muted hover:text-red-400 transition-colors"
                                    title="Delete"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                  <ChevronRight className={`w-4 h-4 text-rt-text-muted/40 transition-transform duration-200 ${expandedSopId === sop.sop_id ? 'rotate-90' : ''}`} />
                                </div>
                              </div>

                              {/* Edit inline */}
                              {editingSopId === sop.sop_id && streamingSop && (
                                <div className="border-t border-rt-border/30 px-5 pb-3 pt-3 flex items-center gap-2 text-sm text-rt-text-muted bg-rt-surface/10">
                                  <Loader2 className="w-4 h-4 animate-spin text-rt-primary-container" />
                                  Updating automation...
                                </div>
                              )}
                              {editingSopId === sop.sop_id && !streamingSop && (
                                <div className="border-t border-rt-border/30 px-5 pb-4 pt-3 bg-rt-surface/10">
                                  <p className="text-xs text-rt-text-muted mb-2 font-medium">Describe the changes:</p>
                                  <div className="flex gap-2 items-end">
                                    <textarea
                                      value={editInstructions}
                                      onChange={(e) => setEditInstructions(e.target.value)}
                                      placeholder="e.g. Add a rollback step after step 3..."
                                      rows={2}
                                      className="flex-1 text-sm min-h-[2.5rem] resize-y bg-rt-bg border border-rt-border rounded-lg px-3 py-2 focus:outline-none focus:border-rt-primary-container/50 transition-colors"
                                      disabled={isEditingSop}
                                      autoFocus
                                    />
                                    <button
                                      type="button"
                                      onClick={() => handleEditSop(sop.sop_id, section.sectionId)}
                                      disabled={isEditingSop || !editInstructions.trim()}
                                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-rt-primary-container text-[#2a1700] hover:bg-rt-primary-container/90 transition-colors disabled:opacity-50"
                                    >
                                      {isEditingSop ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                                      Apply
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => { setEditingSopId(null); setEditInstructions('') }}
                                      disabled={isEditingSop}
                                      className="px-3 py-2 rounded-lg text-xs font-medium text-rt-text-muted hover:bg-rt-surface transition-colors"
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              )}

                              {/* Logs dropdown */}
                              {showLogsDropdown === sop.sop_id && (
                                <div className="border-t border-rt-border/30 px-5 pb-4 pt-3 bg-rt-surface/10">
                                  <div className="flex items-center justify-between mb-3">
                                    <span className="text-xs font-semibold text-rt-text">Execution History</span>
                                    <button onClick={(e) => { e.stopPropagation(); loadRunLogs(sop.sop_id) }} className="text-xs text-rt-primary-container hover:underline font-medium">
                                      {loadingLogs === sop.sop_id ? <Loader2 className="w-3 h-3 animate-spin inline" /> : 'Refresh'}
                                    </button>
                                  </div>
                                  {!runLogs[sop.sop_id] || runLogs[sop.sop_id].length === 0 ? (
                                    <p className="text-xs text-rt-text-muted/60 italic py-6 text-center">No executions yet</p>
                                  ) : (
                                    <div className="space-y-2 max-h-80 overflow-y-auto">
                                      {runLogs[sop.sop_id].map((run: any) => (
                                        <RunLogEntry key={run.run_id} run={run} compact />
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* Expanded detail */}
                              <AnimatePresence>
                                {expandedSopId === sop.sop_id && (
                                  <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    className="overflow-hidden"
                                  >
                                    <div className="border-t border-rt-border/30">
                                      {/* Section tabs */}
                                      <div className="flex gap-1 px-5 pt-3 pb-2 border-b border-rt-border/20">
                                        {[
                                          { key: 'steps' as const, label: 'Steps', icon: ClipboardList },
                                          { key: 'logs' as const, label: 'Execution Logs', icon: History },
                                          ...(sop.status === 'approved' ? [{ key: 'schedule' as const, label: 'Schedule', icon: CalendarClock }] : []),
                                        ].map(tab => (
                                          <button
                                            key={tab.key}
                                            onClick={() => {
                                              setExpandedSection(tab.key)
                                              if (tab.key === 'logs' && !runLogs[sop.sop_id]) loadRunLogs(sop.sop_id)
                                              if (tab.key === 'schedule') {
                                                setEditingScheduleId(sop.sop_id)
                                                setScheduleType(sop.schedule_type || 'none')
                                                setScheduleConfig(sop.schedule_config || {})
                                              }
                                            }}
                                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                                              expandedSection === tab.key
                                                ? 'bg-rt-primary-container/15 text-rt-primary-container border border-rt-primary-container/20'
                                                : 'text-rt-text-muted hover:text-rt-text hover:bg-rt-surface/40'
                                            }`}
                                          >
                                            <tab.icon className="w-3.5 h-3.5" />
                                            {tab.label}
                                            {tab.key === 'logs' && runLogs[sop.sop_id]?.length ? (
                                              <span className="text-[10px] opacity-60">({runLogs[sop.sop_id].length})</span>
                                            ) : null}
                                          </button>
                                        ))}
                                      </div>

                                      {expandedSection === 'steps' && (
                                        <div className="px-5 pb-5 pt-4">
                                          <div className="prose prose-sm max-w-none prose-headings:font-headline prose-headings:tracking-tight">
                                            <ReactMarkdown>{sop.sop_markdown}</ReactMarkdown>
                                          </div>
                                        </div>
                                      )}

                                      {expandedSection === 'logs' && (
                                        <div className="px-5 pb-5 pt-4">
                                          <div className="flex items-center justify-between mb-3">
                                            <span className="text-xs text-rt-text-muted font-medium">Execution History</span>
                                            <button onClick={() => loadRunLogs(sop.sop_id)} className="text-xs text-rt-primary-container hover:underline font-medium">
                                              {loadingLogs === sop.sop_id ? <Loader2 className="w-3 h-3 animate-spin inline" /> : 'Refresh'}
                                            </button>
                                          </div>
                                          {!runLogs[sop.sop_id] || runLogs[sop.sop_id].length === 0 ? (
                                            <p className="text-xs text-rt-text-muted/60 italic py-6 text-center">No executions yet</p>
                                          ) : (
                                            <div className="space-y-2">
                                              {runLogs[sop.sop_id].map((run: any) => (
                                                <RunLogEntry key={run.run_id} run={run} />
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      )}

                                      {expandedSection === 'schedule' && editingScheduleId === sop.sop_id && (
                                        <div className="px-5 pb-5 pt-4">
                                          <InlineScheduleEditor
                                            scheduleType={scheduleType}
                                            scheduleConfig={scheduleConfig}
                                            onChangeType={setScheduleType}
                                            onChangeConfig={setScheduleConfig}
                                            onSave={() => handleSaveSchedule(sop.sop_id, section.sectionId)}
                                            onCancel={() => { setEditingScheduleId(null); setExpandedSection('steps') }}
                                          />
                                        </div>
                                      )}
                                    </div>
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Run log entry component
// ---------------------------------------------------------------------------
function RunLogEntry({ run, compact = false }: { run: any; compact?: boolean }) {
  const [showOutput, setShowOutput] = useState(false)
  const statusStyles: Record<string, { color: string; bg: string; border: string }> = {
    completed: { color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' },
    failed: { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' },
    running: { color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
  }
  const style = statusStyles[run.status] || { color: 'text-rt-text-muted', bg: 'bg-rt-surface', border: 'border-rt-border' }

  if (compact) {
    return (
      <div className="rounded-lg border border-rt-border/30 bg-rt-bg/50 overflow-hidden">
        <div
          className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-rt-surface/30 transition-colors"
          onClick={() => setShowOutput(!showOutput)}
        >
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-semibold ${style.bg} ${style.color} border ${style.border}`}>
            {run.status === 'completed' ? <CheckCircle2 className="w-2.5 h-2.5" /> : run.status === 'failed' ? <XCircle className="w-2.5 h-2.5" /> : <Loader2 className="w-2.5 h-2.5 animate-spin" />}
            {run.status}
          </span>
          <span className="text-[10px] text-rt-text-muted">{run.trigger === 'manual' ? 'Manual' : 'Scheduled'}</span>
          <span className="text-[10px] text-rt-text-muted">{run.steps_completed}/{run.steps_total} steps</span>
          {run.duration_ms && <span className="text-[10px] text-rt-text-muted">{(run.duration_ms / 1000).toFixed(1)}s</span>}
          <span className="text-[10px] text-rt-text-muted/50 ml-auto">
            {run.started_at ? new Date(run.started_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
          </span>
          <ChevronRight className={`w-3 h-3 text-rt-text-muted/40 transition-transform ${showOutput ? 'rotate-90' : ''}`} />
        </div>
        {showOutput && run.output_log && (
          <div className="px-3 pb-2 border-t border-rt-border/20">
            <pre className="bg-rt-bg border border-rt-border/30 text-rt-text text-[10px] p-2.5 rounded-lg overflow-x-auto font-mono whitespace-pre-wrap max-h-32 overflow-y-auto mt-2">
              {run.output_log}
            </pre>
            {run.error && <div className="mt-1.5 text-[10px] text-red-400 bg-red-500/10 rounded-lg px-2.5 py-1 border border-red-500/20">{run.error}</div>}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-rt-border/30 bg-rt-bg/50 overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-rt-surface/30 transition-colors"
        onClick={() => setShowOutput(!showOutput)}
      >
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[10px] font-semibold ${style.bg} ${style.color} border ${style.border}`}>
          {run.status === 'completed' ? <CheckCircle2 className="w-3 h-3" /> : run.status === 'failed' ? <XCircle className="w-3 h-3" /> : <Loader2 className="w-3 h-3 animate-spin" />}
          {run.status}
        </span>
        <span className="text-[10px] text-rt-text-muted">{run.trigger === 'manual' ? 'Manual' : 'Scheduled'}</span>
        <span className="text-[10px] text-rt-text-muted">Steps: {run.steps_completed}/{run.steps_total}</span>
        {run.duration_ms && <span className="text-[10px] text-rt-text-muted">{(run.duration_ms / 1000).toFixed(1)}s</span>}
        <span className="text-[10px] text-rt-text-muted/50 ml-auto">{run.started_at ? new Date(run.started_at).toLocaleString() : ''}</span>
        <ChevronRight className={`w-3 h-3 text-rt-text-muted/40 transition-transform ${showOutput ? 'rotate-90' : ''}`} />
      </div>
      {showOutput && run.output_log && (
        <div className="px-4 pb-3 border-t border-rt-border/20">
          <pre className="bg-rt-bg border border-rt-border/30 text-rt-text text-[10px] p-3 rounded-lg overflow-x-auto font-mono whitespace-pre-wrap max-h-48 overflow-y-auto mt-2">
            {run.output_log}
          </pre>
          {run.error && <div className="mt-1.5 text-[10px] text-red-400 bg-red-500/10 rounded-lg px-2.5 py-1 border border-red-500/20">{run.error}</div>}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline schedule editor
// ---------------------------------------------------------------------------
function InlineScheduleEditor({ scheduleType, scheduleConfig, onChangeType, onChangeConfig, onSave, onCancel }: {
  scheduleType: string
  scheduleConfig: Record<string, any>
  onChangeType: (t: string) => void
  onChangeConfig: (c: Record<string, any>) => void
  onSave: () => void
  onCancel: () => void
}) {
  const options = [
    { value: 'none', label: 'No Schedule', icon: XCircle },
    { value: 'once', label: 'One-Time', icon: CalendarClock },
    { value: 'interval', label: 'Interval', icon: Timer },
    { value: 'daily', label: 'Daily', icon: Clock },
    { value: 'weekly', label: 'Weekly', icon: CalendarClock },
    { value: 'monthly', label: 'Monthly', icon: CalendarClock },
    { value: 'cron', label: 'Cron', icon: Zap },
  ]
  const allDays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

  return (
    <div>
      <p className="text-xs font-semibold text-rt-text mb-3">Schedule Type</p>
      <div className="grid grid-cols-4 sm:grid-cols-7 gap-2 mb-4">
        {options.map(opt => (
          <button key={opt.value} type="button" onClick={() => { onChangeType(opt.value); onChangeConfig({}) }}
            className={`flex flex-col items-center gap-1.5 p-3 rounded-xl border text-center transition-all text-xs ${
              scheduleType === opt.value
                ? 'border-rt-primary-container/50 bg-rt-primary-container/10 text-rt-primary-container'
                : 'border-rt-border/40 hover:border-rt-text-muted/30 text-rt-text-muted hover:bg-rt-surface/30'
            }`}>
            <opt.icon className="w-4 h-4" />
            <span className="font-medium">{opt.label}</span>
          </button>
        ))}
      </div>

      {scheduleType === 'once' && (
        <div className="flex items-center gap-2 mb-4">
          <label className="text-xs text-rt-text-muted font-medium">Run at:</label>
          <input type="datetime-local" value={scheduleConfig.run_at || ''} onChange={e => onChangeConfig({ ...scheduleConfig, run_at: e.target.value })}
            className="bg-rt-bg border border-rt-border rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-rt-primary-container/50 flex-1 transition-colors" />
        </div>
      )}

      {scheduleType === 'interval' && (
        <div className="flex items-center gap-2 mb-4">
          <label className="text-xs text-rt-text-muted font-medium">Every</label>
          <input type="number" min={1} value={scheduleConfig.every || 30} onChange={e => onChangeConfig({ ...scheduleConfig, every: Number(e.target.value) })}
            className="w-16 bg-rt-bg border border-rt-border rounded-lg px-2 py-2 text-xs text-center focus:outline-none focus:border-rt-primary-container/50 transition-colors" />
          <select value={scheduleConfig.unit || 'minutes'} onChange={e => onChangeConfig({ ...scheduleConfig, unit: e.target.value })}
            className="bg-rt-bg border border-rt-border rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-rt-primary-container/50 transition-colors">
            <option value="minutes">Minutes</option>
            <option value="hours">Hours</option>
            <option value="days">Days</option>
          </select>
        </div>
      )}

      {scheduleType === 'daily' && (
        <div className="flex items-center gap-2 mb-4">
          <label className="text-xs text-rt-text-muted font-medium">Every day at:</label>
          <input type="time" value={scheduleConfig.time || '09:00'} onChange={e => onChangeConfig({ ...scheduleConfig, time: e.target.value })}
            className="bg-rt-bg border border-rt-border rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-rt-primary-container/50 transition-colors" />
        </div>
      )}

      {scheduleType === 'weekly' && (
        <div className="mb-4">
          <div className="flex flex-wrap gap-1.5 mb-3">
            {allDays.map(day => (
              <button key={day} type="button"
                onClick={() => {
                  const days = scheduleConfig.days || []
                  onChangeConfig({ ...scheduleConfig, days: days.includes(day) ? days.filter((d: string) => d !== day) : [...days, day] })
                }}
                className={`px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all ${
                  (scheduleConfig.days || []).includes(day)
                    ? 'bg-rt-primary-container/15 text-rt-primary-container border border-rt-primary-container/30'
                    : 'bg-rt-bg text-rt-text-muted border border-rt-border/40 hover:border-rt-border'
                }`}>
                {day.charAt(0).toUpperCase() + day.slice(1, 3)}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-rt-text-muted font-medium">At:</label>
            <input type="time" value={scheduleConfig.time || '09:00'} onChange={e => onChangeConfig({ ...scheduleConfig, time: e.target.value })}
              className="bg-rt-bg border border-rt-border rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-rt-primary-container/50 transition-colors" />
          </div>
        </div>
      )}

      {scheduleType === 'monthly' && (
        <div className="flex items-center gap-2 mb-4">
          <label className="text-xs text-rt-text-muted font-medium">Day</label>
          <input type="number" min={1} max={28} value={scheduleConfig.day_of_month || 1} onChange={e => onChangeConfig({ ...scheduleConfig, day_of_month: Number(e.target.value) })}
            className="w-16 bg-rt-bg border border-rt-border rounded-lg px-2 py-2 text-xs text-center focus:outline-none focus:border-rt-primary-container/50 transition-colors" />
          <label className="text-xs text-rt-text-muted font-medium">at</label>
          <input type="time" value={scheduleConfig.time || '09:00'} onChange={e => onChangeConfig({ ...scheduleConfig, time: e.target.value })}
            className="bg-rt-bg border border-rt-border rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-rt-primary-container/50 transition-colors" />
        </div>
      )}

      {scheduleType === 'cron' && (
        <div className="flex items-center gap-2 mb-4">
          <label className="text-xs text-rt-text-muted font-medium">Expression:</label>
          <input type="text" value={scheduleConfig.expression || '0 9 * * 1-5'} onChange={e => onChangeConfig({ ...scheduleConfig, expression: e.target.value })}
            className="bg-rt-bg border border-rt-border rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-rt-primary-container/50 flex-1 font-mono transition-colors" />
          <span className="text-[10px] text-rt-text-muted/60">min hr dom mon dow</span>
        </div>
      )}

      <div className="flex items-center gap-2 pt-2">
        <button onClick={onSave}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-rt-primary-container text-[#2a1700] hover:bg-rt-primary-container/90 transition-colors">
          <CheckCircle2 className="w-3.5 h-3.5" />
          Save Schedule
        </button>
        <button onClick={onCancel}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium text-rt-text-muted hover:bg-rt-surface/40 transition-colors">
          Cancel
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------
function scheduleLabel(type: string, config?: Record<string, any>): string {
  if (!type || type === 'none') return ''
  if (type === 'once') return 'One-time'
  if (type === 'interval') return `Every ${config?.every || '?'} ${config?.unit || 'min'}`
  if (type === 'daily') return `Daily ${config?.time || ''}`
  if (type === 'weekly') return `Weekly`
  if (type === 'monthly') return `Monthly`
  if (type === 'cron') return `Cron`
  return type
}
