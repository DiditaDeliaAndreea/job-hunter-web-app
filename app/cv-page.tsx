'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, FileText, Upload } from 'lucide-react'
import { apiFetch } from '../lib/api'
import mammoth from 'mammoth'
import { readCachedCvs, writeCachedCvs } from '../lib/client-cache'

type ImportedCv = { id: string; name: string; size?: number; created_at?: string }
type PreviewCacheEntry = { url?: string; html?: string }

const previewCache = new Map<string, PreviewCacheEntry>()
const PREVIEW_TIMEOUT_MS = 20000

export default function CvPage() {
  const [cvs, setCvs] = useState<ImportedCv[]>(() => readCachedCvs<ImportedCv>())
  const [loading, setLoading] = useState(() => readCachedCvs<ImportedCv>().length === 0)
  const [message, setMessage] = useState('')
  const [selectedCv, setSelectedCv] = useState<ImportedCv | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewHtml, setPreviewHtml] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const loadCvs = async () => {
    if (cvs.length === 0) setLoading(true)
    try {
      const response = await apiFetch('/api/cvs', { cache: 'no-store' })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not load CVs.')
      const records = Array.isArray(data.cvs) ? data.cvs as ImportedCv[] : []
      writeCachedCvs(records)
      setCvs(records)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load CVs.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadCvs() }, [])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), PREVIEW_TIMEOUT_MS)
    setPreviewUrl(null)
    setPreviewHtml(null)
    if (!selectedCv) {
      window.clearTimeout(timeoutId)
      controller.abort()
      return () => undefined
    }

    const loadPreview = async () => {
      setPreviewLoading(true)
      try {
        const cachedPreview = previewCache.get(selectedCv.id)
        if (cachedPreview) {
          if (active) {
            setPreviewUrl(cachedPreview.url || null)
            setPreviewHtml(cachedPreview.html || null)
          }
          return
        }

        const response = await apiFetch(`/api/cvs/${selectedCv.id}/content`, { signal: controller.signal })
        if (!response.ok) throw new Error('Could not open this CV.')
        const blob = await response.blob()
        if (selectedCv.name.toLowerCase().endsWith('.docx')) {
          const result = await mammoth.convertToHtml({ arrayBuffer: await blob.arrayBuffer() })
          previewCache.set(selectedCv.id, { html: result.value })
          if (active) setPreviewHtml(result.value)
        } else {
          const objectUrl = URL.createObjectURL(blob)
          previewCache.set(selectedCv.id, { url: objectUrl })
          if (active) setPreviewUrl(objectUrl)
        }
      } catch (error) {
        if (active) {
          setMessage(controller.signal.aborted ? 'CV preview timed out. Please try again.' : error instanceof Error ? error.message : 'Could not open this CV.')
        }
      } finally {
        window.clearTimeout(timeoutId)
        if (active) setPreviewLoading(false)
      }
    }

    void loadPreview()
    return () => {
      active = false
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [selectedCv])

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
    if (!window.confirm(`Remove ${cv.name}? This deletes the saved CV.`)) return
    setMessage('Removing CV...')
    try {
      const response = await apiFetch(`/api/cvs/${cv.id}`, { method: 'DELETE' })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not remove CV.')
      setCvs((current) => current.filter((item) => item.id !== cv.id))
      writeCachedCvs(cvs.filter((item) => item.id !== cv.id))
      if (selectedCv?.id === cv.id) setSelectedCv(null)
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
    const newName = /\.(pdf|docx)$/i.test(trimmedName) ? trimmedName : `${trimmedName}${cv.name.toLowerCase().endsWith('.docx') ? '.docx' : '.pdf'}`
    setMessage('Renaming CV...')
    try {
      const formData = new FormData()
      formData.append('name', newName)
      const response = await apiFetch(`/api/cvs/${cv.id}`, { method: 'PATCH', body: formData })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not rename CV.')
      setCvs((current) => current.map((item) => item.id === cv.id ? { ...item, name: data.cv.name } : item))
      writeCachedCvs(cvs.map((item) => item.id === cv.id ? { ...item, name: data.cv.name } : item))
      setSelectedCv((current) => current?.id === cv.id ? { ...current, name: data.cv.name } : current)
      setMessage(`Renamed to ${data.cv.name}.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not rename CV.')
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 px-5 py-8 text-gray-900 md:px-10">
      <div className="w-full">
        <Link href="/" className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:text-blue-900"><ArrowLeft className="h-4 w-4" /> Back to jobs</Link>
        <header className="mt-8 flex flex-wrap items-end justify-between gap-4 border-b border-gray-200 pb-6"><div><h1 className="text-3xl font-bold tracking-tight">My CVs</h1><p className="mt-2 text-gray-500">Your saved CVs are ready to use for job searches and tailoring.</p></div><label className="inline-flex cursor-pointer items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"><Upload className="h-4 w-4" /> Add CVs<input type="file" accept=".pdf,.docx" multiple onChange={upload} className="hidden" /></label></header>
        {message && <p className="mt-5 rounded-md border border-blue-100 bg-blue-50 p-3 text-sm text-blue-800">{message}</p>}
        <div className="mt-8 grid w-full gap-10 lg:grid-cols-[minmax(0,0.8fr)_minmax(560px,1.5fr)]">
          <div>{loading ? <p className="text-gray-500">Loading CVs...</p> : cvs.length === 0 ? <p className="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center text-gray-500">No CVs imported yet.</p> : <div className="space-y-3">{cvs.map((cv) => <article key={cv.id} className={`flex cursor-pointer items-center gap-4 rounded-xl border bg-white p-4 shadow-sm transition hover:border-blue-300 hover:shadow-md ${selectedCv?.id === cv.id ? 'border-blue-500 ring-2 ring-blue-100' : 'border-gray-200'}`} onClick={() => setSelectedCv(cv)}><FileText className="h-6 w-6 shrink-0 text-blue-600" /><div className="min-w-0 flex-1"><h2 className="truncate font-medium">{cv.name}</h2><p className="mt-1 text-sm text-gray-500">{cv.size ? `${Math.ceil(cv.size / 1024)} KB` : 'CV'}{cv.created_at ? ` · Imported ${new Date(cv.created_at).toLocaleDateString()}` : ''}</p></div><div className="flex shrink-0 gap-2" onClick={(event) => event.stopPropagation()}><button type="button" onClick={() => void renameCv(cv)} className="rounded-md border border-blue-200 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50">Rename</button><button type="button" onClick={() => void removeCv(cv)} className="rounded-md border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50">Remove</button></div></article>)}</div>}</div>
          <aside className="min-h-[720px] rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">{!selectedCv ? <div className="flex h-full min-h-[650px] items-center justify-center text-center text-sm text-gray-500">Click a CV to open its preview here.</div> : <><div className="mb-5 flex items-start justify-between gap-3 border-b border-gray-100 pb-5"><div className="min-w-0"><h2 className="truncate text-lg font-semibold text-gray-900">{selectedCv.name}</h2><p className="mt-1 text-xs text-gray-500">CV preview</p></div><button type="button" onClick={() => setSelectedCv(null)} className="rounded-md p-1 text-gray-500 hover:bg-gray-100" aria-label="Close CV preview">&#10005;</button></div>{previewLoading ? <div className="flex h-[620px] items-center justify-center text-sm text-gray-500">Opening CV...</div> : previewHtml ? <div className="prose prose-sm h-[620px] max-w-none overflow-y-auto rounded-md border border-gray-200 p-6" dangerouslySetInnerHTML={{ __html: previewHtml }} /> : previewUrl ? <iframe src={previewUrl} title={`Preview of ${selectedCv.name}`} className="h-[620px] w-full rounded-md border border-gray-200" /> : <p className="text-sm text-red-600">Could not open this CV.</p>}</>}</aside>
        </div>
      </div>
    </main>
  )
}
