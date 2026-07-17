import { useEffect, useState } from "react";

const MOBILE_QUERY = "(max-width: 768px)";

/** 是否为移动端视口（与 Tailwind md 断点对齐）。 */
export function useIsMobile(query = MOBILE_QUERY): boolean {
  const [mobile, setMobile] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMobile(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return mobile;
}
