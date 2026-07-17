import { Button, Input, Layout, Select, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { fetchAuditActions, fetchAuditLogs, type AuditLogItem } from "../api/client";
import PageHeader from "../components/PageHeader";
import { formatLocalDateTime } from "../utils/datetime";

const { Content } = Layout;

const STATUS_COLOR: Record<string, string> = {
  success: "success",
  blocked: "warning",
  failed: "error",
};

export default function AdminAuditPage() {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [action, setAction] = useState<string | undefined>();
  const [username, setUsername] = useState("");
  const [status, setStatus] = useState<string | undefined>();
  const [actions, setActions] = useState<{ value: string; label: string }[]>([]);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchAuditLogs({
        page,
        page_size: pageSize,
        action,
        username: username.trim() || undefined,
        status,
      });
      setLogs(data.items);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, action, username, status]);

  useEffect(() => {
    fetchAuditActions().then((data) => setActions(data.items)).catch(() => undefined);
  }, []);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const columns: ColumnsType<AuditLogItem> = [
    {
      title: "时间",
      dataIndex: "created_at",
      width: 180,
      render: (v: string | null) => formatLocalDateTime(v),
    },
    { title: "用户", dataIndex: "username", width: 120, render: (v) => v || "-" },
    {
      title: "操作类型",
      dataIndex: "action",
      width: 140,
      render: (v: string) => actions.find((a) => a.value === v)?.label || v,
    },
    { title: "IP", dataIndex: "ip_address", width: 130, render: (v) => v || "-" },
    { title: "操作系统", dataIndex: "os", width: 130, render: (v) => v || "-" },
    { title: "浏览器", dataIndex: "browser", width: 130, render: (v) => v || "-" },
    { title: "设备", dataIndex: "device", width: 130, render: (v) => v || "-" },
    { title: "资源", dataIndex: "resource_id", width: 220, ellipsis: true, render: (v) => v || "-" },
    {
      title: "详情",
      dataIndex: "detail",
      ellipsis: true,
      render: (detail: AuditLogItem["detail"]) =>
        detail ? JSON.stringify(detail) : "-",
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (v: string) => <Tag color={STATUS_COLOR[v] || "default"}>{v}</Tag>,
    },
  ];

  return (
    <Layout className="min-h-screen bg-neutral-50">
      <PageHeader title="审计日志" />

      <Content className="p-3 md:p-6">
        <div className="overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-sm">
          <div className="flex flex-col gap-3 border-b border-neutral-200 px-3 py-3 md:flex-row md:items-center md:justify-between md:px-4">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <Select
                allowClear
                placeholder="操作类型"
                style={{ width: 160 }}
                options={actions}
                value={action}
                onChange={(v) => {
                  setPage(1);
                  setAction(v);
                }}
              />
              <Select
                allowClear
                placeholder="状态"
                style={{ width: 112 }}
                options={[
                  { value: "success", label: "success" },
                  { value: "blocked", label: "blocked" },
                  { value: "failed", label: "failed" },
                ]}
                value={status}
                onChange={(v) => {
                  setPage(1);
                  setStatus(v);
                }}
              />
              <Input
                allowClear
                placeholder="用户名"
                style={{ width: 200 }}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onPressEnter={() => {
                  setPage(1);
                  loadLogs();
                }}
              />
            </div>
            <Button
              type="primary"
              onClick={() => {
                setPage(1);
                loadLogs();
              }}
            >
              查询
            </Button>
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={logs}
            scroll={{ x: 1000 }}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              pageSizeOptions: ["10", "20", "50"],
              showTotal: (n) => `共 ${n} 条`,
              onChange: (p, ps) => {
                setPage(p);
                setPageSize(ps);
              },
            }}
          />
        </div>
      </Content>
    </Layout>
  );
}
