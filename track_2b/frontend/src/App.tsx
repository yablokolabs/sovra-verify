import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, api } from './api'
import { CorpusList } from './documents/CorpusList'
import { EvidenceView } from './evidence/EvidenceView'
import { FindingsPanel, REVIEW_LABEL, RELATION_LABEL } from './findings/FindingsPanel'
import { ReviewPanel } from './review/ReviewPanel'
import { Logo } from './shared/Logo'
import { ListNotice, Notice } from './shared/Notice'
import { UploadPanel } from './upload/UploadPanel'
import type {
  AnalysisView,
  AppConfig,
  DocumentListItem,
  HealthResponse,
  Relation,
  ReviewStatus,
} from './types'

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [documents, setDocuments] = useState<DocumentListItem[]>([])
  const [maxDocuments, setMaxDocuments] = useState(10)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [view, setView] = useState<AnalysisView | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [relationFilter, setRelationFilter] = useState<Relation | 'all'>('all')
  const [reviewFilter, setReviewFilter] = useState<ReviewStatus | 'all'>('all')
  const [activeFindingId, setActiveFindingId] = useState<string | null>(null)

  const refreshDocuments = useCallback(async () => {
    try {
      const response = await api.listDocuments()
      setDocuments(response.documents)
      setMaxDocuments(response.max_documents)
    } catch (caught) {
      setLoadError(caught instanceof ApiError ? caught.message : 'Could not load the corpus.')
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([api.getConfig(), api.getHealth(), api.listDocuments()]).then((results) => {
      if (cancelled) return
      const [configResult, healthResult, documentsResult] = results
      if (configResult.status === 'fulfilled') setConfig(configResult.value)
      if (healthResult.status === 'fulfilled') setHealth(healthResult.value)
      if (documentsResult.status === 'fulfilled') {
        setDocuments(documentsResult.value.documents)
        setMaxDocuments(documentsResult.value.max_documents)
      } else {
        setLoadError('The backend did not answer. Start the API and reload.')
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const warning =
    config?.warning ??
    'Prototype — potential inconsistencies only. Every result requires human review and is not a legal, factual or compliance determination.'

  const inferenceReady = health?.status === 'ok'
  const inferenceReason = inferenceReady
    ? ''
    : `Analysis is disabled because the primary provider is unreachable: ${
        (health?.primary?.error_message as string | undefined) ??
        'the health check reported a degraded state'
      }. Fix the provider credential or endpoint, then reload.`

  const filteredFindings = useMemo(() => {
    if (!view) return []
    return view.analysis.findings.filter((finding) => {
      if (relationFilter !== 'all' && finding.relation !== relationFilter) return false
      if (reviewFilter !== 'all' && finding.review_status !== reviewFilter) return false
      return true
    })
  }, [view, relationFilter, reviewFilter])

  const activeFinding = useMemo(() => {
    if (!view) return null
    const byId = view.analysis.findings.find((finding) => finding.id === activeFindingId)
    return byId ?? filteredFindings[0] ?? null
  }, [view, activeFindingId, filteredFindings])

  function toggleDocument(id: string) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    )
  }

  async function runAnalysis(extractOnly: boolean) {
    setBusy(true)
    setAnalysisError(null)
    try {
      const response = await api.createAnalysis({
        document_ids: selectedIds,
        extract_only: extractOnly,
      })
      setView(response)
      setActiveFindingId(response.analysis.findings[0]?.id ?? null)
    } catch (caught) {
      if (caught instanceof ApiError) {
        setAnalysisError(
          caught.status === 503
            ? `Inference was not available, so nothing was evaluated: ${caught.message}`
            : caught.message,
        )
      } else {
        setAnalysisError('The analysis request failed before the server answered.')
      }
    } finally {
      setBusy(false)
    }
  }

  async function refreshActiveAnalysis() {
    if (!view) return
    try {
      const response = await api.getAnalysis(view.analysis.id)
      setView(response)
    } catch {
      /* a failed refresh leaves the previously loaded view in place */
    }
    void refreshDocuments()
  }

  function step(delta: number) {
    if (filteredFindings.length === 0) return
    const currentIndex = activeFinding
      ? filteredFindings.findIndex((finding) => finding.id === activeFinding.id)
      : -1
    const nextIndex = (currentIndex + delta + filteredFindings.length) % filteredFindings.length
    setActiveFindingId(filteredFindings[nextIndex].id)
  }

  const usage = view?.usage
  const runs = view?.analysis.provider_runs ?? []

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <Logo />
          <div>
            <h1>Sovra Verify</h1>
            <p className="tagline">Don’t Just Answer. Prove It.</p>
          </div>
        </div>
        <p className="header-summary">
          Cross-document consistency auditing with Apertus. Every result is a potential
          inconsistency tied to the exact passage it came from.
        </p>
      </header>

      {loadError ? (
        <Notice tone="error" title="Backend not available">
          <p>{loadError}</p>
        </Notice>
      ) : null}

      <section className="panel" aria-labelledby="settings-heading">
        <h2 id="settings-heading">Application configuration and provider status</h2>
        {config ? (
          <dl className="status-grid">
            <div>
              <dt>Primary provider</dt>
              <dd>
                {config.primary_provider.toUpperCase()} · <code>{config.default_model}</code>
              </dd>
            </div>
            <div>
              <dt>Backup provider</dt>
              <dd>
                {config.backup_provider} · <code>{config.backup_model}</code>
              </dd>
            </div>
            <div>
              <dt>Automatic backup fallback</dt>
              <dd>
                {config.backup_fallback_enabled
                  ? 'enabled by the operator'
                  : 'off — a failed primary call fails visibly instead of switching providers'}
              </dd>
            </div>
            <div>
              <dt>Optional 8B models</dt>
              <dd>{config.optional_8b_enabled ? 'selectable' : 'disabled — no silent downgrade from 70B'}</dd>
            </div>
            <div>
              <dt>Provider reachability</dt>
              <dd>
                <span className={`status status-${health?.status === 'ok' ? 'complete' : 'failed'}`}>
                  {health?.status === 'ok'
                    ? 'primary provider reachable'
                    : 'primary provider not reachable'}
                </span>
              </dd>
            </div>
            <div>
              <dt>Corpus limit</dt>
              <dd>
                {config.limits.max_documents} documents · {Math.round(config.limits.max_upload_bytes / (1024 * 1024))} MB per file
              </dd>
            </div>
          </dl>
        ) : (
          <p className="muted">Loading configuration…</p>
        )}

        <p className="warning-inline" role="note">
          {warning}
        </p>
        <p className="muted small">
          Deployment mode: the application and its storage run locally; analysis calls leave the
          host to the configured provider endpoint. This is external-network inference, so do not
          describe it as air-gapped.
        </p>
      </section>

      <UploadPanel
        maxDocuments={maxDocuments}
        maxUploadBytes={config?.limits.max_upload_bytes ?? 10 * 1024 * 1024}
        currentCount={documents.length}
        onUploaded={() => void refreshDocuments()}
      />

      <CorpusList
        documents={documents}
        selectedIds={selectedIds}
        inferenceReady={inferenceReady}
        inferenceReason={inferenceReason}
        busy={busy}
        warning={warning}
        onToggle={toggleDocument}
        onSelectAll={() => setSelectedIds(documents.map((document) => document.id))}
        onSelectNone={() => setSelectedIds([])}
        onAnalyse={(extractOnly) => void runAnalysis(extractOnly)}
      />

      {analysisError ? (
        <Notice tone="error" title="Analysis did not run">
          <p>{analysisError}</p>
        </Notice>
      ) : null}

      {view ? (
        <>
          <FindingsPanel
            view={view}
            findings={filteredFindings}
            activeFindingId={activeFinding?.id ?? null}
            relationFilter={relationFilter}
            reviewFilter={reviewFilter}
            warning={warning}
            onRelationFilter={setRelationFilter}
            onReviewFilter={setReviewFilter}
            onSelect={setActiveFindingId}
            onStep={step}
          />

          <EvidenceView finding={activeFinding} />

          <ReviewPanel finding={activeFinding} onReviewed={() => void refreshActiveAnalysis()} />

          <section className="panel" aria-labelledby="export-heading">
            <h2 id="export-heading">6. Export</h2>
            <p className="muted">
              Exports carry the source hash, page, offsets, model and prompt version, and the
              current review status. Limitations and recorded failures are inside the report body.
            </p>
            <div className="row actions">
              <a className="button" href={api.exportUrl(view.analysis.id, 'json')} download>
                Download JSON
              </a>
              <a className="button secondary" href={api.exportUrl(view.analysis.id, 'markdown')} download>
                Download Markdown report
              </a>
              <a className="button secondary" href={api.exportUrl(view.analysis.id, 'zip')} download>
                Download ZIP bundle
              </a>
            </div>
            {activeFinding ? (
              <p className="muted small">
                Currently inspecting: {RELATION_LABEL[activeFinding.relation]} ·{' '}
                {REVIEW_LABEL[activeFinding.review_status]} · {activeFinding.id}
              </p>
            ) : null}
          </section>

          <section className="panel" aria-labelledby="usage-heading">
            <h2 id="usage-heading">7. Provider usage and run log</h2>
            {usage ? (
              <dl className="status-grid">
                <div>
                  <dt>Provider calls</dt>
                  <dd>{usage.calls}</dd>
                </div>
                <div>
                  <dt>Failed calls</dt>
                  <dd>{usage.failed_calls}</dd>
                </div>
                <div>
                  <dt>Backup calls</dt>
                  <dd>{usage.backup_calls}</dd>
                </div>
                <div>
                  <dt>Prompt tokens</dt>
                  <dd>{usage.prompt_tokens.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Completion tokens</dt>
                  <dd>{usage.completion_tokens.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Total tokens</dt>
                  <dd>{usage.total_tokens.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Accumulated latency</dt>
                  <dd>{(usage.latency_ms_total / 1000).toFixed(1)} s</dd>
                </div>
                <div>
                  <dt>Models used</dt>
                  <dd>{usage.models.join(', ') || '—'}</dd>
                </div>
              </dl>
            ) : null}

            <ListNotice
              tone="warning"
              title="Model changes recorded during this run"
              items={usage?.downgrades ?? []}
            />

            {runs.length === 0 ? (
              <p className="muted">No provider calls were recorded for this analysis.</p>
            ) : (
              <table className="table">
                <caption className="sr-only">Provider runs recorded for this analysis</caption>
                <thead>
                  <tr>
                    <th scope="col">Provider</th>
                    <th scope="col">Model</th>
                    <th scope="col">Mode</th>
                    <th scope="col">Status</th>
                    <th scope="col">Latency</th>
                    <th scope="col">Tokens</th>
                    <th scope="col">Failure</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => {
                    const promptTokens = Number(run.usage?.prompt_tokens ?? 0)
                    const completionTokens = Number(run.usage?.completion_tokens ?? 0)
                    return (
                      <tr key={run.id}>
                        <td>
                          {run.provider}
                          {run.is_backup ? ' (backup)' : ''}
                        </td>
                        <td>
                          <code>{run.model}</code>
                        </td>
                        <td>
                          <code>{run.mode}</code>
                        </td>
                        <td>
                          <span className={`status status-${run.status === 'ok' ? 'complete' : 'failed'}`}>
                            {run.status}
                          </span>
                        </td>
                        <td>{run.latency_ms === null ? '—' : `${(run.latency_ms / 1000).toFixed(2)} s`}</td>
                        <td>
                          {promptTokens} + {completionTokens}
                        </td>
                        <td>
                          {run.error_class ? (
                            <>
                              <code>{run.error_class}</code>
                              {run.error_message ? ` — ${run.error_message}` : ''}
                            </>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}

            <p className="muted small">
              Analysis id <code>{view.analysis.id}</code> · prompt version{' '}
              <code>{view.analysis.prompt_version}</code> · idempotency key{' '}
              <code>{view.analysis.idempotency_key.slice(0, 16)}…</code>
            </p>
          </section>
        </>
      ) : (
        <section className="panel" aria-labelledby="pending-heading">
          <h2 id="pending-heading">3. Findings</h2>
          <p className="muted">
            No analysis has run in this session. Upload at least two documents, select them, then
            run the analysis. Extracting claims only is available when you want parsing without
            Apertus reasoning.
          </p>
        </section>
      )}
    </div>
  )
}
