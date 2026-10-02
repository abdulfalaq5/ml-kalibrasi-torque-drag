import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import type * as P from "plotly.js";

type Props = {
  data: P.Data[];
  layout: Partial<P.Layout>;
  config?: Partial<P.Config>;
  onHover?: (e: P.PlotHoverEvent) => void;
};

/** Pembungkus tipis Plotly: Plotly.react setiap data/layout berubah. */
export default function PlotlyChart({ data, layout, config, onHover }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const hoverRef = useRef(onHover);
  hoverRef.current = onHover;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    Plotly.react(el, data, layout, config);
  }, [data, layout, config]);

  useEffect(() => {
    const el = ref.current as (HTMLDivElement & { on?: (ev: string, cb: (e: unknown) => void) => void }) | null;
    if (!el) return;
    const ro = new ResizeObserver(() => Plotly.Plots.resize(el));
    ro.observe(el);
    // listener dipasang setelah plot pertama terbentuk
    const t = window.setTimeout(() => {
      el.on?.("plotly_hover", (e) => hoverRef.current?.(e as P.PlotHoverEvent));
    }, 0);
    return () => {
      window.clearTimeout(t);
      ro.disconnect();
      Plotly.purge(el);
    };
  }, []);

  return <div ref={ref} style={{ width: "100%" }} />;
}
