'use client'

import Link from 'next/link'
import { ArrowLeft, Mail, ShieldCheck } from 'lucide-react'
import { useAuth } from '../auth-provider'

export default function AccountPage() {
  const { user } = useAuth()
  return (
    <main className="min-h-screen bg-slate-50 px-5 py-8 text-slate-900 md:px-10">
      <div className="mx-auto max-w-4xl">
        <Link href="/" className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:text-blue-900"><ArrowLeft className="h-4 w-4" /> Back to jobs</Link>
        <header className="mt-8 rounded-2xl border border-slate-200 bg-white px-6 py-7 shadow-sm md:px-8">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">Profile</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Account</h1>
          <p className="mt-2 max-w-xl text-slate-500">Manage your account details and understand how your information is kept private.</p>
        </header>
        <section className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-start gap-4 border-b border-slate-100 p-6 md:p-7">
            <span className="rounded-lg bg-blue-50 p-3"><Mail className="h-5 w-5 text-blue-600" /></span>
            <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Email address</p><p className="mt-2 break-all font-medium text-slate-900">{user?.email}</p></div>
          </div>
          <div className="flex items-start gap-4 bg-emerald-50/60 p-6 md:p-7">
            <span className="rounded-lg bg-emerald-100 p-3"><ShieldCheck className="h-5 w-5 text-emerald-700" /></span>
            <div><h2 className="font-semibold text-slate-900">Your information is private</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Your jobs, CVs, and tailoring prompts are stored securely with your account and are only available after you sign in.</p></div>
          </div>
        </section>
      </div>
    </main>
  )
}