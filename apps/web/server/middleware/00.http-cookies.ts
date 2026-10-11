import { getRequestProtocol } from 'h3'

function stripSecureFlag(value: string | number | readonly string[]): string | number | readonly string[] {
  if (typeof value === 'number') return value
  if (typeof value === 'string') return value.replace(/;\s*Secure/gi, '')
  return value.map((item) => item.replace(/;\s*Secure/gi, ''))
}

export default defineEventHandler((event) => {
  if (getRequestProtocol(event, { xForwardedProto: true }) === 'https') return
  const response = event.node.res
  const setHeader = response.setHeader.bind(response)
  const appendHeader = response.appendHeader.bind(response)
  response.setHeader = ((name: string, value: string | number | readonly string[]) => {
    if (name.toLowerCase() === 'set-cookie') return setHeader(name, stripSecureFlag(value))
    return setHeader(name, value)
  }) as typeof response.setHeader
  response.appendHeader = ((name: string, value: string | number | readonly string[]) => {
    if (name.toLowerCase() === 'set-cookie') return appendHeader(name, stripSecureFlag(value))
    return appendHeader(name, value)
  }) as typeof response.appendHeader
})
