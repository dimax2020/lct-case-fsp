export type DomainErrorCode =
  | 'VALIDATION'
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'INVALID_TRANSITION'
  | 'CONSENT_REQUIRED'
  | 'EXPIRED'
  | 'GONE'
  | 'RATE_LIMITED'
  | 'PAYLOAD_TOO_LARGE'
  | 'INTEGRITY'
  | 'UNAVAILABLE';

const HTTP_STATUS: Record<DomainErrorCode, number> = {
  VALIDATION: 400,
  UNAUTHENTICATED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  INVALID_TRANSITION: 409,
  CONSENT_REQUIRED: 409,
  EXPIRED: 410,
  GONE: 410,
  RATE_LIMITED: 429,
  PAYLOAD_TOO_LARGE: 413,
  INTEGRITY: 422,
  UNAVAILABLE: 503,
};

export class DomainError extends Error {
  readonly code: DomainErrorCode;
  readonly details?: Record<string, unknown>;

  constructor(code: DomainErrorCode, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'DomainError';
    this.code = code;
    this.details = details;
  }

  get httpStatus(): number {
    return HTTP_STATUS[this.code];
  }
}

export const isDomainError = (e: unknown): e is DomainError => e instanceof DomainError;

export const validation = (message: string, details?: Record<string, unknown>) =>
  new DomainError('VALIDATION', message, details);
export const forbidden = (message = 'forbidden') => new DomainError('FORBIDDEN', message);
export const notFound = (what: string) => new DomainError('NOT_FOUND', `${what} not found`);
export const conflict = (message: string, details?: Record<string, unknown>) =>
  new DomainError('CONFLICT', message, details);
export const integrity = (message: string, details?: Record<string, unknown>) =>
  new DomainError('INTEGRITY', message, details);
