import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Form, Input, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchCaptcha, login, type CaptchaInfo } from "../api/client";
import { isRegistrationEnabled } from "../utils/authPolicy";

const { Title } = Typography;

export default function LoginPage() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [captcha, setCaptcha] = useState<CaptchaInfo | null>(null);
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
        const data = await fetchCaptcha();
        if (!active) return;
        setCaptcha(data);
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

  const onFinish = async (values: {
    username: string;
    password: string;
    captcha_answer: string;
  }) => {
    if (!captcha) return;
    setLoading(true);
    setError("");
    try {
      await login(values.username, values.password, captcha.captcha_id, values.captcha_answer);
      navigate("/chat", { replace: true });
    } catch (err) {
      setError((err as Error).message || "登录失败");
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
            AI知识库助手
          </Title>
        </div>
        {error && <Alert type="error" message={error} showIcon className="!mb-4" />}
        <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input placeholder="请输入用户名" prefix={<UserOutlined />} autoComplete="username" size="large" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password
              placeholder="请输入密码"
              prefix={<LockOutlined />}
              autoComplete="current-password"
              size="large"
              visibilityToggle={{ tabIndex: -1 }}
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
            {registrationEnabled && (
              <div className="mb-3 mt-1 flex justify-end">
                <Link to="/register" className="text-sm text-blue-500 hover:text-blue-600">
                  注册
                </Link>
              </div>
            )}
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
