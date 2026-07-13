import { ArrowUpOutlined, PauseOutlined } from "@ant-design/icons";
import { Button, Input } from "antd";

const { TextArea } = Input;

type ChatComposerProps = {
  value: string;
  loading: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
};

export default function ChatComposer({
  value,
  loading,
  onChange,
  onSend,
  onStop,
}: ChatComposerProps) {
  const canSend = value.trim().length > 0 && !loading;

  return (
    <div className="chat-composer">
      <TextArea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="给AI助手发送消息"
        variant="borderless"
        autoSize={{ minRows: 2, maxRows: 8 }}
        onPressEnter={(e) => {
          if (!e.shiftKey && canSend) {
            e.preventDefault();
            onSend();
          }
        }}
        className="!px-0 !py-0 !text-[15px] !leading-relaxed"
      />
      <div className="chat-composer-footer">
        {loading ? (
          <Button
            type="primary"
            shape="circle"
            danger
            icon={<PauseOutlined />}
            onClick={onStop}
            aria-label="停止生成"
          />
        ) : (
          <Button
            type="primary"
            shape="circle"
            icon={<ArrowUpOutlined />}
            disabled={!canSend}
            onClick={onSend}
            aria-label="发送"
            className={canSend ? "chat-send-active" : "chat-send-idle"}
          />
        )}
      </div>
    </div>
  );
}
