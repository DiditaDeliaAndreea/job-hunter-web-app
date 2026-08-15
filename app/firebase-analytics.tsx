'use client'

import { useEffect } from 'react'
import { initializeFirebaseAnalytics } from '../lib/firebase'

export default function FirebaseAnalytics() {
  useEffect(() => {
    void initializeFirebaseAnalytics()
  }, [])

  return null
}