// Types mirroring track_2b/backend/sovra/models.py and api.py response shapes.

export type Relation =
  | 'consistent'
  | 'potential_conflict'
  | 'insufficient_evidence'
  | 'unrelated'

export type ReviewStatus = 'pending' | 'confirmed_for_review' | 'dismissed'

export type ExtractionStatus =
  | 'ok'
  | 'unresolved'
  | 'failed'
  | 'truncated'
  | 'ocr_not_implemented'

export type AnalysisStatus = 'queued' | 'running' | 'complete' | 'partial' | 'failed'

export interface Passage {
  id: string
  document_id: string
  page: number
  text: string
  start_offset: number
  end_offset: number
  paragraph_index: number
}

export interface Citation {
  passage_id: string
  document_id: string
  page: number
  start_offset: number
  end_offset: number
  quote: string
  resolved: boolean
  reason: string
}

export interface Claim {
  id: string
  document_id: string
  subject: string
  predicate: string
  value: string
  unit: string
  scope: string
  effective_date: string
  source_passage_id: string
  quote_start: number
  quote_end: number
  quote: string
  extraction_status: ExtractionStatus
  notes: string
  subject_normalized: string
  predicate_normalized: string
  value_normalized: string
  unit_normalized: string
  origin: string
}

export interface Finding {
  id: string
  analysis_id: string
  claim_ids: string[]
  relation: Relation
  explanation: string
  evidence: Citation[]
  limitations: string[]
  review_status: ReviewStatus
  review_note: string
  provider_run_id: string
  created_at: string
}

export interface ProviderRun {
  id: string
  provider: string
  model: string
  mode: string
  input_hash: string
  parameters: Record<string, unknown>
  started_at: string
  finished_at: string | null
  latency_ms: number | null
  usage: Record<string, unknown>
  status: string
  error_class: string
  error_message: string
  validation_errors: string[]
  downgraded_from: string
  is_backup: boolean
}

export interface CandidateCoverage {
  claims?: number
  documents?: number
  pairs_considered?: number
  pairs_compared?: number
  pairs_dropped_by_cap?: number
  pairs_skipped?: number
  skipped_reasons_top?: Record<string, number>
  skipped_reasons_other_count?: number
  distinct_skip_reasons?: number
  unknown_scope_candidates_kept?: number
  // How many compared pairs were judged each relation, keyed by Relation. A compared
  // pair that ends up consistent, unrelated or insufficient evidence produced no
  // finding, and that outcome is counted and shown rather than left implicit.
  outcomes?: Record<string, number>
  // Comparisons that produced no usable judgement at all (unparseable or truncated
  // model output). This is not an abstention.
  comparisons_without_finding?: number
  // How many potential_conflict findings survived into the report.
  inconsistencies_reported?: number
  [key: string]: unknown
}

export interface Analysis {
  id: string
  idempotency_key: string
  document_ids: string[]
  status: AnalysisStatus
  provider: string
  model: string
  prompt_version: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  findings: Finding[]
  claim_count: number
  pair_count: number
  candidate_coverage: CandidateCoverage
  provider_runs: ProviderRun[]
  failures: string[]
  limitations: string[]
  extract_only: boolean
}

export interface UsageSummary {
  calls: number
  failed_calls: number
  backup_calls: number
  downgrades: string[]
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  models: string[]
  latency_ms_total: number
}

export interface AnalysisView {
  analysis: Analysis
  relation_counts: Record<string, number>
  usage: UsageSummary
  warning: string
}

export interface DocumentRecord {
  id: string
  name: string
  sha256: string
  mime: string
  size_bytes: number
  created_at: string
  extraction_version: string
  page_count: number
  extraction_status: ExtractionStatus
  extraction_notes: string[]
  stored_name: string
  passages: number
}

export interface DocumentListItem extends DocumentRecord {
  characters: number
}

export interface DocumentListResponse {
  documents: DocumentListItem[]
  max_documents: number
}

export interface DocumentDetailResponse {
  document: DocumentRecord
  canonical_text: string
  passages: Passage[]
}

export interface RejectedUpload {
  name: string
  reason: string
  message: string
}

export interface UploadResponse {
  saved: DocumentRecord[]
  rejected: RejectedUpload[]
}

export interface ProviderView {
  provider: string
  base_url: string
  model: string
  credential_env: string
  api_key: string
  configured: boolean
  timeout_seconds: number
  max_output_tokens: number
  max_retries: number
  enabled: boolean
}

export interface AppConfig {
  primary_provider: string
  default_model: string
  backup_provider: string
  backup_model: string
  backup_fallback_enabled: boolean
  optional_8b_enabled: boolean
  limits: {
    max_documents: number
    max_upload_bytes: number
    max_extracted_chars: number
    max_compare_pairs: number
  }
  providers: Record<string, ProviderView>
  provider_status: Record<string, unknown>
  warning: string
}

export interface HealthResponse {
  status: string
  primary: Record<string, unknown> & { reachable?: boolean; model?: string; error_message?: string }
  backup: {
    provider: string
    model: string
    enabled: boolean
    fallback_allowed: boolean
    credential: string
  }
  warning: string
}

export interface ReviewEvent {
  id: string
  finding_id: string
  status: ReviewStatus
  note: string
  reviewer: string
  created_at: string
}

export interface FindingResponse {
  finding: Finding
  review_history: ReviewEvent[]
  analysis_id?: string
}
