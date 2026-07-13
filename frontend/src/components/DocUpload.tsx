import { InboxOutlined, UploadOutlined } from "@ant-design/icons";
import { Button, Modal, Progress, Select, Upload, message } from "antd";
import type { UploadProps } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { pollTask, uploadDocument } from "../api/client";
import type { KnowledgeBaseItem } from "../types";
import {
  defaultVisibilityForKb,
  normalizeVisibilityForKb,
  visibilityOptionsForKb,
} from "../utils/docVisibility";

const { Dragger } = Upload;

type DocUploadProps = {
  onUploaded: () => void;
  disabled?: boolean;
  knowledgeBases?: KnowledgeBaseItem[];
};

type FileUploadState = {
  key: string;
  filename: string;
  percent: number;
  status: "active" | "success" | "exception" | "unchanged";
  hint?: string;
};

function pickDefaultKb(knowledgeBases: KnowledgeBaseItem[]) {
  return knowledgeBases.find((k) => k.slug === "default")?.slug || knowledgeBases[0]?.slug;
}

export default function DocUpload({
  onUploaded,
  disabled = false,
  knowledgeBases = [],
}: DocUploadProps) {
  const [open, setOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [knowledgeBase, setKnowledgeBase] = useState<string | undefined>();
  const [visibility, setVisibility] = useState<string | undefined>();
  const [uploadItems, setUploadItems] = useState<FileUploadState[]>([]);
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const batchFilesRef = useRef<File[]>([]);
  const prevOpenRef = useRef(false);

  const selectedKb = useMemo(
    () => knowledgeBases.find((kb) => kb.slug === knowledgeBase),
    [knowledgeBases, knowledgeBase]
  );

  const visibilityOptions = useMemo(
    () => visibilityOptionsForKb(selectedKb),
    [selectedKb]
  );

  const patchUploadItem = (key: string, patch: Partial<FileUploadState>) => {
    setUploadItems((prev) =>
      prev.map((item) => (item.key === key ? { ...item, ...patch } : item))
    );
  };

  useEffect(() => {
    const justOpened = open && !prevOpenRef.current;
    prevOpenRef.current = open;
    if (!justOpened || knowledgeBases.length === 0) return;
    const slug = pickDefaultKb(knowledgeBases);
    const kb = knowledgeBases.find((k) => k.slug === slug);
    setKnowledgeBase(slug);
    setVisibility(defaultVisibilityForKb(kb));
    setUploadItems([]);
  }, [open, knowledgeBases]);

  useEffect(() => {
    return () => {
      if (batchTimerRef.current) clearTimeout(batchTimerRef.current);
    };
  }, []);

  const onKbChange = (slug: string) => {
    const kb = knowledgeBases.find((k) => k.slug === slug);
    setKnowledgeBase(slug);
    setVisibility((prev) => normalizeVisibilityForKb(prev, kb) || defaultVisibilityForKb(kb));
  };

  const canPickFile = Boolean(knowledgeBase && visibility);

  const handleFiles = async (files: File[]) => {
    const kbSlug = knowledgeBase;
    const vis = visibility;
    if (!kbSlug || !vis || disabled || !files.length) return;
    if (uploading) return;

    setUploading(true);
    let hasFailure = false;
    let ingestedCount = 0;
    try {
      for (const file of files) {
        const key = `${file.name}-${Date.now()}-${Math.random()}`;
        setUploadItems((prev) => [
          ...prev,
          { key, filename: file.name, percent: 5, status: "active", hint: "上传中..." },
        ]);

        try {
          patchUploadItem(key, { percent: 20, hint: "上传中..." });
          const res = await uploadDocument(file, {
            knowledge_base: kbSlug,
            visibility: vis,
          });

          if (res.status === "unchanged") {
            const unchangedMsg = res.message || "内容与当前版本相同，无需更新";
            patchUploadItem(key, {
              percent: 100,
              status: "unchanged",
              hint: unchangedMsg,
            });
            message.info(`「${file.name}」${unchangedMsg}`);
            continue;
          }

          if (!res.task_id) {
            ingestedCount += 1;
            patchUploadItem(key, { percent: 100, status: "success", hint: "已处理" });
            continue;
          }

          patchUploadItem(key, { percent: 40, hint: "解析入库中..." });
          let finished = false;
          for (let i = 0; i < 120; i++) {
            await new Promise((r) => setTimeout(r, 2000));
            const task = await pollTask(res.task_id);
            const percent = Math.min(95, 40 + Math.floor(((i + 1) * 55) / 120));
            patchUploadItem(key, { percent, hint: "解析入库中..." });

            if (task.status === "done" || task.status === "failed") {
              if (task.status === "done") {
                ingestedCount += 1;
                patchUploadItem(key, { percent: 100, status: "success", hint: "入库完成" });
              } else {
                hasFailure = true;
                patchUploadItem(key, {
                  percent: 100,
                  status: "exception",
                  hint: task.error || "入库失败",
                });
              }
              finished = true;
              break;
            }
          }

          if (!finished) {
            hasFailure = true;
            patchUploadItem(key, {
              percent: 100,
              status: "exception",
              hint: "处理超时，请稍后刷新列表查看",
            });
          }
        } catch (e) {
          hasFailure = true;
          patchUploadItem(key, {
            percent: 100,
            status: "exception",
            hint: (e as Error).message,
          });
        }
      }
      onUploaded();
      if (hasFailure) {
        message.error("部分文件上传失败，请查看下方提示");
      } else if (ingestedCount > 0) {
        message.success(
          ingestedCount === 1 ? "文档入库完成" : `${ingestedCount} 个文档入库完成`
        );
        setOpen(false);
      }
      // 全部为重复文件时不自动关弹窗，便于查看提示
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const queueFiles = (file: File) => {
    batchFilesRef.current.push(file);
    if (batchTimerRef.current) clearTimeout(batchTimerRef.current);
    batchTimerRef.current = setTimeout(() => {
      const batch = [...batchFilesRef.current];
      batchFilesRef.current = [];
      batchTimerRef.current = null;
      void handleFiles(batch);
    }, 0);
  };

  const uploadProps: UploadProps = {
    multiple: true,
    showUploadList: false,
    accept: ".pdf,.docx,.txt,.md,.markdown",
    disabled: disabled || !canPickFile || uploading,
    beforeUpload: (file) => {
      queueFiles(file);
      return false;
    },
  };

  return (
    <>
      <Button
        type="primary"
        icon={<UploadOutlined />}
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        上传文档
      </Button>

      <Modal
        title="上传文档"
        open={open}
        footer={null}
        onCancel={() => !uploading && setOpen(false)}
        destroyOnHidden
        width={520}
      >
        <div className="mt-4 space-y-4">
          <div>
            <div className="mb-2 text-sm text-neutral-600">目标知识库</div>
            <Select
              className="w-full"
              placeholder="请选择知识库"
              value={knowledgeBase}
              options={knowledgeBases.map((kb) => ({
                value: kb.slug,
                label: kb.department_name ? `${kb.name}（${kb.department_name}）` : kb.name,
              }))}
              onChange={onKbChange}
            />
          </div>
          <div>
            <div className="mb-2 text-sm text-neutral-600">可见范围</div>
            <Select
              className="w-full"
              placeholder="请选择可见范围"
              value={visibility}
              options={visibilityOptions}
              onChange={setVisibility}
            />
          </div>
          <Dragger {...uploadProps} className="w-full">
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">
              {canPickFile ? "点击或拖拽文件到此区域上传" : "请先选择知识库和可见范围"}
            </p>
            <p className="ant-upload-hint">支持 PDF / Word / TXT / Markdown</p>
          </Dragger>

          {uploadItems.length > 0 && (
            <div className="space-y-3">
              {uploadItems.map((item) => (
                <div key={item.key}>
                  <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                    <span className="truncate text-neutral-700">{item.filename}</span>
                    <span
                      className={
                        item.status === "exception"
                          ? "shrink-0 text-red-500"
                          : item.status === "unchanged"
                            ? "shrink-0 text-amber-600"
                          : item.status === "success"
                            ? "shrink-0 text-green-600"
                            : "shrink-0 text-neutral-500"
                      }
                    >
                      {item.hint}
                    </span>
                  </div>
                  <Progress
                    percent={item.percent}
                    status={
                      item.status === "unchanged"
                        ? "normal"
                        : item.status === "active"
                          ? "active"
                          : item.status
                    }
                    showInfo={false}
                    strokeColor={
                      item.status === "exception"
                        ? undefined
                        : item.status === "unchanged"
                          ? "#faad14"
                          : { from: "#1677ff", to: "#69b1ff" }
                    }
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
