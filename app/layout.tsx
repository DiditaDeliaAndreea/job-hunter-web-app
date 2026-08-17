import './globals.css'
import FirebaseAnalytics from './firebase-analytics'
import AuthProvider from './auth-provider'
import Navigation from './navigation'

export const metadata = {
  title: 'CareerMatch',
  description: 'Find job opportunities matched to your experience.',
}
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        <FirebaseAnalytics />
        <AuthProvider>
          <div className="min-h-screen md:flex">
            <Navigation />
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex-1">{children}</div>
              <footer className="border-t border-gray-200 bg-white px-5 py-4 text-center text-xs text-gray-500 md:px-10">
                Copyright © 2026 CareerMatch. All rights reserved.
              </footer>
            </div>
          </div>
        </AuthProvider>
      </body>
    </html>
  )
}