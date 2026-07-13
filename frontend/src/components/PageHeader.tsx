import { Button, Layout, Typography } from "antd";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import UserAccount from "./UserAccount";

const { Header } = Layout;
const { Title } = Typography;

type PageHeaderProps = {
  title: string;
  icon?: ReactNode;
  backLabel?: string;
  backTo?: string;
};

export default function PageHeader({
  title,
  icon,
  backLabel = "返回聊天",
  backTo = "/chat",
}: PageHeaderProps) {
  const navigate = useNavigate();

  return (
    <Header className="sticky top-0 z-20 flex !h-16 shrink-0 items-center justify-between !bg-white !px-6 !leading-none shadow-sm">
      <div className="flex items-center gap-3">
        {icon}
        <Title level={4} className="!mb-0">
          {title}
        </Title>
      </div>
      <div className="flex items-center gap-4">
        <Button type="link" onClick={() => navigate(backTo)}>
          {backLabel}
        </Button>
        <UserAccount variant="header" menuPlacement="bottom" />
      </div>
    </Header>
  );
}
