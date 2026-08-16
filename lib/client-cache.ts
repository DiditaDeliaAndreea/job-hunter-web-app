const JOBS_CACHE_KEY = 'careermatch-jobs-cache'

export function readCachedJobs<T>(): T[] {
  if (typeof window === 'undefined') return []
  try {
    const cached = JSON.parse(window.sessionStorage.getItem(JOBS_CACHE_KEY) || 'null')
    return Array.isArray(cached) ? cached as T[] : []
  } catch {
    return []
  }
}

export function writeCachedJobs<T>(jobs: T[]): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(JOBS_CACHE_KEY, JSON.stringify(jobs))
  } catch {
    // Session storage can be unavailable in private browsing contexts.
  }
}