/** 页脚备案与版权（备案号来自 VITE_ICP_BEIAN，年份取当年）。 */
export default function SiteBeianFooter({ light = false }: { light?: boolean }) {
  const beian = import.meta.env.VITE_ICP_BEIAN?.trim();
  if (!beian) return null;

  const year = new Date().getFullYear();
  const textClass = light ? "text-neutral-400" : "text-white/45";

  return (
    <footer
      className={`pointer-events-none relative z-10 mt-6 w-full px-4 pb-[max(0.5rem,env(safe-area-inset-bottom))] text-center text-xs leading-relaxed ${textClass}`}
    >
      <div className="flex flex-col items-center gap-0.5 sm:flex-row sm:justify-center sm:gap-2">
        <span>{beian}</span>
        <span>Copyright © {year}</span>
      </div>
    </footer>
  );
}
