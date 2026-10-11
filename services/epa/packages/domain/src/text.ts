// eslint-disable-next-line no-control-regex
const CONTROL_EXCEPT_NEWLINE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;

export function stripControlChars(s: string): string {
  return s.replace(CONTROL_EXCEPT_NEWLINE, '');
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Renders a tiny, safe Markdown subset (inline code, bold, http(s) links, line breaks).
 * Everything is HTML-escaped first, so raw HTML in user input can never reach the DOM.
 */
export function renderSafeMarkdown(input: string): string {
  let html = escapeHtml(stripControlChars(input));
  html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)"'<>]+)\)/g, '<a href="$2" rel="noopener noreferrer nofollow" target="_blank">$1</a>');
  return html.replace(/\n/g, '<br>');
}
