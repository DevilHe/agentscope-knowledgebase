import { AuditOutlined, BookOutlined, DownOutlined, KeyOutlined, LogoutOutlined, SettingOutlined, TeamOutlined, UserOutlined } from "@ant-design/icons";
import { Avatar, Dropdown } from "antd";
import type { MenuProps } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchMe, getStoredUser, logout, updateStoredUser } from "../api/client";
import { formatAccountLabel } from "../utils/accountLabel";
import ChangePasswordModal from "./ChangePasswordModal";

type UserAccountProps = {
  className?: string;
  menuPlacement?: "top" | "bottom";
  variant?: "sidebar" | "header";
};

export default function UserAccount({
  className = "",
  menuPlacement = "top",
  variant = "sidebar",
}: UserAccountProps) {
  const navigate = useNavigate();
  const user = getStoredUser();
  const [accountLabel, setAccountLabel] = useState(
    () => formatAccountLabel(user?.role || "user", user?.department_names)
  );
  const [pwdOpen, setPwdOpen] = useState(false);

  useEffect(() => {
    if (!user) return;
    setAccountLabel(formatAccountLabel(user.role, user.department_names));
    fetchMe()
      .then((me) => {
        const names = (me.departments || []).map((d: { name?: string }) => d.name).filter(Boolean) as string[];
        updateStoredUser({ department_names: names });
        setAccountLabel(formatAccountLabel(me.role, names));
      })
      .catch(() => undefined);
  }, [user?.role, user?.username]);

  if (!user) return null;

  const onLogout = async () => {
    await logout();
    window.location.href = "/login";
  };

  const items: MenuProps["items"] = [];

  items.push({
    key: "about",
    icon: <BookOutlined />,
    label: "说明文档",
    onClick: () => navigate("/about"),
  });

  items.push({
    key: "admin",
    icon: <SettingOutlined />,
    label: "文档管理",
    onClick: () => navigate("/admin"),
  });

  if (user.role === "admin") {
    items.push({
      key: "users",
      icon: <TeamOutlined />,
      label: "用户管理",
      onClick: () => navigate("/admin/users"),
    });
    items.push({
      key: "audit",
      icon: <AuditOutlined />,
      label: "审计日志",
      onClick: () => navigate("/admin/audit"),
    });
  }

  items.push({
    key: "password",
    icon: <KeyOutlined />,
    label: "修改密码",
    onClick: () => setPwdOpen(true),
  });

  items.push({
    key: "logout",
    icon: <LogoutOutlined />,
    label: "退出登录",
    onClick: onLogout,
  });

  const triggerClass =
    variant === "header"
      ? `inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-neutral-800 ${className}`
      : `flex w-full items-center justify-between rounded-lg bg-neutral-100 px-2 py-2 text-left text-xs font-medium text-neutral-800 ${className}`;

  return (
    <>
      <Dropdown
        menu={{ items }}
        trigger={["hover"]}
        placement={menuPlacement === "top" ? "topLeft" : "bottomRight"}
        mouseEnterDelay={0.15}
        mouseLeaveDelay={0.25}
      >
        <button type="button" className={triggerClass}>
          <span className="flex min-w-0 items-center gap-2">
            <Avatar size="small" icon={<UserOutlined />} />
            <span className="truncate">{accountLabel}</span>
          </span>
          <DownOutlined
            className={`shrink-0 text-[10px] text-neutral-400 ${menuPlacement === "top" ? "rotate-180" : ""}`}
          />
        </button>
      </Dropdown>
      <ChangePasswordModal open={pwdOpen} onClose={() => setPwdOpen(false)} />
    </>
  );
}
