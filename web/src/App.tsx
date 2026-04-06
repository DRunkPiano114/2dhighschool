import { Routes, Route, Navigate } from 'react-router-dom'
import { PixiCanvas } from './components/world/PixiCanvas'

// Legacy routes — kept available during transition
import { PageShell } from './components/layout/PageShell'
import { ForceGraph } from './components/relationships/ForceGraph'
import { EmotionTimeline } from './components/timeline/EmotionTimeline'

export default function App() {
  return (
    <Routes>
      {/* Pixel-art world viewer */}
      <Route path="/" element={<PixiCanvas />} />
      <Route path="/day/:dayId/scene/:sceneFile" element={<PixiCanvas />} />

      {/* Phase 2 analytical views (kept as-is) */}
      <Route path="/relationships" element={<PageShell><ForceGraph /></PageShell>} />
      <Route path="/timeline" element={<PageShell><EmotionTimeline /></PageShell>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
