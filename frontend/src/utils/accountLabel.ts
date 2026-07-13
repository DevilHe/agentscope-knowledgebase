export function formatAccountLabel(role: string, departmentNames?: string[]) {
  if (role === "admin") return "admin（管理员）";
  const dept = departmentNames?.length ? departmentNames.join("、") : "-";
  return `user（${dept}）`;
}
