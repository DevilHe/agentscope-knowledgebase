import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Form, Input, Select, Typography, message } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { clearAuth, fetchCaptcha, fetchPublicDepartments, register, type CaptchaInfo } from "../api/client";
import type { DepartmentItem } from "../types";
import {
  AUTH_PASSWORD_POLICY,
  PASSWORD_PLACEHOLDER,
  USERNAME_PLACEHOLDER,
  isRegistrationEnabled,
  validatePassword,
  validateUsername,
} from "../utils/authPolicy";

const { Title } = Typography;

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [captcha, setCaptcha] = useState<CaptchaInfo | null>(null);
  const [departments, setDepartments] = useState<DepartmentItem[]>([]);
  const registrationEnabled = isRegistrationEnabled();

  const loadCaptcha = useCallback(async () => {
    const data = await fetchCaptcha();
    setCaptcha(data);
    form.setFieldValue("captcha_answer", "");
  }, [form]);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const [captchaData, deptData] = await Promise.all([fetchCaptcha(), fetchPublicDepartments()]);
        if (!active) return;
        setCaptcha(captchaData);
        setDepartments(deptData.items || []);
        form.setFieldValue("captcha_answer", "");
      } catch (err) {
        if (!active) return;
        setError((err as Error).message);
      }
    })();

    return () => {
      active = false;
    };
  }, [form]);

  if (!registrationEnabled) {
    return <Navigate to="/login" replace />;
  }

  const onFinish = async (values: {
    username: string;
    password: string;
    captcha_answer: string;
    department_id: string;
  }) => {
    if (!captcha) return;
    setLoading(true);
    setError("");
    try {
      await register(
        values.username,
        values.password,
        captcha.captcha_id,
        values.captcha_answer,
        values.department_id
      );
      clearAuth();
      message.success("注册成功，请登录");
      navigate("/login", { replace: true });
    } catch (err) {
      setError((err as Error).message || "注册失败");
      await loadCaptcha();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-100 px-4">
      <Card className="w-full max-w-sm shadow-sm" variant="borderless">
        <div className="mb-4 flex items-center justify-center gap-3">
          <img src="/avatar.png" alt="AI知识库助手" className="h-16 w-16 shrink-0 object-contain" />
          <Title level={2} className="!mb-0">
            注册账号
          </Title>
        </div>
        {error && <Alert type="error" message={error} showIcon className="!mb-4" />}
        <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            label="用户名"
            name="username"
            rules={[
              {
                validator: (_, value) => {
                  const msg = validateUsername(value || "");
                  return msg ? Promise.reject(new Error(msg)) : Promise.resolve();
                },
              },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder={USERNAME_PLACEHOLDER}
              autoComplete="username"
              size="large"
              maxLength={16}
            />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[
              {
                validator: (_, value) => {
                  const msg = validatePassword(value || "");
                  return msg ? Promise.reject(new Error(msg)) : Promise.resolve();
                },
              },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={PASSWORD_PLACEHOLDER}
              autoComplete="new-password"
              size="large"
              maxLength={AUTH_PASSWORD_POLICY.max_length}
            />
          </Form.Item>
          <Form.Item
            label="所属部门"
            name="department_id"
            rules={[{ required: true, message: "请选择部门" }]}
          >
            <Select
              size="large"
              placeholder="请选择部门"
              options={departments.map((d) => ({ value: d.id, label: d.name }))}
            />
          </Form.Item>
          <Form.Item label="验证码" required>
            <div className="flex items-center gap-2">
              <Form.Item
                name="captcha_answer"
                noStyle
                rules={[{ required: true, message: "请输入验证码" }]}
              >
                <Input placeholder="请输入验证码" size="large" className="flex-1" maxLength={4} />
              </Form.Item>
              <button
                type="button"
                className="h-11 shrink-0 cursor-pointer overflow-hidden rounded-lg border border-neutral-200 bg-white"
                onClick={() => loadCaptcha().catch((e) => setError((e as Error).message))}
                aria-label="刷新验证码"
              >
                {captcha?.image ? (
                  <img src={captcha.image} alt="验证码" className="block h-11 w-[120px]" />
                ) : (
                  <div className="flex h-11 w-[120px] items-center justify-center text-xs text-neutral-400">
                    加载中
                  </div>
                )}
              </button>
            </div>
          </Form.Item>
          <Form.Item className="!mb-0">
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              注册
            </Button>
          </Form.Item>
        </Form>
        <div className="mt-4 text-center">
          <Link to="/login">已有账号？去登录</Link>
        </div>
      </Card>
    </div>
  );
}
