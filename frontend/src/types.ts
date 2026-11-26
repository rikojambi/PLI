export type Role = 'admin' | 'teacher' | 'student'

export interface RoleInfo {
  id: string
  name: Role
  description?: string | null
}

export interface User {
  id: string
  school_id: string
  role_id: string
  username: string
  full_name: string
  email: string | null
  phone: string | null
  student_number: string | null
  is_active: boolean
  must_change_password: boolean
  last_login_at: string | null
  role: RoleInfo
}

export interface AppContext {
  school: { id: string; name: string } | null
  academic_year: { id: string; name: string } | null
  semester: { id: string; name: string } | null
  subjects: Array<{ id: string; name: string; code: string; color: string | null }>
  role: Role
}

export interface ClassRow {
  id: string
  name: string
  academic_year_id: string
  semester_id: string
  grade_level: string | null
  homeroom_teacher_id: string | null
  description: string | null
  is_active: boolean
  student_count: number
  teachers: Array<{ id: string; teacher_id: string; subject_id: string | null }>
}

export interface StudentBrief {
  id: string
  full_name: string
  username: string
  student_number: string | null
  email?: string | null
  is_active: boolean
}

export interface SubjectRow {
  id: string
  code: string
  name: string
  description: string | null
  color: string | null
  is_active: boolean
}

export interface CompetencyRow {
  id: string
  subject_id: string
  code: string
  name: string
  description: string | null
  grade_level: string | null
  parent_id: string | null
  order_index: number
  is_active: boolean
}

export interface SchoolRow {
  id: string
  name: string
  npsn: string | null
  address: string | null
  phone: string | null
  email: string | null
}

export interface AcademicYearRow {
  id: string
  name: string
  start_date: string
  end_date: string
  is_active: boolean
}

