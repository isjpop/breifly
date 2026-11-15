/**
 * Defence in depth: the API only returns absolute http(s) URLs, but links are re-checked
 * before rendering so a bad value can never become a javascript: or relative link.
 */
export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}
