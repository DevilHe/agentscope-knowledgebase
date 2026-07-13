export type PasswordPolicy = {
  min_length: number;
  max_length: number;
  allowed_special: string;
};

export const AUTH_PASSWORD_POLICY: PasswordPolicy = {
  min_length: 8,
  max_length: 16,
  allowed_special: "!@#$%^&*",
};

export const USERNAME_PLACEHOLDER = "4-16位，大小写字母或数字";
export const PASSWORD_PLACEHOLDER = "8-16位，大小写字母、数字、特殊字符至少三种";

export function isRegistrationEnabled() {
  return import.meta.env.VITE_REGISTRATION_ENABLED === "true";
}

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function validateUsername(username: string): string | null {
  const name = username.trim();
  if (!name) return "请输入用户名";
  if (name.length < 4) return "用户名至少 4 位";
  if (name.length > 16) return "用户名不能超过 16 位";
  if (!/^[A-Za-z0-9]+$/.test(name)) return "用户名只能包含大小写字母或数字";
  return null;
}

export function validatePassword(
  password: string,
  policy: PasswordPolicy = AUTH_PASSWORD_POLICY
): string | null {
  const { min_length: min, max_length: max, allowed_special: special } = policy;

  if (!password) return "请输入密码";
  if (password.length < min) return `密码长度至少 ${min} 位`;
  if (password.length > max) return `密码长度不能超过 ${max} 位`;

  const allowed = new RegExp(`^[A-Za-z0-9${escapeRegex(special)}]+$`);
  if (!allowed.test(password)) return `密码只能包含字母、数字和特殊字符（${special}）`;

  let categories = 0;
  if (/[A-Z]/.test(password)) categories += 1;
  if (/[a-z]/.test(password)) categories += 1;
  if (/\d/.test(password)) categories += 1;
  if ([...password].some((ch) => special.includes(ch))) categories += 1;
  if (categories < 3) return "密码需包含大小写、数字、特殊字符中的至少三种";
  return null;
}

export function passwordHint() {
  return PASSWORD_PLACEHOLDER;
}
