import { useEffect, useRef, useState } from "react";

/**
 * Minimal fixed-row virtualizer. Renders only the rows in (and near) the
 * viewport so the table can show thousands of listings without react-window.
 * Returns a scroll-container ref plus the visible [start, end) row range.
 */
export function useVirtualList({ count, rowHeight, overscan = 10 }) {
  const ref = useRef(null);
  const [range, setRange] = useState({ start: 0, end: Math.min(count, 30) });

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;

    const recompute = () => {
      const scrollTop = el.scrollTop;
      const viewport = el.clientHeight;
      const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
      const end = Math.min(count, Math.ceil((scrollTop + viewport) / rowHeight) + overscan);
      setRange((current) =>
        current.start === start && current.end === end ? current : { start, end },
      );
    };

    recompute();
    el.addEventListener("scroll", recompute, { passive: true });
    const observer = new ResizeObserver(recompute);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", recompute);
      observer.disconnect();
    };
  }, [count, rowHeight, overscan]);

  return { ref, range, totalHeight: count * rowHeight };
}
