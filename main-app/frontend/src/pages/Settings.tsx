import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings as SettingsIcon, Zap, CheckCircle, XCircle, Loader2, Monitor, LayoutPanelLeft, Command, Palette, Sun, Moon, Sparkles, ChevronDown, ChevronRight, Plug, Power, PowerOff, Edit2, Trash2 } from 'lucide-react'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import axios from 'axios'
import { getApiBearerToken } from '@/utils/api'
import { useLayout } from '@/context/LayoutContext'

interface LLMSettings {
  api_url: string | null
  api_key: string
  model_name: string
  provider: string
  screenops_mouse_timeout?: number | null
  screenops_image_scale?: number | null
  serper_api_key?: string | null
  debug_logging?: boolean | null
  max_parallel_files?: number | null
  agent_max_iterations?: number | null
}

interface LLMSettingsResponse {
  api_url: string | null
  model_name: string
  provider: string
  api_key_set: boolean
  serper_api_key_set?: boolean
  screenops_api_url?: string | null
  screenops_api_key_set?: boolean
  screenops_model?: string | null
  screenops_mouse_timeout?: number
  screenops_image_scale?: number
  debug_logging?: boolean
  max_parallel_files?: number
  agent_max_iterations?: number
}

const api = axios.create({ baseURL: '/api/v1' })
const addAuth = (c: any) => {
  const t = getApiBearerToken()
  if (t) c.headers.Authorization = `Bearer ${t}`
  return c
}
api.interceptors.request.use(addAuth)

