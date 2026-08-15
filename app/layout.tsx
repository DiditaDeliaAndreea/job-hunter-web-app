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
            <div className="min-w-0 flex-1">{children}</div>
          </div>
        </AuthProvider>
      </body>
    </html>
  )
}