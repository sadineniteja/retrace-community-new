import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ClipboardList, FileText, ArrowRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
}

interface CommandItem {
  id: string
  label: string
  description?: string
  icon: typeof ClipboardList
  action: () => void
  category: string
  keywords: string[]
}

export default function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const navigate = useNavigate()

  const commands: CommandItem[] = useMemo(
    () => [
      {
        id: 'nav-sops',
        label: 'Go to Automations',
        description: 'Scheduled workflows and SOPs',
        icon: ClipboardList,
        action: () => {
          navigate('/sops')
          onClose()
        },
        category: 'Navigation',
        keywords: ['sop', 'schedule', 'workflow', 'automation'],
      },
      {
        id: 'nav-docs',
        label: 'Go to Documentation',
        description: 'Generated documentation',
        icon: FileText,
        action: () => {
          navigate('/docs')
          onClose()
        },
        category: 'Navigation',
        keywords: ['docs', 'documentation', 'wiki'],
      },
    ],
    [navigate, onClose]
  )

  const filtered = useMemo(() => {
    if (!query.trim()) return commands
    const q = query.toLowerCase()
    return commands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(q) ||
        cmd.description?.toLowerCase().includes(q) ||
        cmd.keywords.some((k) => k.includes(q))
    )
  }, [query, commands])

  const grouped = useMemo(() => {
    const groups: Record<string, CommandItem[]> = {}
    filtered.forEach((cmd) => {
      if (!groups[cmd.category]) groups[cmd.category] = []
      groups[cmd.category].push(cmd)
    })
    return groups
  }, [filtered])

  const flatList = useMemo(() => Object.values(grouped).flat(), [grouped])

  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((i) => Math.min(i + 1, flatList.length - 1))
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((i) => Math.max(i - 1, 0))
      }
      if (e.key === 'Enter' && flatList[selectedIndex]) {
        e.preventDefault()
        flatList[selectedIndex].action()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isOpen, onClose, flatList, selectedIndex])

  if (!isOpen) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, y: -10, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.98 }}
          className="w-full max-w-lg bg-rt-bg-light border border-rt-border rounded-xl shadow-2xl overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-3 px-4 py-3 border-b border-rt-border">
            <Search className="w-4 h-4 text-rt-text-muted" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Jump to Automations, Documentation..."
              className="flex-1 bg-transparent text-sm text-rt-text placeholder:text-rt-text-muted outline-none"
            />
          </div>
          <div className="max-h-[50vh] overflow-y-auto py-2">
            {flatList.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-rt-text-muted">No matches</p>
            ) : (
              Object.entries(grouped).map(([category, items]) => (
                <div key={category} className="mb-2">
                  <p className="px-4 py-1 text-[10px] font-semibold uppercase tracking-wider text-rt-text-muted">{category}</p>
                  {items.map((cmd) => {
                    const globalIdx = flatList.indexOf(cmd)
                    const selected = globalIdx === selectedIndex
                    const Icon = cmd.icon
                    return (
                      <button
                        key={cmd.id}
                        type="button"
                        onClick={() => cmd.action()}
                        onMouseEnter={() => setSelectedIndex(globalIdx)}
                        className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                          selected ? 'bg-rt-primary/10 text-rt-primary' : 'hover:bg-rt-surface text-rt-text'
                        }`}
                      >
                        <Icon className="w-4 h-4 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium">{cmd.label}</p>
                          {cmd.description && <p className="text-xs text-rt-text-muted truncate">{cmd.description}</p>}
                        </div>
                        {selected && <ArrowRight className="w-4 h-4 flex-shrink-0" />}
                      </button>
                    )
                  })}
                </div>
              ))
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
