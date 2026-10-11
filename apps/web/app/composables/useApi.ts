import createClient from 'openapi-fetch'
import type { paths } from '~/api/schema'
import { useApiMocks } from '~/utils/read'

export function useApi() {
  const mocks = useApiMocks()
  const baseUrl = import.meta.client ? window.location.origin : ''
  return createClient<paths>({
    baseUrl,
    async fetch(request) {
      if (!mocks) return globalThis.fetch(request)
      const { mockFetch } = await import('~/api/mock/handle')
      return mockFetch(request)
    },
  })
}
