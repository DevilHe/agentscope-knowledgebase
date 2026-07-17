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
    <Header className="sticky top-0 z-20 flex !h-auto min-h-14 shrink-0 flex-wrap items-center justify-between gap-2 !bg-white !px-3 !py-2 !leading-none shadow-sm pt-[max(0.5rem,env(safe-area-inset-top))] md:!h-16 md:!px-6 md:!py-0">
      <div className="flex min-w-0 items-center gap-2 md:gap-3">
        {icon}
        <Title level={4} className="!mb-0 !text-base md:!text-xl">
          {title}
        </Title>
      </div>
      <div className="flex shrink-0 items-center gap-2 md:gap-4">
        <Button type="link" className="!px-1 md:!px-2" onClick={() => navigate(backTo)}>
          {backLabel}
        </Button>
        <UserAccount variant="header" menuPlacement="bottom" />
      </div>
    </Header>
  );
}
