import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Package, Trash2, Play, X, Folder, FolderOpen, ChevronRight, ChevronDown, Check, FolderTree, FileCode, FileText, Image, TicketIcon, AlertTriangle, Database, Layers, File, Brain, Download, Monitor, Server, Loader2, CheckCircle } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import { productApi, groupApi, localFilesApi } from '@/utils/api'
import { Product, FileEntry, FolderGroup } from '@/types'
import TrainingProgressModal from '@/components/TrainingProgressModal'
import { useAuth } from '@/context/AuthContext'

export default function Products() {
  const { user: authUser } = useAuth()
  const isAdmin = authUser?.role === 'admin' || authUser?.role === 'super_admin' || authUser?.role === 'tenant_admin' || authUser?.role === 'zero_admin'
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [trainingProductId, setTrainingProductId] = useState<string | null>(null)
  const [showProgressModal, setShowProgressModal] = useState(false)
  const queryClient = useQueryClient()
  
  const { data: products = [], isLoading } = useQuery({
    queryKey: ['products'],
    queryFn: () => productApi.list(),
  })
  
  const deleteMutation = useMutation({
    mutationFn: productApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      toast.success('Product deleted')
    },
    onError: () => {
      toast.error('Failed to delete product')
    },
  })
  
  const trainMutation = useMutation({
    mutationFn: productApi.trainAll,
    onSuccess: (data: any, productId: string) => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      
      // Open progress modal for this product
      setTrainingProductId(productId)
      setShowProgressModal(true)
      
      toast.success(`Training started for ${data.folder_groups || 0} folder group${(data.folder_groups || 0) === 1 ? '' : 's'}`)
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to start training')
    },
  })
  
  // Check if any product is currently training (for the floating reopen button)
  const anyTrainingProduct = products.find(p => 
    p.folder_groups.some(g => g.training_status === 'training')
  )

  return (
    <div className="px-12 pb-20 pt-8 max-w-7xl mx-auto">
      {/* Editorial Header */}
      <div className="mb-10">
        <h1 className="text-4xl font-headline font-bold tracking-tight mb-3">
          Manage your <span className="text-rt-primary-container italic">intelligent</span> assets.
        </h1>
        <p className="text-on-surface-variant text-lg max-w-2xl leading-relaxed mb-6">
          Curate, train, and deploy your specialized AI agents from a central editorial dashboard.
        </p>
        {isAdmin && (
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Create Product
          </button>
        )}
      </div>

      {/* Products */}
      {isLoading ? (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="h-6 bg-rt-surface rounded w-48 mb-4" />
              <div className="h-4 bg-rt-surface rounded w-full" />
            </div>
          ))}
        </div>
      ) : products.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="card text-center py-16"
        >
          <div className="icon-orb mx-auto mb-4"><Package className="w-6 h-6 text-rt-primary" /></div>
          <h3 className="text-xl font-headline font-bold mb-2">No Products</h3>
          <p className="text-on-surface-variant mb-6 max-w-md mx-auto">
            Create a product to organize your folder groups and start training.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary"
          >
            Create Your First Product
          </button>
        </motion.div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {products.map((product) => (
            <ProductCard
              key={product.product_id}
              product={product}
              isAdmin={isAdmin}
              onDelete={() => {
                if (confirm(`Delete "${product.product_name}" and all its folder groups?`)) {
                  deleteMutation.mutate(product.product_id)
                }
              }}
              onTrain={() => trainMutation.mutate(product.product_id)}
              isTraining={trainMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* Create Modal */}
      <AnimatePresence>
        {showCreateModal && (
          <CreateProductModal
            onClose={() => setShowCreateModal(false)}
          />
        )}
      </AnimatePresence>

      {/* Floating "View Training Progress" button — only when training is actually running */}
      <AnimatePresence>
        {!showProgressModal && anyTrainingProduct && (
          <motion.button
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            onClick={() => {
              setTrainingProductId(anyTrainingProduct.product_id)
              setShowProgressModal(true)
            }}
            className="fixed bottom-6 right-6 z-40 flex items-center gap-2 bg-rt-primary-container hover:bg-rt-primary text-[#2a1700] hover:text-white px-5 py-3 rounded-full editorial-shadow transition-all"
          >
            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            <span className="text-sm font-medium">View Training Progress</span>
          </motion.button>
        )}
      </AnimatePresence>

      {/* Training Progress Modal */}
      <AnimatePresence>
        {showProgressModal && trainingProductId && (
          <TrainingProgressModal
            productId={trainingProductId}
            onClose={() => {
              setShowProgressModal(false)
              setTrainingProductId(null)
              queryClient.invalidateQueries({ queryKey: ['products'] })
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

function ProductCard({
  product,
  isAdmin,
  onDelete,
  onTrain,
  isTraining,
}: {
  product: Product
  isAdmin: boolean
  onDelete: () => void
  onTrain: () => void
  isTraining: boolean
}) {
  const [showDescription, setShowDescription] = useState(false)
  const [showAddGroupModal, setShowAddGroupModal] = useState(false)
  const [showTrainingLog, setShowTrainingLog] = useState(false)
  const [showTrainingTree, setShowTrainingTree] = useState(false)
  const queryClient = useQueryClient()

  const removeGroupMutation = useMutation({
    mutationFn: () => productApi.removeFolderGroup(product.product_id, ''),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      toast.success('Folder group removed')
    },
    onError: () => {
      toast.error('Failed to remove folder group')
    },
  })

  const groupTypeColors: Record<string, string> = {
    code: 'bg-blue-500/10 text-blue-400',
    documentation: 'bg-green-500/10 text-green-400',
    diagrams: 'bg-purple-500/10 text-purple-400',
    configuration: 'bg-yellow-500/10 text-yellow-400',
    tickets: 'bg-orange-500/10 text-orange-400',
    other: 'bg-gray-500/10 text-rt-text-muted',
  }

  return (
    <div className="card !p-4 flex flex-col h-full min-h-0">
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <div className="flex items-center gap-2.5 flex-1 min-w-0">
          <Package className="w-5 h-5 text-rt-primary flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <button
              onClick={() => product.description && setShowDescription(!showDescription)}
              className={`text-left ${product.description ? 'cursor-pointer hover:text-rt-primary transition-colors' : ''}`}
            >
              <h2 className="text-lg font-display font-semibold truncate">{product.product_name}</h2>
            </button>
            {product.description && showDescription && (
              <div className="mt-1 text-xs text-rt-text-muted leading-relaxed">
                {product.description}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs text-rt-text-muted">
            {product.folder_groups.length} {product.folder_groups.length === 1 ? 'group' : 'groups'}
          </span>
          {isAdmin && product.folder_groups.length > 0 && (
            <button
              onClick={onTrain}
              disabled={isTraining || product.folder_groups.some(g => g.training_status === 'training')}
              className="btn-primary text-xs py-1 px-2.5 flex items-center gap-1.5"
            >
              <Play className="w-3 h-3" />
              {isTraining ? 'Starting...' : 'Train'}
            </button>
          )}
          {isAdmin && (
            <button
              onClick={onDelete}
              className="p-1.5 rounded text-rt-text-muted hover:text-rt-accent hover:bg-rt-accent/10 transition-all"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Training Results — fixed height for consistent card layout */}
      <div className="mb-3 min-h-0 overflow-y-auto rounded-lg border border-rt-border bg-rt-bg-light/50 flex-shrink-0 max-h-[180px]">
      {(() => {
        // Get stats from any group that has training metadata (logs, files_kept, or legacy files_discovered)
        const statsGroup = product.folder_groups.find(g => g.metadata && (
          Array.isArray(g.metadata.logs) ||
          g.metadata.files_kept != null ||
          g.metadata.files_discovered != null ||
          g.metadata.phase === 'completed'
        ))
        const stats = statsGroup?.metadata as Record<string, any> | undefined
        const isAnyTraining = product.folder_groups.some(g => g.training_status === 'training')
        const isAnyCompleted = product.folder_groups.some(g => g.training_status === 'completed' && g.last_trained)
        const isAnyFailed = product.folder_groups.some(g => g.training_status === 'failed')
        
        if (isAnyTraining) {
          return (
            <div className="mb-4 p-3 bg-yellow-500/5 border border-yellow-500/20 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 border-2 border-yellow-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm text-yellow-400">Training in progress…</span>
              </div>
              <button
                onClick={async () => {
                  if (!confirm('Stop training?')) return
                  try {
                    await productApi.stopTraining(product.product_id)
                    queryClient.invalidateQueries({ queryKey: ['products'] })
                  } catch (e: any) {
                    // If stop fails, force refresh anyway
                    queryClient.invalidateQueries({ queryKey: ['products'] })
                  }
                }}
                className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 transition-colors"
              >
                Stop
              </button>
            </div>
          )
        }
        
        if (isAnyFailed && !isAnyCompleted) {
          const failedGroup = product.folder_groups.find(g => g.training_status === 'failed')
          const failMeta = failedGroup?.metadata as Record<string, any> | undefined
          const failLogs = failMeta?.logs as string[] | undefined
          return (
            <div className="mb-4 p-3 bg-red-500/5 border border-red-500/20 rounded-lg">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-4 h-4 text-red-400" />
                <span className="text-sm text-red-400">
                  {failMeta?.message || 'Training failed. Check your LLM API key in Settings.'}
                </span>
              </div>
              {failLogs && failLogs.length > 0 && (
                <div className="mt-2 pt-2 border-t border-red-500/20">
                  <button
                    onClick={() => setShowTrainingLog(!showTrainingLog)}
                    className="flex items-center gap-1.5 text-xs text-red-300 hover:text-red-200 transition-colors"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                      <polyline points="14 2 14 8 20 8"/>
                      <line x1="16" y1="13" x2="8" y2="13"/>
                      <line x1="16" y1="17" x2="8" y2="17"/>
                      <line x1="10" y1="9" x2="8" y2="9"/>
                    </svg>
                    {showTrainingLog ? 'Hide Training Log' : 'View Training Log'} ({failLogs.length} entries)
                  </button>
                  {showTrainingLog && (
                    <div className="mt-2 bg-rt-surface rounded-lg border border-red-500/20 p-3 font-mono text-xs text-rt-text max-h-48 overflow-y-auto">
                      {failLogs.map((log: string, i: number) => (
                        <div key={i} className="leading-5 whitespace-pre-wrap">{log}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        }

        if (stats && isAnyCompleted) {
          const breakdown = (stats.classification_breakdown || {}) as Record<string, number>
          // Pipeline stores chunk_map_entries (total chunks), files_kept, files_extracted
          const knowledgeTrained = (stats.chunk_map_entries || stats.chunks_created || stats.chunks_indexed || 0) as number
          const filesKept = (stats.files_kept || stats.files_extracted || stats.files_discovered || 0) as number
          
          return (
            <div className="mb-3 p-3 bg-rt-surface rounded-lg border border-rt-border">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-medium flex items-center gap-1.5">
                  <Database className="w-3.5 h-3.5 text-rt-primary" />
                  Training Results
                </h3>
                {statsGroup?.last_trained && (
                  <span className="text-xs text-rt-text-muted">
                    {new Date(statsGroup.last_trained).toLocaleString()}
                  </span>
                )}
              </div>
              
              {/* Single training metric */}
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-gradient-to-r from-rt-primary/10 to-purple-500/10 rounded-lg p-2 border border-rt-primary/20">
                  <div className="text-[10px] text-rt-text-muted mb-0.5">KB Items Trained</div>
                  <div className="text-lg font-bold text-rt-primary">
                    {knowledgeTrained.toLocaleString()}
                  </div>
                </div>
              </div>
              
              {Object.keys(breakdown).length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {Object.entries(breakdown).map(([type, count]) => (
                    <span key={type} className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-rt-bg text-xs">
                      {type === 'code' && <FileCode className="w-3 h-3 text-blue-400" />}
                      {type === 'doc' && <FileText className="w-3 h-3 text-green-400" />}
                      {type === 'diagram_image' && <Image className="w-3 h-3 text-purple-400" />}
                      {type === 'ticket_export' && <TicketIcon className="w-3 h-3 text-orange-400" />}
                      {!['code', 'doc', 'diagram_image', 'ticket_export'].includes(type) && <Folder className="w-3 h-3 text-rt-text-muted" />}
                      <span className="text-rt-text-muted">{type}:</span>
                      <span className="font-medium">{(count as number).toLocaleString()}</span>
                    </span>
                  ))}
                </div>
              )}

              {/* View Training Tree + Log buttons */}
              <div className="mt-3 pt-3 border-t border-rt-border flex flex-wrap gap-4">
                {/* Training Tree button */}
                <button
                  onClick={() => setShowTrainingTree(!showTrainingTree)}
                  className="flex items-center gap-1.5 text-xs text-rt-text-muted hover:text-rt-text transition-colors"
                >
                  <FolderTree className="w-3.5 h-3.5" />
                  {showTrainingTree ? 'Hide Training Map' : 'View Training Map'}
                </button>

                {/* Training Log button */}
                {stats.logs && Array.isArray(stats.logs) && (stats.logs as string[]).length > 0 && (
                  <button
                    onClick={() => setShowTrainingLog(!showTrainingLog)}
                    className="flex items-center gap-1.5 text-xs text-rt-text-muted hover:text-rt-text transition-colors"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                      <polyline points="14 2 14 8 20 8"/>
                      <line x1="16" y1="13" x2="8" y2="13"/>
                      <line x1="16" y1="17" x2="8" y2="17"/>
                      <line x1="10" y1="9" x2="8" y2="9"/>
                    </svg>
                    {showTrainingLog ? 'Hide Training Log' : 'View Training Log'} ({(stats.logs as string[]).length} entries)
                  </button>
                )}
              </div>

              {/* Training Tree View */}
              {showTrainingTree && (
                <div className="mt-2">
                  <TrainingTreeView productId={product.product_id} />
                </div>
              )}

              {/* Training Log */}
              {showTrainingLog && stats.logs && Array.isArray(stats.logs) && (
                <div className="mt-2 bg-rt-surface rounded-lg border border-rt-border p-3 font-mono text-xs text-rt-text max-h-60 overflow-y-auto">
                  {(stats.logs as string[]).map((log: string, i: number) => (
                    <div key={i} className="leading-5 whitespace-pre-wrap">
                      {log}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        }
        
        return null
      })()}
      </div>


      {/* Training Data — fixed height for consistent card layout */}
      <div className="space-y-2 mb-3 flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-rt-text-muted">Training Data</h3>
          <button
            onClick={() => setShowAddGroupModal(true)}
            className="text-sm text-rt-primary hover:underline flex items-center gap-1"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Training Data
          </button>
        </div>
        <div className="max-h-[120px] overflow-y-auto rounded-lg border border-rt-border bg-rt-bg-light/50">
        {product.folder_groups.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center py-4 bg-rt-surface/50 rounded-lg border border-dashed border-rt-border">
            <p className="text-xs text-rt-text-muted mb-2">No training data added yet</p>
            <button
              onClick={() => setShowAddGroupModal(true)}
              className="btn-secondary text-sm"
            >
              Add Training Data
            </button>
          </div>
        ) : (
          <div className="p-2 space-y-0.5">
              {product.folder_groups.map((group) => {
                return (
                  <div key={group.group_id} className="flex items-center gap-2 py-1 text-xs group/row">
                    <Folder className="w-3 h-3 text-rt-primary flex-shrink-0" />
                    <span className="font-medium truncate">{group.group_name}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] flex-shrink-0 ${groupTypeColors[group.group_type] || groupTypeColors.other}`}>
                      {group.group_type === 'other' ? 'auto-detect' : group.group_type}
                    </span>
                    <span className={`text-[10px] flex-shrink-0 ${
                      group.training_status === 'completed' ? 'text-green-400' :
                      group.training_status === 'failed' ? 'text-red-400' :
                      group.training_status === 'training' ? 'text-blue-400' :
                      'text-rt-text-muted'
                    }`}>{group.training_status}</span>
                    <button
                      onClick={() => {
                        if (confirm(`Delete "${group.group_name}"?`)) {
                          productApi.removeFolderGroup(product.product_id, group.group_id)
                            .then(() => {
                              queryClient.invalidateQueries({ queryKey: ['products'] })
                              toast.success('Removed')
                            })
                            .catch(() => toast.error('Failed'))
                        }
                      }}
                      className="p-0.5 rounded text-rt-text-muted hover:text-red-400 opacity-0 group-hover/row:opacity-100 transition-all ml-auto"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                )
              })}
          </div>
        )}
        </div>
      </div>

      {/* Add Group Modal */}
      <AnimatePresence>
        {showAddGroupModal && (
          <AddGroupModal
            productId={product.product_id}
            onClose={() => setShowAddGroupModal(false)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}



function CreateProductModal({
  onClose,
}: {
  onClose: () => void
}) {
  const [productName, setProductName] = useState('')
  const [description, setDescription] = useState('')
  const [autoGenerateDescription, setAutoGenerateDescription] = useState(true)
  const queryClient = useQueryClient()
  
  const createMutation = useMutation({
    mutationFn: productApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      toast.success('Product created!')
      onClose()
    },
    onError: () => {
      toast.error('Failed to create product')
    },
  })
  
  const handleCreate = () => {
    if (!productName.trim()) {
      toast.error('Please enter a product name')
      return
    }
    
    createMutation.mutate({
      product_name: productName,
      description: description || undefined,
      auto_generate_description: autoGenerateDescription,
    })
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="bg-rt-bg-light border border-rt-border rounded-xl p-6 w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-display font-semibold mb-6">Create Product</h2>
        
        <div className="space-y-4 mb-6">
          <div>
            <label className="label">Product Name</label>
            <input
              type="text"
              className="input"
              placeholder="e.g., My Application"
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
            />
          </div>
          
          <div>
            <label className="label">Description (optional)</label>
            <textarea
              className="input"
              placeholder="Describe this product..."
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="auto-generate-desc"
              checked={autoGenerateDescription}
              onChange={(e) => setAutoGenerateDescription(e.target.checked)}
              className="w-4 h-4 rounded border-rt-border bg-rt-bg text-blue-600 focus:ring-2 focus:ring-blue-500"
            />
            <label htmlFor="auto-generate-desc" className="text-sm text-rt-text cursor-pointer">
              Auto-generate description using AI after first training
            </label>
          </div>
        </div>
        
        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={createMutation.isPending}
            className="btn-primary"
          >
            {createMutation.isPending ? 'Creating...' : 'Create Product'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}

interface TrainingEntry {
  path: string
  contentType: string
}

const CONTENT_TYPES = [
  { value: 'other', label: 'Auto-detect' },
  { value: 'code', label: 'Code' },
  { value: 'documentation', label: 'Documentation' },
  { value: 'tickets', label: 'Tickets / Issues' },
]

function AddGroupModal({
  productId,
  onClose,
}: {
  productId: string
  onClose: () => void
}) {
  const [curType, setCurType] = useState('other')
  const [showBrowser, setShowBrowser] = useState(false)
  const [entries, setEntries] = useState<TrainingEntry[]>([])
  const [submitting, setSubmitting] = useState(false)
  const queryClient = useQueryClient()

  const removeEntry = (index: number) => {
    setEntries(prev => prev.filter((_, i) => i !== index))
  }

  const handleBrowseConfirm = (selectedPaths: string[]) => {
    const existing = new Set(entries.map(e => e.path))
    const newEntries = selectedPaths
      .filter(p => !existing.has(p))
      .map(p => ({ path: p, contentType: curType }))
    setEntries(prev => [...prev, ...newEntries])
    setShowBrowser(false)
  }

  const handleSubmit = async () => {
    if (entries.length === 0) {
      toast.error('Add at least one entry')
      return
    }

    setSubmitting(true)
    try {
      // Group entries by contentType → one folder group per type
      const groups: Record<string, { contentType: string; paths: string[] }> = {}
      for (const e of entries) {
        const key = e.contentType
        if (!groups[key]) groups[key] = { contentType: e.contentType, paths: [] }
        groups[key].paths.push(e.path)
      }

      for (const g of Object.values(groups)) {
        const label = CONTENT_TYPES.find(t => t.value === g.contentType)?.label || g.contentType
        const shortName = g.paths.length === 1
          ? g.paths[0].split('/').slice(-1)[0] || 'data'
          : `${label} (${g.paths.length} folders)`

        await productApi.addFolderGroup(productId, {
          pod_id: '__local__',
          group_name: shortName,
          group_type: g.contentType,
          folder_paths: g.paths.map(p => ({ absolute_path: p, scan_recursive: true })),
        })
      }

      queryClient.invalidateQueries({ queryKey: ['products'] })
      toast.success(`Added ${entries.length} training ${entries.length === 1 ? 'path' : 'paths'}`)
      onClose()
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to add training data')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="bg-rt-bg-light border border-rt-border rounded-xl p-5 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-display font-semibold">Add Training Data</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-rt-surface"><X className="w-4 h-4" /></button>
        </div>

        {/* Controls */}
        <div className="space-y-2 mb-3">
          <div className="flex items-center gap-2">
            <select
              value={curType}
              onChange={(e) => setCurType(e.target.value)}
              className="bg-rt-surface border border-rt-border rounded px-2 py-1.5 text-xs focus:outline-none focus:border-rt-primary flex-1 min-w-0"
            >
              {CONTENT_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => setShowBrowser(true)}
            className="w-full py-1.5 rounded bg-rt-primary text-white text-xs hover:bg-rt-primary-dark transition-colors flex items-center justify-center gap-1.5"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            Browse Folders
          </button>
        </div>

        {/* Entries */}
        {entries.length > 0 ? (
          <div className="border border-rt-border rounded overflow-hidden mb-3 max-h-40 overflow-y-auto">
            {entries.map((entry, index) => {
              const typeLabel = CONTENT_TYPES.find(t => t.value === entry.contentType)?.label || entry.contentType
              return (
                <div key={index} className="flex items-center gap-1.5 px-2 py-1 border-b border-rt-border last:border-b-0 hover:bg-rt-surface/30">
                  <Folder className="w-3 h-3 text-rt-primary flex-shrink-0" />
                  <span className="flex-1 font-mono truncate text-[11px]" title={entry.path}>{entry.path.split('/').slice(-2).join('/')}</span>
                  <span className="text-[10px] text-rt-text-muted flex-shrink-0">{typeLabel}</span>
                  <button onClick={() => removeEntry(index)} className="p-0.5 text-rt-text-muted hover:text-red-400"><X className="w-2.5 h-2.5" /></button>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-center py-3 rounded border border-dashed border-rt-border mb-3 text-[11px] text-rt-text-muted">
            Select folders to add
          </div>
        )}

        <div className="flex items-center justify-end gap-2">
          <button onClick={onClose} className="btn-secondary text-xs py-1 px-2.5">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={submitting || entries.length === 0}
            className="btn-primary text-xs py-1 px-2.5"
          >
            {submitting ? 'Saving…' : entries.length > 0 ? `Save ${entries.length}` : 'Save'}
          </button>
        </div>

        <AnimatePresence>
          {showBrowser && (
            <FileBrowserModal
              selectedPaths={entries.map(e => e.path)}
              onConfirm={handleBrowseConfirm}
              onClose={() => setShowBrowser(false)}
            />
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  )
}

// ProductAgents removed for community edition
// Training Tree View – hierarchical visualization of indexed training data
// ---------------------------------------------------------------------------

interface TreeFile {
  path: string
  name: string
  chunks: number
}

interface TreeSubCategory {
  name: string
  chunks: number
  files: TreeFile[]
  file_count: number
}

interface TreeType {
  type: string
  chunks: number
  file_count: number
  sub_categories: TreeSubCategory[]
}

interface TrainingTree {
  product_id: string
  product_name: string
  total_chunks: number
  total_files: number
  tree: TreeType[]
}

const TYPE_CONFIG: Record<string, { icon: typeof FileCode; color: string; label: string }> = {
  code: { icon: FileCode, color: 'text-blue-400', label: 'Code' },
  doc: { icon: FileText, color: 'text-green-400', label: 'Documentation' },
  ticket_export: { icon: TicketIcon, color: 'text-orange-400', label: 'Tickets / Issues' },
  diagram_image: { icon: Image, color: 'text-purple-400', label: 'Diagrams' },
  doc_with_diagrams: { icon: Image, color: 'text-indigo-400', label: 'Docs with Diagrams' },
  summary: { icon: Brain, color: 'text-yellow-400', label: 'Summaries (auto-generated)' },
  other: { icon: Folder, color: 'text-rt-text-muted', label: 'Other' },
}

function TrainingTreeView({ productId }: { productId: string }) {
  const { data, isLoading, error } = useQuery<TrainingTree>({
    queryKey: ['training-tree', productId],
    queryFn: () => productApi.getTrainingTree(productId),
  })
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set())
  const [expandedSubCats, setExpandedSubCats] = useState<Set<string>>(new Set())

  const toggleType = (type: string) => {
    const next = new Set(expandedTypes)
    if (next.has(type)) next.delete(type)
    else next.add(type)
    setExpandedTypes(next)
  }

  const toggleSubCat = (key: string) => {
    const next = new Set(expandedSubCats)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setExpandedSubCats(next)
  }

  if (isLoading) {
    return (
      <div className="p-4 bg-rt-surface rounded-lg border border-rt-border text-center text-sm text-rt-text-muted">
        Loading training map…
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 bg-rt-surface rounded-lg border border-rt-border text-center text-sm text-rt-text-muted">
        Error loading training map: {error instanceof Error ? error.message : 'Unknown error'}
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-4 bg-rt-surface rounded-lg border border-rt-border text-center text-sm text-rt-text-muted">
        Loading training map…
      </div>
    )
  }

  if (data.tree.length === 0) {
    return (
      <div className="p-4 bg-rt-surface rounded-lg border border-rt-border text-center text-sm text-rt-text-muted">
        No training data found. Train this product first.
      </div>
    )
  }

  // Calculate total knowledge coverage
  const totalKnowledgeItems = data.total_chunks
  const totalDocuments = data.total_files
  const knowledgeCoverage = totalKnowledgeItems > 0 ? Math.round((totalKnowledgeItems / Math.max(totalDocuments * 10, 1)) * 100) : 0

  return (
    <div className="bg-rt-surface rounded-lg border border-rt-border p-4 text-rt-text">
      {/* Header with brain visualization */}
      <div className="mb-4 pb-4 border-b border-rt-border">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="relative">
              <Brain className="w-6 h-6 text-rt-primary" />
              <div className="absolute -top-1 -right-1 w-3 h-3 bg-rt-primary/20 rounded-full animate-pulse" />
            </div>
            <div>
              <h3 className="text-sm font-semibold">{data.product_name}</h3>
              <p className="text-xs text-rt-text-muted">Knowledge Base Overview</p>
            </div>
          </div>
        </div>
        
        {/* Single training metric */}
        <div className="mt-3">
          <div className="bg-gradient-to-r from-rt-primary/10 to-purple-500/10 rounded-lg p-2 border border-rt-primary/20">
            <div className="text-[10px] text-rt-text-muted mb-0.5">KB Items Trained</div>
            <div className="text-xl font-bold text-rt-primary">{totalKnowledgeItems.toLocaleString()}</div>
          </div>
        </div>
      </div>

      {/* Knowledge categories - brain structure */}
      <div className="space-y-2 max-h-[450px] overflow-y-auto">
        {data.tree.map((typeNode) => {
          const config = TYPE_CONFIG[typeNode.type] || TYPE_CONFIG.other
          const TypeIcon = config.icon
          const isExpanded = expandedTypes.has(typeNode.type)
          const knowledgePercentage = totalKnowledgeItems > 0 ? Math.round((typeNode.chunks / totalKnowledgeItems) * 100) : 0

          return (
            <div key={typeNode.type} className="bg-rt-bg/30 rounded-lg border border-rt-border/50 overflow-hidden">
              {/* Category header */}
              <button
                onClick={() => toggleType(typeNode.type)}
                className="w-full flex items-center gap-3 py-2.5 px-3 hover:bg-rt-bg/50 transition-colors text-left"
              >
                <div className={`p-1.5 rounded-lg ${
                  config.color === 'text-blue-400' ? 'bg-blue-400/10' :
                  config.color === 'text-green-400' ? 'bg-green-400/10' :
                  config.color === 'text-orange-400' ? 'bg-orange-400/10' :
                  config.color === 'text-purple-400' ? 'bg-purple-400/10' :
                  config.color === 'text-indigo-400' ? 'bg-indigo-400/10' :
                  config.color === 'text-yellow-400' ? 'bg-yellow-400/10' :
                  'bg-rt-text-muted/10'
                }`}>
                  <TypeIcon className={`w-4 h-4 ${config.color} flex-shrink-0`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-rt-text">{config.label}</div>
                  <div className="text-xs text-rt-text-muted mt-0.5">
                    {typeNode.file_count} {typeNode.file_count === 1 ? 'document' : 'documents'} · {typeNode.chunks.toLocaleString()} knowledge items
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <div className="w-16 h-1.5 bg-rt-border rounded-full overflow-hidden">
                    <div 
                      className={`h-full transition-all ${
                        config.color === 'text-blue-400' ? 'bg-blue-400' :
                        config.color === 'text-green-400' ? 'bg-green-400' :
                        config.color === 'text-orange-400' ? 'bg-orange-400' :
                        config.color === 'text-purple-400' ? 'bg-purple-400' :
                        config.color === 'text-indigo-400' ? 'bg-indigo-400' :
                        config.color === 'text-yellow-400' ? 'bg-yellow-400' :
                        'bg-rt-text-muted'
                      }`}
                      style={{ width: `${knowledgePercentage}%` }}
                    />
                  </div>
                  <span className="text-xs text-rt-text-muted w-10 text-right">{knowledgePercentage}%</span>
                  {isExpanded ? <ChevronDown className="w-4 h-4 text-rt-text-muted" /> : <ChevronRight className="w-4 h-4 text-rt-text-muted" />}
                </div>
              </button>

              {/* Sub-categories - expanded view */}
              {isExpanded && typeNode.sub_categories.length > 0 && (
                <div className="border-t border-rt-border/50 bg-rt-bg/20">
                  {typeNode.sub_categories.map((subCat) => {
                    const subKey = `${typeNode.type}:${subCat.name}`
                    const isSubExpanded = expandedSubCats.has(subKey)

                    return (
                      <div key={subKey} className="border-b border-rt-border/30 last:border-b-0">
                        <button
                          onClick={() => toggleSubCat(subKey)}
                          className="w-full flex items-center gap-2 py-2 px-4 hover:bg-rt-bg/30 transition-colors text-left"
                        >
                          <Layers className="w-3.5 h-3.5 text-rt-text-muted/60 flex-shrink-0" />
                          <span className="text-xs text-rt-text flex-1">{subCat.name}</span>
                          <span className="text-xs text-rt-text-muted">
                            {subCat.file_count} docs · {subCat.chunks.toLocaleString()} items
                          </span>
                          {isSubExpanded ? <ChevronDown className="w-3 h-3 text-rt-text-muted ml-2" /> : <ChevronRight className="w-3 h-3 text-rt-text-muted ml-2" />}
                        </button>

                        {/* Individual documents */}
                        {isSubExpanded && subCat.files.length > 0 && (
                          <div className="bg-rt-bg/10 pl-4 pr-2 py-1.5 space-y-1">
                            {subCat.files.map((file) => (
                              <div
                                key={file.path}
                                className="flex items-center gap-2 py-1 px-2 rounded hover:bg-rt-bg/20 transition-colors group"
                                title={file.path}
                              >
                                <File className="w-3 h-3 text-rt-text-muted/60 flex-shrink-0" />
                                <span className="text-xs text-rt-text-muted flex-1 truncate">
                                  {file.name}
                                </span>
                                <span className="text-xs text-rt-text-muted/80 font-medium">
                                  {file.chunks} items
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}


function FileBrowserModal({
  selectedPaths,
  onConfirm,
  onClose,
}: {
  selectedPaths: string[]
  onConfirm: (paths: string[]) => void
  onClose: () => void
}) {
  const [currentPath, setCurrentPath] = useState('/')
  const [selected, setSelected] = useState<Set<string>>(new Set(selectedPaths))
  
  const { data: directory, isLoading } = useQuery({
    queryKey: ['local-browse', currentPath],
    queryFn: () => localFilesApi.browse(currentPath),
  })
  
  const pathParts = currentPath.split('/').filter(Boolean)
  
  const togglePath = (path: string) => {
    const newSelected = new Set(selected)
    if (newSelected.has(path)) {
      newSelected.delete(path)
    } else {
      newSelected.add(path)
    }
    setSelected(newSelected)
  }
  
  const handleConfirm = () => {
    onConfirm(Array.from(selected))
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="bg-rt-bg-light border border-rt-border rounded-xl p-6 w-full max-w-3xl h-[600px] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-display font-semibold mb-4">Browse Folders</h2>
        
        <div className="flex items-center gap-1 text-sm mb-4 overflow-x-auto bg-rt-surface rounded-lg px-3 py-2">
          <button
            onClick={() => setCurrentPath('/')}
            className={`px-2 py-1 rounded hover:bg-rt-border transition-colors ${
              currentPath === '/' ? 'text-rt-primary' : ''
            }`}
          >
            Root
          </button>
          {pathParts.map((part, i) => (
            <div key={i} className="flex items-center">
              <ChevronRight className="w-4 h-4 text-rt-text-muted" />
              <button
                onClick={() => setCurrentPath('/' + pathParts.slice(0, i + 1).join('/'))}
                className={`px-2 py-1 rounded hover:bg-rt-border transition-colors ${
                  i === pathParts.length - 1 ? 'text-rt-primary' : ''
                }`}
              >
                {part}
              </button>
            </div>
          ))}
        </div>
        
        <div className="flex-1 border border-rt-border rounded-lg overflow-hidden flex flex-col">
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center text-rt-text-muted">
              Loading...
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto divide-y divide-rt-border">
              {currentPath !== '/' && (
                <button
                  onClick={() => {
                    const parent = '/' + pathParts.slice(0, -1).join('/')
                    setCurrentPath(parent || '/')
                  }}
                  className="w-full flex items-center gap-3 p-3 hover:bg-rt-surface transition-colors text-left"
                >
                  <FolderOpen className="w-5 h-5 text-rt-primary" />
                  <span>..</span>
                </button>
              )}
              
              {directory?.files
                .filter((f: FileEntry) => f.type === 'directory')
                .map((file: FileEntry) => (
                  <div
                    key={file.path}
                    className="flex items-center gap-3 p-3 hover:bg-rt-surface transition-colors group"
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(file.path)}
                      onChange={() => togglePath(file.path)}
                      className="w-4 h-4 rounded border-rt-border bg-rt-surface text-rt-primary focus:ring-rt-primary"
                    />
                    <button
                      onClick={() => setCurrentPath(file.path)}
                      className="flex items-center gap-3 flex-1 text-left"
                    >
                      <Folder className="w-5 h-5 text-rt-primary" />
                      <span className="truncate">{file.name}</span>
                    </button>
                    {selected.has(file.path) && (
                      <div className="badge badge-success text-xs">
                        <Check className="w-3 h-3" />
                      </div>
                    )}
                  </div>
                ))}
            </div>
          )}
        </div>
        
        <div className="text-sm text-rt-text-muted mt-4">
          {selected.size} {selected.size === 1 ? 'folder' : 'folders'} selected
        </div>
        
        <div className="flex gap-3 justify-end mt-4">
          <button onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={selected.size === 0}
            className="btn-primary"
          >
            Add Selected Paths
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
