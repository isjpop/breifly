/** Response envelopes returned by the Flask API (see backend/app/utils/responses.py). */

export interface ApiSuccess<T> {
  data: T
  meta?: Record<string, unknown>
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
  }
}

export interface HealthStatus {
  status: 'ok' | 'degraded'
  database: 'ok' | 'unavailable'
  timestamp: string
}
