import { useRef, useState } from 'react'
import { ApiError, api } from '../api'
import { ListNotice, Notice } from '../shared/Notice'
import type { RejectedUpload } from '../types'

interface UploadPanelProps {
  maxDocuments: number
  maxUploadBytes: number
  currentCount: number
  onUploaded: () => void
}

const EXTRACTION_LABEL: Record<string, string> = {
  ok: 'text layer extracted',
  truncated: 'text layer extracted, then truncated at the configured budget',
  ocr_not_implemented: 'no text layer — OCR is not implemented in this prototype',
  failed: 'extraction failed',
  unresolved: 'extraction unresolved',
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} kB`
  return `${bytes} B`
}

export function UploadPanel({
  maxDocuments,
  maxUploadBytes,
  currentCount,
  onUploaded,
}: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [rejected, setRejected] = useState<RejectedUpload[]>([])
  const [savedNames, setSavedNames] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [selection, setSelection] = useState<string[]>([])

  const remaining = Math.max(0, maxDocuments - currentCount)

  async function handleUpload() {
    const files = Array.from(inputRef.current?.files ?? [])
    if (files.length === 0) {
      setError('Choose at least one .pdf or .txt file to upload.')
      return
    }
    setBusy(true)
    setError(null)
    setRejected([])
    setSavedNames([])
    try {
      const result = await api.uploadDocuments(files)
      setRejected(result.rejected)
      setSavedNames(result.saved.map((document) => document.name))
      onUploaded()
      if (inputRef.current) inputRef.current.value = ''
    } catch (caught) {
      if (caught instanceof ApiError) setError(caught.message)
      else setError('The upload request failed before the server answered.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="upload-heading">
      <h2 id="upload-heading">1. Add documents to the corpus</h2>
      <p className="muted">
        Text-native PDF and UTF-8 TXT only. At most {maxDocuments} documents per project and{' '}
        {formatBytes(maxUploadBytes)} per file. Scanned PDFs are rejected as unreadable rather than
        silently producing empty evidence.
      </p>

      <div className="row">
        <label className="field">
          <span className="field-label">Documents</span>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.txt,application/pdf,text/plain"
            onChange={(event) =>
              setSelection(Array.from(event.target.files ?? []).map((file) => file.name))
            }
            disabled={busy || remaining === 0}
          />
        </label>
        <button type="button" onClick={handleUpload} disabled={busy || remaining === 0}>
          {busy ? 'Uploading…' : 'Upload'}
        </button>
      </div>

      {selection.length > 0 ? (
        <p className="muted">Selected: {selection.join(', ')}</p>
      ) : null}

      {remaining === 0 ? (
        <Notice tone="warning" title="Corpus is full">
          <p>
            This project already holds {maxDocuments} documents. Remove a document from the corpus
            before adding another.
          </p>
        </Notice>
      ) : null}

      {error ? (
        <Notice tone="error" title="Upload failed">
          <p>{error}</p>
        </Notice>
      ) : null}

      {savedNames.length > 0 ? (
        <Notice tone="success" title={`Stored ${savedNames.length} document(s)`}>
          <ul className="notice-list">
            {savedNames.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      {rejected.length > 0 ? (
        <>
          <Notice tone="warning" title={`Rejected ${rejected.length} file(s)`}>
            <p>
              Each entry below names the reason the file was not added. Nothing was partially
              imported.
            </p>
          </Notice>
          <table className="table">
            <caption className="sr-only">Rejected uploads</caption>
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Reason code</th>
                <th scope="col">Detail</th>
              </tr>
            </thead>
            <tbody>
              {rejected.map((entry) => (
                <tr key={`${entry.name}-${entry.reason}`}>
                  <td>{entry.name}</td>
                  <td>
                    <code>{entry.reason}</code>
                  </td>
                  <td>{entry.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      <ListNotice
        tone="info"
        title="Extraction status meanings"
        items={Object.values(EXTRACTION_LABEL)}
      />
    </section>
  )
}
