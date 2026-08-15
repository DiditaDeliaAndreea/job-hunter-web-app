'use client'

import Link from 'next/link'
import { ArrowLeft, Mail, ShieldCheck, UserRound } from 'lucide-react'
import { useAuth } from '../auth-provider'

export default function AccountPage() {
  const { user } = useAuth()
  return (
    <main className="min-h-screen bg-gray-50 px-5 py-8 text-gray-900 md:px-10">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:text-blue-900"><ArrowLeft className="h-4 w-4" /> Back to jobs</Link>
        <header className="mt-8 border-b border-gray-200 pb-6">
          <h1 className="text-3xl font-bold tracking-tight">Account</h1>
          <p className="mt-2 text-gray-500">Your sign-in and privacy details.</p>
        </header>
        <section className="mt-6 space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-3"><Mail className="h-5 w-5 text-blue-600" /><div><p className="text-xs font-medium uppercase tracking-wide text-gray-500">Email</p><p className="mt-1 font-medium">{user?.email}</p></div></div>
          <div className="flex items-center gap-3"><UserRound className="h-5 w-5 text-blue-600" /><div><p className="text-xs font-medium uppercase tracking-wide text-gray-500">User ID</p><p className="mt-1 break-all font-mono text-sm text-gray-700">{user?.uid}</p></div></div>
          <div className="flex items-center gap-3"><ShieldCheck className="h-5 w-5 text-emerald-600" /><p className="text-sm text-gray-700">Your jobs, CVs, and tailoring prompts are stored in your Firebase account space.</p></div>
        </section>
      </div>
    </main>
  )
}