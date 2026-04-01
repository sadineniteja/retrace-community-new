import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Loader2, ArrowRight, Sparkles } from 'lucide-react'
import { brainApi } from '@/utils/api'
import type { BrainTemplate } from '@/types/brain'
import { BRAIN_ICONS } from '@/types/brain'

export default function BrainGallery() {
  const navigate = useNavigate()
  const [selectedTemplate, setSelectedTemplate] = useState<BrainTemplate | null>(null)
  const [brainName, setBrainName] = useState('')
  const [showCreate, setShowCreate] = useState(false)

  const { data: templates, isLoading } = useQuery<BrainTemplate[]>({
    queryKey: ['brain-templates'],
    queryFn: () => brainApi.listTemplates(),
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; template_slug: string }) => brainApi.createBrain(data),
    onSuccess: (brain) => {
      navigate(`/brains/${brain.brain_id}/setup`)
    },
  })

  const handleSelect = (template: BrainTemplate) => {
    setSelectedTemplate(template)
    setBrainName(template.name)
    setShowCreate(true)
  }

  const handleCreate = () => {
    if (!selectedTemplate || !brainName.trim()) return
    createMutation.mutate({ name: brainName, template_slug: selectedTemplate.slug })
  }

  return (
    <div className="px-12 pb-20 pt-8">
      {/* Header */}
      <motion.section
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-12"
      >
        <h1 className="text-5xl font-headline font-bold tracking-tight mb-4">
          Create a <span className="text-rt-primary-container italic">Brain</span>
        </h1>
        <p className="text-on-surface-variant text-lg max-w-2xl leading-relaxed">
          Each Brain is an autonomous AI employee that works for you 24/7.
          Pick a template to get started — the Brain will ask you a few questions and then start working.
        </p>
      </motion.section>

      {isLoading ? (
        <div className="flex items-center justify-center py-20 gap-3 text-rt-text-muted">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Loading templates...</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {templates?.map((template, i) => (
            <motion.button
              key={template.template_id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              onClick={() => handleSelect(template)}
              className={`group text-left p-6 rounded-2xl border-2 transition-all duration-200 hover:shadow-lg hover:-translate-y-1 ${
                selectedTemplate?.template_id === template.template_id
                  ? 'border-rt-primary bg-rt-primary-fixed/10 shadow-lg'
                  : 'border-rt-border bg-rt-surface hover:border-rt-primary/50'
              }`}
            >
              <div className="flex items-start gap-4">
                <div
                  className="w-14 h-14 rounded-xl flex items-center justify-center text-2xl flex-shrink-0"
                  style={{ backgroundColor: template.color + '20' }}
                >
                  {BRAIN_ICONS[template.slug] || '🧠'}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-lg font-bold mb-1 group-hover:text-rt-primary transition-colors">
                    {template.name}
                  </h3>
                  <p className="text-sm text-rt-text-muted line-clamp-2 mb-3">
                    {template.description}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {template.required_accounts?.slice(0, 3).map((acc) => (
                      <span
                        key={acc}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-rt-bg-lighter text-rt-text-muted font-medium uppercase tracking-wide"
                      >
                        {acc}
                      </span>
                    ))}
                    {(template.required_accounts?.length || 0) > 3 && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-rt-bg-lighter text-rt-text-muted">
                        +{template.required_accounts.length - 3}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2 text-xs text-rt-text-muted">
                <Sparkles className="w-3 h-3" />
                <span>{template.interview_questions?.length || 0} setup questions</span>
              </div>
            </motion.button>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && selectedTemplate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowCreate(false)}>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-rt-surface rounded-2xl shadow-2xl p-8 max-w-md w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-6">
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center text-xl"
                style={{ backgroundColor: selectedTemplate.color + '20' }}
              >
                {BRAIN_ICONS[selectedTemplate.slug] || '🧠'}
              </div>
              <div>
                <h2 className="text-xl font-bold">Name your Brain</h2>
                <p className="text-sm text-rt-text-muted">{selectedTemplate.name}</p>
              </div>
            </div>

            <input
              type="text"
              value={brainName}
              onChange={(e) => setBrainName(e.target.value)}
              placeholder="e.g. My Job Hunter"
              className="w-full px-4 py-3 rounded-xl bg-rt-bg border border-rt-border text-rt-text placeholder:text-rt-text-muted/50 focus:outline-none focus:ring-2 focus:ring-rt-primary/50 mb-6"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            />

            <div className="flex gap-3">
              <button
                onClick={() => setShowCreate(false)}
                className="flex-1 px-4 py-3 rounded-xl border border-rt-border text-rt-text-muted hover:bg-rt-bg-lighter transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!brainName.trim() || createMutation.isPending}
                className="flex-1 px-4 py-3 rounded-xl bg-rt-primary text-white font-medium hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {createMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    Create <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  )
}
