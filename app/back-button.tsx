'use client'

import { ArrowLeft } from 'lucide-react'
import { useRouter } from 'next/navigation'

export default function BackButton({ label = 'Back' }: { label?: string }) {
  const router = useRouter()

  return (
    <button
      type="button"
      onClick={() => {
        if (window.history.length > 1) {
          router.back()
        } else {
          router.push('/')
        }
      }}
      className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:text-blue-900"
    >
      <ArrowLeft className="h-4 w-4" /> {label}
    </button>
  )
}