export default function Settings() {
  const [apiUrl, setApiUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [modelName, setModelName] = useState('gpt-4o')
  const [useCustomLlm, setUseCustomLlm] = useState(false)
  const [screenopsApiUrl, setScreenopsApiUrl] = useState('')
  const [screenopsApiKey, setScreenopsApiKey] = useState('')
  const [screenopsModel, setScreenopsModel] = useState('')
  const [screenopsMouseTimeout, setScreenopsMouseTimeout] = useState(30)
  const [screenopsImageScale, setScreenopsImageScale] = useState(100)
  const [agentMaxIterations, setAgentMaxIterations] = useState(50)
  type ConnectionTestBlock = {
    success?: boolean
    message?: string
    latency_ms?: number
    response?: string
  }

  const [testResult, setTestResult] = useState<{
    success: boolean
    message: string
    latency_ms?: number
    model_info?: {
      model?: string
      chat?: ConnectionTestBlock
      screenops?: ConnectionTestBlock
      web_search?: ConnectionTestBlock
    }
  } | null>(null)
  const [layoutThemeExpanded, setLayoutThemeExpanded] = useState(false)
  const [llmExpanded, setLlmExpanded] = useState(false)
  const [mcpExpanded, setMcpExpanded] = useState(false)
  const [mcpJsonInput, setMcpJsonInput] = useState('')
  const [mcpEditId, setMcpEditId] = useState<string | null>(null)
  const [mcpEditName, setMcpEditName] = useState('')

  const queryClient = useQueryClient()
  
  // Load current settings
  const { data: currentSettings } = useQuery<LLMSettingsResponse>({
    queryKey: ['settings', 'llm'],
    queryFn: async () => {
      const response = await api.get('/settings/llm')
      return response.data
    }
  })

  // Load MCP tool configs
  const { data: mcpConfigs = [] } = useQuery<any[]>({
    queryKey: ['settings', 'mcp-tools'],
    queryFn: async () => {
      const r = await api.get('/settings/mcp-tools')
      return r.data
    }
  })

  const mcpSaveMutation = useMutation({
    mutationFn: async (data: any) => {
      if (data.config_id) {
        return api.put(`/settings/mcp-tools/${data.config_id}`, data)
      }
      return api.post('/settings/mcp-tools', data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'mcp-tools'] })
      setMcpJsonInput(''); setMcpEditId(null); setMcpEditName('')
      toast.success('MCP server saved')
    },
    onError: () => toast.error('Failed to save MCP server'),
  })

  const mcpDeleteMutation = useMutation({
    mutationFn: async (id: string) => api.delete(`/settings/mcp-tools/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'mcp-tools'] })
      toast.success('MCP server removed')
    },
  })

  const mcpToggleMutation = useMutation({
    mutationFn: async (id: string) => api.post(`/settings/mcp-tools/${id}/toggle`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'mcp-tools'] })
    },
  })

  // Update form when settings load or change
  React.useEffect(() => {
    if (currentSettings) {
      setApiUrl(currentSettings.api_url || '')
      setModelName(currentSettings.model_name || 'gpt-4o')
      setScreenopsApiUrl(currentSettings.screenops_api_url || '')
      setScreenopsModel(currentSettings.screenops_model || '')
      setScreenopsMouseTimeout(Math.max(5, Math.min(120, currentSettings.screenops_mouse_timeout ?? 30)))
      setScreenopsImageScale(Math.max(25, Math.min(100, currentSettings.screenops_image_scale ?? 100)))
      setAgentMaxIterations(Math.max(1, Math.min(100, currentSettings.agent_max_iterations ?? 50)))
      setUseCustomLlm(currentSettings.provider === 'custom')
    }
  }, [currentSettings])
  
  // Save settings
  const saveMutation = useMutation({
    mutationFn: async (data: LLMSettings) => {
      console.log('Sending save request...', { ...data, api_key: '***' })
      try {
        const response = await api.post('/settings/llm', data, {
          timeout: 10000 // 10 second timeout
        })
        console.log('Save response received:', response.data)
        return response.data
      } catch (error: any) {
        console.error('Save request failed:', error)
        throw error
      }
    },
    onSuccess: async () => {
      console.log('Save successful, refetching settings')
      // Clear password fields
      setApiKey('')
      setScreenopsApiKey('')
      
      // Invalidate and wait for refetch to complete
      await queryClient.invalidateQueries({ queryKey: ['settings', 'llm'] })
      await queryClient.refetchQueries({ queryKey: ['settings', 'llm'] })
      
      toast.success('Settings saved successfully')
    },
    onError: (error: any) => {
      console.error('Save settings error:', error)
      const message = error.response?.data?.detail || error.response?.data?.message || error.message || 'Failed to save settings'
      toast.error(`Failed to save: ${message}`)
    }
  })
  
  // Test connection
  const testMutation = useMutation({
    mutationFn: async (data: LLMSettings) => {
      console.log('Testing connection with:', { ...data, api_key: '***' })
      const response = await api.post('/settings/llm/test', data)
      console.log('Test response:', response.data)
      return response.data
    },
    onSuccess: (data) => {
      console.log('Test successful:', data)
      setTestResult(data)
      if (data.success) {
        toast.success('Connection test completed!')
      } else {
        toast.error('Connection test failed')
      }
    },
    onError: (error: any) => {
      console.error('Test connection error:', error)
      const message = error.response?.data?.detail || error.message || 'Connection test failed'
      setTestResult({ success: false, message })
      toast.error(message)
    }
  })
  
  const handleSave = () => {
    if (useCustomLlm) {
      if (!apiUrl.trim()) {
        toast.error('API URL is required for custom LLM')
        return
      }
      if (!modelName.trim()) {
        toast.error('Model name is required for custom LLM')
        return
      }
      const hasKey = apiKey.trim() || currentSettings?.api_key_set
      if (!hasKey) {
        toast.error('API key is required for custom LLM')
        return
      }
    }

    const payload: any = {
      model_name: useCustomLlm ? modelName.trim() : (modelName.trim() || 'gpt-4o'),
      provider: useCustomLlm ? 'custom' : 'openai',
    }
    if (useCustomLlm && apiKey.trim()) {
      payload.api_key = apiKey.trim()
    }
    if (useCustomLlm && apiUrl.trim()) {
      payload.api_url = apiUrl.trim()
    } else {
      payload.api_url = null
    }
    if (useCustomLlm) {
      payload.screenops_api_url = screenopsApiUrl.trim() || null
      if (screenopsApiKey.trim()) payload.screenops_api_key = screenopsApiKey.trim()
      payload.screenops_model = screenopsModel.trim() || null
    }
    payload.screenops_mouse_timeout = Math.max(5, Math.min(120, screenopsMouseTimeout))
    payload.screenops_image_scale = Math.max(25, Math.min(100, screenopsImageScale))
    payload.debug_logging = true
    payload.max_parallel_files = 10
    payload.agent_max_iterations = Math.max(1, Math.min(100, agentMaxIterations))

    console.log('Saving settings with payload:', {
      ...payload,
      api_key: payload.api_key ? '***' + payload.api_key.slice(-4) : 'not sent',
    })
    saveMutation.mutate(payload)
  }
  
  const handleTest = () => {
    if (!useCustomLlm) {
      toast('Testing managed gateway...', { icon: 'ℹ️' })
      setTestResult(null)
      testMutation.mutate({
        api_url: null,
        api_key: 'sk-gateway-managed',
        model_name: modelName || 'gpt-4o',
        provider: 'openai',
        screenops_mouse_timeout: screenopsMouseTimeout,
      })
      return
    }

    const hasApiKey = apiKey.trim() || currentSettings?.api_key_set
    if (!hasApiKey) {
      toast.error('Save your API key first, then test')
      return
    }
    if (!modelName.trim()) {
      toast.error('Model name is required')
      return
    }

    const testApiKey = apiKey.trim() || 'saved-key-placeholder'

    if (!apiKey.trim() && currentSettings?.api_key_set) {
      toast('Testing with saved credentials...', { icon: 'ℹ️' })
    }

    setTestResult(null)
    testMutation.mutate({
      api_url: apiUrl || null,
      api_key: testApiKey,
      model_name: modelName,
      provider: 'custom',
      screenops_mouse_timeout: screenopsMouseTimeout,
    })
  }

  const { layoutMode, setLayoutMode, themeMode, setThemeMode } = useLayout()

  return (
    <div className="px-12 pb-20 pt-8 max-w-5xl mx-auto">
      {/* Header — Editorial */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-10"
      >
        <h1 className="text-4xl font-headline font-bold tracking-tight mb-2">
          Platform <span className="text-rt-primary-container italic">Settings</span>
        </h1>
        <p className="text-on-surface-variant text-lg">
          Configure your digital workspace and AI intelligence protocols.
        </p>
      </motion.div>

      {/* Layout & Theme: expandable */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <div className="card overflow-hidden">
          <button
            type="button"
            onClick={() => setLayoutThemeExpanded((e) => !e)}
            className="w-full flex items-center justify-between gap-3 p-5 text-left hover:bg-rt-bg-lighter/50 transition-colors"
          >
            <div className="flex items-center gap-3">
              {layoutThemeExpanded ? (
                <ChevronDown className="w-4 h-4 text-rt-text-muted" />
              ) : (
                <ChevronRight className="w-4 h-4 text-rt-text-muted" />
              )}
              <div className="icon-orb-sm"><Palette className="w-4 h-4 text-rt-primary" /></div>
              <span className="text-base font-headline font-bold">Interface <span className="italic text-rt-primary-container">Identity</span></span>
            </div>
            <span className="text-xs text-rt-text-muted font-medium">
              {layoutMode === 'classic' ? 'Classic' : 'Command Center'} · {themeMode === 'dark' ? 'Dark' : themeMode === 'light' ? 'Light' : 'Colorful'}
            </span>
          </button>
          {layoutThemeExpanded && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 pt-0 border-t border-rt-border/50">
              {/* Layout */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <LayoutPanelLeft className="w-4 h-4 text-rt-primary" />
                  <h2 className="text-sm font-headline font-bold">Interface Layout</h2>
                </div>
                <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setLayoutMode('classic')}
              className={`relative rounded-lg border-2 p-2.5 text-left transition-all ${
                layoutMode === 'classic'
                  ? 'border-rt-primary bg-rt-primary/5 ring-1 ring-rt-primary/20'
                  : 'border-rt-border hover:border-rt-text-muted/30'
              }`}
            >
              {layoutMode === 'classic' && (
                <div className="absolute top-1.5 right-1.5">
                  <CheckCircle className="w-4 h-4 text-rt-primary" />
                </div>
              )}
              <div className="mb-2 rounded border border-rt-border/50 bg-rt-bg overflow-hidden h-14">
                <div className="flex h-full">
                  <div className="w-1/4 bg-rt-bg-light border-r border-rt-border/30 p-1">
                    <div className="w-full h-1 rounded bg-rt-primary/30 mb-0.5" />
                    <div className="w-3/4 h-0.5 rounded bg-rt-surface mb-0.5" />
                    <div className="w-3/4 h-0.5 rounded bg-rt-surface" />
                  </div>
                  <div className="flex-1 p-1">
                    <div className="w-1/2 h-1 rounded bg-rt-text/20 mb-0.5" />
                    <div className="w-full h-0.5 rounded bg-rt-surface/50 mb-0.5" />
                    <div className="w-4/5 h-0.5 rounded bg-rt-surface/50" />
                  </div>
                </div>
              </div>
              <h3 className="font-semibold text-xs">Classic</h3>
              <p className="text-[10px] text-rt-text-muted leading-tight">Sidebar + full nav</p>
            </button>
            <button
              type="button"
              onClick={() => setLayoutMode('command-center')}
              className={`relative rounded-lg border-2 p-2.5 text-left transition-all ${
                layoutMode === 'command-center'
                  ? 'border-rt-primary bg-rt-primary/5 ring-1 ring-rt-primary/20'
                  : 'border-rt-border hover:border-rt-text-muted/30'
              }`}
            >
              {layoutMode === 'command-center' && (
                <div className="absolute top-1.5 right-1.5">
                  <CheckCircle className="w-4 h-4 text-rt-primary" />
                </div>
              )}
              <div className="mb-2 rounded border border-rt-border/50 bg-rt-bg overflow-hidden h-14">
                <div className="flex flex-col h-full">
                  <div className="h-[1px] bg-gradient-to-r from-rt-primary-container via-rt-primary to-rt-primary-container" />
                  <div className="h-2 bg-rt-bg-light border-b border-rt-border/30 flex items-center px-1">
                    <div className="w-1 h-1 rounded bg-rt-primary/40" />
                    <div className="ml-0.5 w-6 h-0.5 rounded bg-rt-text/10" />
                  </div>
                  <div className="flex flex-1">
                    <div className="w-2 bg-rt-bg-light/60 border-r border-rt-border/20 flex flex-col items-center pt-0.5 gap-0.5">
                      <div className="w-1 h-1 rounded bg-rt-primary/40" />
                      <div className="w-1 h-1 rounded bg-rt-surface" />
                    </div>
                    <div className="flex-1 p-1">
                      <div className="w-1/3 h-0.5 rounded bg-rt-text/20 mb-0.5" />
                      <div className="w-full h-0.5 rounded bg-rt-surface/40" />
                    </div>
                  </div>
                </div>
              </div>
              <h3 className="font-semibold text-xs flex items-center gap-1">
                Command Center
                <span className="px-1 py-0.5 rounded bg-rt-primary-container/20 text-[8px] font-bold text-rt-primary uppercase">Pro</span>
              </h3>
              <p className="text-[10px] text-rt-text-muted leading-tight">Top bar, <Command className="w-2 h-2 inline" />K</p>
            </button>
                </div>
              </div>

              {/* Theme */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Palette className="w-4 h-4 text-rt-primary" />
                  <h2 className="text-sm font-headline font-bold">Color Theme</h2>
                </div>
                <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => setThemeMode('dark')}
              className={`relative rounded-lg border-2 p-2.5 text-left transition-all ${
                themeMode === 'dark'
                  ? 'border-rt-primary ring-1 ring-rt-primary/20'
                  : 'border-rt-border hover:border-rt-text-muted/30'
              }`}
            >
              {themeMode === 'dark' && (
                <div className="absolute top-1.5 right-1.5">
                  <CheckCircle className="w-4 h-4 text-rt-primary" />
                </div>
              )}
              <div className="mb-2 rounded overflow-hidden h-10 border border-[#3a3530]">
                <div className="h-full bg-[#1a1714] flex">
                  <div className="w-1/4 bg-[#221f1b] border-r border-[#3a3530]" />
                  <div className="flex-1 p-1">
                    <div className="w-2/3 h-0.5 rounded bg-[#ede0d4]/20 mb-0.5" />
                    <div className="w-full h-0.5 rounded bg-[#2e2a25]" />
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Moon className="w-3 h-3 text-rt-text-muted" />
                <h3 className="font-semibold text-xs">Dark</h3>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setThemeMode('light')}
              className={`relative rounded-lg border-2 p-2.5 text-left transition-all ${
                themeMode === 'light'
                  ? 'border-rt-primary ring-1 ring-rt-primary/20'
                  : 'border-rt-border hover:border-rt-text-muted/30'
              }`}
            >
              {themeMode === 'light' && (
                <div className="absolute top-1.5 right-1.5">
                  <CheckCircle className="w-4 h-4 text-rt-primary" />
                </div>
              )}
              <div className="mb-2 rounded overflow-hidden h-10 border border-[#d8c3ad]/30">
                <div className="h-full bg-[#fbf8fc] flex">
                  <div className="w-1/4 bg-[#f6f2f7] border-r border-[#d8c3ad]/20" />
                  <div className="flex-1 p-1">
                    <div className="w-2/3 h-0.5 rounded bg-[#1b1b1e]/20 mb-0.5" />
                    <div className="w-full h-0.5 rounded bg-[#eae7eb]" />
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Sun className="w-3 h-3 text-amber-500" />
                <h3 className="font-semibold text-xs">Light</h3>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setThemeMode('colorful')}
              className={`relative rounded-lg border-2 p-2.5 text-left transition-all ${
                themeMode === 'colorful'
                  ? 'border-rt-primary ring-1 ring-rt-primary/20'
                  : 'border-rt-border hover:border-rt-text-muted/30'
              }`}
            >
              {themeMode === 'colorful' && (
                <div className="absolute top-1.5 right-1.5">
                  <CheckCircle className="w-4 h-4 text-rt-primary" />
                </div>
              )}
              <div className="mb-2 rounded overflow-hidden h-10 border border-[#5c4a2e]">
                <div className="h-full bg-[#1c1408] flex flex-col">
                  <div className="h-[1px] bg-gradient-to-r from-[#f59e0b] via-[#d48806] to-[#f59e0b]" />
                  <div className="flex-1 flex">
                    <div className="w-1/4 bg-[#261c0d] border-r border-[#5c4a2e]" />
                    <div className="flex-1 p-1">
                      <div className="w-2/3 h-0.5 rounded bg-[#f59e0b]/30 mb-0.5" />
                      <div className="w-full h-0.5 rounded bg-[#3a2d1a]" />
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-rt-primary-container" />
                <h3 className="font-semibold text-xs">Colorful</h3>
              </div>
            </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </motion.div>

      {/* LLM Configuration — collapsible */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <div className="card overflow-hidden">
          <button
            type="button"
            onClick={() => setLlmExpanded((e) => !e)}
            className="w-full flex items-center justify-between gap-3 p-5 text-left hover:bg-rt-bg-lighter/50 transition-colors"
          >
            <div className="flex items-center gap-3">
              {llmExpanded ? (
                <ChevronDown className="w-4 h-4 text-rt-text-muted" />
              ) : (
                <ChevronRight className="w-4 h-4 text-rt-text-muted" />
              )}
              <div className="icon-orb-sm"><Zap className="w-4 h-4 text-rt-primary" /></div>
              <span className="text-base font-headline font-bold">Intelligence <span className="italic text-rt-primary-container">Engine</span></span>
            </div>
            <span className="text-xs text-rt-text-muted font-medium">
              {useCustomLlm ? `Custom · ${modelName || 'not set'}` : 'Default'}
            </span>
          </button>
          {llmExpanded && (
          <div className="p-4 pt-0 border-t border-rt-border/50">

          <div className="space-y-4 mt-4">
            {/* Connect to custom LLM toggle */}
            <div className="flex items-center justify-between p-3 rounded-lg border border-rt-border bg-rt-surface/30">
              <div>
                <p className="text-sm font-medium">Connect to custom LLM</p>
                <p className="text-xs text-rt-text-muted">Use your own API key, model, and endpoint instead of the managed gateway</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={useCustomLlm}
                onClick={() => setUseCustomLlm((v) => !v)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  useCustomLlm ? 'bg-rt-primary' : 'bg-rt-border'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    useCustomLlm ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {useCustomLlm && (
              <div className="space-y-4 p-4 rounded-lg border border-rt-border bg-rt-surface/20">
                <div>
                  <label className="label">API URL</label>
                  <input
                    type="text"
                    className="input"
                    placeholder="https://api.openai.com/v1"
                    value={apiUrl}
                    onChange={(e) => setApiUrl(e.target.value)}
                  />
                  <p className="text-xs text-rt-text-muted mt-1">
                    OpenAI-compatible base URL ending in /v1
                  </p>
                </div>

                <div>
                  <label className="label">Model Name</label>
                  <input
                    type="text"
                    className="input"
                    placeholder="gpt-4o"
                    value={modelName}
                    onChange={(e) => setModelName(e.target.value)}
                  />
                  <p className="text-xs text-rt-text-muted mt-1">
                    Examples: gpt-4o, claude-3-5-sonnet-20241022, grok-4-1-fast
                  </p>
                </div>

                <div>
                  <label className="label">API Key</label>
                  <input
                    type="password"
                    className="input font-mono"
                    placeholder="sk-..."
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                  />
                  {currentSettings?.api_key_set && !apiKey && (
                    <p className="text-xs text-rt-success mt-1 flex items-center gap-1">
                      <CheckCircle className="w-3 h-3" />
                      API key is configured (enter new key to update)
                    </p>
                  )}
                </div>

                {/* ScreenOps separate config */}
                <div className="border-t border-rt-border/50 pt-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Monitor className="w-4 h-4 text-rt-primary" />
                    <p className="text-sm font-medium">ScreenOps Coordinate Finder</p>
                  </div>
                  <p className="text-xs text-rt-text-muted mb-3">
                    Optional: use a separate model/endpoint for coordinate finding (e.g. Qwen2.5-VL-7B, OS-Atlas). Leave blank to use the main LLM above.
                  </p>
                  <div className="space-y-3">
                    <div>
                      <label className="label">ScreenOps API URL</label>
                      <input
                        type="text"
                        className="input"
                        placeholder="http://10.0.0.x:1234/v1 (leave blank to use main URL)"
                        value={screenopsApiUrl}
                        onChange={(e) => setScreenopsApiUrl(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="label">ScreenOps Model</label>
                      <input
                        type="text"
                        className="input"
                        placeholder="Qwen2.5-VL-7B-Instruct (leave blank to use main model)"
                        value={screenopsModel}
                        onChange={(e) => setScreenopsModel(e.target.value)}
                      />
                      <p className="text-xs text-rt-text-muted mt-1">
                        Best options: Qwen2.5-VL-7B, OS-Atlas-7B, UI-TARS-7B, ShowUI-2B
                      </p>
                    </div>
                    <div>
                      <label className="label">ScreenOps API Key</label>
                      <input
                        type="password"
                        className="input font-mono"
                        placeholder="sk-... (leave blank to use main API key)"
                        value={screenopsApiKey}
                        onChange={(e) => setScreenopsApiKey(e.target.value)}
                      />
                      {currentSettings?.screenops_api_key_set && !screenopsApiKey && (
                        <p className="text-xs text-rt-success mt-1 flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" />
                          ScreenOps key configured (enter new key to update)
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Agent — Max iterations */}
            <div className="border-t border-rt-border pt-4 mt-4">
              <h4 className="text-xs font-semibold text-rt-text-muted uppercase tracking-wide mb-3">Agent</h4>
              <div className="flex items-center gap-3">
                <label htmlFor="agent-max-iterations" className="label whitespace-nowrap">Max iterations</label>
                <select
                  id="agent-max-iterations"
                  value={agentMaxIterations}
                  onChange={(e) => setAgentMaxIterations(Number(e.target.value))}
                  className="input w-24"
                >
                  {[10, 20, 30, 40, 50, 100].map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
                <p className="text-xs text-rt-text-muted">
                  Max tool-use steps per agent task.
                </p>
              </div>
            </div>

            {/* ScreenOps — mouse timeout only (API routed through gateway) */}
            <div className="border-t border-rt-border pt-4 mt-4">
              <div className="flex items-center gap-2 mb-3">
                <Monitor className="w-4 h-4 text-rt-primary" />
                <label className="label mb-0">ScreenOps — Computer Use</label>
              </div>
              <div className="space-y-3 bg-rt-surface/30 rounded-lg p-3">
                <div className="flex items-center gap-3">
                  <label htmlFor="screenops-mouse-timeout" className="label text-xs whitespace-nowrap mb-0">Mouse wait timeout</label>
                  <input
                    id="screenops-mouse-timeout"
                    type="number"
                    className="input w-20 text-center"
                    min={5}
                    max={120}
                    value={screenopsMouseTimeout}
                    onChange={(e) => setScreenopsMouseTimeout(Math.max(5, Math.min(120, Number(e.target.value) || 30)))}
                  />
                  <span className="text-xs text-rt-text-muted">seconds — how long to wait for a manual click in keyboard-only mode</span>
                </div>
              </div>
            </div>

          </div>

          {/* Test Result */}
          {testResult && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`mt-6 p-4 rounded-lg border flex items-start gap-3 ${
                testResult.success
                  ? 'bg-rt-success/10 border-rt-success/20'
                  : 'bg-rt-accent/10 border-rt-accent/20'
              }`}
            >
              {testResult.success ? (
                <CheckCircle className="w-5 h-5 text-rt-success flex-shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-5 h-5 text-rt-accent flex-shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                {/* Only show top-level message when no detailed model_info breakdown */}
                {!(testResult.model_info?.chat || testResult.model_info?.screenops || testResult.model_info?.web_search) && (
                  <p className={`font-medium mb-1 whitespace-pre-line ${
                    testResult.success ? 'text-rt-success' : 'text-rt-accent'
                  }`}>
                    {testResult.message}
                  </p>
                )}
                {testResult.latency_ms && (
                  <p className="text-sm text-rt-text-muted">
                    Response time: {testResult.latency_ms}ms
                  </p>
                )}
                {testResult.model_info &&
                  (testResult.model_info.chat ||
                    testResult.model_info.screenops ||
                    testResult.model_info.web_search) && (
                    <ul className="text-xs mt-3 space-y-2 font-mono bg-rt-surface/50 p-3 rounded border border-rt-border/40">
                      {(
                        [
                          ['chat', 'Chat'],
                          ['screenops', 'ScreenOps'],
                          ['web_search', 'Web search'],
                        ] as const
                      ).map(([key, label]) => {
                        const block = testResult.model_info![key]
                        if (!block?.message) return null
                        return (
                          <li key={key} className="list-none">
                            <span
                              className={
                                block.success ? 'text-rt-success' : 'text-rt-accent'
                              }
                            >
                              {label}: {block.message}
                            </span>
                            {typeof block.latency_ms === 'number' && block.latency_ms > 0 && (
                              <span className="text-rt-text-muted ml-2">
                                ({block.latency_ms}ms)
                              </span>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  )}
                {testResult.model_info?.model && (
                  <div className="text-xs text-rt-text-muted mt-2 font-mono bg-rt-surface/50 p-2 rounded">
                    Model: {testResult.model_info.model}
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {/* Actions */}
          <div className="flex gap-3 justify-end mt-6 pt-6 border-t border-rt-border">
            <button
              onClick={handleTest}
              disabled={testMutation.isPending}
              className="btn-secondary flex items-center gap-2"
            >
              {testMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Testing...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  Verify Services
                </>
              )}
            </button>
            <button
              onClick={handleSave}
              disabled={saveMutation.isPending}
              className="btn-primary flex items-center gap-2"
            >
              {saveMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <SettingsIcon className="w-4 h-4" />
                  Save Settings
                </>
              )}
            </button>
          </div>
          </div>
          )}
        </div>
      </motion.div>

      {/* ─── MCP Servers ──────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="mt-8"
      >
        <div className="card overflow-hidden">
          <button
            type="button"
            onClick={() => setMcpExpanded((e) => !e)}
            className="w-full flex items-center justify-between gap-3 p-5 text-left hover:bg-rt-bg-lighter/50 transition-colors"
          >
            <div className="flex items-center gap-3">
              {mcpExpanded ? (
                <ChevronDown className="w-4 h-4 text-rt-text-muted" />
              ) : (
                <ChevronRight className="w-4 h-4 text-rt-text-muted" />
              )}
              <div className="icon-orb-sm"><Plug className="w-4 h-4 text-rt-primary" /></div>
              <span className="text-base font-headline font-bold">MCP <span className="italic text-rt-primary-container">Servers</span></span>
            </div>
            <span className="text-xs text-rt-text-muted font-medium">
              {mcpConfigs.length > 0 ? `${mcpConfigs.length} configured` : 'Not configured'}
            </span>
          </button>

          {mcpExpanded && (
            <div className="p-4 pt-0 border-t border-rt-border/50 space-y-4">
              {/* Existing MCP configs */}
              {mcpConfigs.length > 0 && (
                <div className="space-y-2 mt-4">
                  {mcpConfigs.map((cfg: any) => {
                    const cj = cfg.config_json || {}
                    const transport = cj.url ? 'HTTP/SSE' : 'stdio'
                    const summary = cj.command
                      ? `${cj.command} ${(cj.args || []).join(' ')}`
                      : cj.url || 'No config'
                    return (
                      <div key={cfg.config_id} className="flex items-center justify-between p-3 bg-rt-surface/30 rounded-lg border border-rt-border/20">
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => mcpToggleMutation.mutate(cfg.config_id)}
                            className={`p-1 rounded transition-colors ${cfg.enabled ? 'text-green-600 hover:text-green-700' : 'text-rt-text-muted hover:text-rt-text'}`}
                            title={cfg.enabled ? 'Enabled — click to disable' : 'Disabled — click to enable'}
                          >
                            {cfg.enabled ? <Power className="w-4 h-4" /> : <PowerOff className="w-4 h-4" />}
                          </button>
                          <div>
                            <div className="font-medium text-sm">{cfg.name} <span className="text-xs text-rt-text-muted font-normal">({transport})</span></div>
                            <div className="text-xs text-rt-text-muted font-mono truncate max-w-md">{summary}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => {
                              setMcpEditId(cfg.config_id)
                              setMcpEditName(cfg.name)
                              setMcpJsonInput(JSON.stringify({ [cfg.name]: cfg.config_json }, null, 2))
                            }}
                            className="p-1.5 text-rt-text-muted hover:text-rt-primary transition-colors"
                            title="Edit"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => mcpDeleteMutation.mutate(cfg.config_id)}
                            className="p-1.5 text-rt-text-muted hover:text-red-500 transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Add/Edit MCP config — JSON paste */}
              <div className="space-y-3 p-3 border border-dashed border-rt-border/40 rounded-lg">
                <div className="text-xs font-semibold text-rt-text-muted uppercase tracking-wider">
                  {mcpEditId ? `Edit: ${mcpEditName}` : 'Add MCP Server(s)'}
                </div>
                <div>
                  <label className="text-xs text-rt-text-muted mb-1 block">
                    Paste MCP JSON config (same format as Claude Desktop / Cursor)
                  </label>
                  <textarea
                    value={mcpJsonInput}
                    onChange={(e) => setMcpJsonInput(e.target.value)}
                    placeholder={`{\n  "github": {\n    "command": "npx",\n    "args": ["-y", "@modelcontextprotocol/server-github"],\n    "env": {\n      "GITHUB_TOKEN": "ghp_xxx"\n    }\n  }\n}`}
                    rows={10}
                    className="w-full px-3 py-2 text-sm border border-rt-border/30 rounded-lg bg-rt-surface/30 focus:outline-none focus:ring-1 focus:ring-rt-primary/30 font-mono"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      if (!mcpJsonInput.trim()) {
                        toast.error('Paste a JSON config')
                        return
                      }
                      try {
                        let parsed = JSON.parse(mcpJsonInput)
                        // Handle wrapping: {"mcpServers": {...}} or direct {"name": {...}}
                        if (parsed.mcpServers) parsed = parsed.mcpServers

                        if (mcpEditId) {
                          // Editing a single server — extract first key
                          const keys = Object.keys(parsed)
                          const name = keys[0] || mcpEditName
                          const config_json = keys[0] ? parsed[keys[0]] : parsed
                          mcpSaveMutation.mutate({ config_id: mcpEditId, name, config_json })
                        } else {
                          // Adding — could be single or multiple
                          mcpSaveMutation.mutate({ mcp_servers: parsed })
                        }
                      } catch {
                        toast.error('Invalid JSON — check your config')
                      }
                    }}
                    className="btn-primary text-sm"
                  >
                    {mcpEditId ? 'Update' : 'Add Server(s)'}
                  </button>
                  {mcpEditId && (
                    <button
                      onClick={() => { setMcpEditId(null); setMcpEditName(''); setMcpJsonInput('') }}
                      className="btn-secondary text-sm"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>

              <p className="text-xs text-rt-text-muted">
                Paste the same JSON you'd use in Claude Desktop or Cursor. Multiple servers can be added at once. Tools appear in Agent Chat and can be toggled on/off.
              </p>
            </div>
          )}
        </div>
      </motion.div>

      {/* Company attribution */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
        className="max-w-4xl mt-16 mb-4"
      >
        <div className="flex items-center justify-center gap-2 py-6 text-[10px] text-rt-text-muted/40">
          <span>ReTrace by Lumena</span>
          <span>·</span>
          <span>Community Edition</span>
        </div>
      </motion.div>
    </div>
  )
}
