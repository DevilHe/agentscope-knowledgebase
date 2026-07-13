import { BookOutlined } from "@ant-design/icons";
import { Layout } from "antd";
import MarkdownView from "../components/MarkdownView";
import PageHeader from "../components/PageHeader";
import projectOverview from "../content/project-overview.md?raw";

const { Content } = Layout;

export default function AboutPage() {
  return (
    <Layout className="min-h-screen bg-neutral-50">
      <PageHeader title="说明文档" />
      <Content className="p-6">
        <div className="mx-auto max-w-4xl overflow-hidden rounded-xl border border-neutral-200 bg-white px-8 py-6 shadow-sm">
          <MarkdownView content={projectOverview} />
        </div>
      </Content>
    </Layout>
  );
}
