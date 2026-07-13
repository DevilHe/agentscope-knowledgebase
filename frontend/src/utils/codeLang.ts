const LANG_LABELS: Record<string, string> = {
  bash: "Bash",
  sh: "Bash",
  shell: "Bash",
  zsh: "Bash",
  python: "Python",
  py: "Python",
  javascript: "JavaScript",
  js: "JavaScript",
  typescript: "TypeScript",
  ts: "TypeScript",
  tsx: "TypeScript",
  jsx: "JavaScript",
  json: "JSON",
  sql: "SQL",
  java: "Java",
  go: "Go",
  golang: "Go",
  rust: "Rust",
  rs: "Rust",
  cpp: "C++",
  c: "C",
  csharp: "C#",
  cs: "C#",
  yaml: "YAML",
  yml: "YAML",
  markdown: "Markdown",
  md: "Markdown",
  html: "HTML",
  css: "CSS",
  dockerfile: "Dockerfile",
  docker: "Docker",
  plaintext: "Text",
  text: "Text",
};

export function parseCodeLanguage(className?: string): string {
  const match = /language-([\w+#-]+)/i.exec(className || "");
  if (!match) return "Text";
  const raw = match[1].toLowerCase();
  return LANG_LABELS[raw] || raw.charAt(0).toUpperCase() + raw.slice(1);
}
