const API_BASE = '/api/v1'
const CSRF_KEY = 'pli_csrf'

export class ApiError extends Error {
  status: number
  errors?: Array<{ field: string; message: string }>

  constructor(status: number, message: string, errors?: Array<{ field: string; message: string }>) {
    super(message)
    this.status = status
    this.errors = errors
  }
}

export function setCsrf(token: string): void {
  sessionStorage.setItem(CSRF_KEY, token)
}

export function clearCsrf(): void {
  sessionStorage.removeItem(CSRF_KEY)
}

export function haveCsrf(): boolean {
  return Boolean(sessionStorage.getItem(CSRF_KEY))
}

interface Options {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
}

async function parseResponse<T>(response: Response): Promise<T> {
  let payload: unknown = null
  const text = await response.text()
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    const detail = payload as { detail?: string | unknown; errors?: Array<{ field: string; message: string }> } | null
    const message =
      typeof detail?.detail === 'string'
        ? detail.detail
        : response.status === 422
          ? 'Periksa kembali isian formulir.'
          : `Permintaan gagal (${response.status})`
    throw new ApiError(response.status, message, detail?.errors)
  }
  return payload as T
}

function writeHeaders(): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = sessionStorage.getItem(CSRF_KEY)
  if (token) headers['X-CSRF-Token'] = token
  return headers
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers = method !== 'GET' ? writeHeaders() : { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: 'same-origin',
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch {
    throw new ApiError(0, 'Tidak dapat terhubung ke server. Periksa koneksi atau jalankan backend.')
  }
  return parseResponse<T>(response)
}

/** Multipart upload. The browser sets the Content-Type boundary itself. */
export async function apiUpload<T>(
  path: string, file: File, field = 'file', fields: Record<string, string> = {},
): Promise<T> {
  const form = new FormData()
  form.append(field, file)
  for (const [key, value] of Object.entries(fields)) {
    if (value) form.append(key, value)
  }
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: writeHeaders(),
      credentials: 'same-origin',
      body: form,
    })
  } catch {
    throw new ApiError(0, 'Tidak dapat terhubung ke server. Periksa koneksi atau jalankan backend.')
  }
  return parseResponse<T>(response)
}

/** Authenticated file download. Errors are parsed as JSON before any blob is saved. */
export async function apiDownload(
  path: string,
  fallbackName: string,
  options: { method?: 'GET' | 'POST'; body?: unknown } = {},
): Promise<void> {
  const method = options.method ?? 'GET'
  const headers = writeHeaders()
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: 'same-origin',
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch {
    throw new ApiError(0, 'Tidak dapat terhubung ke server. Periksa koneksi atau jalankan backend.')
  }

  if (!response.ok) {
    await parseResponse<void>(response)
    return
  }

  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') ?? ''
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? fallbackName
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Terjadi kesalahan yang tidak diketahui'
}
