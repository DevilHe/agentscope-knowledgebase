import {
  Button,
  Form,
  Input,
  Layout,
  Modal,
  Select,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import {
  createUser,
  fetchDepartments,
  fetchUsers,
  resetUserPassword,
  updateUser,
  type UserItem,
} from "../api/client";
import type { DepartmentItem } from "../types";
import {
  AUTH_PASSWORD_POLICY,
  PASSWORD_PLACEHOLDER,
  USERNAME_PLACEHOLDER,
  validatePassword,
  validateUsername,
} from "../utils/authPolicy";
import PageHeader from "../components/PageHeader";
import { formatLocalDateTime } from "../utils/datetime";

const { Content } = Layout;
const { Text } = Typography;

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [departments, setDepartments] = useState<DepartmentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [deptUser, setDeptUser] = useState<UserItem | null>(null);
  const [resetUser, setResetUser] = useState<UserItem | null>(null);
  const [createForm] = Form.useForm();
  const [deptForm] = Form.useForm();
  const [resetForm] = Form.useForm();

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchUsers();
      setUsers(data);
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDepartments()
      .then((data) => setDepartments(data.items || []))
      .catch(() => undefined);
    loadUsers();
  }, [loadUsers]);

  const onToggleActive = async (record: UserItem, checked: boolean) => {
    try {
      await updateUser(record.id, { is_active: checked });
      message.success(checked ? "已启用" : "已禁用");
      loadUsers();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const onCreate = async () => {
    const values = await createForm.validateFields();
    try {
      await createUser(values.username, values.password, values.role, values.department_ids || []);
      message.success("用户已创建");
      setCreateOpen(false);
      createForm.resetFields();
      loadUsers();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const onResetPassword = async () => {
    if (!resetUser) return;
    const values = await resetForm.validateFields();
    try {
      await resetUserPassword(resetUser.id, values.new_password);
      message.success("密码已重置");
      setResetUser(null);
      resetForm.resetFields();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const onSaveDepartments = async () => {
    if (!deptUser) return;
    const values = await deptForm.validateFields();
    try {
      await updateUser(deptUser.id, { department_ids: values.department_ids || [] });
      message.success("部门已更新");
      setDeptUser(null);
      deptForm.resetFields();
      loadUsers();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const columns: ColumnsType<UserItem> = [
    { title: "用户名", dataIndex: "username" },
    {
      title: "角色",
      dataIndex: "role",
      width: 100,
      render: (role: string) => (
        <Tag color={role === "admin" ? "blue" : "default"}>
          {role === "admin" ? "管理员" : "用户"}
        </Tag>
      ),
    },
    {
      title: "部门",
      dataIndex: "department_names",
      width: 180,
      render: (names: string[] | undefined, record) =>
        names && names.length > 0 ? names.join("、") : record.role === "admin" ? "全部" : "-",
    },
    {
      title: "状态",
      dataIndex: "is_active",
      width: 100,
      render: (active: boolean, record) => (
        <Switch checked={active} onChange={(checked) => onToggleActive(record, checked)} />
      ),
    },
    {
      title: "失败次数",
      dataIndex: "failed_login_attempts",
      width: 100,
      align: "center",
    },
    {
      title: "锁定至",
      dataIndex: "locked_until",
      width: 180,
      render: (v: string | null) => formatLocalDateTime(v),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 180,
      render: (v: string | null) => formatLocalDateTime(v),
    },
    {
      title: "操作",
      width: 180,
      render: (_, record) => (
        <div className="flex gap-1">
          <Button
            type="link"
            size="small"
            disabled={record.role === "admin"}
            onClick={() => {
              if (record.role === "admin") return;
              setDeptUser(record);
              deptForm.setFieldsValue({ department_ids: record.department_ids || [] });
            }}
          >
            分配部门
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setResetUser(record);
              resetForm.resetFields();
            }}
          >
            重置密码
          </Button>
        </div>
      ),
    },
  ];

  return (
    <Layout className="min-h-screen bg-neutral-50">
      <PageHeader title="用户管理" />

      <Content className="p-3 md:p-6">
        <div className="overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-neutral-200 px-3 py-3 md:px-4">
            <Text type="secondary"></Text>
            <Button type="primary" onClick={() => setCreateOpen(true)}>
              新建用户
            </Button>
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={users}
            scroll={{ x: 800 }}
            pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条` }}
          />
        </div>
      </Content>

      <Modal title="新建用户" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={onCreate}>
        <Form form={createForm} layout="vertical" className="mt-4" initialValues={{ role: "user" }}>
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
            <Input placeholder={USERNAME_PLACEHOLDER} maxLength={16} />
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
            <Input.Password placeholder={PASSWORD_PLACEHOLDER} maxLength={AUTH_PASSWORD_POLICY.max_length} />
          </Form.Item>
          <Form.Item label="角色" name="role" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "user", label: "用户" },
                { value: "admin", label: "管理员" },
              ]}
            />
          </Form.Item>
          <Form.Item label="所属部门" name="department_ids">
            <Select
              mode="multiple"
              allowClear
              placeholder="普通用户需分配部门以访问部门知识库"
              options={departments.map((d) => ({ value: d.id, label: d.name }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`分配部门：${deptUser?.username || ""}`}
        open={!!deptUser}
        onCancel={() => setDeptUser(null)}
        onOk={onSaveDepartments}
        okButtonProps={{ disabled: deptUser?.role === "admin" }}
      >
        <Form form={deptForm} layout="vertical" className="mt-4">
          <Form.Item label="所属部门" name="department_ids">
            <Select
              mode="multiple"
              allowClear
              disabled={deptUser?.role === "admin"}
              options={departments.map((d) => ({ value: d.id, label: d.name }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`重置密码：${resetUser?.username || ""}`}
        open={!!resetUser}
        onCancel={() => setResetUser(null)}
        onOk={onResetPassword}
      >
        <Form form={resetForm} layout="vertical" className="mt-4">
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
            <Input.Password placeholder={PASSWORD_PLACEHOLDER} maxLength={AUTH_PASSWORD_POLICY.max_length} />
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  );
}
