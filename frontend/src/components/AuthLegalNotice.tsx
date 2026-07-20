import { Link } from "react-router-dom";

/** 登录 / 注册按钮上方的协议同意提示 */
export default function AuthLegalNotice() {
  return (
    <p className="mt-3 text-center text-xs leading-relaxed text-neutral-400">
      登录 / 注册即代表您同意
      <Link to="/legal" className="mx-0.5 text-blue-500 hover:text-blue-600" target="_blank" rel="noopener noreferrer">
        《用户协议》
      </Link>
      及
      <Link to="/legal" className="mx-0.5 text-blue-500 hover:text-blue-600" target="_blank" rel="noopener noreferrer">
        《隐私政策》
      </Link>
    </p>
  );
}
