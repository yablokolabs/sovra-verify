import type { DocumentListItem } from '../types'

interface CorpusListProps {
  documents: DocumentListItem[]
  selectedIds: string[]
  inferenceReady: boolean
  inferenceReason: string
  busy: boolean
  warning: string
  onToggle: (id: string) => void
  onSelectAll: () => void
  onSelectNone: () => void
  onAnalyse: (extractOnly: boolean) => void
}

const STATUS_TEXT: Record<string, string> = {
  ok: 'text extracted',
  truncated: 'text truncated at budget',
  ocr_not_implemented: 'scanned — OCR not implemented',
  failed: 'extraction failed',
  unresolved: 'extraction unresolved',
}

export function CorpusList({
  documents,
  selectedIds,
  inferenceReady,
  inferenceReason,
  busy,
  warning,
  onToggle,
  onSelectAll,
  onSelectNone,
  onAnalyse,
}: CorpusListProps) {
  const selected = documents.filter((document) => selectedIds.includes(document.id))

  return (
    <section className="panel" aria-labelledby="corpus-heading">
      <h2 id="corpus-heading">2. Corpus and analysis controls</h2>

      <p className="warning-inline" role="note">
        {warning}
      </p>

      {documents.length === 0 ? (
        <p className="muted">
          No documents stored yet. Upload at least two documents that describe the same subject to
          make a comparison meaningful.
        </p>
      ) : (
        <>
          <div className="row">
            <button type="button" className="ghost" onClick={onSelectAll}>
              Select all
            </button>
            <button type="button" className="ghost" onClick={onSelectNone}>
              Clear selection
            </button>
            <span className="muted" aria-live="polite">
              {selected.length} of {documents.length} selected
            </span>
          </div>

          <ul className="document-list">
            {documents.map((document) => {
              const problems = document.extraction_notes
              const checked = selectedIds.includes(document.id)
              return (
                <li key={document.id} className="document-item">
                  <label className="document-select">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggle(document.id)}
                      aria-describedby={`doc-meta-${document.id}`}
                    />
                    <span className="document-name">{document.name}</span>
                  </label>
                  <dl className="doc-meta" id={`doc-meta-${document.id}`}>
                    <div>
                      <dt>Pages</dt>
                      <dd>{document.page_count}</dd>
                    </div>
                    <div>
                      <dt>Characters</dt>
                      <dd>{document.characters.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt>Passages</dt>
                      <dd>{document.passages}</dd>
                    </div>
                    <div>
                      <dt>SHA-256</dt>
                      <dd>
                        <code title={document.sha256}>{document.sha256.slice(0, 16)}…</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Extraction</dt>
                      <dd>
                        <span className={`status status-${document.extraction_status}`}>
                          {STATUS_TEXT[document.extraction_status] ?? document.extraction_status}
                        </span>
                      </dd>
                    </div>
                  </dl>
                  {problems.length > 0 ? (
                    <ul className="note-list">
                      {problems.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              )
            })}
          </ul>
        </>
      )}

      <div className="row actions">
        <button
          type="button"
          onClick={() => onAnalyse(false)}
          disabled={busy || selected.length < 2 || !inferenceReady}
          title={!inferenceReady ? inferenceReason : undefined}
        >
          {busy ? 'Running analysis…' : 'Analyse corpus with Apertus'}
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => onAnalyse(true)}
          disabled={busy || selected.length === 0}
        >
          Extract claims only (no Apertus reasoning)
        </button>
      </div>

      {selected.length === 1 ? (
        <p className="muted">
          Select at least two documents: a comparison needs claims from more than one source.
        </p>
      ) : null}

      {!inferenceReady ? (
        <p className="warning-inline" role="alert">
          {inferenceReason}
        </p>
      ) : null}
    </section>
  )
}
