import { useEffect, useState } from 'react'
import { Activity, ArrowRight, Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react'
import { supabase, supabaseConfigError } from './lib/supabase'
import Dashboard from './pages/Dashboard'

function SignIn({ onSignedIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    if (!supabase) return
    setBusy(true)
    setError('')
    const { data, error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    setBusy(false)
    if (signInError) {
      setError(signInError.message)
      return
    }
    onSignedIn(data.session)
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-12">
      <section className="w-full max-w-[430px] rounded-[26px] border border-[#263138] bg-[#10171b]/95 p-7 shadow-[0_30px_100px_rgba(0,0,0,0.42)] sm:p-9">
        <BrandMark />
        <div className="mt-9">
          <p className="text-[11px] font-semibold tracking-[0.2em] text-[#9cadb1]">
            PRIVATE TRADING WORKSPACE
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[#f0f5f4]">
            Welcome back.
          </h1>
          <p className="mt-2 text-sm leading-6 text-[#8d9ba0]">
            Sign in to view your account activity and AI trade decisions.
          </p>
        </div>

        {supabaseConfigError ? (
          <div className="mt-7 rounded-2xl border border-[#695334] bg-[#332817]/55 p-4 text-sm leading-6 text-[#f0cf91]">
            {supabaseConfigError}
          </div>
        ) : (
          <form className="mt-7 space-y-4" onSubmit={submit}>
            <label className="block">
              <span className="mb-2 block text-xs font-medium text-[#bdc8ca]">Email address</span>
              <input
                autoComplete="email"
                className="h-12 w-full rounded-xl border border-[#2a373d] bg-[#0b1115] px-4 text-sm text-[#ecf2f1] outline-none transition placeholder:text-[#56656a] focus:border-[#9bd85f] focus:ring-2 focus:ring-[#9bd85f]/10"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                required
                type="email"
                value={email}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-xs font-medium text-[#bdc8ca]">Password</span>
              <span className="relative block">
                <input
                  autoComplete="current-password"
                  className="h-12 w-full rounded-xl border border-[#2a373d] bg-[#0b1115] px-4 pr-12 text-sm text-[#ecf2f1] outline-none transition placeholder:text-[#56656a] focus:border-[#9bd85f] focus:ring-2 focus:ring-[#9bd85f]/10"
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Your password"
                  required
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                />
                <button
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute inset-y-0 right-0 flex w-12 items-center justify-center text-[#819095] hover:text-white"
                  onClick={() => setShowPassword((value) => !value)}
                  type="button"
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </span>
            </label>
            {error && (
              <p className="rounded-xl border border-[#713c3c] bg-[#331c1c] px-4 py-3 text-sm text-[#ffc3b5]">
                {error}
              </p>
            )}
            <button
              className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#b6f36b] text-sm font-bold text-[#10170c] transition hover:bg-[#c8ff82] disabled:cursor-wait disabled:opacity-60"
              disabled={busy}
              type="submit"
            >
              {busy ? 'Signing in…' : 'Sign in'}
              {!busy && <ArrowRight size={16} />}
            </button>
          </form>
        )}

        <div className="mt-7 flex items-center gap-3 border-t border-[#253037] pt-5 text-xs leading-5 text-[#78888d]">
          <ShieldCheck className="shrink-0 text-[#9bd85f]" size={17} />
          <p>Access is private. Your Supabase service key is never used in this browser.</p>
        </div>
      </section>
    </main>
  )
}

function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-10 w-10 items-center justify-center rounded-[13px] border border-[#34473d] bg-[#18251d] text-[#b6f36b]">
        <Activity size={20} strokeWidth={2.2} />
      </span>
      <span>
        <span className="block text-[15px] font-semibold tracking-[0.06em] text-[#eef4f1]">
          NORTHSTAR
        </span>
        <span className="mt-0.5 block text-[9px] font-semibold tracking-[0.22em] text-[#819095]">
          AI TRADING ENGINE
        </span>
      </span>
      <span className="ml-auto flex items-center gap-1.5 rounded-full border border-[#2d3b39] bg-[#14201b] px-2.5 py-1 text-[10px] font-semibold tracking-wide text-[#b6f36b]">
        <KeyRound size={11} /> PRIVATE
      </span>
    </div>
  )
}

function App() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(Boolean(supabase))

  useEffect(() => {
    if (!supabase) return undefined
    let active = true
    supabase.auth.getSession().then(({ data, error }) => {
      if (error) console.error('Could not restore Supabase session:', error.message)
      if (active) {
        setSession(data.session)
        setLoading(false)
      }
    })
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
      setLoading(false)
    })
    return () => {
      active = false
      listener.subscription.unsubscribe()
    }
  }, [])

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-[#91a0a4]">
        <span className="mr-3 h-4 w-4 animate-spin rounded-full border-2 border-[#34413f] border-t-[#b6f36b]" />
        Restoring secure session…
      </main>
    )
  }

  if (!session) return <SignIn onSignedIn={setSession} />
  return <Dashboard session={session} />
}

export default App
