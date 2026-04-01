// Brain platform types

export interface BrainTemplate {
  template_id: string
  slug: string
  name: string
  description: string
  icon: string
  color: string
  category: string
  interview_questions: InterviewQuestion[]
  required_accounts: string[]
  optional_accounts: string[]
  available_tools: string[]
  is_builtin: boolean
  created_at: string | null
}

export interface InterviewQuestion {
  key: string
  question: string
  type: 'text' | 'textarea' | 'select' | 'multi_select' | 'multiselect' | 'multi_text' | 'number' | 'boolean' | 'connect_account' | 'file_upload'
  required?: boolean
  options?: (string | { label: string; value: unknown })[]
  placeholder?: string
  provider?: string  // for connect_account type
  accept?: string    // for file_upload type
  condition?: { key: string; values?: string[]; value?: string }
}

export interface Brain {
  brain_id: string
  user_id: string
  tenant_id: string | null
  template_id: string | null
  name: string
  brain_type: string
  description: string | null
  icon: string | null
  color: string | null
  setup_status: 'pending' | 'interview' | 'ready' | 'error'
  setup_step: number
  autonomy_level: 'supervised' | 'semi_auto' | 'full_auto'
  status: 'inactive' | 'active' | 'paused' | 'error'
  is_active: boolean
  max_daily_tasks: number
  max_daily_cost_cents: number
  tasks_today: number
  cost_today_cents: number
  config: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface InterviewState {
  brain_id: string
  setup_status: string
  current_step: number
  total_steps: number
  current_question: InterviewQuestion | null
  answers: Record<string, unknown>
  is_complete: boolean
}

export interface ConnectedAccount {
  account_id: string
  brain_id: string
  provider: string
  provider_display_name: string
  account_identifier: string | null
  auth_type: string
  status: string
  status_message: string | null
  is_active: boolean
  last_used_at: string | null
  last_verified_at: string | null
  created_at: string | null
}

export interface BrainTask {
  task_id: string
  brain_id: string
  schedule_id: string | null
  pipeline_item_id: string | null
  parent_task_id: string | null
  task_type: string
  title: string
  instructions: string | null
  status: 'pending' | 'awaiting_approval' | 'running' | 'completed' | 'failed' | 'cancelled'
  priority: number
  trigger: string
  requires_approval: boolean
  result_summary: string | null
  error: string | null
  cost_cents: number
  queued_at: string | null
  started_at: string | null
  completed_at: string | null
}

export interface ApprovalRequest {
  request_id: string
  brain_id: string
  task_id: string | null
  action_type: string
  action_summary: string
  action_data: Record<string, unknown> | null
  status: 'pending' | 'approved' | 'denied' | 'expired' | 'auto_approved'
  expires_at: string | null
  resolved_at: string | null
  denial_reason: string | null
  created_at: string | null
}

export interface BrainMonitor {
  monitor_id: string
  brain_id: string
  name: string
  monitor_type: string
  target_url: string | null
  target_config: Record<string, unknown>
  check_interval_minutes: number
  trigger_condition: string
  trigger_action: string
  notification_channels: string[]
  is_active: boolean
  last_check_at: string | null
  trigger_count: number
  created_at: string | null
}

export interface PipelineItem {
  item_id: string
  brain_id: string
  pipeline_type: string
  title: string
  external_url: string | null
  stage: string
  stage_order: number
  data_json: Record<string, unknown>
  history_json: { stage: string; timestamp: string }[]
  is_starred: boolean
  is_archived: boolean
  created_at: string | null
  updated_at: string | null
}

export interface BrainActivity {
  activity_id: string
  brain_id: string
  task_id: string | null
  activity_type: string
  title: string
  description: string | null
  detail_json: Record<string, unknown> | null
  severity: 'info' | 'success' | 'warning' | 'error'
  created_at: string | null
}

export interface DashboardOverview {
  brains: {
    total: number
    active: number
    paused: number
    inactive: number
  }
  today: {
    tasks_completed: number
    cost_cents: number
  }
  pending_approvals: number
}

export interface BrainStats {
  brain: Brain
  tasks: { total: number; by_status: Record<string, number> }
  pipeline: { total: number; by_stage: Record<string, number> }
  connected_accounts: number
  active_monitors: number
  total_activities: number
}

// Icon mapping for brain types
export const BRAIN_ICONS: Record<string, string> = {
  job_searcher: '💼',
  trader: '📈',
  social_media: '📱',
  coder: '💻',
  personal_finance: '💰',
  custom: '🧠',
}

export const BRAIN_STATUS_COLORS: Record<string, string> = {
  active: 'text-green-500',
  paused: 'text-yellow-500',
  inactive: 'text-gray-400',
  error: 'text-red-500',
}

export const TASK_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-600',
  awaiting_approval: 'bg-yellow-100 text-yellow-700',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-100 text-gray-500',
}
