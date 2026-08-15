import { firebaseAuth } from './firebase'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const user = firebaseAuth.currentUser
  const token = user ? await user.getIdToken() : null
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)

  return fetch(`${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`, {
    ...init,
    headers,
  })
}
