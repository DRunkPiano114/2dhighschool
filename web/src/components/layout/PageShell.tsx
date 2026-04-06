import type { ReactNode } from 'react'
import { Header } from './Header'
import { useAppStore } from '../../stores/useAppStore'

export function PageShell({ children }: { children: ReactNode }) {
  const mindReading = useAppStore((s) => s.mindReadingEnabled)

  return (
    <div className={`min-h-screen transition-colors duration-300 ${mindReading ? 'mind-reading-active' : ''}`}>
      <Header />
      <main className="max-w-6xl mx-auto px-4 py-6">
        {children}
      </main>
    </div>
  )
}
