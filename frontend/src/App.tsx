import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import Targets from './pages/Targets'
import Workspace from './pages/Workspace'
import PromptStudio from './pages/PromptStudio'
import OptimizationLab from './pages/OptimizationLab'
import ResponseAnalyzer from './pages/ResponseAnalyzer'
import History from './pages/History'
import Analytics from './pages/Analytics'
import Strategies from './pages/Strategies'
import Team from './pages/Team'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="targets" element={<Targets />} />
        <Route path="workspace" element={<Workspace />} />
        <Route path="studio" element={<PromptStudio />} />
        <Route path="lab" element={<OptimizationLab />} />
        <Route path="analyzer" element={<ResponseAnalyzer />} />
        <Route path="history" element={<History />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="strategies" element={<Strategies />} />
        <Route path="team" element={<Team />} />
      </Route>
    </Routes>
  )
}
