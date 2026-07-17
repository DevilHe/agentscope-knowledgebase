import { ArrowUpOutlined, PauseOutlined } from "@ant-design/icons";
import { Button, Input } from "antd";

const { TextArea } = Input;

type ChatComposerProps = {
  value: string;
  loading: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  /** 移动端更紧凑的行数 */
  compact?: boolean;
};

export default function ChatComposer({
  value,
  loading,
  onChange,
  onSend,
  onStop,
  compact = false,
}: ChatComposerProps) {
  const canSend = value.trim().length > 0 && !loading;

  return (
    <div className="chat-composer">
      <TextArea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="给AI助手发送消息"
        variant="borderless"
        autoSize={{ minRows: compact ? 1 : 2, maxRows: compact ? 5 : 8 }}
        onPressEnter={(e) => {
          // 移动端 Enter 常用于换行；桌面 Enter 发送、Shift+Enter 换行
          if (compact) return;
          if (!e.shiftKey && canSend) {
            e.preventDefault();
            onSend();
          }
        }}
        className="!px-0 !py-0 !text-[16px] !leading-relaxed md:!text-[15px]"
      />
      <div className="chat-composer-footer">
        {loading ? (
          <Button
            type="primary"
            shape="circle"
            danger
            size="large"
            icon={<PauseOutlined />}
            onClick={onStop}
            aria-label="停止生成"
            className="!h-11 !w-11"
          />
        ) : (
          <Button
            type="primary"
            shape="circle"
            size="large"
            icon={<ArrowUpOutlined />}
            disabled={!canSend}
            onClick={onSend}
            aria-label="发送"
            className={`!h-11 !w-11 ${canSend ? "chat-send-active" : "chat-send-idle"}`}
          />
        )}
      </div>
    </div>
  );
}
