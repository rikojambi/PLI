import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ProtectedRoute } from './components/ProtectedRoute'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { MyClassesPage } from './pages/MyClassesPage'
import { ProgressPage } from './pages/ProgressPage'
import { SyncPage } from './pages/SyncPage'
import { ClassesPage } from './pages/admin/ClassesPage'
import { OperationsPage } from './pages/admin/OperationsPage'
import { SettingsPage } from './pages/admin/SettingsPage'
import { SubjectsPage } from './pages/admin/SubjectsPage'
import { UsersPage } from './pages/admin/UsersPage'
import { AdaptivePage } from './pages/intelligence/AdaptivePage'
import { EngineSettingsPage } from './pages/intelligence/EngineSettingsPage'
import { EvaluationPage } from './pages/intelligence/EvaluationPage'
import { GapsPage } from './pages/intelligence/GapsPage'
import { MasteryPage } from './pages/intelligence/MasteryPage'
import { DocumentsPage } from './pages/ai/DocumentsPage'
import { GeneratorPage } from './pages/ai/GeneratorPage'
import { ProvidersPage } from './pages/ai/ProvidersPage'
import { RagPage } from './pages/ai/RagPage'
import { TutorPage } from './pages/ai/TutorPage'
import { UsagePage } from './pages/ai/UsagePage'
import { AnalyticsPage } from './pages/learning/AnalyticsPage'
import { AssessmentsPage } from './pages/learning/AssessmentsPage'
import { GradingPage } from './pages/learning/GradingPage'
import { ImportPage } from './pages/learning/ImportPage'
import { MaterialsPage } from './pages/learning/MaterialsPage'
import { NotesPage } from './pages/learning/NotesPage'
import { QuestionsPage } from './pages/learning/QuestionsPage'
import { ResultsPage } from './pages/learning/ResultsPage'
import { TakeAssessmentPage } from './pages/learning/TakeAssessmentPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="my-classes" element={<MyClassesPage />} />
          <Route path="progress" element={<ProgressPage />} />
          <Route path="sync" element={<SyncPage />} />
          <Route path="materials" element={<MaterialsPage />} />
          <Route path="assessments" element={<AssessmentsPage />} />
          <Route path="notes" element={<NotesPage />} />
          <Route path="mastery" element={<MasteryPage />} />
          <Route path="ai-ask" element={<RagPage />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute roles={['admin', 'teacher']} />}>
        <Route element={<AppShell />}>
          <Route path="questions" element={<QuestionsPage />} />
          <Route path="grading" element={<GradingPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="gaps" element={<GapsPage />} />
          <Route path="evaluation" element={<EvaluationPage />} />
          <Route path="ai-documents" element={<DocumentsPage />} />
          <Route path="ai-generator" element={<GeneratorPage />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute roles={['student']} />}>
        <Route element={<AppShell />}>
          <Route path="results" element={<ResultsPage />} />
          <Route path="adaptive" element={<AdaptivePage />} />
          <Route path="ai-tutor" element={<TutorPage />} />
          <Route path="assessments/:assessmentId/take" element={<TakeAssessmentPage />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute roles={['admin']} />}>
        <Route element={<AppShell />}>
          <Route path="users" element={<UsersPage />} />
          <Route path="classes" element={<ClassesPage />} />
          <Route path="subjects" element={<SubjectsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="operations" element={<OperationsPage />} />
          <Route path="engine" element={<EngineSettingsPage />} />
          <Route path="ai-providers" element={<ProvidersPage />} />
          <Route path="ai-usage" element={<UsagePage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
