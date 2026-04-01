import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2, ArrowRight, Mail, ArrowLeft, CheckCircle, Lock, Cloud } from 'lucide-react'
import toast from 'react-hot-toast'
import RetraceLogo from '@/components/RetraceLogo'
import axios from 'axios'
import { supabase, isSupabaseConfigured } from '@/lib/supabase'
import { useAuth } from '@/context/AuthContext'

const api = axios.create({ baseURL: '/api/v1/auth' })

export default function Login() {
  const { establishCloudSession } = useAuth()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [showForgot, setShowForgot] = useState(false)
  const [forgotEmail, setForgotEmail] = useState('')
  const [forgotLoading, setForgotLoading] = useState(false)
  const [forgotSent, setForgotSent] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  useEffect(() => {
    const err = searchParams.get('error')
    if (err === 'callback_missing') toast.error('Sign-in was interrupted. Please try again.')
    else if (err) toast.error('Sign-in failed. Please try again.')
  }, [searchParams])

  const handleCloudLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!identifier.trim() || !password) return
    setLoading(true)
    try {
      const { data: supaData, error: supaError } = await supabase.auth.signInWithPassword({
        email: identifier.trim(),
        password,
      })
      if (supaError) throw supaError
      if (!supaData.session) throw new Error('No session returned')

      const access = supaData.session.access_token
      await api.post('/remote-login', { supabase_token: access })
      await establishCloudSession(access)
      navigate('/')
    } catch (err: any) {
      const msg = err?.message || err?.response?.data?.detail || 'Sign-in failed'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!forgotEmail) return
    setForgotLoading(true)
    try {
      await supabase.auth.resetPasswordForEmail(forgotEmail)
      setForgotSent(true)
    } catch {
      setForgotSent(true)
    } finally {
      setForgotLoading(false)
    }
  }

  if (!isSupabaseConfigured()) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-rt-bg p-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md card p-6 text-center"
        >
          <Cloud className="w-10 h-10 text-rt-primary mx-auto mb-4" />
          <h1 className="text-xl font-display font-bold text-rt-text mb-2">ReTrace Community</h1>
          <p className="text-sm text-rt-text-muted mb-4">
            Cloud sign-in requires Supabase. Set <code className="text-xs bg-rt-surface px-1 rounded">VITE_SUPABASE_URL</code> and{' '}
            <code className="text-xs bg-rt-surface px-1 rounded">VITE_SUPABASE_ANON_KEY</code> in{' '}
            <code className="text-xs bg-rt-surface px-1 rounded">.env</code>, then restart the dev server.
          </p>
          <p className="text-xs text-rt-text-muted">See <code className="text-[10px] bg-rt-surface px-1 rounded">.env.example</code> for a template.</p>
        </motion.div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-rt-bg p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        <div className="text-center mb-10">
          <div className="flex justify-center mb-2"><RetraceLogo variant="lg" /></div>
        </div>

        <div className="card p-6">
          <AnimatePresence mode="wait">
            {!showForgot ? (
              <motion.div key="signin" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <h2 className="text-lg font-semibold text-rt-text mb-1">Sign in with your Lumena account</h2>
                <p className="text-xs text-rt-text-muted mb-6">Use the email and password from your cloud account.</p>

                <form onSubmit={handleCloudLogin} className="space-y-4">
                  <div>
                    <label className="label">Email</label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-rt-text-muted" />
                      <input
                        type="email"
                        className="input pl-10"
                        placeholder="you@company.com"
                        value={identifier}
                        onChange={e => setIdentifier(e.target.value)}
                        required
                        autoComplete="email"
                        autoFocus
                      />
                    </div>
                  </div>
                  <div>
                    <label className="label">Password</label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-rt-text-muted" />
                      <input
                        type="password"
                        className="input pl-10"
                        placeholder="Your password"
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        required
                        autoComplete="current-password"
                      />
                    </div>
                  </div>
                  <button
                    type="submit"
                    disabled={loading}
                    className="btn-primary w-full flex items-center justify-center gap-2 py-2.5"
                  >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                    {loading ? 'Signing in...' : 'Sign in'}
                  </button>
                </form>

                <div className="mt-4 text-center">
                  <button
                    type="button"
                    onClick={() => {
                      setShowForgot(true)
                      setForgotSent(false)
                      setForgotEmail(identifier.includes('@') ? identifier : '')
                    }}
                    className="text-xs text-rt-primary hover:text-rt-primary/80 transition-colors"
                  >
                    Forgot password?
                  </button>
                </div>
              </motion.div>
            ) : (
              <motion.div key="forgot" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <button
                  type="button"
                  onClick={() => {
                    setShowForgot(false)
                    setForgotSent(false)
                  }}
                  className="flex items-center gap-1 text-xs text-rt-text-muted hover:text-rt-text mb-4 transition-colors"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Back to sign in
                </button>

                {forgotSent ? (
                  <div className="text-center py-4">
                    <CheckCircle className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
                    <h3 className="text-base font-semibold text-rt-text mb-2">Check your email</h3>
                    <p className="text-sm text-rt-text-muted">
                      If an account exists with <strong>{forgotEmail}</strong>, we&apos;ve sent a password reset link. Check your inbox.
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        setShowForgot(false)
                        setForgotSent(false)
                      }}
                      className="btn-secondary mt-4 text-sm"
                    >
                      Return to Sign In
                    </button>
                  </div>
                ) : (
                  <>
                    <h2 className="text-lg font-semibold text-rt-text mb-1">Reset your password</h2>
                    <p className="text-xs text-rt-text-muted mb-6">
                      Enter your email address and we&apos;ll send you a link to reset your password (via Lumena cloud).
                    </p>
                    <form onSubmit={handleForgotPassword} className="space-y-4">
                      <div>
                        <label className="label">Email Address</label>
                        <div className="relative">
                          <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-rt-text-muted" />
                          <input
                            type="email"
                            className="input pl-10"
                            placeholder="you@company.com"
                            value={forgotEmail}
                            onChange={e => setForgotEmail(e.target.value)}
                            required
                            autoFocus
                          />
                        </div>
                      </div>
                      <button
                        type="submit"
                        disabled={forgotLoading}
                        className="btn-primary w-full flex items-center justify-center gap-2 py-2.5"
                      >
                        {forgotLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
                        {forgotLoading ? 'Sending...' : 'Send Reset Link'}
                      </button>
                    </form>
                  </>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  )
}
