import { Routes, Route, Navigate } from 'react-router-dom'
import { PageShell } from './components/layout/PageShell'
import { SeatMap } from './components/classroom/SeatMap'
import { SceneViewer } from './components/dialogue/SceneViewer'
import { ProfilePage } from './components/character/ProfilePage'
import { ForceGraph } from './components/relationships/ForceGraph'
import { PropagationView } from './components/gossip/PropagationView'
import { EmotionTimeline } from './components/timeline/EmotionTimeline'

export default function App() {
  return (
    <PageShell>
      <Routes>
        <Route path="/" element={<SeatMap />} />
        <Route path="/day/:dayId/scene/:sceneFile" element={<SceneViewer />} />
        <Route path="/character/:agentId" element={<ProfilePage />} />
        <Route path="/relationships" element={<ForceGraph />} />
        <Route path="/gossip" element={<PropagationView />} />
        <Route path="/timeline" element={<EmotionTimeline />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </PageShell>
  )
}
