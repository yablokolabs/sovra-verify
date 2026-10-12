import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import { REVIEW_LABEL } from '../findings/FindingsPanel'
import { Notice } from '../shared/Notice'
import type { Finding, ReviewEvent, ReviewStatus } from '../types'

interface ReviewPanelProps {
  finding: Finding | null
  onReviewed: () => void
}

const REVIEWER = 'local reviewer'

export function ReviewPanel({ finding, onReviewed }: ReviewPanelProps) {
  const [note, setNote] = useState('')
  const [history, setHistory] = useState<ReviewEvent[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (!finding) {
      setHistory([])
      setNote('')
      return
    }
    setNote(finding.review_note ?? '')
    api
      .getFinding(finding.id)
      .then((response) => {
        if (!cancelled) setHistory(response.review_history)
      })
      .catch(() => {
        if (!cancelled) setHistory([])
      })
    return () => {
      cancelled = true
    }
  }, [finding?.id])

  if (!finding) {
    return (
      <section className="panel" aria-labelledby="review-heading">
        <h2 id="review-heading">5. Human review</h2>
        <p className="muted">
          Select a finding to record a review decision. Review decisions are held with the analysis
          and appear in the exported report.
        </p>
      </section>
    )
  }

  async function submit(status: ReviewStatus) {
    if (!finding) return
    setBusy(true)
    setError(null)
    try {
      const response = await api.reviewFinding(finding.id, { status, note, reviewer: REVIEWER })
      setHistory(response.review_history)
      onReviewed()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'The review request failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="review-heading">
      <h2 id="review-heading">5. Human review</h2>

      <p className="muted">
        A review decision records that a person looked at this finding. It is not a legal
        resolution, and the tool does not decide which document prevails.
      </p>

      <p>
        Current decision:{' '}
        <strong>{REVIEW_LABEL[finding.review_status]}</strong>
      </p>

      <label className="field field-wide">
        <span className="field-label">Reviewer note</span>
        <textarea
          rows={3}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="What was checked, and what remains uncertain?"
        />
      </label>

      <div className="row actions">
        <button type="button" onClick={() => submit('confirmed_for_review')} disabled={busy}>
          Confirm for review
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => submit('dismissed')}
          disabled={busy}
        >
          Dismiss
        </button>
        <button type="button" className="ghost" onClick={() => submit('pending')} disabled={busy}>
          Reset to pending
        </button>
      </div>

      {error ? (
        <Notice tone="error" title="Review not saved">
          <p>{error}</p>
        </Notice>
      ) : null}

      <h3>Review history</h3>
      {history.length === 0 ? (
        <p className="muted">No review decisions recorded for this finding yet.</p>
      ) : (
        <table className="table">
          <caption className="sr-only">Review history for the selected finding</caption>
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Decision</th>
              <th scope="col">Reviewer</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {history.map((event) => (
              <tr key={event.id}>
                <td>{new Date(event.created_at).toLocaleString()}</td>
                <td>{REVIEW_LABEL[event.status]}</td>
                <td>{event.reviewer}</td>
                <td>{event.note || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
