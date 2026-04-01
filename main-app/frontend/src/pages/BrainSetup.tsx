import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2, ArrowRight, Check, RotateCcw, Link2, Upload, Plus, X, FileText, Trash2 } from 'lucide-react'
import { brainApi } from '@/utils/api'
import type { InterviewState } from '@/types/brain'

// Options from the seeder can be plain strings OR {label, value} objects
type OptionItem = string | { label: string; value: unknown }
function getOptionLabel(opt: OptionItem): string {
  return typeof opt === 'object' && opt !== null ? opt.label : String(opt)
}
function getOptionValue(opt: OptionItem): unknown {
  return typeof opt === 'object' && opt !== null ? opt.value : opt
}

export default function BrainSetup() {
  const { brainId } = useParams<{ brainId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [currentAnswer, setCurrentAnswer] = useState<string>('')
  const [selectedOptions, setSelectedOptions] = useState<unknown[]>([])
  const [multiTextItems, setMultiTextItems] = useState<string[]>([])
  const [multiTextInput, setMultiTextInput] = useState('')
  const [uploadedFile, setUploadedFile] = useState<{ file_id: string; filename: string; size: number } | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: interview, isLoading } = useQuery<InterviewState>({
    queryKey: ['brain-interview', brainId],
    queryFn: () => brainApi.getInterview(brainId!),
    enabled: !!brainId,
  })

  const submitMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      brainApi.submitAnswer(brainId!, key, value),
    onSuccess: (data) => {
      queryClient.setQueryData(['brain-interview', brainId], data)
      setCurrentAnswer('')
      setSelectedOptions([])
      setMultiTextItems([])
      setMultiTextInput('')
      setUploadedFile(null)
      setUploadError('')
    },
  })

  const handleFileUpload = async (file: File) => {
    if (!brainId || !question) return
    setIsUploading(true)
    setUploadError('')
    try {
      const result = await brainApi.uploadFile(brainId, file, question.key)
      setUploadedFile({ file_id: result.file_id, filename: result.filename, size: result.size })
      setCurrentAnswer(`file:${result.file_id}:${result.filename}`)
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Upload failed. Please try again.'
      setUploadError(msg)
    } finally {
      setIsUploading(false)
    }
  }

  const completeMutation = useMutation({
    mutationFn: () => brainApi.completeInterview(brainId!),
    onSuccess: () => {
      navigate(`/brains/${brainId}`)
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => brainApi.resetInterview(brainId!),
    onSuccess: (data) => {
      queryClient.setQueryData(['brain-interview', brainId], data)
      setCurrentAnswer('')
      setSelectedOptions([])
      setMultiTextItems([])
      setMultiTextInput('')
      setUploadedFile(null)
      setUploadError('')
    },
  })

  const question = interview?.current_question as (Record<string, any> | null)
  const qType: string = question?.type || ''
  const qOptions: OptionItem[] = question?.options || []
  const progress = interview ? (interview.current_step / interview.total_steps) * 100 : 0

  // Pre-fill from existing answers
  useEffect(() => {
    if (question && interview?.answers[question.key] != null) {
      const existing = interview.answers[question.key]
      if (qType === 'multi_text') {
        setMultiTextItems(Array.isArray(existing) ? (existing as string[]) : String(existing).split(',').map(s => s.trim()).filter(Boolean))
      } else if (qType === 'multi_select' || qType === 'multiselect') {
        setSelectedOptions(Array.isArray(existing) ? existing : [existing])
      } else {
        setCurrentAnswer(String(existing))
      }
    } else {
      setCurrentAnswer('')
      setSelectedOptions([])
      setMultiTextItems([])
      setMultiTextInput('')
    }
  }, [question?.key])

  const handleSubmit = () => {
    if (!question) return
    let value: unknown

    switch (qType) {
      case 'multi_select':
      case 'multiselect':
        value = selectedOptions
        break
      case 'multi_text':
        value = multiTextItems
        break
      case 'number':
        value = Number(currentAnswer)
        break
      case 'boolean':
        value = currentAnswer === 'true'
        break
      case 'select': {
        // For select with object options, store the value not the label
        const matched = qOptions.find(o => String(getOptionValue(o)) === currentAnswer)
        value = matched ? getOptionValue(matched) : currentAnswer
        break
      }
      case 'connect_account':
        // For connect_account, store "connected" or "skipped"
        value = currentAnswer || 'skipped'
        break
      case 'file_upload':
        value = currentAnswer || 'skipped'
        break
      default:
        value = currentAnswer
    }

    submitMutation.mutate({ key: question.key, value })
  }

  const canSubmit = (): boolean => {
    if (submitMutation.isPending) return false
    const required = question?.required !== false

    switch (qType) {
      case 'multi_select':
      case 'multiselect':
        return !required || selectedOptions.length > 0
      case 'multi_text':
        return !required || multiTextItems.length > 0
      case 'connect_account':
      case 'file_upload':
        return true // always allow skip or proceed
      default:
        return !required || currentAnswer.trim().length > 0
    }
  }

  const toggleOption = (val: unknown) => {
    setSelectedOptions((prev) =>
      prev.includes(val) ? prev.filter((o) => o !== val) : [...prev, val]
    )
  }

  const addMultiTextItem = () => {
    const trimmed = multiTextInput.trim()
    if (trimmed && !multiTextItems.includes(trimmed)) {
      setMultiTextItems(prev => [...prev, trimmed])
      setMultiTextInput('')
    }
  }

  const removeMultiTextItem = (item: string) => {
    setMultiTextItems(prev => prev.filter(i => i !== item))
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh] gap-3 text-rt-text-muted">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span>Loading setup...</span>
      </div>
    )
  }

  if (!interview) {
    return (
      <div className="px-12 pt-8">
        <p className="text-rt-text-muted">Brain not found.</p>
      </div>
    )
  }

  return (
    <div className="px-12 pb-20 pt-8 max-w-2xl mx-auto">
      {/* Progress Bar */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-rt-text-muted font-medium">
            Setup — Step {interview.current_step + (interview.is_complete ? 0 : 1)} of {interview.total_steps}
          </span>
          <button
            onClick={() => resetMutation.mutate()}
            className="text-xs text-rt-text-muted hover:text-rt-accent flex items-center gap-1 transition-colors"
          >
            <RotateCcw className="w-3 h-3" /> Start over
          </button>
        </div>
        <div className="h-2 bg-rt-bg-lighter rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-rt-primary rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${interview.is_complete ? 100 : progress}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </div>

      <AnimatePresence mode="wait">
        {interview.is_complete ? (
          /* ── Complete Screen ── */
          <motion.div
            key="complete"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="text-center py-12"
          >
            <div className="w-20 h-20 rounded-2xl bg-green-100 flex items-center justify-center text-4xl mx-auto mb-6">
              <Check className="w-10 h-10 text-green-600" />
            </div>
            <h2 className="text-3xl font-headline font-bold mb-3">Setup Complete!</h2>
            <p className="text-rt-text-muted mb-8 max-w-md mx-auto">
              Your Brain is configured and ready. Activate it to start working autonomously.
            </p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={() => navigate(`/brains/${brainId}`)}
                className="px-6 py-3 rounded-xl border border-rt-border text-rt-text-muted hover:bg-rt-bg-lighter transition-colors"
              >
                View Brain
              </button>
              <button
                onClick={() => completeMutation.mutate()}
                disabled={completeMutation.isPending}
                className="px-6 py-3 rounded-xl bg-rt-primary text-white font-medium hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
              >
                {completeMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    Finalize & Continue <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </motion.div>
        ) : question ? (
          /* ── Question Card ── */
          <motion.div
            key={question.key}
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -30 }}
            transition={{ duration: 0.2 }}
          >
            <div className="bg-rt-surface border border-rt-border rounded-2xl p-8 shadow-sm">
              <h2 className="text-2xl font-headline font-bold mb-2">{question.question}</h2>
              {question.placeholder && qType !== 'connect_account' && qType !== 'file_upload' && (
                <p className="text-sm text-rt-text-muted mb-6">{question.placeholder}</p>
              )}
              {!question.placeholder && <div className="mb-6" />}

              {/* ── text ── */}
              {qType === 'text' && (
                <input
                  type="text"
                  value={currentAnswer}
                  onChange={(e) => setCurrentAnswer(e.target.value)}
                  placeholder={question.placeholder || 'Type your answer...'}
                  className="w-full px-4 py-3 rounded-xl bg-rt-bg border border-rt-border text-rt-text placeholder:text-rt-text-muted/50 focus:outline-none focus:ring-2 focus:ring-rt-primary/50"
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && canSubmit() && handleSubmit()}
                />
              )}

              {/* ── textarea ── */}
              {qType === 'textarea' && (
                <textarea
                  value={currentAnswer}
                  onChange={(e) => setCurrentAnswer(e.target.value)}
                  placeholder={question.placeholder || 'Type your answer...'}
                  rows={4}
                  className="w-full px-4 py-3 rounded-xl bg-rt-bg border border-rt-border text-rt-text placeholder:text-rt-text-muted/50 focus:outline-none focus:ring-2 focus:ring-rt-primary/50 resize-none"
                  autoFocus
                />
              )}

              {/* ── number ── */}
              {qType === 'number' && (
                <input
                  type="number"
                  value={currentAnswer}
                  onChange={(e) => setCurrentAnswer(e.target.value)}
                  placeholder={question.placeholder || '0'}
                  className="w-full px-4 py-3 rounded-xl bg-rt-bg border border-rt-border text-rt-text focus:outline-none focus:ring-2 focus:ring-rt-primary/50"
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && canSubmit() && handleSubmit()}
                />
              )}

              {/* ── boolean ── */}
              {qType === 'boolean' && (
                <div className="flex gap-3">
                  {[{ label: 'Yes', value: 'true' }, { label: 'No', value: 'false' }].map((btn) => (
                    <button
                      key={btn.value}
                      onClick={() => setCurrentAnswer(btn.value)}
                      className={`flex-1 px-4 py-3 rounded-xl border-2 transition-all font-medium ${
                        currentAnswer === btn.value
                          ? 'border-rt-primary bg-rt-primary-fixed/10'
                          : 'border-rt-border hover:border-rt-primary/50'
                      }`}
                    >
                      {btn.label}
                    </button>
                  ))}
                </div>
              )}

              {/* ── select (with object or string options) ── */}
              {qType === 'select' && qOptions.length > 0 && (
                <div className="grid grid-cols-1 gap-2">
                  {qOptions.map((opt, idx) => {
                    const label = getOptionLabel(opt)
                    const val = String(getOptionValue(opt))
                    return (
                      <button
                        key={idx}
                        onClick={() => setCurrentAnswer(val)}
                        className={`text-left px-4 py-3 rounded-xl border-2 transition-all ${
                          currentAnswer === val
                            ? 'border-rt-primary bg-rt-primary-fixed/10'
                            : 'border-rt-border hover:border-rt-primary/50'
                        }`}
                      >
                        {label}
                      </button>
                    )
                  })}
                </div>
              )}

              {/* ── multi_select / multiselect (with object or string options) ── */}
              {(qType === 'multi_select' || qType === 'multiselect') && qOptions.length > 0 && (
                <div className="grid grid-cols-1 gap-2">
                  {qOptions.map((opt, idx) => {
                    const label = getOptionLabel(opt)
                    const val = getOptionValue(opt)
                    const isSelected = selectedOptions.includes(val)
                    return (
                      <button
                        key={idx}
                        onClick={() => toggleOption(val)}
                        className={`text-left px-4 py-3 rounded-xl border-2 transition-all flex items-center gap-3 ${
                          isSelected
                            ? 'border-rt-primary bg-rt-primary-fixed/10'
                            : 'border-rt-border hover:border-rt-primary/50'
                        }`}
                      >
                        <div className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                          isSelected ? 'border-rt-primary bg-rt-primary' : 'border-rt-border'
                        }`}>
                          {isSelected && <Check className="w-3 h-3 text-white" />}
                        </div>
                        {label}
                      </button>
                    )
                  })}
                </div>
              )}

              {/* ── multi_text (tags input) ── */}
              {qType === 'multi_text' && (
                <div>
                  <div className="flex gap-2 mb-3">
                    <input
                      type="text"
                      value={multiTextInput}
                      onChange={(e) => setMultiTextInput(e.target.value)}
                      placeholder={question.placeholder || 'Type and press Enter or Add...'}
                      className="flex-1 px-4 py-3 rounded-xl bg-rt-bg border border-rt-border text-rt-text placeholder:text-rt-text-muted/50 focus:outline-none focus:ring-2 focus:ring-rt-primary/50"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          addMultiTextItem()
                        }
                      }}
                    />
                    <button
                      onClick={addMultiTextItem}
                      disabled={!multiTextInput.trim()}
                      className="px-4 py-3 rounded-xl bg-rt-primary text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                  {multiTextItems.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {multiTextItems.map((item) => (
                        <span
                          key={item}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-rt-primary-fixed/20 text-rt-primary text-sm font-medium"
                        >
                          {item}
                          <button onClick={() => removeMultiTextItem(item)} className="hover:text-red-500 transition-colors">
                            <X className="w-3 h-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ── connect_account ── */}
              {qType === 'connect_account' && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 p-4 rounded-xl bg-rt-bg-lighter border border-rt-border">
                    <Link2 className="w-5 h-5 text-rt-primary flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm font-medium capitalize">{question.provider || 'Account'} Connection</p>
                      <p className="text-xs text-rt-text-muted">
                        Account connections will be configured after setup. You can connect accounts from the Brain detail page.
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setCurrentAnswer('connect_later'); handleSubmit() }}
                      className={`flex-1 px-4 py-3 rounded-xl border-2 transition-all text-sm font-medium ${
                        currentAnswer === 'connect_later'
                          ? 'border-rt-primary bg-rt-primary-fixed/10'
                          : 'border-rt-border hover:border-rt-primary/50'
                      }`}
                    >
                      I'll connect later
                    </button>
                    <button
                      onClick={() => { setCurrentAnswer('acknowledged'); handleSubmit() }}
                      className="flex-1 px-4 py-3 rounded-xl bg-rt-primary text-white text-sm font-medium hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
                    >
                      <Check className="w-4 h-4" /> Got it, next
                    </button>
                  </div>
                </div>
              )}

              {/* ── file_upload ── */}
              {qType === 'file_upload' && (
                <div className="space-y-4">
                  {/* Hidden file input */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={question.accept || '.pdf,.doc,.docx,.txt,.rtf'}
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) handleFileUpload(file)
                      e.target.value = ''
                    }}
                  />

                  {/* Upload area */}
                  {!uploadedFile ? (
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploading}
                      className="w-full p-8 rounded-xl border-2 border-dashed border-rt-border hover:border-rt-primary/50 hover:bg-rt-primary-fixed/5 transition-all text-center group"
                      onDragOver={(e) => { e.preventDefault(); e.stopPropagation() }}
                      onDrop={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        const file = e.dataTransfer.files?.[0]
                        if (file) handleFileUpload(file)
                      }}
                    >
                      {isUploading ? (
                        <div className="flex flex-col items-center gap-3">
                          <Loader2 className="w-8 h-8 animate-spin text-rt-primary" />
                          <p className="text-sm text-rt-text-muted">Uploading...</p>
                        </div>
                      ) : (
                        <div className="flex flex-col items-center gap-3">
                          <div className="w-14 h-14 rounded-xl bg-rt-primary-fixed/20 flex items-center justify-center group-hover:bg-rt-primary-fixed/30 transition-colors">
                            <Upload className="w-6 h-6 text-rt-primary" />
                          </div>
                          <div>
                            <p className="text-sm font-medium">Click to upload or drag & drop</p>
                            <p className="text-xs text-rt-text-muted mt-1">
                              {question.accept ? question.accept.split(',').join(', ') : 'PDF, DOC, DOCX, TXT'} — Max 20MB
                            </p>
                          </div>
                        </div>
                      )}
                    </button>
                  ) : (
                    /* Uploaded file preview */
                    <div className="flex items-center gap-3 p-4 rounded-xl bg-green-50 border border-green-200">
                      <FileText className="w-8 h-8 text-green-600 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-green-800 truncate">{uploadedFile.filename}</p>
                        <p className="text-xs text-green-600">
                          {(uploadedFile.size / 1024).toFixed(1)} KB — Uploaded successfully
                        </p>
                      </div>
                      <button
                        onClick={() => {
                          setUploadedFile(null)
                          setCurrentAnswer('')
                          setUploadError('')
                        }}
                        className="p-1.5 rounded-lg hover:bg-green-100 text-green-600 hover:text-red-500 transition-colors"
                        title="Remove file"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  )}

                  {/* Upload error */}
                  {uploadError && (
                    <p className="text-sm text-red-500 px-1">{uploadError}</p>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setCurrentAnswer('upload_later'); handleSubmit() }}
                      className="flex-1 px-4 py-3 rounded-xl border-2 border-rt-border hover:border-rt-primary/50 transition-all text-sm font-medium text-rt-text-muted"
                    >
                      Skip for now
                    </button>
                    {uploadedFile && (
                      <button
                        onClick={handleSubmit}
                        disabled={submitMutation.isPending}
                        className="flex-1 px-4 py-3 rounded-xl bg-rt-primary text-white text-sm font-medium hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
                      >
                        {submitMutation.isPending ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <>
                            Continue <ArrowRight className="w-4 h-4" />
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* ── Submit button (for types that need it) ── */}
              {!['connect_account', 'file_upload'].includes(qType) && (
                <div className="mt-6 flex justify-end">
                  <button
                    onClick={handleSubmit}
                    disabled={!canSubmit()}
                    className="px-6 py-3 rounded-xl bg-rt-primary text-white font-medium hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
                  >
                    {submitMutation.isPending ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <>
                        Next <ArrowRight className="w-4 h-4" />
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>

            {/* Answered so far */}
            {Object.keys(interview.answers).length > 0 && (
              <div className="mt-6 space-y-2">
                <p className="text-xs text-rt-text-muted uppercase tracking-wide font-medium">Your answers</p>
                {Object.entries(interview.answers).map(([key, val]) => (
                  <div key={key} className="flex items-center gap-2 text-sm text-rt-text-muted">
                    <Check className="w-3 h-3 text-green-500 flex-shrink-0" />
                    <span className="font-medium">{key}:</span>
                    <span className="truncate">
                      {Array.isArray(val) ? (val as string[]).join(', ') : String(val)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}
