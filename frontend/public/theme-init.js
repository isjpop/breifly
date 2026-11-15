// Apply the saved/system theme before first paint to avoid a light→dark flash.
// Loaded as a static file (not inline) so the Content Security Policy can forbid inline scripts.
;(function () {
  var theme = null
  try {
    theme = localStorage.getItem('briefly-theme')
  } catch {
    // Storage unavailable (private mode, blocked site data): fall back to the OS preference.
  }
  if (theme !== 'light' && theme !== 'dark') {
    theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  if (theme === 'dark') document.documentElement.classList.add('dark')
})()
