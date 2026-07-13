import type { KnowledgeBaseItem } from "../types";

export const VISIBILITY_OPTIONS = [
  { value: "org", label: "全公司可见" },
  { value: "department", label: "本部门可见" },
  { value: "private", label: "仅管理员可见" },
] as const;

/** 全公司共享库（无 department_id）不可选「本部门可见」 */
export function isOrgWideKnowledgeBase(kb?: KnowledgeBaseItem | null) {
  return !kb?.department_id;
}

export function visibilityOptionsForKb(kb?: KnowledgeBaseItem | null) {
  const orgWide = isOrgWideKnowledgeBase(kb);
  return VISIBILITY_OPTIONS.map((o) => ({
    value: o.value,
    label: o.label,
    disabled: orgWide && o.value === "department",
  }));
}

export function defaultVisibilityForKb(kb?: KnowledgeBaseItem | null) {
  return isOrgWideKnowledgeBase(kb) ? "org" : "department";
}

export function normalizeVisibilityForKb(
  visibility: string | undefined,
  kb?: KnowledgeBaseItem | null
) {
  if (isOrgWideKnowledgeBase(kb) && visibility === "department") {
    return "org";
  }
  return visibility;
}

export function formatDocVisibility(
  visibility?: string,
  visibilityLabel?: string | null,
  departmentName?: string | null
) {
  if (visibility === "department" && departmentName) {
    return departmentName;
  }
  if (visibility === "private") return "仅管理员可见";
  return visibilityLabel || "-";
}
