import axios from 'axios'
import { FolderGroup, Product, TrainingJob, QueryResponse, DirectoryListing, AgentSession, AgentTool, Conversation } from '@/types'

/** Supabase access token used as API Bearer when using cloud auth (preferred over ReTrace JWT). */
export const RT_SUPABASE_ACCESS_TOKEN_KEY = 'rt_supabase_access_token'

export function getApiBearerToken(): string | null {
  return localStorage.getItem(RT_SUPABASE_ACCESS_TOKEN_KEY) || localStorage.getItem('rt_access_token')
}

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = getApiBearerToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/** Backend `product_id` query value for agent docs/SOPs not tied to a product. */
export const AGENT_GENERAL_SCOPE = '__none__'

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      if (localStorage.getItem(RT_SUPABASE_ACCESS_TOKEN_KEY)) {
        try {
          const { supabase, isSupabaseConfigured } = await import('@/lib/supabase')
          if (isSupabaseConfigured()) {
            const { data, error: refErr } = await supabase.auth.refreshSession()
            if (data.session?.access_token && !refErr) {
              localStorage.setItem(RT_SUPABASE_ACCESS_TOKEN_KEY, data.session.access_token)
              original.headers.Authorization = `Bearer ${data.session.access_token}`
              return api(original)
            }
          }
        } catch {
          /* fall through */
        }
        localStorage.removeItem(RT_SUPABASE_ACCESS_TOKEN_KEY)
        window.location.href = '/login'
        return Promise.reject(error)
      }
      const refresh = localStorage.getItem('rt_refresh_token')
      if (refresh) {
        try {
          const resp = await axios.post('/api/v1/auth/refresh', { refresh_token: refresh })
          localStorage.setItem('rt_access_token', resp.data.access_token)
          localStorage.setItem('rt_refresh_token', resp.data.refresh_token)
          original.headers.Authorization = `Bearer ${resp.data.access_token}`
          return api(original)
        } catch {
          localStorage.removeItem('rt_access_token')
          localStorage.removeItem('rt_refresh_token')
          window.location.href = '/login'
        }
      } else {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// Local filesystem browse (backend server)
export const localFilesApi = {
  browse: async (path: string = '/'): Promise<DirectoryListing> => {
    const response = await api.get('/files/browse', { params: { path } })
    return response.data
  },
}

// Product APIs
export const productApi = {
  list: async (): Promise<Product[]> => {
    const response = await api.get('/products')
    return response.data
  },
  
  get: async (productId: string): Promise<Product> => {
    const response = await api.get(`/products/${productId}`)
    return response.data
  },
  
  create: async (data: {
    product_name: string
    description?: string
    auto_generate_description?: boolean
    folder_groups?: Array<{
      pod_id: string
      group_name: string
      group_type: string
      folder_paths: Array<{
        absolute_path: string
        scan_recursive: boolean
        file_filters?: { include: string[]; exclude: string[] }
      }>
    }>
  }): Promise<Product> => {
    const response = await api.post('/products', data)
    return response.data
  },
  
  update: async (productId: string, data: Partial<{
    product_name: string
    description: string
  }>): Promise<Product> => {
    const response = await api.put(`/products/${productId}`, data)
    return response.data
  },
  
  delete: async (productId: string) => {
    const response = await api.delete(`/products/${productId}`)
    return response.data
  },
  
  addFolderGroup: async (productId: string, data: {
    pod_id: string
    group_name: string
    group_type: string
    folder_paths: Array<{
      absolute_path: string
      scan_recursive: boolean
      file_filters?: { include: string[]; exclude: string[] }
    }>
  }): Promise<FolderGroup> => {
    const response = await api.post(`/products/${productId}/groups`, data)
    return response.data
  },
  
  removeFolderGroup: async (productId: string, groupId: string) => {
    const response = await api.delete(`/products/${productId}/groups/${groupId}`)
    return response.data
  },
  
  trainAll: async (productId: string) => {
    const response = await api.post(`/products/${productId}/train`)
    return response.data
  },
  
  getTrainingStatus: async (productId: string) => {
    const response = await api.get(`/products/${productId}/training-status`)
    return response.data
  },
  
  stopTraining: async (productId: string) => {
    const response = await api.post(`/products/${productId}/stop-training`)
    return response.data
  },

  syncQA: async (productId: string, qaPairs: { question: string; answer: string }[]) => {
    const response = await api.post(`/products/${productId}/sync-qa`, { qa_pairs: qaPairs })
    return response.data
  },

  getTrainingTree: async (productId: string) => {
    const response = await api.get(`/products/${productId}/training-tree`)
    return response.data
  },

}

// Folder Group APIs (kept for backward compatibility and training)
export const groupApi = {
  startTraining: async (groupId: string) => {
    const response = await api.post(`/groups/${groupId}/train`)
    return response.data
  },
}

// Training APIs
export const trainingApi = {
  listJobs: async (groupId?: string, status?: string): Promise<TrainingJob[]> => {
    const response = await api.get('/training/jobs', {
      params: { group_id: groupId, status_filter: status }
    })
    return response.data
  },
  
  getJob: async (jobId: string): Promise<TrainingJob> => {
    const response = await api.get(`/training/jobs/${jobId}`)
    return response.data
  },
  
  cancelJob: async (jobId: string) => {
    const response = await api.post(`/training/jobs/${jobId}/cancel`)
    return response.data
  },
}

// Query APIs
export const queryApi = {
  ask: async (question: string, productIds: string[]): Promise<QueryResponse> => {
    const response = await api.post('/query', { question, product_ids: productIds })
    return response.data
  },
  
  getHistory: async (limit: number = 20) => {
    const response = await api.get('/query/history', { params: { limit } })
    return response.data
  },
  
  get: async (queryId: string): Promise<QueryResponse> => {
    const response = await api.get(`/query/${queryId}`)
    return response.data
  },
}

// Agent APIs
export const agentApi = {
  /** Returns the SSE endpoint URL (caller uses fetch + EventSource pattern) */
  getExecuteUrl: () => '/api/v1/agent/execute',

  listSessions: async (productId?: string): Promise<AgentSession[]> => {
    const response = await api.get('/agent/sessions', { params: { product_id: productId } })
    return response.data
  },

  getSession: async (sessionId: string): Promise<AgentSession> => {
    const response = await api.get(`/agent/sessions/${sessionId}`)
    return response.data
  },

  listTools: async (): Promise<AgentTool[]> => {
    const response = await api.get('/agent/tools')
    return response.data
  },

  updateAgentTools: async (disabledTools: string[]) => {
    const response = await api.patch('/settings/agent-tools', { disabled_tools: disabledTools })
    return response.data
  },

  // Conversations
  listConversations: async (productId: string): Promise<Conversation[]> => {
    const response = await api.get('/agent/conversations', { params: { product_id: productId || '__none__' } })
    return response.data
  },

  createConversation: async (productId: string, title?: string): Promise<Conversation> => {
    const response = await api.post('/agent/conversations', {
      product_id: productId || null,
      title: title || 'New conversation',
    })
    return response.data
  },

  getConversation: async (conversationId: string): Promise<Conversation> => {
    const response = await api.get(`/agent/conversations/${conversationId}`)
    return response.data
  },

  renameConversation: async (conversationId: string, title: string) => {
    const response = await api.put(`/agent/conversations/${conversationId}`, { title })
    return response.data
  },

  deleteConversation: async (conversationId: string) => {
    const response = await api.delete(`/agent/conversations/${conversationId}`)
    return response.data
  },

  deleteAllConversations: async (productId: string) => {
    const response = await api.delete(`/agent/conversations`, { params: { product_id: productId } })
    return response.data
  },

  saveMessages: async (conversationId: string, messages: Array<{
    type: string; content: string; iteration?: number; meta?: Record<string, any>
  }>) => {
    const response = await api.post(`/agent/conversations/${conversationId}/messages`, { messages })
    return response.data
  },

  // Learn This — train Q&A as expert knowledge
  learnThis: async (productId: string, question: string, answer: string) => {
    const response = await api.post('/agent/learn', { product_id: productId, question, answer })
    return response.data
  },

  // SOPs (Automations)
  listSOPs: async (productId: string) => {
    const response = await api.get('/agent/sops', { params: { product_id: productId } })
    return response.data
  },

  deleteSOP: async (sopId: string) => {
    const response = await api.delete(`/agent/sops/${sopId}`)
    return response.data
  },

  approveSOP: async (sopId: string, scheduleType: string = 'none', scheduleConfig?: Record<string, any>) => {
    const response = await api.put(`/agent/sops/${sopId}/approve`, {
      schedule_type: scheduleType,
      schedule_config: scheduleConfig || {},
    })
    return response.data
  },

  manualRun: async (sopId: string) => {
    const response = await api.post(`/agent/sops/${sopId}/run`)
    return response.data
  },

  listRuns: async (sopId: string) => {
    const response = await api.get(`/agent/sops/${sopId}/runs`)
    return response.data
  },

  updateSchedule: async (sopId: string, scheduleType: string, scheduleConfig?: Record<string, any>) => {
    const response = await api.put(`/agent/sops/${sopId}/schedule`, {
      schedule_type: scheduleType,
      schedule_config: scheduleConfig || {},
    })
    return response.data
  },

  // Documentation
  listDocs: async (productId: string) => {
    const response = await api.get('/agent/docs', { params: { product_id: productId } })
    return response.data
  },

  deleteDoc: async (docId: string) => {
    const response = await api.delete(`/agent/docs/${docId}`)
    return response.data
  },

  approveDoc: async (docId: string) => {
    const response = await api.put(`/agent/docs/${docId}/approve`)
    return response.data
  },

  // Dashboard
  getDashboardStats: async () => {
    const response = await api.get('/agent/dashboard-stats')
    return response.data
  },
}

// Channel API (Slack / Teams)
export const channelApi = {
  listConnections: async (productId?: string) => {
    const response = await api.get('/channels/connections', {
      params: productId ? { product_id: productId } : {},
    })
    return response.data
  },
  createConnection: async (data: {
    product_id: string
    platform: string
    channel_name: string
    channel_id: string
    bot_token: string
    team_id?: string
    auto_respond?: boolean
    ingest_history?: boolean
  }) => {
    const response = await api.post('/channels/connections', data)
    return response.data
  },
  updateConnection: async (connectionId: string, data: {
    is_active?: boolean
    auto_respond?: boolean
    ingest_history?: boolean
  }) => {
    const response = await api.patch(`/channels/${connectionId}`, data)
    return response.data
  },
  deleteConnection: async (connectionId: string) => {
    const response = await api.delete(`/channels/${connectionId}`)
    return response.data
  },
  testConnection: async (connectionId: string) => {
    const response = await api.post(`/channels/${connectionId}/test`)
    return response.data
  },
  syncConnection: async (connectionId: string) => {
    const response = await api.post(`/channels/${connectionId}/sync`)
    return response.data
  },
  previewMessages: async (connectionId: string) => {
    const response = await api.get(`/channels/${connectionId}/preview`)
    return response.data
  },
}

// ── Brain Platform API ─────────────────────────────────────────────

export const brainApi = {
  // Templates
  listTemplates: async () => {
    const r = await api.get('/brains/templates')
    return r.data
  },
  getTemplate: async (slug: string) => {
    const r = await api.get(`/brains/templates/${slug}`)
    return r.data
  },

  // Brain CRUD
  listBrains: async (status?: string) => {
    const r = await api.get('/brains', { params: status ? { status_filter: status } : {} })
    return r.data
  },
  getBrain: async (brainId: string) => {
    const r = await api.get(`/brains/${brainId}`)
    return r.data
  },
  createBrain: async (data: { name: string; template_slug?: string; template_id?: string; description?: string; autonomy_level?: string }) => {
    const r = await api.post('/brains', data)
    return r.data
  },
  updateBrain: async (brainId: string, data: Record<string, unknown>) => {
    const r = await api.put(`/brains/${brainId}`, data)
    return r.data
  },
  deleteBrain: async (brainId: string) => {
    await api.delete(`/brains/${brainId}`)
  },
  activateBrain: async (brainId: string) => {
    const r = await api.post(`/brains/${brainId}/activate`)
    return r.data
  },
  pauseBrain: async (brainId: string) => {
    const r = await api.post(`/brains/${brainId}/pause`)
    return r.data
  },

  // Interview
  getInterview: async (brainId: string) => {
    const r = await api.get(`/brains/${brainId}/interview`)
    return r.data
  },
  submitAnswer: async (brainId: string, key: string, value: unknown) => {
    const r = await api.post(`/brains/${brainId}/interview/answer`, { key, value })
    return r.data
  },
  completeInterview: async (brainId: string) => {
    const r = await api.post(`/brains/${brainId}/interview/complete`)
    return r.data
  },
  resetInterview: async (brainId: string) => {
    const r = await api.post(`/brains/${brainId}/interview/reset`)
    return r.data
  },

  // Connected Accounts
  listAccounts: async (brainId: string) => {
    const r = await api.get(`/brains/${brainId}/accounts`)
    return r.data
  },
  startOAuth: async (brainId: string, provider: string, redirectUri: string) => {
    const r = await api.post(`/brains/${brainId}/accounts/oauth/start`, { provider, redirect_uri: redirectUri })
    return r.data
  },
  oauthCallback: async (brainId: string, code: string, state: string) => {
    const r = await api.post(`/brains/${brainId}/accounts/oauth/callback`, { code, state })
    return r.data
  },
  storeApiKey: async (brainId: string, data: { provider: string; api_key: string; api_secret?: string; display_name?: string }) => {
    const r = await api.post(`/brains/${brainId}/accounts/api-key`, data)
    return r.data
  },
  disconnectAccount: async (brainId: string, accountId: string) => {
    await api.delete(`/brains/${brainId}/accounts/${accountId}`)
  },
  browserLoginStart: async (brainId: string, provider: string) => {
    const r = await api.post(`/brains/${brainId}/accounts/browser-login/start`, { provider })
    return r.data
  },
  browserLoginCapture: async (brainId: string) => {
    const r = await api.post(`/brains/${brainId}/accounts/browser-login/capture`)
    return r.data
  },

  // Tasks
  listTasks: async (brainId: string, statusFilter?: string, limit = 50) => {
    const r = await api.get(`/brains/${brainId}/tasks`, { params: { status_filter: statusFilter, limit } })
    return r.data
  },
  createTask: async (brainId: string, data: { title: string; instructions: string; task_type?: string; priority?: number }) => {
    const r = await api.post(`/brains/${brainId}/tasks`, data)
    return r.data
  },
  cancelTask: async (brainId: string, taskId: string) => {
    const r = await api.post(`/brains/${brainId}/tasks/${taskId}/cancel`)
    return r.data
  },

  // Approvals
  listApprovals: async (status = 'pending', brainId?: string) => {
    const r = await api.get('/approvals', { params: { status_filter: status, brain_id: brainId } })
    return r.data
  },
  decideApproval: async (requestId: string, approved: boolean, denialReason?: string) => {
    const r = await api.post(`/approvals/${requestId}/decide`, { approved, denial_reason: denialReason })
    return r.data
  },
  pendingApprovalCount: async () => {
    const r = await api.get('/approvals/count/pending')
    return r.data
  },

  // Monitors
  listMonitors: async (brainId: string) => {
    const r = await api.get(`/brains/${brainId}/monitors`)
    return r.data
  },
  createMonitor: async (brainId: string, data: Record<string, unknown>) => {
    const r = await api.post(`/brains/${brainId}/monitors`, data)
    return r.data
  },
  deleteMonitor: async (brainId: string, monitorId: string) => {
    await api.delete(`/brains/${brainId}/monitors/${monitorId}`)
  },

  // Pipeline
  listPipeline: async (brainId: string, pipelineType?: string) => {
    const r = await api.get(`/brains/${brainId}/pipeline`, { params: { pipeline_type: pipelineType } })
    return r.data
  },
  updatePipelineItem: async (brainId: string, itemId: string, data: Record<string, unknown>) => {
    const r = await api.put(`/brains/${brainId}/pipeline/${itemId}`, data)
    return r.data
  },

  // Activity
  listActivity: async (brainId: string, limit = 100) => {
    const r = await api.get(`/brains/${brainId}/activity`, { params: { limit } })
    return r.data
  },

  // Files
  uploadFile: async (brainId: string, file: File, questionKey?: string) => {
    const formData = new FormData()
    formData.append('file', file)
    if (questionKey) formData.append('question_key', questionKey)
    const r = await api.post(`/brains/${brainId}/files`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return r.data
  },
  listFiles: async (brainId: string) => {
    const r = await api.get(`/brains/${brainId}/files`)
    return r.data
  },
  deleteFile: async (brainId: string, fileId: string) => {
    await api.delete(`/brains/${brainId}/files/${fileId}`)
  },

  // Dashboard
  dashboardOverview: async () => {
    const r = await api.get('/brain-dashboard/overview')
    return r.data
  },
  brainStats: async (brainId: string) => {
    const r = await api.get(`/brain-dashboard/${brainId}/stats`)
    return r.data
  },
}

export default api
