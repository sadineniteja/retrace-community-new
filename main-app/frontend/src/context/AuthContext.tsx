import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import axios from 'axios'
import { supabase, isSupabaseConfigured } from '@/lib/supabase'
import { RT_SUPABASE_ACCESS_TOKEN_KEY } from '@/utils/api'

interface AuthUser {
  user_id: string
  email: string
  display_name?: string
  role: string
  tenant_id?: string
  auth_provider: string
  force_password_change?: boolean
}

interface Tenant {
  tenant_id: string
  name: string
  domain?: string
  auth_method: string
}

interface AuthState {
  user: AuthUser | null
  tenant: Tenant | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (identifier: string, password: string) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  /** After Supabase + remote-login: persist tokens and load user into context (required for protected routes). */
  establishSession: (accessToken: string, refreshToken: string) => Promise<void>
  /** Community cloud: use Supabase access token as API Bearer (no ReTrace JWT). */
  establishCloudSession: (supabaseAccessToken: string) => Promise<void>
  logout: () => Promise<void>
  refreshAuth: () => Promise<boolean>
  changePassword: (newPassword: string, newEmail?: string, currentPassword?: string) => Promise<void>
}

interface RegisterData {
  tenant_name: string
  admin_email: string
  admin_password: string
  admin_display_name?: string
  domain?: string
}

const AuthContext = createContext<AuthState | null>(null)

const api = axios.create({ baseURL: '/api/v1/auth' })

function getStoredTokens() {
  return {
    access: localStorage.getItem('rt_access_token'),
    refresh: localStorage.getItem('rt_refresh_token'),
  }
}

function storeTokens(access: string, refresh: string) {
  localStorage.setItem('rt_access_token', access)
  localStorage.setItem('rt_refresh_token', refresh)
}

function clearTokens() {
  localStorage.removeItem('rt_access_token')
  localStorage.removeItem('rt_refresh_token')
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchMe = useCallback(async (token: string) => {
    try {
      const resp = await api.get('/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      setUser(resp.data.user)
      setTenant(resp.data.tenant)
      return true
    } catch {
      return false
    }
  }, [])

  const refreshAuth = useCallback(async (): Promise<boolean> => {
    const { refresh } = getStoredTokens()
    if (!refresh) return false
    try {
      const resp = await api.post('/refresh', { refresh_token: refresh })
      storeTokens(resp.data.access_token, resp.data.refresh_token)
      setUser(resp.data.user)
      return true
    } catch {
      clearTokens()
      setUser(null)
      setTenant(null)
      return false
    }
  }, [])

  useEffect(() => {
    const init = async () => {
      const cloud = localStorage.getItem(RT_SUPABASE_ACCESS_TOKEN_KEY)
      if (cloud) {
        let ok = await fetchMe(cloud)
        if (!ok && isSupabaseConfigured()) {
          const { data: sess } = await supabase.auth.getSession()
          if (sess.session?.access_token) {
            localStorage.setItem(RT_SUPABASE_ACCESS_TOKEN_KEY, sess.session.access_token)
            ok = await fetchMe(sess.session.access_token)
          }
          if (!ok) {
            const { data: ref } = await supabase.auth.refreshSession()
            if (ref.session?.access_token) {
              localStorage.setItem(RT_SUPABASE_ACCESS_TOKEN_KEY, ref.session.access_token)
              ok = await fetchMe(ref.session.access_token)
            }
          }
        }
        if (!ok) {
          localStorage.removeItem(RT_SUPABASE_ACCESS_TOKEN_KEY)
          setUser(null)
          setTenant(null)
        }
      } else {
        const { access } = getStoredTokens()
        if (access) {
          const ok = await fetchMe(access)
          if (!ok) {
            await refreshAuth()
          }
        }
      }
      setIsLoading(false)
    }
    init()
  }, [fetchMe, refreshAuth])

  useEffect(() => {
    if (!isSupabaseConfigured()) return
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'TOKEN_REFRESHED' && session?.access_token) {
        if (localStorage.getItem(RT_SUPABASE_ACCESS_TOKEN_KEY)) {
          localStorage.setItem(RT_SUPABASE_ACCESS_TOKEN_KEY, session.access_token)
        }
      }
      if (event === 'SIGNED_OUT') {
        localStorage.removeItem(RT_SUPABASE_ACCESS_TOKEN_KEY)
      }
    })
    return () => subscription.unsubscribe()
  }, [])

  const establishSession = useCallback(async (accessToken: string, refreshToken: string) => {
    localStorage.removeItem(RT_SUPABASE_ACCESS_TOKEN_KEY)
    storeTokens(accessToken, refreshToken)
    const ok = await fetchMe(accessToken)
    if (!ok) {
      clearTokens()
      setUser(null)
      setTenant(null)
      throw new Error('Could not load your profile')
    }
  }, [fetchMe])

  const establishCloudSession = useCallback(async (supabaseAccessToken: string) => {
    clearTokens()
    localStorage.setItem(RT_SUPABASE_ACCESS_TOKEN_KEY, supabaseAccessToken)
    const ok = await fetchMe(supabaseAccessToken)
    if (!ok) {
      localStorage.removeItem(RT_SUPABASE_ACCESS_TOKEN_KEY)
      setUser(null)
      setTenant(null)
      throw new Error('Could not load your profile')
    }
  }, [fetchMe])

  const login = async (identifier: string, password: string) => {
    const resp = await api.post('/login', { identifier, password })
    storeTokens(resp.data.access_token, resp.data.refresh_token)
    setUser(resp.data.user)
    const meResp = await api.get('/me', {
      headers: { Authorization: `Bearer ${resp.data.access_token}` },
    })
    setTenant(meResp.data.tenant)
  }

  const register = async (data: RegisterData) => {
    const resp = await api.post('/register', data)
    storeTokens(resp.data.access_token, resp.data.refresh_token)
    setUser(resp.data.user)
    const meResp = await api.get('/me', {
      headers: { Authorization: `Bearer ${resp.data.access_token}` },
    })
    setTenant(meResp.data.tenant)
  }

  const changePassword = async (newPassword: string, newEmail?: string, currentPassword?: string) => {
    const access =
      localStorage.getItem(RT_SUPABASE_ACCESS_TOKEN_KEY) || getStoredTokens().access
    if (!access) throw new Error('Not authenticated')
    const resp = await api.post('/change-password', {
      new_password: newPassword,
      new_email: newEmail || undefined,
      current_password: currentPassword || '',
    }, {
      headers: { Authorization: `Bearer ${access}` },
    })
    storeTokens(resp.data.access_token, resp.data.refresh_token)
    setUser(resp.data.user)
  }

  const logout = async () => {
    const cloud = localStorage.getItem(RT_SUPABASE_ACCESS_TOKEN_KEY)
    const { access } = getStoredTokens()
    const bearer = cloud || access
    try {
      if (bearer && !cloud) {
        await api.post('/logout', {}, {
          headers: { Authorization: `Bearer ${bearer}` },
        })
      }
    } catch { /* ignore */ }
    if (isSupabaseConfigured()) {
      await supabase.auth.signOut()
    }
    clearTokens()
    localStorage.removeItem(RT_SUPABASE_ACCESS_TOKEN_KEY)
    setUser(null)
    setTenant(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        tenant,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        establishSession,
        establishCloudSession,
        logout,
        refreshAuth,
        changePassword,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
