import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import { Notice } from '../shared/Notice'
import type { Citation, DocumentDetailResponse, Finding } from '../types'

interface EvidenceViewProps {
  finding: Finding | null
}

const CONTEXT_CHARS = 320

/**
 * Highlight the cited span inside the document's canonical text.
 *
 * The slice comes from the canonical text at the stored offsets, exactly as the
 * backend derived the quote. Nothing here re-derives or re-words a citation.
 */
function HighlightedText({ detail, citation }: { detail: DocumentDetailResponse; citation: Citation }) {
  const text = detail.canonical_text
  const start = Math.max(0, citation.start_offset - CONTEXT_CHARS)
  const end = Math.min(text.length, citation.end_offset + CONTEXT_CHARS)
  const before = text.slice(start, citation.start_offset)
  const middle = text.slice(citation.start_offset, citation.end_offset)
  const after = text.slice(citation.end_offset, end)

  return (
    <pre className="source-text" tabIndex={0} aria-label={`Source text around page ${citation.page}`}>
      {start > 0 ? '…' : ''}
      {before}
      <mark className="highlight">{middle}</mark>
      {after}
      {end < text.length ? '…' : ''}
    </pre>
  )
}

export function EvidenceView({ finding }: EvidenceViewProps) {
  const [details, setDetails] = useState<Record<string, DocumentDetailResponse>>({})
  const [errors, setErrors] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  const documentIds = finding
    ? Array.from(new Set(finding.evidence.map((citation) => citation.document_id)))
    : []
  const documentKey = documentIds.join(',')

  useEffect(() => {
    let cancelled = false
    if (documentKey === '') {
      setDetails({})
      setErrors([])
      return
    }
    setLoading(true)
    Promise.all(
      documentKey.split(',').map(async (id) => {
        try {
          return { id, detail: await api.getDocument(id), error: null as string | null }
        } catch (caught) {
          const message =
            caught instanceof ApiError
              ? `document ${id}: ${caught.message}`
              : `document ${id}: request failed`
          return { id, detail: null, error: message }
        }
      }),
    ).then((results) => {
      if (cancelled) return
      const next: Record<string, DocumentDetailResponse> = {}
      const nextErrors: string[] = []
      for (const result of results) {
        if (result.detail) next[result.id] = result.detail
        if (result.error) nextErrors.push(result.error)
      }
      setDetails(next)
      setErrors(nextErrors)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [documentKey])

  if (!finding) {
    return (
      <section className="panel" aria-labelledby="evidence-heading">
        <h2 id="evidence-heading">4. Evidence</h2>
        <p className="muted">
          Select a finding to see the exact quoted spans it rests on, the page, and the character
          offsets in the extracted text.
        </p>
      </section>
    )
  }

  return (
    <section className="panel" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">4. Evidence for the selected finding</h2>

      <p className="muted">
        Quotes below are sliced from the canonical extracted text at the recorded offsets. A model
        may nominate a span, but it cannot author the quote text.
      </p>

      {loading ? <p className="muted">Loading document text…</p> : null}

      {errors.length > 0 ? (
        <Notice tone="error" title="Some source text could not be loaded">
          <ul className="notice-list">
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      {finding.evidence.length === 0 ? (
        <Notice tone="warning" title="No resolvable citation on this finding">
          <p>
            This judgement carries no span that resolved against the source text. Treat it as a
            prompt to look, not as evidence.
          </p>
        </Notice>
      ) : (
        <div className="evidence-grid">
          {finding.evidence.map((citation, index) => {
            const detail = details[citation.document_id]
            const name = detail?.document.name ?? citation.document_id
            return (
              <article className="evidence-card" key={`${citation.passage_id}-${citation.start_offset}`}>
                <h3>
                  Span {index + 1}: {name}
                </h3>
                <dl className="doc-meta">
                  <div>
                    <dt>Page</dt>
                    <dd>{citation.page}</dd>
                  </div>
                  <div>
                    <dt>Offsets</dt>
                    <dd>
                      <code>
                        [{citation.start_offset}, {citation.end_offset}]
                      </code>
                    </dd>
                  </div>
                  <div>
                    <dt>Passage</dt>
                    <dd>
                      <code>{citation.passage_id}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>Document</dt>
                    <dd>
                      <code>{citation.document_id}</code>
                    </dd>
                  </div>
                </dl>
                <blockquote className="quote">{citation.quote}</blockquote>
                {detail ? (
                  <>
                    <p className="muted small">In the surrounding extracted text:</p>
                    <HighlightedText detail={detail} citation={citation} />
                  </>
                ) : null}
              </article>
            )
          })}
        </div>
      )}

      {finding.limitations.length > 0 ? (
        <Notice tone="info" title="Limitations recorded for this finding">
          <ul className="notice-list">
            {finding.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </Notice>
      ) : null}
    </section>
  )
}
