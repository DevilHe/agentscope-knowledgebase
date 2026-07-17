import {
  Button,
  Input,
  Layout,
  Modal,
  Popconfirm,
  Select,
  Table,
  Tag,
  message,
} from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  deleteDocument,
  fetchDocuments,
  fetchKnowledgeBases,
  getStoredUser,
  updateDocument,
} from "../api/client";
import DocUpload from "../components/DocUpload";
import PageHeader from "../components/PageHeader";
import type { DocumentItem, KnowledgeBaseItem } from "../types";
import { formatLocalDateTime } from "../utils/datetime";
import { formatDocVisibility, normalizeVisibilityForKb, visibilityOptionsForKb } from "../utils/docVisibility";

const { Content } = Layout;

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  done: { color: "success", label: "已完成" },
  failed: { color: "error", label: "失败" },
  processing: { color: "processing", label: "处理中" },
};

export default function AdminPage() {
  const user = getStoredUser();
  const canManage = user?.role === "admin";
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [editDoc, setEditDoc] = useState<DocumentItem | null>(null);
  const [editKb, setEditKb] = useState<string | undefined>();
  const [editVisibility, setEditVisibility] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [pagination, setPagination] = useState<TablePaginationConfig>({
    current: 1,
    pageSize: 10,
    showSizeChanger: true,
    pageSizeOptions: ["10", "20", "50"],
    showTotal: (total) => `共 ${total} 条`,
  });

  const loadDocs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchDocuments();
      setDocs(data.items || []);
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKnowledgeBases()
      .then((data) => setKnowledgeBases(data.items || []))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  const kbNameMap = useMemo(
    () => Object.fromEntries(knowledgeBases.map((kb) => [kb.slug, kb.name])),
    [knowledgeBases]
  );

  const filteredDocs = useMemo(() => {
    const q = keyword.trim().toLowerCase();
    if (!q) return docs;
    return docs.filter((d) => d.filename.toLowerCase().includes(q));
  }, [docs, keyword]);

  useEffect(() => {
    setPagination((prev) => ({ ...prev, current: 1 }));
  }, [keyword]);

  const onDelete = async (id: string) => {
    try {
      await deleteDocument(id);
      message.success("已删除");
      loadDocs();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const editKbItem = useMemo(
    () => knowledgeBases.find((kb) => kb.slug === editKb),
    [knowledgeBases, editKb]
  );

  const editVisibilityOptions = useMemo(
    () => visibilityOptionsForKb(editKbItem),
    [editKbItem]
  );

  const openEdit = (record: DocumentItem) => {
    setEditDoc(record);
    setEditKb(record.knowledge_base);
    setEditVisibility(record.visibility || "department");
  };

  const onSaveEdit = async () => {
    if (!editDoc || !editKb || !editVisibility) return;
    setSaving(true);
    try {
      await updateDocument(editDoc.id, {
        knowledge_base: editKb,
        visibility: editVisibility,
      });
      message.success("文档已更新");
      setEditDoc(null);
      loadDocs();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<DocumentItem> = [
    {
      title: "文档名称",
      dataIndex: "filename",
      ellipsis: true,
    },
    {
      title: "版本",
      dataIndex: "version",
      width: 70,
      align: "center",
      render: (v: number | undefined) => (v ? `v${v}` : "v1"),
    },
    {
      title: "知识库",
      dataIndex: "knowledge_base",
      width: 140,
      render: (v: string) => kbNameMap[v] || v,
    },
    {
      title: "可见范围",
      dataIndex: "visibility_label",
      width: 140,
      render: (_v: string | null, record) =>
        formatDocVisibility(record.visibility, record.visibility_label, record.department_name),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 110,
      render: (status: string) => {
        const meta = STATUS_MAP[status] || { color: "default", label: status };
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: "分块数",
      dataIndex: "chunk_count",
      width: 90,
      align: "center",
    },
    {
      title: "上传时间",
      dataIndex: "created_at",
      width: 180,
      render: (v: string | null) => formatLocalDateTime(v),
    },
    {
      title: "操作",
      width: 130,
      align: "center",
      render: (_, record) => (
        <div className="flex justify-center gap-1">
          <Button
            type="link"
            size="small"
            disabled={!canManage}
            onClick={() => canManage && openEdit(record)}
          >
            编辑
          </Button>
          {canManage ? (
            <Popconfirm
              title="确认删除该文档及向量数据？"
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => onDelete(record.id)}
            >
              <Button type="link" danger size="small">
                删除
              </Button>
            </Popconfirm>
          ) : (
            <Button type="link" danger size="small" disabled>
              删除
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <Layout className="min-h-screen bg-neutral-50">
      <PageHeader title="文档管理" />

      <Content className="p-3 md:p-6">
        <div className="overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-sm">
          <div className="flex flex-col gap-3 border-b border-neutral-200 px-3 py-3 sm:flex-row sm:items-center sm:justify-between md:px-4">
            <Input.Search
              allowClear
              placeholder="搜索文档名称"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={setKeyword}
              className="w-full max-w-sm"
            />
            <DocUpload
              onUploaded={loadDocs}
              disabled={!canManage}
              knowledgeBases={knowledgeBases}
            />
          </div>

          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={filteredDocs}
            pagination={pagination}
            scroll={{ x: 900 }}
            onChange={(pager) => setPagination((prev) => ({ ...prev, ...pager }))}
            locale={{ emptyText: keyword ? "未找到匹配的文档" : "暂无文档" }}
          />
        </div>
      </Content>

      <Modal
        title={`编辑文档：${editDoc?.filename || ""}`}
        open={!!editDoc}
        onCancel={() => !saving && setEditDoc(null)}
        onOk={onSaveEdit}
        confirmLoading={saving}
        okButtonProps={{ disabled: !editKb || !editVisibility }}
      >
        <div className="mt-4 space-y-4">
          <div>
            <div className="mb-2 text-sm text-neutral-600">目标知识库</div>
            <Select
              className="w-full"
              value={editKb}
              options={knowledgeBases.map((kb) => ({
                value: kb.slug,
                label: kb.department_name ? `${kb.name}（${kb.department_name}）` : kb.name,
              }))}
              onChange={(slug) => {
                const kb = knowledgeBases.find((k) => k.slug === slug);
                setEditKb(slug);
                setEditVisibility((prev) => normalizeVisibilityForKb(prev, kb) || prev);
              }}
            />
          </div>
          <div>
            <div className="mb-2 text-sm text-neutral-600">可见范围</div>
            <Select
              className="w-full"
              value={editVisibility}
              options={editVisibilityOptions}
              onChange={setEditVisibility}
            />
          </div>
        </div>
      </Modal>
    </Layout>
  );
}
