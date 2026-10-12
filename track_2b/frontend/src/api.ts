import type {
  AnalysisView,
  AppConfig,
  Claim,
  DocumentDetailResponse,
  DocumentListResponse,
  FindingResponse,
  HealthResponse,
  ReviewEvent,
  ReviewStatus,
  UploadResponse,
} from './types'

/** The API is mounted at the server root; the UI build lives under /app. */
const API_ROOT = (import.meta.env.VITE_API_ROOT as string | undefined) ?? ''

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function describeDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((entry) => {
        if (entry && typeof entry === 'object' && 'message' in entry) {
          const item = entry as { name?: string; message?: string }
          return `${item.name ?? 'file'}: ${item.message ?? 'rejected'}`
        }
        return JSON.stringify(entry)
      })
      .join('; ')
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return 'request failed'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, init)
  if (!response.ok) {
    let detail: unknown = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (body && 'detail' in body) detail = body.detail
    } catch {
      /* a non-JSON error body is not fatal to reporting */
    }
    throw new ApiError(describeDetail(detail), response.status, detail)
  }
  return (await response.json()) as T
}

export const api = {
  getConfig: () => request<AppConfig>('/config'),

  getHealth: () => request<HealthResponse>('/health'),

  listDocuments: () => request<DocumentListResponse>('/documents'),

  getDocument: (id: string) =>
    request<DocumentDetailResponse>(`/documents/${encodeURIComponent(id)}`),

  async uploadDocuments(files: File[]): Promise<UploadResponse> {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request<UploadResponse>('/documents', { method: 'POST', body: form })
  },

  createAnalysis: (body: { document_ids: string[]; extract_only?: boolean; force?: boolean }) =>
    request<AnalysisView>('/analyses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  getAnalysis: (id: string) => request<AnalysisView>(`/analyses/${encodeURIComponent(id)}`),

  getClaims: (id: string) =>
    request<{ claims: Claim[] }>(`/analyses/${encodeURIComponent(id)}/claims`),

  getFinding: (id: string) => request<FindingResponse>(`/findings/${encodeURIComponent(id)}`),

  reviewFinding: (id: string, body: { status: ReviewStatus; note: string; reviewer: string }) =>
    request<{ finding: FindingResponse['finding']; review_history: ReviewEvent[] }>(
      `/findings/${encodeURIComponent(id)}/reviews`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    ),

  exportUrl: (id: string, format: 'json' | 'markdown' | 'zip') =>
    `${API_ROOT}/analyses/${encodeURIComponent(id)}/export?format=${format}`,
}
