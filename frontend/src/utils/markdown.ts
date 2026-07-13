/**
 * 将用作乘号的 * 转义，避免 remark 解析为斜体/粗体。
 * 例如 (1+9)*7 → (1+9)\*7
 */
export function escapeMathAsterisks(content: string): string {
  return content.replace(/([)\]}\d])\*(?=\d)/g, "$1\\*");
}

function countSingleAsterisks(text: string): number {
  let count = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] !== "*") continue;
    if (text[i - 1] === "*" || text[i + 1] === "*") continue;
    count++;
  }
  return count;
}

function countInlineBackticks(text: string): number {
  let count = 0;
  let inFence = false;
  let i = 0;
  while (i < text.length) {
    if (text.startsWith("```", i)) {
      inFence = !inFence;
      i += 3;
      continue;
    }
    if (!inFence && text[i] === "`") count++;
    i++;
  }
  return count;
}

/** 流式输出时补齐未闭合的 Markdown 标记，避免整段排版错乱 */
export function closeUnbalancedMarkdown(content: string): string {
  let text = content;

  const fenceCount = (text.match(/```/g) || []).length;
  if (fenceCount % 2 === 1) {
    text += "\n```";
  }

  const boldMarkers = text.split("**").length - 1;
  if (boldMarkers % 2 === 1) {
    text += "**";
  }

  if (countSingleAsterisks(text) % 2 === 1) {
    text += "*";
  }

  if (countInlineBackticks(text) % 2 === 1) {
    text += "`";
  }

  return text;
}

export function prepareMarkdownContent(content: string, streaming = false): string {
  const escaped = escapeMathAsterisks(content);
  return streaming ? closeUnbalancedMarkdown(escaped) : escaped;
}
