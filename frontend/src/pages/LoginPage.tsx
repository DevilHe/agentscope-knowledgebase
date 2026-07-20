import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Button, Card, Form, Input, Typography, message } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchCaptcha, login, type CaptchaInfo } from "../api/client";
import AuthLegalNotice from "../components/AuthLegalNotice";
import ParticleWave from "../components/ParticleWave";
import SiteBeianFooter from "../components/SiteBeianFooter";
import { useIsMobile } from "../hooks/useIsMobile";
import { isRegistrationEnabled } from "../utils/authPolicy";

const { Title } = Typography;

export default function LoginPage() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [captcha, setCaptcha] = useState<CaptchaInfo | null>(null);
  const captchaRef = useRef<CaptchaInfo | null>(null);
  const registrationEnabled = isRegistrationEnabled();

  const loadCaptcha = useCallback(async () => {
    const data = await fetchCaptcha();
    captchaRef.current = data;
    setCaptcha(data);
    form.setFieldValue("captcha_answer", "");
  }, [form]);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const data = await fetchCaptcha();
        if (!active) return;
        captchaRef.current = data;
        setCaptcha(data);
        form.setFieldValue("captcha_answer", "");
      } catch (err) {
        if (!active) return;
        message.error((err as Error).message || "验证码加载失败");
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
    const current = captchaRef.current;
    if (!current) return;
    setLoading(true);
    try {
      await login(
        values.username,
        values.password,
        current.captcha_id,
        values.captcha_answer
      );
      navigate("/chat", { replace: true });
    } catch (err) {
      message.error((err as Error).message || "登录失败");
      // 校验失败后服务端已删除旧 id，必须清空再拉新码
      captchaRef.current = null;
      setCaptcha(null);
      form.setFieldValue("captcha_answer", "");
      await loadCaptcha().catch((e) => message.error((e as Error).message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className={`relative flex min-h-[100dvh] items-center justify-center overflow-hidden px-4 py-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))] ${
        isMobile ? "bg-neutral-50" : "bg-[#0b1220]"
      }`}
    >
      {!isMobile && <ParticleWave color={0x7dd3fc} amountX={50} amountY={50} />}
      <Card
        className={`relative z-10 w-full max-w-sm shadow-xl ${
          isMobile
            ? "border border-neutral-200 bg-white"
            : "border border-white/10 bg-white/95 backdrop-blur-sm"
        }`}
        variant="borderless"
      >
        <div className="mb-4 flex items-center justify-center gap-2 sm:gap-3">
          <img src="/avatar.png" alt="AI知识库助手" className="h-12 w-12 shrink-0 object-contain sm:h-16 sm:w-16" />
          <Title level={2} className="!mb-0 !text-xl sm:!text-2xl">
            AI知识库助手
          </Title>
        </div>
        <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            name="username"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input placeholder="请输入用户名" prefix={<UserOutlined />} autoComplete="username" size="large" />
          </Form.Item>
          <Form.Item
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
          <Form.Item>
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
                onClick={() =>
                  loadCaptcha().catch((e) => message.error((e as Error).message || "验证码刷新失败"))
                }
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
            <AuthLegalNotice />
          </Form.Item>
        </Form>
      </Card>
      <SiteBeianFooter light={isMobile} />
    </div>
  );
}
