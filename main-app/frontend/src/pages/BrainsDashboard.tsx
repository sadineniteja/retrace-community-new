import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Loader2, Plus, Bot, AlertCircle,
  Zap, TrendingUp, Bell, Trash2,
} from 'lucide-react'
import { brainApi } from '@/utils/api'
import type { Brain, DashboardOverview } from '@/types/brain'
import { BRAIN_ICONS } from '@/types/brain'

export default function BrainsDashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: (brainId: string) => brainApi.deleteBrain(brainId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brains-list'] })
      queryClient.invalidateQueries({ queryKey: ['brain-dashboard-overview'] })
    },
  })

  const { data: overview, isLoading: overviewLoading } = useQuery<DashboardOverview>({
    queryKey: ['brain-dashboard-overview'],
    queryFn: () => brainApi.dashboardOverview(),
    refetchInterval: 30000,
  })

  const { data: brains, isLoading: brainsLoading } = useQuery<Brain[]>({
    queryKey: ['brains-list'],
    queryFn: () => brainApi.listBrains(),
  })

  const { data: approvalData } = useQuery({
    queryKey: ['approval-count'],
    queryFn: () => brainApi.pendingApprovalCount(),
    refetchInterval: 15000,
  })

  const pendingApprovals = approvalData?.pending_count || overview?.pending_approvals || 0
  const isLoading = overviewLoading || brainsLoading

  return (
    <div className="px-12 pb-20 pt-8">
      {/* Header */}
      <motion.section
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-10 flex items-start justify-between"
      >
        <div>
          <h1 className="text-5xl font-headline font-bold tracking-tight mb-3">
            Your <span className="text-rt-primary-container italic">Brains</span>
          </h1>
          <p className="text-on-surface-variant text-lg max-w-xl">
            {overview?.brains.active
              ? `${overview.brains.active} Brain${overview.brains.active > 1 ? 's' : ''} actively working for you.`
              : 'Create your first Brain to get started.'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {pendingApprovals > 0 && (
            <Link
              to="/brains/approvals"
              className="relative px-4 py-2.5 rounded-xl bg-yellow-50 text-yellow-700 border border-yellow-200 hover:bg-yellow-100 transition-colors flex items-center gap-2 text-sm font-medium"
            >
              <Bell className="w-4 h-4" />
              {pendingApprovals} pending
            </Link>
          )}
          <Link
            to="/brains/new"
            className="px-5 py-2.5 rounded-xl bg-rt-primary text-white font-medium hover:opacity-90 transition-opacity flex items-center gap-2"
          >
            <Plus className="w-4 h-4" /> New Brain
          </Link>
        </div>
      </motion.section>

      {isLoading ? (
        <div className="flex items-center justify-center py-20 gap-3 text-rt-text-muted">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Loading...</span>
        </div>
      ) : (
        <>
          {/* Stats Row */}
          {overview && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
              <StatCard label="Active Brains" value={overview.brains.active} icon={<Bot className="w-5 h-5 text-green-500" />} />
              <StatCard label="Tasks Today" value={overview.today.tasks_completed} icon={<Zap className="w-5 h-5 text-blue-500" />} />
              <StatCard label="Cost Today" value={`$${(overview.today.cost_cents / 100).toFixed(2)}`} icon={<TrendingUp className="w-5 h-5 text-purple-500" />} />
              <StatCard label="Pending Approvals" value={pendingApprovals} icon={<AlertCircle className="w-5 h-5 text-yellow-500" />} />
            </div>
          )}

          {/* Brain Cards */}
          {brains && brains.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {brains.map((brain, i) => (
                <motion.div
                  key={brain.brain_id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <div className="group relative p-6 rounded-2xl border border-rt-border bg-rt-surface hover:shadow-lg hover:-translate-y-1 transition-all duration-200">
                    {/* Delete button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        if (confirm(`Delete "${brain.name}" and all its data?`)) {
                          deleteMutation.mutate(brain.brain_id)
                        }
                      }}
                      className="absolute top-3 right-3 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 text-rt-text-muted hover:text-red-500 hover:bg-red-50 transition-all z-10"
                      title="Delete Brain"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>

                    <Link
                      to={brain.setup_status === 'ready' || brain.status !== 'inactive'
                        ? `/brains/${brain.brain_id}`
                        : `/brains/${brain.brain_id}/setup`
                      }
                      className="block"
                    >
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div
                            className="w-12 h-12 rounded-xl flex items-center justify-center text-xl"
                            style={{ backgroundColor: (brain.color || '#6366f1') + '20' }}
                          >
                            {BRAIN_ICONS[brain.brain_type] || '🧠'}
                          </div>
                          <div>
                            <h3 className="font-bold group-hover:text-rt-primary transition-colors">
                              {brain.name}
                            </h3>
                            <p className="text-xs text-rt-text-muted capitalize">{brain.brain_type.replace('_', ' ')}</p>
                          </div>
                        </div>
                        <StatusBadge status={brain.status} setupStatus={brain.setup_status} />
                      </div>

                      {brain.description && (
                        <p className="text-sm text-rt-text-muted line-clamp-2 mb-4">{brain.description}</p>
                      )}

                      <div className="flex items-center justify-between text-xs text-rt-text-muted">
                        <div className="flex items-center gap-3">
                          <span className="flex items-center gap-1">
                            <Zap className="w-3 h-3" /> {brain.tasks_today} tasks today
                          </span>
                        </div>
                        <span className="capitalize text-[10px] px-2 py-0.5 rounded-full bg-rt-bg-lighter">
                          {brain.autonomy_level.replace('_', ' ')}
                        </span>
                      </div>
                    </Link>
                  </div>
                </motion.div>
              ))}

              {/* Add Brain Card */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: brains.length * 0.05 }}
              >
                <Link
                  to="/brains/new"
                  className="flex items-center justify-center h-full min-h-[180px] rounded-2xl border-2 border-dashed border-rt-border hover:border-rt-primary/50 hover:bg-rt-primary-fixed/5 transition-all text-rt-text-muted hover:text-rt-primary"
                >
                  <div className="text-center">
                    <Plus className="w-8 h-8 mx-auto mb-2" />
                    <span className="text-sm font-medium">Add Brain</span>
                  </div>
                </Link>
              </motion.div>
            </div>
          ) : (
            /* Empty State */
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center py-20"
            >
              <div className="w-20 h-20 rounded-2xl bg-rt-primary-fixed/20 flex items-center justify-center text-4xl mx-auto mb-6">
                🧠
              </div>
              <h2 className="text-2xl font-headline font-bold mb-3">No Brains yet</h2>
              <p className="text-rt-text-muted mb-8 max-w-md mx-auto">
                Create your first autonomous AI Brain. It'll ask you a few questions, connect to your accounts, and start working for you.
              </p>
              <Link
                to="/brains/new"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-rt-primary text-white font-medium hover:opacity-90 transition-opacity"
              >
                <Plus className="w-4 h-4" /> Create your first Brain
              </Link>
            </motion.div>
          )}
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, icon }: { label: string; value: number | string; icon: React.ReactNode }) {
  return (
    <div className="p-5 rounded-2xl border border-rt-border bg-rt-surface">
      <div className="flex items-center gap-3 mb-2">
        {icon}
        <span className="text-xs text-rt-text-muted font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  )
}

function StatusBadge({ status, setupStatus }: { status: string; setupStatus: string }) {
  if (setupStatus === 'interview' || setupStatus === 'pending') {
    return (
      <span className="text-[10px] px-2.5 py-1 rounded-full bg-blue-50 text-blue-600 font-medium">
        Setup needed
      </span>
    )
  }
  const colors: Record<string, string> = {
    active: 'bg-green-50 text-green-600',
    paused: 'bg-yellow-50 text-yellow-600',
    inactive: 'bg-gray-100 text-gray-500',
    error: 'bg-red-50 text-red-600',
  }
  return (
    <span className={`text-[10px] px-2.5 py-1 rounded-full font-medium capitalize ${colors[status] || colors.inactive}`}>
      {status === 'active' && <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 mr-1 animate-pulse" />}
      {status}
    </span>
  )
}
