import { Form, Input, Modal, message } from "antd";
import { useEffect, useState } from "react";
import { changePassword } from "../api/client";
import {
  AUTH_PASSWORD_POLICY,
  PASSWORD_PLACEHOLDER,
  validatePassword,
} from "../utils/authPolicy";

type ChangePasswordModalProps = {
  open: boolean;
  onClose: () => void;
};

export default function ChangePasswordModal({ open, onClose }: ChangePasswordModalProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    form.resetFields();
  }, [open, form]);

  const onSubmit = async () => {
    const values = await form.validateFields();
    setLoading(true);
    try {
      await changePassword(values.old_password, values.new_password);
      message.success("密码已修改，请重新登录");
      onClose();
      const { logout } = await import("../api/client");
      await logout();
      window.location.href = "/login";
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title="修改密码"
      open={open}
      onCancel={onClose}
      onOk={onSubmit}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" className="mt-4">
        <Form.Item
          label="原密码"
          name="old_password"
          rules={[{ required: true, message: "请输入原密码" }]}
        >
          <Input.Password />
        </Form.Item>
        <Form.Item
          label="新密码"
          name="new_password"
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
            placeholder={PASSWORD_PLACEHOLDER}
            maxLength={AUTH_PASSWORD_POLICY.max_length}
          />
        </Form.Item>
        <Form.Item
          label="确认新密码"
          name="confirm_password"
          dependencies={["new_password"]}
          rules={[
            { required: true, message: "请确认新密码" },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue("new_password") === value) return Promise.resolve();
                return Promise.reject(new Error("两次输入的密码不一致"));
              },
            }),
          ]}
        >
          <Input.Password />
        </Form.Item>
      </Form>
    </Modal>
  );
}
