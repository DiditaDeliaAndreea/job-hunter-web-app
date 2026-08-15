'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, FileText, Upload } from 'lucide-react'
import { apiFetch } from '../../lib/api'

type ImportedCv = { id: string; name: string; size?: number; created_at?: string }

export default function CvsPage() {
  const [cvs, setCvs] = useState<ImportedCv[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  const loadCvs = async () => {
    setLoading(true)
    try {
      const response = await apiFetch('/api/cvs', { cache: 'no-store' })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not load CVs.')
      setCvs(Array.isArray(data.cvs) ? data.cvs : [])
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load CVs.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadCvs() }, [])

  const upload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    if (!files.length) return
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    setMessage('Uploading CVs...')
    try {
      const response = await apiFetch('/api/cvs', { method: 'POST', body: formData })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not upload CVs.')
      setMessage(`${data.cvs?.length || 0} CVs saved.`)
      await loadCvs()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not upload CVs.')
    } finally {
      event.target.value = ''
    }
  }

  const removeCv = async (cv: ImportedCv) => {
    if (!window.confirm(`Remove ${cv.name}? This deletes the saved CV from Firebase.`)) return
    setMessage('Removing CV...')
    try {
      const response = await apiFetch(`/api/cvs/${cv.id}`, { method: 'DELETE' })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not remove CV.')
      setCvs((current) => current.filter((item) => item.id !== cv.id))
      setMessage(`${cv.name} was removed.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not remove CV.')
    }
  }

  const renameCv = async (cv: ImportedCv) => {
    const currentName = cv.name.replace(/\.(pdf|docx)$/i, '')
    const enteredName = window.prompt('Enter a new CV filename:', currentName)
    if (enteredName === null || !enteredName.trim()) return
    const trimmedName = enteredName.trim()
    const newName = /\.(pdf|docx)$/i.test(trimmedName)
      ? trimmedName
      : `${trimmedName}${cv.name.toLowerCase().endsWith('.docx') ? '.docx' : '.pdf'}`
    setMessage('Renaming CV...')
    try {
      const formData = new FormData()
      formData.append('name', newName)
      const response = await apiFetch(`/api/cvs/${cv.id}`, { method: 'PATCH', body: formData })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not rename CV.')
      setCvs((current) => current.map((item) => item.id === cv.id ? { ...item, name: data.cv.name } : item))
      setMessage(`Renamed to ${data.cv.name}.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not rename CV.')
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 px-5 py-8 text-gray-900 md:px-10">
      <div className="mx-auto max-w-4xl">
        <Link href="/" className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:text-blue-900"><ArrowLeft className="h-4 w-4" /> Back to jobs</Link>
        <header className="mt-8 flex flex-wrap items-end justify-between gap-4 border-b border-gray-200 pb-6"><div><h1 className="text-3xl font-bold tracking-tight">My CVs</h1><p className="mt-2 text-gray-500">Your saved CVs are available for job searches and tailoring.</p></div><label className="inline-flex cursor-pointer items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"><Upload className="h-4 w-4" /> Import CVs<input type="file" accept=".pdf,.docx" multiple onChange={upload} className="hidden" /></label></header>
        {message && <p className="mt-5 rounded-md border border-blue-100 bg-blue-50 p-3 text-sm text-blue-800">{message}</p>}
        {loading ? <p className="mt-6 text-gray-500">Loading CVs...</p> : cvs.length === 0 ? <p className="mt-6 rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center text-gray-500">No CVs imported yet.</p> : <div className="mt-6 space-y-3">{cvs.map((cv) => <article key={cv.id} className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm"><FileText className="h-6 w-6 shrink-0 text-blue-600" /><div className="min-w-0 flex-1"><h2 className="truncate font-medium">{cv.name}</h2><p className="mt-1 text-sm text-gray-500">{cv.size ? `${Math.ceil(cv.size / 1024)} KB` : 'CV'}{cv.created_at ? ` · Imported ${new Date(cv.created_at).toLocaleDateString()}` : ''}</p></div><div className="flex shrink-0 gap-2"><button type="button" onClick={() => void renameCv(cv)} className="rounded-md border border-blue-200 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50">Rename</button><button type="button" onClick={() => void removeCv(cv)} className="rounded-md border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50">Remove</button></div></article>)}</div>}
      </div>
    </main>
  )
}