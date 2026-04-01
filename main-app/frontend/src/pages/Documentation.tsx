import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  FileText, Loader2, Trash2,
  Package, ChevronDown, ChevronRight, Send,
  Edit2, CheckCircle2, Tag, Layers,
  BookOpen, Search, Filter, Calendar,
  Shield, Clock,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import toast from 'react-hot-toast'
import { productApi, agentApi, AGENT_GENERAL_SCOPE } from '@/utils/api'
import { Product } from '@/types'

export default function Documentation() {
  const [docsByProduct, setDocsByProduct] = useState<Record<string, any[]>>({})
  const [isLoading, setIsLoading] = useState(false)
  const [expandedProducts, setExpandedProducts] = useState<Set<string>>(new Set())
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null)
  const [streamingDoc, setStreamingDoc] = useState<string | null>(null)
  const [editingDocId, setEditingDocId] = useState<string | null>(null)
  const [editInstructions, setEditInstructions] = useState('')
  const [isEditing, setIsEditing] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterStatus, setFilterStatus] = useState<'all' | 'approved' | 'draft'>('all')

  const { data: products = [] } = useQuery({
    queryKey: ['products'],
    queryFn: () => productApi.list(),
  })

  const trainedProducts = products.filter((p: Product) =>
    p.folder_groups?.some(g => g.training_status === 'completed') === true
  )

  const loadAllDocs = useCallback(async () => {
    setIsLoading(true)
    try {
      const results: Record<string, any[]> = {}
      try {
        const general = await agentApi.listDocs(AGENT_GENERAL_SCOPE)
        results[AGENT_GENERAL_SCOPE] = Array.isArray(general) ? general : []
      } catch {
        results[AGENT_GENERAL_SCOPE] = []
      }
      await Promise.all(
        trainedProducts.map(async (p: Product) => {
          try {
            const docs = await agentApi.listDocs(p.product_id)
            results[p.product_id] = Array.isArray(docs) ? docs : []
          } catch {
            results[p.product_id] = []
          }
        })
      )
      setDocsByProduct(results)
    } catch {
      toast.error('Failed to load documentation')
    } finally {
      setIsLoading(false)
    }
  }, [trainedProducts.map(p => p.product_id).join(',')])

  useEffect(() => {
    loadAllDocs()
  }, [loadAllDocs])

  const handleDelete = useCallback(async (docId: string, productId: string) => {
    try {
      await agentApi.deleteDoc(docId)
      setDocsByProduct(prev => ({
        ...prev,
        [productId]: (prev[productId] || []).filter(d => d.doc_id !== docId),
      }))
      toast.success('Documentation deleted')
    } catch {
      toast.error('Failed to delete documentation')
    }
  }, [])

  const handleApproveDoc = useCallback(async (docId: string, productId: string) => {
    try {
      const updated = await agentApi.approveDoc(docId)
      setDocsByProduct(prev => ({
        ...prev,
        [productId]: (prev[productId] || []).map(d => d.doc_id === docId ? { ...d, status: updated.status } : d),
      }))
      toast.success('Documentation approved')
    } catch {
      toast.error('Failed to approve documentation')
    }
  }, [])

  const handleEditDoc = useCallback(async (docId: string, productId: string) => {
    if (!editInstructions.trim()) return
    setIsEditing(true)
    try {
      const response = await fetch('/api/v1/agent/edit-doc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId, edit_instructions: editInstructions.trim() }),
      })
      if (!response.ok) throw new Error(await response.text())
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No stream reader')
      const decoder = new TextDecoder()
      let buffer = ''
      let editResult: { doc_markdown: string; title: string } = { doc_markdown: '', title: '' }
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
              if (currentEvent === 'doc_chunk') {
                setStreamingDoc(eventData.chunk)
              } else if (currentEvent === 'doc_done') {
                editResult = { doc_markdown: eventData.doc_markdown, title: eventData.title }
                setStreamingDoc(null)
              } else if (currentEvent === 'doc_error') {
                setStreamingDoc(null)
                throw new Error(eventData.detail || 'Edit failed')
              }
            } catch (e) { if (e instanceof Error && e.message !== 'Edit failed') { /* ignore parse errors */ } else throw e }
            currentEvent = ''
          }
        }
      }
      setDocsByProduct(prev => ({
        ...prev,
        [productId]: (prev[productId] || []).map(d =>
          d.doc_id === docId ? { ...d, doc_markdown: editResult.doc_markdown, title: editResult.title } : d
        ),
      }))
      setEditingDocId(null)
      setEditInstructions('')
      toast.success('Documentation updated!')
    } catch (err: any) {
      toast.error(err?.message || 'Failed to edit documentation')
      setStreamingDoc(null)
    } finally {
      setIsEditing(false)
    }
  }, [editInstructions])

  // Compute stats
  const allDocs = Object.values(docsByProduct).flat()
  const totalDocs = allDocs.length
  const approvedCount = allDocs.filter(d => d.status === 'approved').length
  const draftCount = totalDocs - approvedCount
  const tagCount = new Set(allDocs.flatMap(d => d.doc_json?.tags || [])).size

  const generalDocsList = docsByProduct[AGENT_GENERAL_SCOPE] || []
  const displayDocSections: { sectionId: string; sectionName: string; isGeneral: boolean }[] = []
  if (generalDocsList.length > 0) {
    displayDocSections.push({ sectionId: AGENT_GENERAL_SCOPE, sectionName: 'General', isGeneral: true })
  }
  for (const p of trainedProducts) {
    if ((docsByProduct[p.product_id] || []).length > 0) {
      displayDocSections.push({ sectionId: p.product_id, sectionName: p.product_name, isGeneral: false })
    }
  }

  const toggleProduct = (productId: string) => {
    setExpandedProducts(prev => {
      const next = new Set(prev)
      if (next.has(productId)) next.delete(productId)
      else next.add(productId)
      return next
    })
  }

  const handleExpand = (docId: string) => {
    setExpandedDocId(expandedDocId === docId ? null : docId)
    setEditingDocId(null)
    setEditInstructions('')
  }

  // Filter docs
  const filterDocs = (docs: any[]) => {
    let filtered = docs
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      filtered = filtered.filter(d => d.title?.toLowerCase().includes(q) || d.goal?.toLowerCase().includes(q) || d.doc_json?.tags?.some((t: string) => t.toLowerCase().includes(q)))
    }
    if (filterStatus !== 'all') {
      filtered = filtered.filter(d => filterStatus === 'approved' ? d.status === 'approved' : d.status !== 'approved')
    }
    return filtered
  }

  return (
    <div className="h-full flex flex-col bg-rt-bg">
      {/* Enterprise Header */}
      <div className="px-12 pt-10 pb-8 border-b border-rt-border/50">
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
          <div className="flex items-start justify-between mb-6">
            <div>
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500/20 to-blue-500/5 flex items-center justify-center">
                  <BookOpen className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <h1 className="text-3xl font-headline font-bold tracking-tight">Documentation</h1>
                  <p className="text-sm text-on-surface-variant mt-0.5">Knowledge articles curated from agent conversations</p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-rt-text-muted" />
                <input
                  type="text"
                  placeholder="Search articles..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 pr-3 py-2.5 bg-rt-surface/60 border border-rt-border text-rt-text rounded-xl text-xs w-60 focus:outline-none focus:border-blue-500 focus:bg-rt-bg transition-colors placeholder:text-rt-text-muted"
                />
              </div>
              <div className="flex items-center border border-rt-border rounded-xl overflow-hidden">
                {(['all', 'approved', 'draft'] as const).map(status => (
                  <button
                    key={status}
                    onClick={() => setFilterStatus(status)}
                    className={`px-3 py-2 text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                      filterStatus === status
                        ? 'bg-rt-surface/60 text-rt-text'
                        : 'text-rt-text-muted hover:text-rt-text hover:bg-rt-surface/30'
                    }`}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Stats Row */}
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: 'Articles', value: totalDocs, icon: FileText, color: 'text-blue-400', bg: 'bg-blue-500/10' },
              { label: 'Approved', value: approvedCount, icon: Shield, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
              { label: 'Drafts', value: draftCount, icon: Edit2, color: 'text-rt-text-muted', bg: 'bg-rt-surface/50' },
              { label: 'Tags', value: tagCount, icon: Tag, color: 'text-rt-primary-container', bg: 'bg-rt-primary-container/10' },
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
            <div className="w-12 h-12 rounded-full bg-blue-500/10 flex items-center justify-center">
              <Loader2 className="w-6 h-6 animate-spin text-blue-400" />
            </div>
            <span className="text-sm">Loading documentation...</span>
          </div>
        ) : displayDocSections.length === 0 ? (
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="text-center py-24">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-blue-500/20 to-blue-500/5 flex items-center justify-center">
              <BookOpen className="w-10 h-10 text-blue-400/60" />
            </div>
            <h3 className="text-2xl font-headline font-bold mb-3">No documentation yet</h3>
            <p className="text-on-surface-variant max-w-md mx-auto text-sm leading-relaxed mb-6">
              Documentation is created from Agent conversations. Ask the agent a question, then use <strong className="text-blue-400">Build Documentation</strong> to generate a knowledge article.
            </p>
            <div className="flex items-center justify-center gap-6 text-xs text-rt-text-muted">
              <div className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Approve & publish</div>
              <div className="flex items-center gap-1.5"><Edit2 className="w-3.5 h-3.5 text-blue-400" /> Edit with AI</div>
              <div className="flex items-center gap-1.5"><Tag className="w-3.5 h-3.5 text-rt-primary-container" /> Auto-tagged</div>
            </div>
          </motion.div>
        ) : (
          <div className="max-w-6xl space-y-6">
            {displayDocSections.map((section) => {
              const productDocs = filterDocs(docsByProduct[section.sectionId] || [])
              if ((searchQuery.trim() || filterStatus !== 'all') && productDocs.length === 0) return null
              const isExpanded = expandedProducts.has(section.sectionId)
              return (
                <motion.div key={section.sectionId} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  {/* Section header */}
                  <button
                    type="button"
                    onClick={() => toggleProduct(section.sectionId)}
                    className="w-full flex items-center gap-3 px-6 py-4 rounded-xl bg-rt-surface/20 border border-rt-border/30 hover:bg-rt-surface/40 transition-all mb-3 group"
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
                      {productDocs.length}
                    </span>
                    <div className="ml-auto flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <span className="text-[10px] text-rt-text-muted">
                        {productDocs.filter(d => d.status === 'approved').length} approved
                      </span>
                    </div>
                  </button>

                  {/* Docs list */}
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
                          {productDocs.map(doc => (
                            <div key={doc.doc_id} className="rounded-xl border border-rt-border/50 bg-rt-surface/10 overflow-hidden hover:border-rt-border/70 hover:bg-rt-surface/20 transition-all duration-200">
                              <div
                                className="flex items-center gap-4 px-6 py-5 cursor-pointer transition-colors"
                                onClick={() => handleExpand(doc.doc_id)}
                              >
                                <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                                  doc.status === 'approved' ? 'bg-blue-500/10' : 'bg-rt-surface/50'
                                }`}>
                                  <FileText className={`w-4 h-4 ${doc.status === 'approved' ? 'text-blue-400' : 'text-rt-text-muted'}`} />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                                    <span className="text-base font-semibold truncate">{doc.title}</span>
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                                      <FileText className="w-2.5 h-2.5" />
                                      {doc.doc_type === 'knowledge-article' ? 'Knowledge Article' : doc.doc_type}
                                    </span>
                                    {(doc.status || 'draft') === 'approved' ? (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                        <CheckCircle2 className="w-2.5 h-2.5" />
                                        Approved
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold bg-rt-surface/60 text-rt-text-muted border border-rt-border/30">
                                        Draft
                                      </span>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-3 flex-wrap">
                                    <p className="text-sm text-rt-text-muted truncate max-w-md">{doc.goal}</p>
                                    {doc.doc_json?.tags && doc.doc_json.tags.length > 0 && (
                                      <div className="flex items-center gap-1">
                                        {doc.doc_json.tags.slice(0, 4).map((tag: string) => (
                                          <span key={tag} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[9px] font-medium bg-rt-primary-container/10 text-rt-primary-container/80 border border-rt-primary-container/15">
                                            <Tag className="w-2 h-2" />{tag}
                                          </span>
                                        ))}
                                        {doc.doc_json.tags.length > 4 && (
                                          <span className="text-[9px] text-rt-text-muted/50">+{doc.doc_json.tags.length - 4}</span>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-1 flex-shrink-0">
                                  <span className="text-[10px] text-rt-text-muted/50 mr-3 flex items-center gap-1">
                                    <Calendar className="w-2.5 h-2.5" />
                                    {doc.created_at ? new Date(doc.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : ''}
                                  </span>
                                  {(doc.status || 'draft') !== 'approved' && (
                                    <button
                                      onClick={(e) => { e.stopPropagation(); handleApproveDoc(doc.doc_id, section.sectionId) }}
                                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 transition-colors"
                                      title="Approve"
                                    >
                                      <CheckCircle2 className="w-3.5 h-3.5" />
                                      Approve
                                    </button>
                                  )}
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      setEditingDocId(editingDocId === doc.doc_id ? null : doc.doc_id)
                                      setEditInstructions('')
                                    }}
                                    className="p-2.5 rounded-lg hover:bg-rt-surface/60 text-rt-text-muted hover:text-blue-400 transition-colors"
                                    title="Edit"
                                  >
                                    <Edit2 className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={(e) => { e.stopPropagation(); handleDelete(doc.doc_id, section.sectionId) }}
                                    className="p-2.5 rounded-lg hover:bg-red-500/10 text-rt-text-muted hover:text-red-400 transition-colors"
                                    title="Delete"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                  <ChevronRight className={`w-4 h-4 text-rt-text-muted/40 transition-transform duration-200 ${expandedDocId === doc.doc_id ? 'rotate-90' : ''}`} />
                                </div>
                              </div>

                              {/* Edit inline */}
                              {editingDocId === doc.doc_id && !streamingDoc && (
                                <div className="border-t border-rt-border/30 px-5 pb-4 pt-3 bg-rt-surface/10">
                                  <p className="text-xs text-rt-text-muted mb-2 font-medium">Describe the changes:</p>
                                  <div className="flex gap-2 items-end">
                                    <textarea
                                      value={editInstructions}
                                      onChange={(e) => setEditInstructions(e.target.value)}
                                      placeholder="e.g. Add a troubleshooting section..."
                                      rows={2}
                                      className="flex-1 text-sm min-h-[2.5rem] resize-y bg-rt-bg border border-rt-border rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500/50 transition-colors"
                                      disabled={isEditing}
                                      autoFocus
                                    />
                                    <button
                                      type="button"
                                      onClick={() => handleEditDoc(doc.doc_id, section.sectionId)}
                                      disabled={isEditing || !editInstructions.trim()}
                                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-rt-primary-container text-[#2a1700] hover:bg-rt-primary-container/90 transition-colors disabled:opacity-50"
                                    >
                                      {isEditing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                                      Apply
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => { setEditingDocId(null); setEditInstructions('') }}
                                      disabled={isEditing}
                                      className="px-3 py-2 rounded-lg text-xs font-medium text-rt-text-muted hover:bg-rt-surface transition-colors"
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              )}

                              {/* Expanded content */}
                              <AnimatePresence>
                                {(expandedDocId === doc.doc_id || (streamingDoc !== null && editingDocId === doc.doc_id)) && (
                                  <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    transition={{ duration: 0.2 }}
                                    className="overflow-hidden"
                                  >
                                    <div className="border-t border-rt-border/30 px-5 pb-5 pt-4">
                                      {streamingDoc !== null && editingDocId === doc.doc_id ? (
                                        <div className="prose prose-sm max-w-none prose-headings:font-headline prose-headings:tracking-tight">
                                          <div className="flex items-center gap-2 mb-3 text-sm text-rt-text-muted">
                                            <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />
                                            <span>Updating documentation...</span>
                                          </div>
                                          <ReactMarkdown>{streamingDoc}</ReactMarkdown>
                                        </div>
                                      ) : (
                                        <div className="prose prose-sm max-w-none prose-headings:font-headline prose-headings:tracking-tight">
                                          <ReactMarkdown>{doc.doc_markdown}</ReactMarkdown>
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
