/** 页脚备案与版权（备案号来自 VITE_ICP_BEIAN，年份取当年）。 */
export default function SiteBeianFooter({ light = false }: { light?: boolean }) {
  const beian = import.meta.env.VITE_ICP_BEIAN?.trim();
  if (!beian) return null;

  const year = new Date().getFullYear();
  const textClass = light ? "text-neutral-400" : "text-white/45";

  return (
    <footer
      className={`absolute bottom-0 left-0 right-0 z-10 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 text-center text-xs ${textClass}`}
    >
      <span>{beian}</span>
      <span className="mx-1.5">Copyright © {year}</span>
    </footer>
  );
}
