import { Navigate, Outlet } from "react-router-dom";
import { getStoredUser, getToken } from "../api/client";

export function RequireAuth() {
  if (!getToken()) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function RequireAdmin() {
  const user = getStoredUser();
  if (!getToken()) return <Navigate to="/login" replace />;
  if (user?.role !== "admin") return <Navigate to="/chat" replace />;
  return <Outlet />;
}
