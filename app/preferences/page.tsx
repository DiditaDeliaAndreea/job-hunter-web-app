'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Save } from 'lucide-react'

const STORAGE_KEY = 'careermatch-role-preferences'

export default function PreferencesPage() {
  const [targetRoles, setTargetRoles] = useState('')
  const [excludedRoles, setExcludedRoles] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (!saved) return
    try {
      const preferences = JSON.parse(saved)
      setTargetRoles(typeof preferences.targetRoles === 'string' ? preferences.targetRoles : '')
      setExcludedRoles(typeof preferences.excludedRoles === 'string' ? preferences.excludedRoles : '')
    } catch {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  }, [])

  const save = () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ targetRoles, excludedRoles }))
    setMessage('Job preferences saved for future searches.')
  }

  const clear = () => {
    window.localStorage.removeItem(STORAGE_KEY)
    setTargetRoles('')
    setExcludedRoles('')
    setMessage('Job preferences cleared. Default roles will be used.')
  }

  return (
    <main className="min-h-screen bg-gray-50 px-5 py-8 text-gray-900 md:px-10">
      <div className="mx-auto max-w-4xl">
        <Link href="/" className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:text-blue-900"><ArrowLeft className="h-4 w-4" /> Back to jobs</Link>
        <header className="mt-8 border-b border-gray-200 pb-6"><h1 className="text-3xl font-bold tracking-tight">Job preferences</h1><p className="mt-2 text-gray-500">Set the roles to prioritize and exclude from your searches.</p></header>
        <div className="mt-6 grid gap-5 rounded-xl border border-gray-200 bg-white p-6 shadow-sm md:grid-cols-2">
          <label className="text-sm font-medium text-gray-700">Target roles<textarea value={targetRoles} onChange={(event) => setTargetRoles(event.target.value)} rows={10} placeholder="One role per line or separated by commas" className="mt-2 w-full rounded-md border border-gray-300 p-3 font-normal focus:border-blue-500 focus:outline-none" /></label>
          <label className="text-sm font-medium text-gray-700">Excluded roles<textarea value={excludedRoles} onChange={(event) => setExcludedRoles(event.target.value)} rows={10} placeholder="Roles you do not want to see" className="mt-2 w-full rounded-md border border-gray-300 p-3 font-normal focus:border-blue-500 focus:outline-none" /></label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3"><button type="button" onClick={save} className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"><Save className="h-4 w-4" /> Save preferences</button><button type="button" onClick={clear} className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Clear</button>{message && <span className="text-sm text-gray-600">{message}</span>}</div>
      </div>
    </main>
  )
}