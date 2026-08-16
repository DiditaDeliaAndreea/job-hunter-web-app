const JOBS_CACHE_KEY = 'careermatch-jobs-cache'
const CVS_CACHE_KEY = 'careermatch-cvs-cache'
const PREFERENCES_CACHE_KEY = 'careermatch-preferences-cache'

function readCache<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback
  try {
    const cached = JSON.parse(window.sessionStorage.getItem(key) || 'null')
    return cached === null ? fallback : cached as T
  } catch {
    return fallback
  }
}

function writeCache<T>(key: string, value: T): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Session storage can be unavailable in private browsing contexts.
  }
}

export function readCachedJobs<T>(): T[] {
  const cached = readCache<unknown>(JOBS_CACHE_KEY, [])
  return Array.isArray(cached) ? cached as T[] : []
}

export function writeCachedJobs<T>(jobs: T[]): void {
  writeCache(JOBS_CACHE_KEY, jobs)
}

export function readCachedCvs<T>(): T[] {
  const cached = readCache<unknown>(CVS_CACHE_KEY, [])
  return Array.isArray(cached) ? cached as T[] : []
}

export function writeCachedCvs<T>(cvs: T[]): void {
  writeCache(CVS_CACHE_KEY, cvs)
}

export type CachedPreferences = {
  targetRoles: string[]
  excludedRoles: string[]
}

export function readCachedPreferences(): CachedPreferences | null {
  return readCache<CachedPreferences | null>(PREFERENCES_CACHE_KEY, null)
}

export function writeCachedPreferences(preferences: CachedPreferences): void {
  writeCache(PREFERENCES_CACHE_KEY, preferences)
}