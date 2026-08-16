'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { ArrowUpRight, BriefcaseBusiness, CheckCircle2, ExternalLink, RefreshCw } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { readCachedJobs, writeCachedJobs } from '../lib/client-cache'

type Job = Record<string, string | undefined>
type IndexedJob = { job: Job; index: number }

export default function JobList({ applied }: { applied: boolean }) {
  const cachedJobs = readCachedJobs<Job>()
  const [jobs, setJobs] = useState<IndexedJob[]>(() => cachedJobs.map((job, index) => ({ job, index })).filter(({ job }) => (job.Applied === 'Yes') === applied))
  const [loading, setLoading] = useState(cachedJobs.length === 0)
  const [error, setError] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [verificationProgress, setVerificationProgress] = useState(0)
  const [verificationMessage, setVerificationMessage] = useState('')
  const [verificationLogs, setVerificationLogs] = useState<string[]>([])

  const loadJobs = async () => {
    if (jobs.length === 0) setLoading(true)
    setError('')
    try {
      const response = await apiFetch('/api/jobs', { cache: 'no-store' })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not load jobs.')
      const savedJobs = Array.isArray(data.jobs) ? data.jobs as Job[] : []
      writeCachedJobs(savedJobs)
      setJobs(savedJobs.map((job, index) => ({ job, index })).filter(({ job }) => (job.Applied === 'Yes') === applied))
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load jobs.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadJobs() }, [applied])

  const verifyJobs = async () => {
    setVerifying(true)
    setVerificationProgress(5)
    setVerificationMessage('Starting saved job verification...')
    setVerificationLogs(['Starting saved job verification...'])
    try {
      const response = await apiFetch('/api/jobs/verify/start', { method: 'POST' })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not start verification.')
      const poller = window.setInterval(async () => {
        try {
          const statusResponse = await apiFetch(`/api/search/status/${data.verification_id}`, { cache: 'no-store' })
          const status = await statusResponse.json()
          if (!statusResponse.ok) throw new Error(status?.detail || 'Verification status failed.')
          if (Array.isArray(status.logs)) setVerificationLogs(status.logs)
          if (typeof status.progress === 'number') setVerificationProgress(status.progress)
          if (status.message) setVerificationMessage(status.message)
          if (status.status === 'complete' || status.status === 'error') {
            window.clearInterval(poller)
            setVerifying(false)
            if (status.status === 'complete') await loadJobs()
          }
        } catch (pollError) {
          window.clearInterval(poller)
          setVerifying(false)
          setVerificationMessage(pollError instanceof Error ? pollError.message : 'Verification failed.')
        }
      }, 1200)
    } catch (verifyError) {
      setVerifying(false)
      setVerificationMessage(verifyError instanceof Error ? verifyError.message : 'Could not start verification.')
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-5 py-8 text-slate-900 md:px-10">
      <div className="mx-auto max-w-7xl">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-6">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">Your jobs</p>
            <h1 className="text-3xl font-bold tracking-tight">{applied ? 'Applied jobs' : 'Open jobs'}</h1>
            <p className="mt-2 text-sm text-slate-600">{applied ? 'Keep track of roles you have already applied to.' : 'Review saved opportunities that still need your attention.'}</p>
          </div>
          <button type="button" onClick={() => void loadJobs()} disabled={loading} className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </header>

        {!applied && <section className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-start gap-3"><CheckCircle2 className="mt-0.5 h-5 w-5 text-amber-700" /><div><h2 className="font-semibold text-slate-900">Check open listings</h2><p className="mt-1 text-sm text-slate-600">Check whether saved listings are still active.</p></div></div>
            <button type="button" onClick={() => void verifyJobs()} disabled={verifying || jobs.length === 0} className="rounded-md bg-amber-700 px-4 py-2 text-sm font-medium text-white hover:bg-amber-800 disabled:cursor-not-allowed disabled:opacity-50">{verifying ? 'Checking...' : 'Check listings'}</button>
          </div>
          {(verifying || verificationMessage) && <div className="mt-4"><div className="mb-2 flex justify-between text-sm text-slate-700"><span>{verificationMessage}</span><span>{verificationProgress}%</span></div><div className="h-2 overflow-hidden rounded-full bg-amber-200"><div className="h-full bg-amber-700 transition-all" style={{ width: `${verificationProgress}%` }} /></div><div className="mt-3 max-h-28 space-y-1 overflow-auto text-xs text-slate-600">{verificationLogs.map((log, index) => <p key={`${log}-${index}`}>{log}</p>)}</div></div>}
        </section>}

        {error && <p className="mt-6 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</p>}
        {loading ? <p className="mt-8 text-sm text-slate-500">Loading jobs...</p> : jobs.length === 0 ? (
          <section className="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
            <BriefcaseBusiness className="mx-auto h-10 w-10 text-slate-300" />
            <h2 className="mt-4 font-semibold">No {applied ? 'applied' : 'open'} jobs yet</h2>
            <p className="mt-1 text-sm text-slate-500">{applied ? 'Mark a job as applied and it will appear here.' : 'Run a search to build your open-jobs list.'}</p>
            {!applied && <Link href="/" className="mt-5 inline-flex rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">Start a search</Link>}
          </section>
        ) : (
          <section className="mt-8">
            <div className="mb-4 flex items-center justify-between gap-4"><h2 className="font-semibold">{jobs.length} {applied ? 'applied' : 'open'} {jobs.length === 1 ? 'job' : 'jobs'}</h2><span className="text-xs text-slate-500">Select a card for full details</span></div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {jobs.map(({ job, index }) => {
                const status = job['Verification Status'] || 'Not verified'
                const statusClass = applied
                  ? 'bg-emerald-50 text-emerald-700'
                  : status === 'Expired'
                    ? 'bg-red-50 text-red-700'
                    : status === 'Active'
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-blue-50 text-blue-700'
                return (
                  <article key={`${job['Job Title']}-${job.Company}`} className="flex min-h-56 flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md">
                    <div className="flex items-start justify-between gap-3">
                      <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${statusClass}`}>{applied ? 'Applied' : status}</span>
                      <span className="text-xs font-semibold text-slate-500">{job['Fit Score (%)'] || 'No score'}</span>
                    </div>
                    <div className="mt-5 min-w-0 flex-1">
                      <h3 className="line-clamp-2 text-lg font-semibold leading-6 text-slate-900">{job['Job Title']}</h3>
                      <p className="mt-2 truncate text-sm font-medium text-slate-600">{job.Company}</p>
                      <p className="mt-1 truncate text-sm text-slate-500">{job.Location || 'Location not specified'}</p>
                    </div>
                    <div className="mt-5 flex items-center justify-between gap-3 border-t border-slate-100 pt-4">
                      <span className="truncate text-xs text-slate-500">{job['Working Type'] || 'Working type not specified'}</span>
                      <div className="flex shrink-0 items-center gap-2"><Link href={`/jobs/${index}`} className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700">Details <ArrowUpRight className="h-3.5 w-3.5" /></Link>{job.URL && /^https?:\/\//i.test(job.URL) && <a href={job.URL} target="_blank" rel="noreferrer" className="rounded-md border border-slate-300 p-2 text-slate-500 hover:bg-slate-100 hover:text-blue-700" title="Open listing"><ExternalLink className="h-4 w-4" /></a>}</div>
                    </div>
                  </article>
                )
              })}
            </div>
          </section>
        )}
      </div>
    </main>
  )
}