import { Routes, Route, Navigate } from 'react-router-dom'
import { PixiCanvas } from './components/world/PixiCanvas'
import { DailyReport, DailyReportHome } from './components/daily/DailyReport'
import { CharacterGallery, CharacterArchivePage } from './components/gallery/CharacterGallery'
import { GodModeChat } from './components/ui/GodModeChat'
import { RolePlayChat } from './components/ui/RolePlayChat'

// Legacy routes — kept available during transition
import { PageShell } from './components/layout/PageShell'
import { ForceGraph } from './components/relationships/ForceGraph'
import { EmotionTimeline } from './components/timeline/EmotionTimeline'

export default function App() {
  return (
    <>
      <Routes>
        {/* Landing = 班级日报. Redirects to /day/<latest>. */}
        <Route path="/" element={<DailyReportHome />} />
        <Route path="/day/:dayId" element={<DailyReport />} />

        {/* Pixel-art world viewer — scene deep-dive, reached from a daily link. */}
        <Route path="/day/:dayId/scene/:sceneFile" element={<PixiCanvas />} />

        {/* Character archive gallery */}
        <Route path="/characters" element={<CharacterGallery />} />
        <Route path="/characters/day/:dayId" element={<CharacterGallery />} />
        <Route path="/characters/:agentId" element={<CharacterArchivePage />} />

        {/* Phase 2 analytical views (kept as-is) */}
        <Route path="/relationships" element={<PageShell><ForceGraph /></PageShell>} />
        <Route path="/timeline" element={<PageShell><EmotionTimeline /></PageShell>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <GodModeChat />
      <RolePlayChat />
    </>
  )
}
