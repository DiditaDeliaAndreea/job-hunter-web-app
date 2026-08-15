'use client'

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
  User,
} from 'firebase/auth'
import { firebaseAuth } from '../lib/firebase'

type AuthContextValue = {
  user: User | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readableAuthError(error: unknown): Error {
  const code = error && typeof error === 'object' && 'code' in error ? String(error.code) : ''
  console.error('Firebase authentication failed:', code, error)
  const messages: Record<string, string> = {
    'auth/invalid-credential': 'The email or password is incorrect.',
    'auth/email-already-in-use': 'An account with this email already exists.',
    'auth/weak-password': 'Use a password with at least six characters.',
    'auth/invalid-email': 'Enter a valid email address.',
    'auth/operation-not-allowed': 'Email/password sign-in is disabled. Enable it in Firebase Console > Authentication > Sign-in method.',
    'auth/configuration-not-found': 'Firebase Authentication is not configured for this project. Enable Email/Password sign-in in the Firebase Console.',
    'auth/api-key-not-valid.-please-pass-a-valid-api-key.': 'The Firebase Web API key is invalid. Check the NEXT_PUBLIC_FIREBASE_API_KEY value.',
    'auth/network-request-failed': 'Firebase could not be reached. Check your network connection and Firebase configuration.',
  }
  return new Error(messages[code] || 'Could not complete authentication.')
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}

function AuthScreen() {
  const { signIn, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      if (mode === 'login') await signIn(email, password)
      else await register(email, password)
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : 'Could not complete authentication.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10">
      <section className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">CareerMatch</h1>
        <p className="mt-2 text-sm text-gray-500">Sign in to keep your job matches private and synced.</p>
        <div className="mt-6 grid grid-cols-2 rounded-lg bg-gray-100 p-1 text-sm font-medium">
          {(['login', 'register'] as const).map((option) => (
            <button key={option} type="button" onClick={() => setMode(option)} className={`rounded-md px-3 py-2 ${mode === option ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500'}`}>
              {option === 'login' ? 'Sign in' : 'Create account'}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <label className="block text-sm font-medium text-gray-700">
            Email
            <input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 font-normal focus:border-blue-500 focus:outline-none" />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            Password
            <input type="password" required minLength={6} value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 font-normal focus:border-blue-500 focus:outline-none" />
          </label>
          {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          <button type="submit" disabled={submitting} className="w-full rounded-md bg-blue-600 px-4 py-2.5 font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            {submitting ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
      </section>
    </main>
  )
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const value = useMemo(() => ({
    user,
    loading,
    signIn: async (email: string, password: string) => {
      try { await signInWithEmailAndPassword(firebaseAuth, email, password) } catch (error) { throw readableAuthError(error) }
    },
    register: async (email: string, password: string) => {
      try { await createUserWithEmailAndPassword(firebaseAuth, email, password) } catch (error) { throw readableAuthError(error) }
    },
    logout: () => signOut(firebaseAuth),
  }), [user, loading])

  useEffect(() => onAuthStateChanged(firebaseAuth, (nextUser) => {
    setUser(nextUser)
    setLoading(false)
  }), [])

  return <AuthContext.Provider value={value}>{loading ? <div className="flex min-h-screen items-center justify-center text-gray-500">Loading...</div> : user ? children : <AuthScreen />}</AuthContext.Provider>
}