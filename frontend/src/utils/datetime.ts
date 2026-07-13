/** 将后端 UTC ISO 时间格式化为本地时间字符串 */
export function formatLocalDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