export interface SemesterRow {
  id: string
  academic_year_id: string
  name: string
  start_date: string
  end_date: string
  is_active: boolean
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface AuditRow {
  id: string
  actor_id: string | null
  action: string
  entity_type: string | null
  entity_id: string | null
  details_json: Record<string, unknown>
  ip_address: string | null
  created_at: string
}

export const QUESTION_TYPES = [
  { value: 'multiple_choice', label: 'Pilihan ganda' },
  { value: 'multiple_response', label: 'Pilihan ganda kompleks' },
  { value: 'true_false', label: 'Benar / salah' },
  { value: 'matching', label: 'Menjodohkan' },
  { value: 'short_answer', label: 'Isian singkat' },
  { value: 'fill_blank', label: 'Melengkapi' },
  { value: 'essay', label: 'Uraian' },
  { value: 'stepped_essay', label: 'Uraian bertahap' },
  { value: 'image_based', label: 'Bergambar' },
  { value: 'project', label: 'Proyek' },
] as const

export type QuestionType = (typeof QUESTION_TYPES)[number]['value']

export interface QuestionOption {
  id: string
  label: string
  content: string
  is_correct: boolean | null
  match_key: string | null
  position: number
}

export interface QuestionRow {
  id: string
  subject_id: string
  competency_id: string | null
  question_type: QuestionType
  difficulty: 'easy' | 'medium' | 'hard'
  content: string
  image_path: string | null
  points: number
  time_limit_sec: number | null
  explanation: string | null
  rubric_json: Record<string, unknown>
  is_published: boolean
  options: QuestionOption[]
}

export interface MaterialRow {
  id: string
  subject_id: string
  competency_id: string | null
  teacher_id: string
  title: string
  content: string | null
  material_type: string
  file_path: string | null
  file_name: string | null
  is_published: boolean
  created_at: string
}

export interface AssessmentRow {
  id: string
  subject_id: string
  class_id: string
  teacher_id: string
  title: string
  description: string | null
  duration_min: number
  start_at: string | null
  end_at: string | null
  shuffle_questions: boolean
  shuffle_options: boolean
  allow_resume: boolean
  allow_offline: boolean
  is_published: boolean
  question_ids: string[]
  question_count: number
  max_points: number
  attempt_count: number
  already_started: boolean
}

export interface AnswerRow {
  id: string
  question_id: string
  client_id: string | null
  answer_json: Record<string, unknown>
  is_correct: boolean | null
  points_earned: number | null
  time_spent_sec: number
  changed_count: number
  updated_at: string | null
  synced_at: string | null
}

export interface AttemptRow {
  id: string
  assessment_id: string
  student_id: string
  started_at: string
  submitted_at: string | null
  status: string
  total_points: number | null
  max_points: number | null
  sync_status: string
  anomaly_flags: string[]
  answers: AnswerRow[]
  questions: QuestionRow[]
  assessment: {
    id: string
    title: string
    description: string | null
    duration_min: number
    shuffle_options: boolean
    allow_offline: boolean
    allow_resume: boolean
    started_at: string
  } | null
}

export interface SubmitResult {
  attempt_id: string
  status: string
  total_points: number
  max_points: number
  score_percent: number
  graded_automatically: number
  pending_manual: number
  anomaly_flags: string[]
}

export interface ResultRow {
  id: string
  attempt_id: string
  assessment_id: string
  student_id: string
  score: number
  mastery_percent: number | null
  graded_by: string | null
  graded_at: string
  notes: string | null
  assessment_title: string | null
  student_name: string | null
}

export interface NoteRow {
  id: string
  student_id: string
  teacher_id: string
  class_id: string | null
  note_type: 'info' | 'warning' | 'encouragement'
  title: string
  content: string
  is_read: boolean
  created_at: string
}

export interface Analytics {
  class_id: string | null
  subject_id: string | null
  student_count: number
  attempt_count: number
  average_score: number
  passing_count: number
  hardest_competencies: Array<{
    competency_id: string
    name: string
    code: string
    correct: number
    total: number
    accuracy_percent: number
  }>
  students_needing_help: Array<{
    student_id: string
    name: string
    average_score: number
    attempts: number
  }>
  evidence: Record<string, unknown>
}

export interface ImportOutcome {
  created: number
  updated: number
  skipped: number
  errors: string[]
}

// Fase 3 - Intelligence Engine
export interface BktParams {
  p_init: number
  p_transit: number
  p_slip: number
  p_guess: number
  mastery_threshold: number
}

export interface MasteryRow {
  competency_id: string
  code: string
  name: string
  subject_id: string
  mastery_probability: number
  mastery_percent: number
  status: 'not_started' | 'emerging' | 'developing' | 'proficient' | 'mastered'
  practice_count: number
  correct_count: number
  accuracy_percent: number
  last_practiced_at: string | null
  probability_trend: number[]
  observation_count: number
  evidence: Record<string, unknown>
}

export interface MasteryResponse {
  mode: 'student' | 'class'
  student_id?: string
  class_id?: string | null
  subject_id?: string | null
  rows?: MasteryRow[]
  students?: Array<{
    student_id: string
    name: string
    rows: MasteryRow[]
  }>
  competency_count: number
  evidence: Record<string, unknown>
}

export interface Recommendation {
  id: string
  student_id: string
  competency_id: string | null
  rec_type: string
  title: string
  reason: string
  payload_json: Record<string, unknown>
  priority: number
  is_completed: boolean
  evidence_json: Record<string, unknown>
}

export interface AdaptiveQuestion {
  question: {
    id: string
    subject_id: string
    competency_id: string | null
    question_type: string
    content: string
    difficulty: string
    points: number
    rubric_json: Record<string, unknown>
    gap_category: string
    options: Array<{
      id: string
      label: string
      content: string
      position: number
      is_correct?: boolean | null
      match_key?: string | null
    }>
  } | null
  reason: string
  evidence: Record<string, unknown>
}

export interface AdaptiveResult {
  idempotent: boolean
  is_correct: boolean
  points_earned: number
  mastery_before: number
  mastery_after: number
  status: string
  evidence: Record<string, unknown>
}

export interface GapRow {
  competency_id: string
  code: string
  name: string
  subject_id: string
  accuracy_percent: number
  mastery_probability: number
  gap_score: number
  dominant_category: string
  category_counts: Record<string, number>
  observations: number
  evidence: Record<string, unknown>
}

export interface GapReport {
  mode: 'student' | 'class'
  rows: GapRow[]
  student_count: number
  observation_count: number
  evidence: Record<string, unknown>
}

export interface DropoutEvaluation {
  available: boolean
  status: string
  reason: string | null
  requirements?: string[]
  advisory_note?: string
  metrics?: Record<string, unknown>
  source?: string | null
  validated_at?: string | null
  limitations?: string[]
  note?: string
  advisory_indicators: Array<{
    student_id: string
    name: string
    average_mastery_percent: number
    low_competency_count: number
    signals: string[]
    is_prediction: boolean
  }>
}

export interface BktParamsInfo {
  params: BktParams
  source: 'environment_defaults' | 'database_override'
  updated_at: string | null
  definitions: Record<string, string>
}

// Fase 4 - AI Provider, Tutor, RAG dan Generator
export interface AiAdapterInfo {
  name: string
  label: string
  requires_key: boolean
  default_base_url: string
  supports_chat: boolean
  supports_embedding: boolean
  discovery: string
  note: string
  seed_adapter: string
}

export interface AiBudget {
  daily_token_limit: number
  monthly_cost_limit_usd: number
  max_tokens_per_request: number
  allow_unknown_cost: boolean
}

export interface AiBudgetStatus {
  policy: AiBudget
  used_today_tokens: number
  used_30d_cost_usd: number
  daily_remaining_tokens: number
  cost_remaining_usd: number
}

export interface AiStatus {
  available: boolean
  active_providers: number
  verified_models: number
  detail: string
  budget: AiBudgetStatus
}

export interface AiProvider {
  id: string
  name: string
  display_name: string
  adapter: string
  base_url: string | null
  model: string | null
  embedding_model: string | null
  api_key_env: string | null
  key_hint: string | null
  has_key: boolean
  is_active: boolean
  is_primary: boolean
  is_fallback: boolean
  priority: number
  max_tokens: number
  timeout_sec: number
  requests_per_hour: number
  monthly_token_limit: number
  input_cost_per_million: number
  output_cost_per_million: number
  config_json: Record<string, unknown>
  last_tested_at: string | null
  last_error: string | null
  model_count: number
}

export interface AiModel {
  id: string
  provider_id: string
  model_id: string
  display_name: string | null
  capabilities_json: Record<string, unknown>
  context_window: number | null
  discovered: boolean
  is_enabled: boolean
}

export interface AiUsage {
  id: string
  provider_id: string | null
  provider_name: string | null
  user_id: string | null
  purpose: string
  model: string | null
  tokens_in: number
  tokens_out: number
  cost_usd: number
  cost_source: string
  request_id: string | null
  latency_ms: number | null
  success: boolean
  error: string | null
  created_at: string
}

export interface AiDocument {
  id: string
  subject_id: string | null
  class_id: string | null
  teacher_id: string
  title: string
  mime_type: string
  file_size: number
  status: string
  chunk_count: number
  created_at: string
  updated_at: string
}

export interface AiCitation {
  number: number
  document_id: string
  title: string
  chunk_index: number
  score: number
}

export interface RagAnswer {
  available: boolean
  status: string
  answer: string
  citations: AiCitation[]
  evidence: Record<string, unknown>
}

export interface TutorMessage {
  id: string
  role: string
  content: string
  sources_json: AiCitation[]
  created_at: string
}

export interface TutorConversation {
  id: string
  title: string
  subject_id: string | null
  competency_id: string | null
  updated_at: string
  messages: TutorMessage[]
}

export interface TutorChatResult {
  idempotent: boolean
  conversation_id: string
  message: TutorMessage
  available: boolean
  evidence: Record<string, unknown>
}

export interface GeneratedDraft {
  id: string
  kind: 'question' | 'material'
  status: 'draft' | 'approved' | 'published' | 'rejected'
  title: string
  content_json: Record<string, unknown>
  sources_json: AiCitation[]
  model_info_json: Record<string, unknown>
  review_note: string | null
  published_ref_id: string | null
  created_at: string
  updated_at: string
}
