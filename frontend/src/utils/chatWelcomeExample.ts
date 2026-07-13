/** 部门名称 → 欢迎页示例问题（支持全称或简称作为 key） */
export const DEPARTMENT_WELCOME_EXAMPLES: Record<string, string> = {
  研发部: "Python代码规范-换行",
  研发: "Python代码规范-换行",
  产品部: "信息技术应用创新产品",
  产品: "信息技术应用创新产品",
  人力行政部: "人事管理",
  人事: "人事管理",
};

const DEFAULT_EXAMPLE = "Python代码规范";

export function resolveWelcomeExample(departmentNames?: string[]): string {
  if (!departmentNames?.length) return DEFAULT_EXAMPLE;

  for (const dept of departmentNames) {
    if (DEPARTMENT_WELCOME_EXAMPLES[dept]) {
      return DEPARTMENT_WELCOME_EXAMPLES[dept];
    }
    for (const [key, example] of Object.entries(DEPARTMENT_WELCOME_EXAMPLES)) {
      if (dept.includes(key)) return example;
    }
  }

  return DEFAULT_EXAMPLE;
}

export function buildWelcomeHint(departmentNames?: string[]): string {
  const example = resolveWelcomeExample(departmentNames);
  return `开始对话吧，例如：${example}或今天北京的天气怎么样或搜索新闻等`;
}
