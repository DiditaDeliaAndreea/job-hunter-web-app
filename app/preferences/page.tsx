'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Save } from 'lucide-react'
import { apiFetch } from '../../lib/api'

const STORAGE_KEY = 'careermatch-role-preferences'

export default function PreferencesPage() {
  const [targetRoles, setTargetRoles] = useState<string[]>([])
  const [excludedRoles, setExcludedRoles] = useState<string[]>([])
  const [targetInput, setTargetInput] = useState('')
  const [excludedInput, setExcludedInput] = useState('')
  const [message, setMessage] = useState('')

  const parseRoles = (value: unknown): string[] => {
    if (typeof value !== 'string') return []
    return [...new Set(value.split(/[\n,]/).map((role) => role.trim().replace(/^['"]|['"]$/g, '').trim()).filter(Boolean))]
  }

  useEffect(() => {
    const loadPreferences = async () => {
      try {
        const response = await apiFetch('/api/preferences/roles', { cache: 'no-store' })
        const preferences = await response.json()
        if (!response.ok) throw new Error(preferences?.detail || 'Could not load preferences.')
        setTargetRoles(Array.isArray(preferences.target_roles) ? preferences.target_roles : parseRoles(preferences.targetRoles))
        setExcludedRoles(Array.isArray(preferences.excluded_roles) ? preferences.excluded_roles : parseRoles(preferences.excludedRoles))
      } catch {
        const saved = window.localStorage.getItem(STORAGE_KEY)
        if (!saved) return
        try {
          const preferences = JSON.parse(saved)
          setTargetRoles(parseRoles(preferences.targetRoles))
          setExcludedRoles(parseRoles(preferences.excludedRoles))
        } catch {
          window.localStorage.removeItem(STORAGE_KEY)
        }
      }
    }
    void loadPreferences()
  }, [])

  const save = () => {
    const nextTargetRoles = addRole(targetRoles, targetInput)
    const nextExcludedRoles = addRole(excludedRoles, excludedInput)
    setTargetRoles(nextTargetRoles)
    setExcludedRoles(nextExcludedRoles)
    setTargetInput('')
    setExcludedInput('')
    const formData = new FormData()
    formData.append('target_roles', nextTargetRoles.join('\n'))
    formData.append('excluded_roles', nextExcludedRoles.join('\n'))
    void apiFetch('/api/preferences/roles', { method: 'PUT', body: formData }).then(async (response) => {
      if (!response.ok) throw new Error('Could not save preferences.')
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ targetRoles: nextTargetRoles.join('\n'), excludedRoles: nextExcludedRoles.join('\n') }))
      setMessage('Job preferences saved for future searches.')
    }).catch((error) => setMessage(error instanceof Error ? error.message : 'Could not save preferences.'))
  }

  const clear = () => {
    setTargetRoles([])
    setExcludedRoles([])
    setTargetInput('')
    setExcludedInput('')
    const formData = new FormData()
    void apiFetch('/api/preferences/roles', { method: 'PUT', body: formData }).then(() => {
      window.localStorage.removeItem(STORAGE_KEY)
      setMessage('Job preferences cleared. Default roles will be used.')
    }).catch(() => setMessage('Could not clear preferences.'))
  }

  const addRole = (roles: string[], value: string): string[] => {
    const newRoles = parseRoles(value)
    return [...new Set([...roles, ...newRoles])]
  }

  const handleRoleInput = (
    event: React.KeyboardEvent<HTMLInputElement>,
    roles: string[],
    setRoles: (roles: string[]) => void,
    input: string,
    setInput: (value: string) => void,
  ) => {
    if (event.key !== 'Enter' && event.key !== ',') return
    event.preventDefault()
    const nextRoles = addRole(roles, input)
    setRoles(nextRoles)
    setInput('')
  }

  const RolePills = ({ roles, setRoles, input, setInput, placeholder }: {
    roles: string[]
    setRoles: (roles: string[]) => void
    input: string
    setInput: (value: string) => void
    placeholder: string
  }) => (
    <div className="mt-6 min-h-60 flex-1 rounded-xl border border-slate-300 bg-white p-4 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 md:p-5">
      <div className="flex flex-wrap content-start gap-3">
        {roles.map((role) => (
          <button key={role} type="button" onClick={() => setRoles(roles.filter((item) => item !== role))} className="inline-flex max-w-full items-center gap-2 rounded-full bg-blue-50 px-3 py-1.5 text-left text-xs font-semibold text-blue-700 hover:bg-blue-100" title="Remove role">
            <span className="truncate">{role}</span><span aria-hidden="true" className="text-blue-400">x</span>
          </button>
        ))}
        <input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => handleRoleInput(event, roles, setRoles, input, setInput)} onBlur={() => { const nextRoles = addRole(roles, input); setRoles(nextRoles); setInput('') }} placeholder={roles.length ? 'Add another role...' : placeholder} className="min-w-[14rem] flex-1 border-0 px-1 py-2 text-sm text-slate-800 outline-none" />
      </div>
    </div>
  )

  return (
    <main className="min-h-screen bg-slate-50 px-5 py-10 text-slate-900 md:px-12 lg:px-16">
      <div className="w-full">
        <Link href="/" className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:text-blue-900"><ArrowLeft className="h-4 w-4" /> Back to jobs</Link>
        <header className="mt-10 rounded-2xl border border-slate-200 bg-white px-7 py-9 shadow-sm md:px-10">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">Search settings</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Job preferences</h1>
          <p className="mt-2 max-w-2xl text-slate-500">Choose the roles you want to see more often and the ones you want to leave out.</p>
        </header>
        <div className="mt-8 grid w-full gap-8 md:grid-cols-2">
          <label className="flex min-h-[25rem] w-full flex-col rounded-2xl border border-slate-200 bg-white p-7 text-sm font-semibold text-slate-800 shadow-sm md:p-8">
            <span className="block text-base">Roles to look for</span>
            <span className="mt-1 block font-normal text-slate-500">Add one role per line or separate roles with commas.</span>
            <RolePills roles={targetRoles} setRoles={setTargetRoles} input={targetInput} setInput={setTargetInput} placeholder="Type a role and press Enter" />
          </label>
          <label className="flex min-h-[25rem] w-full flex-col rounded-2xl border border-slate-200 bg-white p-7 text-sm font-semibold text-slate-800 shadow-sm md:p-8">
            <span className="block text-base">Roles to leave out</span>
            <span className="mt-1 block font-normal text-slate-500">Add roles you do not want included in your results.</span>
            <RolePills roles={excludedRoles} setRoles={setExcludedRoles} input={excludedInput} setInput={setExcludedInput} placeholder="Type a role and press Enter" />
          </label>
        </div>
        <div className="mt-8 flex min-h-16 flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white px-6 py-4 shadow-sm">
          <button type="button" onClick={save} className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700"><Save className="h-4 w-4" /> Save preferences</button>
          <button type="button" onClick={clear} className="rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">Clear</button>
          {message && <span className="basis-full text-sm text-slate-600 md:basis-auto">{message}</span>}
        </div>
      </div>
    </main>
  )
}