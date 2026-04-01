import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Loader2, ArrowLeft, CheckCircle2, XCircle,
  AlertTriangle,
} from 'lucide-react'
import { brainApi } from '@/utils/api'
import type { ApprovalRequest } from '@/types/brain'

export default function BrainApprovals() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('pending')
  const [denyReason, setDenyReason] = useState('')
  const [denyingId, setDenyingId] = useState<string | null>(null)

  const { data: approvals, isLoading } = useQuery<ApprovalRequest[]>({
    queryKey: ['approvals', statusFilter],
    queryFn: () => brainApi.listApprovals(statusFilter),
    refetchInterval: 10000,
  })

  const decideMutation = useMutation({
    mutationFn: ({ requestId, approved, reason }: { requestId: string; approved: boolean; reason?: string }) =>
      brainApi.decideApproval(requestId, approved, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] })
      queryClient.invalidateQueries({ queryKey: ['approval-count'] })
      setDenyingId(null)
      setDenyReason('')
    },
  })

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
        <div>
          <h1 className="text-4xl font-headline font-bold mb-2">Approval Queue</h1>
          <p className="text-on-surface-variant">
            Review and approve actions your Brains want to take.
          </p>
        </div>
        <div className="flex gap-1 bg-rt-bg-lighter rounded-xl p-1">
          {['pending', 'approved', 'denied'].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors capitalize ${
                statusFilter === s ? 'bg-rt-surface text-rt-text shadow-sm' : 'text-rt-text-muted hover:text-rt-text'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </motion.div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20 gap-3 text-rt-text-muted">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : approvals?.length === 0 ? (
        <div className="text-center py-20">
          <CheckCircle2 className="w-12 h-12 text-green-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium mb-1">
            {statusFilter === 'pending' ? 'All caught up!' : `No ${statusFilter} approvals`}
          </h3>
          <p className="text-sm text-rt-text-muted">
            {statusFilter === 'pending'
              ? 'No actions waiting for your approval.'
              : 'Nothing to show for this filter.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {approvals?.map((approval, i) => (
            <motion.div
              key={approval.request_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
              className="p-5 rounded-2xl border border-rt-border bg-rt-surface"
            >
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-xl bg-yellow-50 flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="w-5 h-5 text-yellow-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-rt-text-muted capitalize">{approval.action_type}</span>
                    <span className="text-rt-border">·</span>
                    <StatusPill status={approval.status} />
                  </div>
                  <p className="text-sm font-medium mb-1">{approval.action_summary}</p>
                  {approval.created_at && (
                    <p className="text-[10px] text-rt-text-muted">
                      {new Date(approval.created_at).toLocaleString()}
                    </p>
                  )}
                  {approval.denial_reason && (
                    <p className="text-xs text-red-500 mt-1">Reason: {approval.denial_reason}</p>
                  )}
                </div>

                {approval.status === 'pending' && (
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {denyingId === approval.request_id ? (
                      <div className="flex items-center gap-2">
                        <input
                          value={denyReason}
                          onChange={(e) => setDenyReason(e.target.value)}
                          placeholder="Reason (optional)"
                          className="px-3 py-1.5 text-xs rounded-lg bg-rt-bg border border-rt-border w-40"
                          autoFocus
                        />
                        <button
                          onClick={() => decideMutation.mutate({ requestId: approval.request_id, approved: false, reason: denyReason })}
                          disabled={decideMutation.isPending}
                          className="px-3 py-1.5 text-xs rounded-lg bg-red-500 text-white hover:bg-red-600"
                        >
                          Confirm Deny
                        </button>
                        <button
                          onClick={() => { setDenyingId(null); setDenyReason('') }}
                          className="text-xs text-rt-text-muted"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          onClick={() => decideMutation.mutate({ requestId: approval.request_id, approved: true })}
                          disabled={decideMutation.isPending}
                          className="px-4 py-2 rounded-xl bg-green-500 text-white text-sm font-medium hover:bg-green-600 transition-colors flex items-center gap-1.5"
                        >
                          <CheckCircle2 className="w-4 h-4" /> Approve
                        </button>
                        <button
                          onClick={() => setDenyingId(approval.request_id)}
                          className="px-4 py-2 rounded-xl border border-red-200 text-red-500 text-sm font-medium hover:bg-red-50 transition-colors flex items-center gap-1.5"
                        >
                          <XCircle className="w-4 h-4" /> Deny
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}

function StatusPill({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'bg-yellow-50 text-yellow-600',
    approved: 'bg-green-50 text-green-600',
    denied: 'bg-red-50 text-red-600',
    expired: 'bg-gray-100 text-gray-500',
  }
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium capitalize ${styles[status] || styles.pending}`}>
      {status}
    </span>
  )
}
