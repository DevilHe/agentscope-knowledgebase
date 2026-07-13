import { CheckOutlined, CopyOutlined } from "@ant-design/icons";
import { Typography } from "antd";
import { useRef, type MouseEvent, type ReactNode } from "react";
import { parseCodeLanguage } from "../utils/codeLang";

const { Text } = Typography;

type CodeBlockProps = {
  className?: string;
  children: ReactNode;
};

function extractCodeText(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(extractCodeText).join("");
  if (node && typeof node === "object" && "props" in node) {
    const props = (node as { props?: { children?: ReactNode } }).props;
    return extractCodeText(props?.children ?? "");
  }
  return "";
}

export default function CodeBlock({ className, children }: CodeBlockProps) {
  const copyRef = useRef<HTMLElement>(null);
  const language = parseCodeLanguage(className);
  const code = extractCodeText(children).replace(/\n$/, "");

  const onCopyAreaClick = (e: MouseEvent<HTMLElement>) => {
    if ((e.target as HTMLElement).closest(".ant-typography-copy")) return;
    copyRef.current
      ?.querySelector<HTMLButtonElement>(".ant-typography-copy")
      ?.click();
  };

  return (
    <div className="code-block-shell">
      <div className="code-block-toolbar">
        <span className="code-block-lang">{language}</span>
        <Text
          ref={copyRef}
          className="code-block-copy-text"
          actions={{ placement: "start" }}
          onClick={onCopyAreaClick}
          copyable={{
            text: code,
            tooltips: false,
            icon: [<CopyOutlined key="copy" />, <CheckOutlined key="copied" />],
          }}
        >
          复制
        </Text>
      </div>
      <pre className="code-block-pre">
        <code className={className}>{children}</code>
      </pre>
    </div>
  );
}
