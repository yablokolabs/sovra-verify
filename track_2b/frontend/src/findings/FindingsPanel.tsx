import { ListNotice } from '../shared/Notice'
import type { AnalysisView, Finding, Relation, ReviewStatus } from '../types'

export const RELATION_LABEL: Record<Relation, string> = {
  potential_conflict: 'Potential conflict',
  consistent: 'Consistent',
  insufficient_evidence: 'Insufficient evidence',
  unrelated: 'Unrelated',
}

export const REVIEW_LABEL: Record<ReviewStatus, string> = {
  pending: 'Pending review',
  confirmed_for_review: 'Confirmed for review',
  dismissed: 'Dismissed',
}

const RELATION_ORDER: Relation[] = [
  'potential_conflict',
  'insufficient_evidence',
  'consistent',
  'unrelated',
]

const REVIEW_ORDER: ReviewStatus[] = ['pending', 'confirmed_for_review', 'dismissed']

interface FindingsPanelProps {
  view: AnalysisView
  findings: Finding[]
  activeFindingId: string | null
  relationFilter: Relation | 'all'
  reviewFilter: ReviewStatus | 'all'
  warning: string
  onRelationFilter: (value: Relation | 'all') => void
  onReviewFilter: (value: ReviewStatus | 'all') => void
  onSelect: (id: string) => void
  onStep: (delta: number) => void
}

function formatCoverage(view: AnalysisView): string[] {
  const coverage = view.analysis.candidate_coverage ?? {}
  const lines: string[] = []
  if (coverage.claims !== undefined) lines.push(`${coverage.claims} validated claims in the corpus`)
  if (coverage.pairs_considered !== undefined) {
    lines.push(`${coverage.pairs_considered} candidate pairs passed the scoping filter`)
  }
  if (coverage.pairs_compared !== undefined) lines.push(`${coverage.pairs_compared} pairs sent to Apertus`)
  if (coverage.pairs_dropped_by_cap) {
    lines.push(`${coverage.pairs_dropped_by_cap} candidate pairs were not compared because of the cap`)
  }
  if (coverage.unknown_scope_candidates_kept) {
    lines.push(
      `${coverage.unknown_scope_candidates_kept} kept candidates had an unknown scope and were reviewed rather than dropped`,
    )
  }
  const skipped = coverage.skipped_reasons_top ?? {}
  for (const [reason, count] of Object.entries(skipped).slice(0, 4)) {
    lines.push(`${count} pairs skipped: ${reason}`)
  }
  return lines
}

export function FindingsPanel({
  view,
  findings,
  activeFindingId,
  relationFilter,
  reviewFilter,
  warning,
  onRelationFilter,
  onReviewFilter,
  onSelect,
  onStep,
}: FindingsPanelProps) {
  const analysis = view.analysis
  const status = analysis.status

  return (
    <section className="panel" aria-labelledby="findings-heading">
      <h2 id="findings-heading">3. Findings</h2>

      <p className="warning-inline" role="note">
        {warning}
      </p>

      <dl className="status-grid">
        <div>
          <dt>Run status</dt>
          <dd>
            <span className={`status status-${status}`}>{status}</span>
          </dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>{analysis.provider || '—'}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>
            <code>{analysis.model || '—'}</code>
          </dd>
        </div>
        <div>
          <dt>Prompt version</dt>
          <dd>
            <code>{analysis.prompt_version || '—'}</code>
          </dd>
        </div>
        <div>
          <dt>Validated claims</dt>
          <dd>{analysis.claim_count}</dd>
        </div>
        <div>
          <dt>Pairs compared</dt>
          <dd>{analysis.pair_count}</dd>
        </div>
        <div>
          <dt>Mode</dt>
          <dd>{analysis.extract_only ? 'extract only (no Apertus reasoning)' : 'Apertus comparison'}</dd>
        </div>
      </dl>

      {status === 'failed' || status === 'partial' ? (
        <div className="notice notice-error" role="alert">
          <p className="notice-title">
            This run is <strong>{status}</strong> — an empty finding list below means “not
            evaluated”, not “no inconsistencies”.
          </p>
          <div className="notice-body">
            <p>
              The result does not cover the whole corpus. Read the recorded failures and
              limitations before drawing any conclusion.
            </p>
          </div>
        </div>
      ) : null}

      <ListNotice
        tone="warning"
        title={`Recorded failures (${analysis.failures.length})`}
        items={analysis.failures}
      />
      <ListNotice
        tone="info"
        title={`Run limitations (${analysis.limitations.length})`}
        items={analysis.limitations}
      />
      <ListNotice tone="info" title="Candidate coverage" items={formatCoverage(view)} />

      <div className="row filters">
        <label className="field">
          <span className="field-label">Relation</span>
          <select
            value={relationFilter}
            onChange={(event) => onRelationFilter(event.target.value as Relation | 'all')}
          >
            <option value="all">All relations ({analysis.findings.length})</option>
            {RELATION_ORDER.map((relation) => (
              <option key={relation} value={relation}>
                {RELATION_LABEL[relation]} ({view.relation_counts?.[relation] ?? 0})
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Review status</span>
          <select
            value={reviewFilter}
            onChange={(event) => onReviewFilter(event.target.value as ReviewStatus | 'all')}
          >
            <option value="all">All review states</option>
            {REVIEW_ORDER.map((state) => (
              <option key={state} value={state}>
                {REVIEW_LABEL[state]}
              </option>
            ))}
          </select>
        </label>
        <div className="row stepper">
          <button type="button" className="ghost" onClick={() => onStep(-1)}>
            Previous finding
          </button>
          <button type="button" className="ghost" onClick={() => onStep(1)}>
            Next finding
          </button>
        </div>
      </div>

      <p className="muted" aria-live="polite">
        Showing {findings.length} of {analysis.findings.length} findings.
      </p>

      {analysis.findings.length === 0 ? (
        <p className="muted">
          No findings were recorded for this run. Check the status above: a failed or extract-only
          run produces an empty list without evaluating the corpus.
        </p>
      ) : findings.length === 0 ? (
        <p className="muted">No findings match the current filters.</p>
      ) : (
        <ul className="finding-list">
          {findings.map((finding) => (
            <li key={finding.id}>
              <button
                type="button"
                className={`finding-item${finding.id === activeFindingId ? ' is-active' : ''}`}
                aria-current={finding.id === activeFindingId}
                onClick={() => onSelect(finding.id)}
              >
                <span className="finding-head">
                  <span className={`relation relation-${finding.relation}`}>
                    {RELATION_LABEL[finding.relation]}
                  </span>
                  <span className="finding-review">{REVIEW_LABEL[finding.review_status]}</span>
                  <span className="muted small">
                    {finding.evidence.length} validated span(s)
                  </span>
                  {finding.evidence.length === 0 ? (
                    <span className="muted small">no resolvable citation</span>
                  ) : null}
                </span>
                <span className="finding-explanation">{finding.explanation}</span>
                <span className="finding-ids">
                  Claims: {finding.claim_ids.join(', ') || '—'} · Provider run:{' '}
                  {finding.provider_run_id || '—'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
