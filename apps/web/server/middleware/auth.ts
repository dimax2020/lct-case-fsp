import { defineEventHandler, getCookie, getQuery, getRequestHeader, getRequestURL, proxyRequest, readBody, sendRedirect, setResponseHeader, setResponseStatus, type H3Event } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getUserSession, refreshUserSession } from 'nuxt-oidc-auth/runtime/server/utils/session.js'
import { afterRole, forbiddenHtml, rolePickerHtml, safeNext } from '../utils/auth-pages'
import { businessRole, readAccessToken, tokenSubject, type BusinessRole } from '../utils/access-token'
import { assignRealmRole } from '../utils/keycloak-admin'

const SESSION_COOKIE = 'nuxt-oidc-auth'

function isCabinet(pathname: string, role: 'candidate' | 'employer'): boolean {
  return pathname === `/${role}` || pathname.startsWith(`/${role}/`)
}

function allows(pathname: string, role: BusinessRole): boolean {
  if (role === 'admin') return true
  if (isCabinet(pathname, 'candidate')) return role === 'candidate'
  if (isCabinet(pathname, 'employer')) return role === 'employer'
  return true
}

function loginUrl(nextPath: string): string {
  return `/auth/keycloak/login?callbackRedirectUrl=${encodeURIComponent(nextPath)}`
}

function sameOrigin(event: H3Event): boolean {
  const origin = getRequestHeader(event, 'origin')
  if (!origin) return true
  try {
    return new URL(origin).host === getRequestURL(event).host
  } catch {
    return false
  }
}

export default defineEventHandler(async (event) => {
  const url = getRequestURL(event)
  const pathname = url.pathname
  const nextPath = `${pathname}${url.search}`

  if (pathname === '/api' || pathname.startsWith('/api/')) {
    if (pathname.startsWith('/api/_auth')) return
    const config = useRuntimeConfig()
    const targetBase = String(config.apiProxyTarget || 'http://api:8000').replace(/\/$/, '')
    const headers: Record<string, string> = {}
    if (getCookie(event, SESSION_COOKIE)) {
      try {
        await getUserSession(event)
      } catch {
        // The API answers 401 in the contract shape when the session cannot be refreshed.
      }
      const token = await readAccessToken(event)
      if (token) headers.authorization = `Bearer ${token}`
    }
    return proxyRequest(event, `${targetBase}${pathname}${url.search}`, { headers })
  }

  if (pathname === '/auth/role') {
    if (!getCookie(event, SESSION_COOKIE)) {
      return sendRedirect(event, loginUrl(`/auth/role${url.search}`), 302)
    }
    try {
      await getUserSession(event)
    } catch {
      return sendRedirect(event, loginUrl(`/auth/role${url.search}`), 302)
    }
    const token = await readAccessToken(event)
    const role = token ? businessRole(token) : null
    const queryNext = safeNext(getQuery(event).next)
    if (event.method === 'GET') {
      if (role === 'candidate' || role === 'employer') {
        return sendRedirect(event, afterRole(role, queryNext), 302)
      }
      if (role === 'admin') return sendRedirect(event, queryNext === '/' ? '/candidate/profile' : queryNext, 302)
      setResponseHeader(event, 'content-type', 'text/html; charset=utf-8')
      return rolePickerHtml(queryNext)
    }
    if (event.method !== 'POST') return
    if (!sameOrigin(event)) {
      setResponseStatus(event, 403)
      return 'Недостаточно прав'
    }
    const raw = await readBody(event)
    const body: Record<string, unknown> = typeof raw === 'string'
      ? Object.fromEntries(new URLSearchParams(raw))
      : raw && typeof raw === 'object'
        ? raw as Record<string, unknown>
        : {}
    const picked = body.role
    const postedNext = safeNext(body.next ?? queryNext)
    if (role === 'candidate' || role === 'employer') {
      return sendRedirect(event, afterRole(role, postedNext), 302)
    }
    if (picked !== 'candidate' && picked !== 'employer') {
      setResponseStatus(event, 400)
      setResponseHeader(event, 'content-type', 'text/html; charset=utf-8')
      return rolePickerHtml(postedNext)
    }
    const sub = token ? tokenSubject(token) : null
    if (!sub) return sendRedirect(event, loginUrl(postedNext), 302)
    await assignRealmRole(sub, picked)
    try {
      await refreshUserSession(event)
    } catch {
      return sendRedirect(event, loginUrl(afterRole(picked, postedNext)), 302)
    }
    const refreshed = await readAccessToken(event)
    if (!refreshed || businessRole(refreshed) !== picked) {
      return sendRedirect(event, loginUrl(afterRole(picked, postedNext)), 302)
    }
    return sendRedirect(event, afterRole(picked, postedNext), 302)
  }

  if (pathname.startsWith('/_nuxt') || pathname.startsWith('/__nuxt') || pathname.startsWith('/auth') || pathname.startsWith('/brand') || pathname.startsWith('/fonts') || pathname.includes('.')) {
    return
  }

  const cabinet = isCabinet(pathname, 'candidate') || isCabinet(pathname, 'employer')
  if (!cabinet && !getCookie(event, SESSION_COOKIE)) return

  if (!getCookie(event, SESSION_COOKIE)) {
    if (cabinet) return sendRedirect(event, loginUrl(nextPath), 302)
    return
  }

  try {
    await getUserSession(event)
  } catch {
    if (cabinet) return sendRedirect(event, loginUrl(nextPath), 302)
    return
  }

  const token = await readAccessToken(event)
  const role = token ? businessRole(token) : null
  if (!role) {
    return sendRedirect(event, `/auth/role?next=${encodeURIComponent(nextPath)}`, 302)
  }
  if (cabinet && !allows(pathname, role)) {
    setResponseStatus(event, 403)
    setResponseHeader(event, 'content-type', 'text/html; charset=utf-8')
    return forbiddenHtml()
  }
})
