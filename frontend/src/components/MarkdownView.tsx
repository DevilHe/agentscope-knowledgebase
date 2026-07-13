import type { Components } from "react-markdown";
import { isValidElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import CodeBlock from "./CodeBlock";
import { prepareMarkdownContent } from "../utils/markdown";

type MarkdownViewProps = {
  content: string;
  streaming?: boolean;
};

const markdownComponents: Components = {
  pre({ children }) {
    if (isValidElement(children)) {
      const props = children.props as { className?: string; children?: ReactNode };
      return <CodeBlock className={props.className}>{props.children}</CodeBlock>;
    }
    return <pre>{children}</pre>;
  },
  code({ className, children, ...props }) {
    if (className?.startsWith("language-")) {
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className="rag-inline-code" {...props}>
        {children}
      </code>
    );
  },
};

export default function MarkdownView({ content, streaming = false }: MarkdownViewProps) {
  return (
    <div className={`rag-markdown max-w-none${streaming ? " rag-markdown-streaming" : ""}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {prepareMarkdownContent(content, streaming)}
      </ReactMarkdown>
      {streaming && content.trim() && <span className="streaming-cursor" aria-hidden />}
    </div>
  );
}
