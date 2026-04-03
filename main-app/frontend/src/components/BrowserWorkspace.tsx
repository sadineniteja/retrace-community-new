import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Globe, ArrowLeft, ArrowRight, RotateCw,
  Loader2, MousePointer, Wifi, WifiOff, Plus, X,
  Keyboard,
} from 'lucide-react'

interface Tab {
  id: string
  title: string
  url: string
  screenshot: string | null
}

interface BrowserWorkspaceProps {
  conversationId: string | null
  isVisible: boolean
}

let tabIdCounter = 0

/** Generate a standalone session ID for independent browsing. */
function makeStandaloneId(): string {
  return `standalone_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export default function BrowserWorkspace({ conversationId, isVisible }: BrowserWorkspaceProps) {
  // If no conversation, create a standalone session so user can still browse
  const standaloneIdRef = useRef<string>(makeStandaloneId())
  const effectiveSessionId = conversationId || standaloneIdRef.current

  const [tabs, setTabs] = useState<Tab[]>([
    { id: `tab_${tabIdCounter++}`, title: 'New Tab', url: '', screenshot: null },
  ])
  const [activeTabId, setActiveTabId] = useState(tabs[0].id)
  const activeTabIdRef = useRef(activeTabId) // Keep ref in sync for WS handler
  activeTabIdRef.current = activeTabId
  const [urlInput, setUrlInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [browserFocused, setBrowserFocused] = useState(false)
  const [clickIndicator, setClickIndicator] = useState<{ x: number; y: number; id: number } | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const viewportRef = useRef<HTMLDivElement>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const connectAttemptRef = useRef(0)
  const clickIndicatorTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const activeTab = tabs.find(t => t.id === activeTabId) || tabs[0]

  const showClickIndicator = useCallback((browserX: number, browserY: number) => {
    const img = imgRef.current
    const viewport = viewportRef.current
    if (!img || !viewport) return
    const imgRect = img.getBoundingClientRect()
    const vpRect = viewport.getBoundingClientRect()
    const natW = img.naturalWidth || 1280
    const natH = img.naturalHeight || 900
    const elemAspect = imgRect.width / imgRect.height
    const imgAspect = natW / natH
    let renderW: number, renderH: number, offsetX: number, offsetY: number
    if (imgAspect > elemAspect) {
      renderW = imgRect.width; renderH = imgRect.width / imgAspect
      offsetX = 0; offsetY = (imgRect.height - renderH) / 2
    } else {
      renderH = imgRect.height; renderW = imgRect.height * imgAspect
      offsetX = (imgRect.width - renderW) / 2; offsetY = 0
    }
    const x = (browserX / natW) * renderW + offsetX + (imgRect.left - vpRect.left)
    const y = (browserY / natH) * renderH + offsetY + (imgRect.top - vpRect.top)
    if (clickIndicatorTimer.current) clearTimeout(clickIndicatorTimer.current)
    setClickIndicator({ x, y, id: Date.now() })
    clickIndicatorTimer.current = setTimeout(() => setClickIndicator(null), 900)
  }, [])

  // Connect WebSocket
  const connect = useCallback(() => {
    if (!isVisible) return

    // Clean up any existing connection
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/browser/${effectiveSessionId}`

    connectAttemptRef.current += 1
    const attempt = connectAttemptRef.current
    setStatusMessage('Connecting...')

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      if (connectAttemptRef.current !== attempt) return // stale
      setIsConnected(true)
      setStatusMessage('Connected')
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        // Use ref for activeTabId so we always get the latest value,
        // not the stale one captured when connect() was created.
        const currentTabId = activeTabIdRef.current
        switch (msg.type) {
          case 'screenshot':
            setTabs(prev => prev.map(t =>
              t.id === currentTabId
                ? { ...t, screenshot: msg.data, url: msg.url || t.url, title: msg.title || t.title }
                : t
            ))
            if (msg.url) setUrlInput(msg.url)
            break
          case 'status':
            setStatusMessage(msg.message || '')
            if (msg.url && msg.url !== 'about:blank') setUrlInput(msg.url)
            break
          case 'action_result':
            if (msg.result?.url) {
              setTabs(prev => prev.map(t =>
                t.id === currentTabId
                  ? { ...t, url: msg.result.url, title: msg.result.title || t.title }
                  : t
              ))
              setUrlInput(msg.result.url)
            }
            break
          case 'click_indicator':
            showClickIndicator(msg.x, msg.y)
            break
          case 'closed':
            setStatusMessage('Session ended')
            setIsConnected(false)
            break
          case 'error':
            setStatusMessage(`Error: ${msg.data}`)
            break
        }
      } catch { /* ignore parse errors */ }
    }

    ws.onclose = () => {
      if (connectAttemptRef.current !== attempt) return // stale
      setIsConnected(false)
      // Auto-reconnect after 3s
      if (isVisible) {
        reconnectTimer.current = setTimeout(connect, 3000)
      }
    }

    ws.onerror = () => {
      setStatusMessage('Connection error — retrying...')
    }
  }, [effectiveSessionId, isVisible, showClickIndicator])

  // Connect on mount / visibility change
  useEffect(() => {
    if (isVisible) {
      connect()
    }
    return () => {
      connectAttemptRef.current += 1
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [isVisible, connect])

  // When conversation changes, reconnect to the conversation's browser session
  // so the workspace mirrors what the agent tools see.
  const prevConversationIdRef = useRef<string | null>(conversationId)
  useEffect(() => {
    // Only reconnect when conversationId actually changes (not on initial mount,
    // which is handled by the connect effect above).
    if (conversationId !== prevConversationIdRef.current) {
      prevConversationIdRef.current = conversationId
      if (conversationId) {
        connectAttemptRef.current += 1
        if (wsRef.current) {
          wsRef.current.close()
          wsRef.current = null
        }
        // Small delay to let the previous connection cleanup finish
        const timer = setTimeout(() => connect(), 100)
        return () => clearTimeout(timer)
      }
    }
  }, [conversationId, connect])

  const send = useCallback((msg: Record<string, any>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
      return true
    }
    setStatusMessage('Not connected — waiting for browser session...')
    return false
  }, [])

  const handleImageClick = useCallback((e: React.MouseEvent<HTMLImageElement>) => {
    const img = imgRef.current
    if (!img) return

    // Account for objectFit: contain — the image may be letterboxed
    const rect = img.getBoundingClientRect()
    const natW = img.naturalWidth
    const natH = img.naturalHeight
    if (!natW || !natH) return

    const elemAspect = rect.width / rect.height
    const imgAspect = natW / natH
    let renderW: number, renderH: number, offsetX: number, offsetY: number

    if (imgAspect > elemAspect) {
      renderW = rect.width
      renderH = rect.width / imgAspect
      offsetX = 0
      offsetY = (rect.height - renderH) / 2
    } else {
      renderH = rect.height
      renderW = rect.height * imgAspect
      offsetX = (rect.width - renderW) / 2
      offsetY = 0
    }

    const relX = e.clientX - rect.left - offsetX
    const relY = e.clientY - rect.top - offsetY
    if (relX < 0 || relY < 0 || relX > renderW || relY > renderH) return

    const x = Math.round((relX / renderW) * natW)
    const y = Math.round((relY / renderH) * natH)

    send({ type: 'click', x, y })
    showClickIndicator(x, y)
    setStatusMessage(`Clicked (${x}, ${y})`)
    viewportRef.current?.focus()
  }, [send])

  const handleNavigate = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if (!urlInput.trim()) return
    let url = urlInput.trim()
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      // If it looks like a domain, add https
      if (url.includes('.') && !url.includes(' ')) {
        url = `https://${url}`
      } else {
        // Treat as search query
        url = `https://www.google.com/search?q=${encodeURIComponent(url)}`
      }
    }
    setUrlInput(url)
    if (send({ type: 'navigate', url })) {
      setStatusMessage(`Navigating to ${url}...`)
    }
  }, [urlInput, send])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const direction = e.deltaY > 0 ? 'down' : 'up'
    send({ type: 'scroll', direction, amount: Math.min(Math.abs(e.deltaY), 500) })
  }, [send])

  // Capture real keyboard events and forward them to the browser
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if ((e.target as HTMLElement).tagName === 'INPUT') return
    e.preventDefault()
    e.stopPropagation()

    const keyMap: Record<string, string> = {
      'Enter': 'Enter', 'Tab': 'Tab', 'Escape': 'Escape',
      'Backspace': 'Backspace', 'Delete': 'Delete',
      'ArrowUp': 'ArrowUp', 'ArrowDown': 'ArrowDown',
      'ArrowLeft': 'ArrowLeft', 'ArrowRight': 'ArrowRight',
      'Home': 'Home', 'End': 'End', 'PageUp': 'PageUp',
      'PageDown': 'PageDown', ' ': 'Space',
    }

    if (keyMap[e.key]) {
      send({ type: 'key', key: keyMap[e.key] })
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
      send({ type: 'type', text: e.key })
    } else if (e.ctrlKey || e.metaKey) {
      const combo = `${e.metaKey ? 'Meta+' : 'Control+'}${e.key}`
      send({ type: 'key', key: combo })
    }
  }, [send])

  // Tab management
  const addTab = useCallback(() => {
    const newTab: Tab = { id: `tab_${tabIdCounter++}`, title: 'New Tab', url: '', screenshot: null }
    setTabs(prev => [...prev, newTab])
    setActiveTabId(newTab.id)
    setUrlInput('')
  }, [])

  const closeTab = useCallback((tabId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setTabs(prev => {
      const filtered = prev.filter(t => t.id !== tabId)
      if (filtered.length === 0) {
        const fresh: Tab = { id: `tab_${tabIdCounter++}`, title: 'New Tab', url: '', screenshot: null }
        setActiveTabId(fresh.id)
        setUrlInput('')
        return [fresh]
      }
      if (activeTabId === tabId) {
        setActiveTabId(filtered[filtered.length - 1].id)
        setUrlInput(filtered[filtered.length - 1].url)
      }
      return filtered
    })
  }, [activeTabId])

  const selectTab = useCallback((tabId: string) => {
    setActiveTabId(tabId)
    const tab = tabs.find(t => t.id === tabId)
    if (tab) setUrlInput(tab.url)
  }, [tabs])

  if (!isVisible) return null

  return (
    <div className="h-full flex flex-col mt-2 mr-2 mb-4 ml-0">
      {/* Outer card shell with visible border */}
      <div className="flex-1 flex flex-col rounded-2xl overflow-hidden border border-[#d8c3ad]/40 shadow-[0_4px_24px_rgba(133,83,0,0.08)] bg-rt-bg">

        {/* Tab bar */}
        <div className="flex items-center bg-rt-bg-light flex-shrink-0 px-1 pt-1">
          <div className="flex items-center gap-0.5 flex-1 overflow-x-auto min-w-0">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => selectTab(tab.id)}
                className={`group flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-t-lg transition-all min-w-0 max-w-[160px] ${
                  activeTabId === tab.id
                    ? 'bg-rt-bg text-rt-text font-semibold'
                    : 'text-rt-text-muted hover:bg-rt-bg-lighter/50 hover:text-rt-text'
                }`}
              >
                <Globe className="w-3 h-3 flex-shrink-0 text-rt-primary/60" />
                <span className="truncate">{tab.title || 'New Tab'}</span>
                <button
                  onClick={(e) => closeTab(tab.id, e)}
                  className="ml-auto flex-shrink-0 p-0.5 rounded hover:bg-rt-surface opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </button>
            ))}
          </div>
          <button
            onClick={addTab}
            className="flex-shrink-0 p-1.5 rounded-lg hover:bg-rt-bg-lighter text-rt-text-muted hover:text-rt-primary transition-colors ml-1"
            title="New tab"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Browser toolbar */}
        <div className="flex items-center gap-2 px-3 py-2 bg-rt-bg flex-shrink-0 border-b border-[#d8c3ad]/30">
          <button
            onClick={() => send({ type: 'back' })}
            className="p-1.5 rounded-full hover:bg-rt-bg-lighter text-rt-text-muted hover:text-rt-text transition-colors"
            title="Back"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => send({ type: 'forward' })}
            className="p-1.5 rounded-full hover:bg-rt-bg-lighter text-rt-text-muted hover:text-rt-text transition-colors"
            title="Forward"
          >
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => send({ type: 'refresh' })}
            className="p-1.5 rounded-full hover:bg-rt-bg-lighter text-rt-text-muted hover:text-rt-text transition-colors"
            title="Refresh"
          >
            <RotateCw className="w-3 h-3" />
          </button>

          {/* URL bar */}
          <form onSubmit={handleNavigate} className="flex-1 flex items-center">
            <div className="flex-1 flex items-center gap-2 bg-rt-surface-container-high rounded-full px-4 py-1.5 transition-all focus-within:ring-2 ring-rt-primary-container/50">
              {isConnected ? (
                <div className="w-2 h-2 rounded-full bg-rt-success flex-shrink-0" />
              ) : (
                <Loader2 className="w-3 h-3 animate-spin text-rt-text-muted/50 flex-shrink-0" />
              )}
              <input
                type="text"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="Search or enter URL..."
                className="flex-1 bg-transparent text-xs focus:outline-none placeholder:text-rt-text-muted/50 font-body"
              />
            </div>
          </form>

          {/* Quick key buttons */}
          <button
            onClick={() => send({ type: 'key', key: 'Enter' })}
            className="p-1.5 rounded-full hover:bg-rt-bg-lighter text-rt-text-muted hover:text-rt-text transition-colors text-[9px] font-bold"
            title="Press Enter"
          >
            ↵
          </button>
          <button
            onClick={() => send({ type: 'key', key: 'Tab' })}
            className="p-1.5 rounded-full hover:bg-rt-bg-lighter text-rt-text-muted hover:text-rt-text transition-colors text-[9px] font-bold"
            title="Press Tab"
          >
            ⇥
          </button>
          <button
            onClick={() => send({ type: 'key', key: 'Backspace' })}
            className="p-1.5 rounded-full hover:bg-rt-bg-lighter text-rt-text-muted hover:text-rt-text transition-colors text-[9px] font-bold"
            title="Backspace"
          >
            ⌫
          </button>

          {/* Keyboard focus indicator */}
          {browserFocused && (
            <span className="flex items-center gap-1 text-[10px] font-medium text-rt-primary bg-rt-primary/10 px-2 py-0.5 rounded-full">
              <Keyboard className="w-3 h-3" /> Typing
            </span>
          )}

          {/* Connection status */}
          <div className="flex items-center gap-1.5 text-[10px] text-rt-text-muted flex-shrink-0 font-bold uppercase tracking-wider">
            {isConnected ? (
              <>
                <Wifi className="w-3 h-3 text-rt-success" />
                <span className="hidden xl:inline">Live</span>
              </>
            ) : (
              <WifiOff className="w-3 h-3 text-rt-text-muted/40" />
            )}
          </div>
        </div>

        {/* Browser viewport — focusable for keyboard capture */}
        <div
          ref={viewportRef}
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onFocus={() => setBrowserFocused(true)}
          onBlur={() => setBrowserFocused(false)}
          className={`flex-1 overflow-hidden bg-white relative outline-none ${browserFocused ? 'ring-2 ring-rt-primary/40 ring-inset' : ''}`}
        >
          {activeTab?.screenshot ? (
            <img
              ref={imgRef}
              src={`data:image/jpeg;base64,${activeTab.screenshot}`}
              alt={activeTab.title || 'Browser view'}
              className="w-full h-full object-contain cursor-crosshair"
              onClick={handleImageClick}
              onWheel={handleWheel}
              draggable={false}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center p-8 bg-rt-bg-lighter/30">
              <div className="icon-orb mb-5">
                <Globe className="w-6 h-6 text-rt-primary" />
              </div>
              <h3 className="text-xl font-headline font-bold mb-2">
                Browser <span className="text-rt-primary-container italic">Workspace</span>
              </h3>
              <p className="text-sm text-on-surface-variant max-w-xs leading-relaxed mb-4">
                {isConnected
                  ? 'Connected! Enter a URL above to start browsing.'
                  : 'Launching browser session...'}
              </p>
              {!isConnected && (
                <div className="flex items-center gap-2 text-xs text-rt-text-muted">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Starting Chromium...
                </div>
              )}
            </div>
          )}

          {/* Click indicator — shows where the agent (or user) clicked */}
          {clickIndicator && (
            <div
              key={clickIndicator.id}
              className="pointer-events-none absolute z-20"
              style={{ left: clickIndicator.x, top: clickIndicator.y, transform: 'translate(-50%, -50%)' }}
            >
              {/* Ripple ring */}
              <span className="absolute inset-0 rounded-full bg-orange-400 opacity-60 animate-ping" style={{ width: 28, height: 28, margin: -6 }} />
              {/* Solid dot */}
              <span className="relative block w-4 h-4 rounded-full bg-orange-500 border-2 border-white shadow-lg" />
            </div>
          )}

          {/* Click-to-focus hint */}
          {activeTab?.screenshot && !browserFocused && (
            <div className="absolute top-3 right-3 flex items-center gap-1.5 bg-black/50 backdrop-blur-sm rounded-full px-3 py-1.5 text-[10px] text-white/80 pointer-events-none z-10">
              <Keyboard className="w-3 h-3" /> Click browser to enable keyboard
            </div>
          )}

          {/* Floating status bar */}
          {statusMessage && statusMessage !== 'Connected' && statusMessage !== 'connected' && (
            <div className="absolute bottom-3 left-3 right-3 flex items-center gap-2 bg-rt-bg-light/90 backdrop-blur-sm rounded-full px-4 py-1.5 text-xs text-rt-text-muted editorial-shadow-sm">
              {(statusMessage.includes('Navigat') || statusMessage.includes('Connect')) && (
                <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
              )}
              {statusMessage.includes('Clicked') && <MousePointer className="w-3 h-3 flex-shrink-0" />}
              <span className="truncate">{statusMessage}</span>
            </div>
          )}
        </div>

        {/* Page info footer */}
        {activeTab?.title && activeTab.title !== 'New Tab' && (
          <div className="px-3 py-1.5 bg-rt-bg-light text-[10px] text-rt-text-muted truncate flex-shrink-0 border-t border-[#d8c3ad]/30 font-body">
            {activeTab.title} — {activeTab.url}
          </div>
        )}
      </div>
    </div>
  )
}
