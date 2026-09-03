'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { ArrowUpRight, BriefcaseBusiness, CheckCircle2, ExternalLink, Filter, RefreshCw, ThumbsDown, ThumbsUp, Trash2 } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { readCachedJobs, writeCachedJobs } from '../lib/client-cache'

type Job = Record<string, string | undefined>
type IndexedJob = { job: Job; index: number }

function getPostedAgeDays(value: unknown): number | null {
  const rawValue = String(value || '').trim()
  if (!rawValue || rawValue.toLowerCase() === 'not specified') return null

  const relativeMatch = rawValue.match(/(\d+)\s+(minute|hour|day|week)s?\s+ago/i)
  if (relativeMatch) {
    const amount = Number(relativeMatch[1])
    const unit = relativeMatch[2].toLowerCase()
    if (unit === 'minute' || unit === 'hour') return 0
    if (unit === 'week') return amount * 7
    return amount
  }

  const postedAt = new Date(rawValue)
  if (Number.isNaN(postedAt.getTime())) return null
  return Math.max(0, (Date.now() - postedAt.getTime()) / (1000 * 60 * 60 * 24))
}

export default function JobList({ applied }: { applied: boolean }) {
  const cachedJobs = readCachedJobs<Job>()
  const [jobs, setJobs] = useState<IndexedJob[]>(() => cachedJobs.map((job, index) => ({ job, index })).filter(({ job }) => (job.Applied === 'Yes') === applied))
  const [loading, setLoading] = useState(cachedJobs.length === 0)
  const [error, setError] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [verificationProgress, setVerificationProgress] = useState(0)
  const [verificationMessage, setVerificationMessage] = useState('')
  const [verificationLogs, setVerificationLogs] = useState<string[]>([])
  const [jobFilter, setJobFilter] = useState('')
  const [workingTypeFilter, setWorkingTypeFilter] = useState('All')
  const [minimumScore, setMinimumScore] = useState('70')
  const [salaryFilter, setSalaryFilter] = useState('All')
  const [postedDateFilter, setPostedDateFilter] = useState('All')
  const [jobSort, setJobSort] = useState('fit-score-desc')
  const [hideExpired, setHideExpired] = useState(true)
  const [dismissingExpired, setDismissingExpired] = useState(false)
  const [feedbackSent, setFeedbackSent] = useState<Record<string, string>>({})

  const loadJobs = async () => {
    if (jobs.length === 0) setLoading(true)
    setError('')
    try {
      const searchQuery = jobFilter.trim()
      const response = await apiFetch(searchQuery ? `/api/jobs/search?q=${encodeURIComponent(searchQuery)}` : '/api/jobs', { cache: 'no-store' })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not load jobs.')
      const savedJobs = Array.isArray(data.jobs) ? data.jobs as Job[] : []
      if (!searchQuery) writeCachedJobs(savedJobs)
      setJobs(savedJobs.map((job, index) => ({ job, index })).filter(({ job }) => (job.Applied === 'Yes') === applied))
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load jobs.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadJobs() }, [applied, jobFilter])

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

  const dismissAllExpired = async () => {
    if (!window.confirm('Remove all expired jobs from your list? They will be kept for deduplication but hidden.')) return
    setDismissingExpired(true)
    try {
      const response = await apiFetch('/api/jobs/dismiss-expired', { method: 'POST' })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not remove expired jobs.')
      await loadJobs()
    } catch (dismissError) {
      setError(dismissError instanceof Error ? dismissError.message : 'Could not remove expired jobs.')
    } finally {
      setDismissingExpired(false)
    }
  }

  const dismissJob = async (job: Job) => {
    const jobTitle = job['Job Title'] || ''
    const company = job.Company || ''
    if (!window.confirm(`Remove ${jobTitle}${company ? ` at ${company}` : ''} from your open jobs?`)) return

    const formData = new FormData()
    formData.append('job_title', jobTitle)
    formData.append('company', company)
    try {
      const response = await apiFetch('/api/jobs/dismiss', { method: 'POST', body: formData })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Could not remove this job.')
      setJobs((current) => current.filter(({ job: currentJob }) => !(currentJob['Job Title'] === jobTitle && currentJob.Company === company)))
      const cachedJobs = readCachedJobs<Job>().filter((cachedJob) => !(cachedJob['Job Title'] === jobTitle && cachedJob.Company === company))
      writeCachedJobs(cachedJobs)
    } catch (dismissError) {
      setError(dismissError instanceof Error ? dismissError.message : 'Could not remove this job.')
    }
  }

  const submitMatchFeedback = async (job: Job, feedbackType: string) => {
    const feedbackKey = `${job['Job Title'] || ''}-${job.Company || ''}`
    const formData = new FormData()
    formData.append('job_title', job['Job Title'] || '')
    formData.append('company', job.Company || '')
    formData.append('feedback_type', feedbackType)
    formData.append('fit_score', job['Fit Score (%)'] || '')
    try {
      const response = await apiFetch('/api/jobs/feedback', { method: 'POST', body: formData })
      if (!response.ok) throw new Error('Could not save feedback.')
      setFeedbackSent((current) => ({ ...current, [feedbackKey]: feedbackType }))
    } catch (feedbackError) {
      setError(feedbackError instanceof Error ? feedbackError.message : 'Could not save feedback.')
    }
  }

  const displayedJobs = useMemo(() => {
    const filtered = jobs.filter(({ job }) => {
      const searchableText = [job['Job Title'], job.Company, job.Location].filter(Boolean).join(' ').toLowerCase()
      const score = Number.parseInt(String(job['Fit Score (%)'] || '').replace('%', ''), 10)
      const salary = String(job.Salary || '').trim().toLowerCase()
      const hasSalary = Boolean(salary && salary !== 'not specified')
      const ageDays = getPostedAgeDays(job['Posted Date'])
      const isExpired = (job['Verification Status'] || '').toLowerCase() === 'expired'
      return (
        (!hideExpired || !isExpired) &&
        (!jobFilter.trim() || searchableText.includes(jobFilter.trim().toLowerCase())) &&
        (workingTypeFilter === 'All' || (job['Working Type'] || 'Not specified') === workingTypeFilter) &&
        (minimumScore === '0' || Number.isNaN(score) || score >= Number(minimumScore)) &&
        (salaryFilter === 'All' || (salaryFilter === 'Available' && hasSalary) || (salaryFilter === 'Not specified' && !hasSalary)) &&
        (postedDateFilter === 'All' ||
          (postedDateFilter === 'Not specified' && ageDays === null) ||
          (postedDateFilter === '24h' && ageDays !== null && ageDays <= 1) ||
          (postedDateFilter === '3d' && ageDays !== null && ageDays <= 3) ||
          (postedDateFilter === '7d' && ageDays !== null && ageDays <= 7) ||
          (postedDateFilter === 'Older' && ageDays !== null && ageDays > 7))
      )
    })

    return [...filtered].sort((a, b) => {
      const scoreA = Number.parseInt(String(a.job['Fit Score (%)'] || '').replace('%', ''), 10)
      const scoreB = Number.parseInt(String(b.job['Fit Score (%)'] || '').replace('%', ''), 10)
      const ageA = getPostedAgeDays(a.job['Posted Date'])
      const ageB = getPostedAgeDays(b.job['Posted Date'])
      switch (jobSort) {
        case 'newest': return (ageA ?? Number.POSITIVE_INFINITY) - (ageB ?? Number.POSITIVE_INFINITY)
        case 'oldest': return (ageB ?? Number.NEGATIVE_INFINITY) - (ageA ?? Number.NEGATIVE_INFINITY)
        case 'title-asc': return String(a.job['Job Title'] || '').localeCompare(String(b.job['Job Title'] || ''))
        case 'company-asc': return String(a.job.Company || '').localeCompare(String(b.job.Company || ''))
        default: return (Number.isNaN(scoreB) ? -1 : scoreB) - (Number.isNaN(scoreA) ? -1 : scoreA)
      }
    })
  }, [jobs, jobFilter, workingTypeFilter, minimumScore, salaryFilter, postedDateFilter, jobSort])

  const clearJobFilters = () => {
    setJobFilter('')
    setWorkingTypeFilter('All')
    setMinimumScore('70')
    setSalaryFilter('All')
    setPostedDateFilter('All')
    setJobSort('fit-score-desc')
    setHideExpired(true)
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
            <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                <div>
                  <h2 className="font-semibold">Refine {applied ? 'applied' : 'open'} jobs</h2>
                  <p className="mt-1 text-xs text-slate-500">Showing {displayedJobs.length} of {jobs.length} jobs</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" onClick={() => setHideExpired((v) => !v)} className={`rounded-md border px-3 py-1.5 text-xs font-medium ${hideExpired ? 'border-red-200 bg-red-50 text-red-700 hover:bg-red-100' : 'border-slate-300 text-slate-700 hover:bg-slate-50'}`}>
                    {hideExpired ? 'Showing active only' : 'Showing all (incl. expired)'}
                  </button>
                  {!applied && (
                    <button type="button" onClick={() => void dismissAllExpired()} disabled={dismissingExpired} className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50">
                      {dismissingExpired ? 'Removing...' : 'Remove all expired'}
                    </button>
                  )}
                  <button type="button" onClick={clearJobFilters} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">Clear filters</button>
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <label className="text-sm text-slate-700 md:col-span-2 lg:col-span-2">
                  <span className="mb-2 flex items-center gap-2 font-medium"><Filter className="h-4 w-4" /> Search jobs</span>
                  <input type="search" value={jobFilter} onChange={(event) => setJobFilter(event.target.value)} placeholder="Title, company, or location" className="w-full rounded-md border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none" />
                </label>
                <label className="text-sm text-slate-700">
                  <span className="mb-2 block font-medium">Order by</span>
                  <select value={jobSort} onChange={(event) => setJobSort(event.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none">
                    <option value="fit-score-desc">Best match</option>
                    <option value="newest">Newest</option>
                    <option value="oldest">Oldest</option>
                    <option value="title-asc">Job title</option>
                    <option value="company-asc">Company</option>
                  </select>
                </label>
                <label className="text-sm text-slate-700">
                  <span className="mb-2 block font-medium">Working type</span>
                  <select value={workingTypeFilter} onChange={(event) => setWorkingTypeFilter(event.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none">
                    <option>All</option><option>Remote</option><option>Hybrid</option><option>On-site</option><option>Not specified</option>
                  </select>
                </label>
                <label className="text-sm text-slate-700">
                  <span className="mb-2 block font-medium">Minimum match</span>
                  <select value={minimumScore} onChange={(event) => setMinimumScore(event.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none">
                    <option value="0">Any score</option><option value="70">70%+</option><option value="80">80%+</option><option value="90">90%+</option>
                  </select>
                </label>
                <label className="text-sm text-slate-700">
                  <span className="mb-2 block font-medium">Salary</span>
                  <select value={salaryFilter} onChange={(event) => setSalaryFilter(event.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none">
                    <option>All</option><option value="Available">Salary available</option><option value="Not specified">Not specified</option>
                  </select>
                </label>
                <label className="text-sm text-slate-700">
                  <span className="mb-2 block font-medium">Posted date</span>
                  <select value={postedDateFilter} onChange={(event) => setPostedDateFilter(event.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none">
                    <option>All</option><option value="24h">Last 24 hours</option><option value="3d">Last 3 days</option><option value="7d">Last 7 days</option><option value="Older">Older than 7 days</option><option value="Not specified">Not specified</option>
                  </select>
                </label>
              </div>
            </div>
            <div className="mb-4 flex items-center justify-between gap-4"><h2 className="font-semibold">{displayedJobs.length} {applied ? 'applied' : 'open'} {displayedJobs.length === 1 ? 'job' : 'jobs'}</h2><span className="text-xs text-slate-500">Select a card for full details</span></div>
            {displayedJobs.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">No jobs match these filters.</p> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {displayedJobs.map(({ job, index }) => {
                const status = job['Verification Status'] || job.Status || 'Not verified'
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
                      <div className="flex shrink-0 items-center gap-2"><button type="button" onClick={() => void submitMatchFeedback(job, 'good_match')} className={`rounded-md border p-2 ${feedbackSent[`${job['Job Title'] || ''}-${job.Company || ''}`] === 'good_match' ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : 'border-slate-300 text-slate-500 hover:bg-slate-100'}`} title="Good match" aria-label="Good match"><ThumbsUp className="h-4 w-4" /></button><button type="button" onClick={() => void submitMatchFeedback(job, 'poor_match')} className={`rounded-md border p-2 ${feedbackSent[`${job['Job Title'] || ''}-${job.Company || ''}`] === 'poor_match' ? 'border-red-300 bg-red-50 text-red-700' : 'border-slate-300 text-slate-500 hover:bg-slate-100'}`} title="Poor match" aria-label="Poor match"><ThumbsDown className="h-4 w-4" /></button>{!applied && <button type="button" onClick={() => void submitMatchFeedback(job, 'job_expired')} className="rounded-md border border-amber-300 p-2 text-amber-700 hover:bg-amber-50" title="Report expired listing" aria-label="Report expired listing"><span className="text-xs font-bold">X</span></button>}<Link href={`/jobs/${index}`} className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700">Details <ArrowUpRight className="h-3.5 w-3.5" /></Link>{job.URL && /^https?:\/\//i.test(job.URL) && <a href={job.URL} target="_blank" rel="noreferrer" className="rounded-md border border-slate-300 p-2 text-slate-500 hover:bg-slate-100 hover:text-blue-700" title="Open listing"><ExternalLink className="h-4 w-4" /></a>}{!applied && <button type="button" onClick={() => void dismissJob(job)} className="rounded-md border border-red-200 p-2 text-red-600 hover:bg-red-50" title="Remove job" aria-label={`Remove ${job['Job Title'] || 'job'}`}><Trash2 className="h-4 w-4" /></button>}</div>
                    </div>
                  </article>
                )
              })}
            </div>}
          </section>
        )}
      </div>
    </main>
  )
}