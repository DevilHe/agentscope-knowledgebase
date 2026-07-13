const TERM_RE = /[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}/g;

export function extractHighlightTerms(query: string): string[] {
  const terms = new Set<string>();
  for (const match of query.matchAll(TERM_RE)) {
    terms.add(match[0].toLowerCase());
  }
  return [...terms].sort((a, b) => b.length - a.length);
}

export type HighlightPart = { text: string; highlight: boolean };

export function splitHighlightText(text: string, query: string): HighlightPart[] {
  const terms = extractHighlightTerms(query);
  if (!terms.length || !text) {
    return [{ text, highlight: false }];
  }

  const pattern = new RegExp(
    `(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi"
  );
  const parts: HighlightPart[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > last) {
      parts.push({ text: text.slice(last, index), highlight: false });
    }
    parts.push({ text: match[0], highlight: true });
    last = index + match[0].length;
  }
  if (last < text.length) {
    parts.push({ text: text.slice(last), highlight: false });
  }
  return parts.length ? parts : [{ text, highlight: false }];
}
