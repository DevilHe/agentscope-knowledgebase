import { Button, Layout } from "antd";
import { Link } from "react-router-dom";
import MarkdownView from "../components/MarkdownView";
import legalContent from "../content/legal.md?raw";

const { Content } = Layout;

export default function LegalPage() {
  return (
    <Layout className="min-h-[100dvh] bg-neutral-50">
      <header className="sticky top-0 z-10 border-b border-neutral-200 bg-white/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <img src="/avatar.png" alt="" className="h-8 w-8 shrink-0 object-contain" />
            <span className="truncate text-sm font-semibold text-neutral-800">用户协议及隐私政策</span>
          </div>
          <Link to="/login">
            <Button type="link" className="!px-0">
              返回登录
            </Button>
          </Link>
        </div>
      </header>
      <Content className="p-3 pb-6 md:p-6">
        <div className="mx-auto max-w-4xl overflow-hidden rounded-xl border border-neutral-200 bg-white px-4 py-4 shadow-sm md:px-8 md:py-6">
          <MarkdownView content={legalContent} />
        </div>
      </Content>
    </Layout>
  );
}
