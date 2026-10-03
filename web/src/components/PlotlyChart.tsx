import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import type * as P from "plotly.js";

type PlotEl = HTMLDivElement & {
  on?: (ev: string, cb: (e: unknown) => void) => void;
  _fullLayout?: { _size: { l: number; t: number; w: number; h: number }; yaxis: { l2p: (v: number) => number } };
};

type Props = {
  data: P.Data[];
  layout: Partial<P.Layout>;
  config?: Partial<P.Config>;
  onHover?: (e: P.PlotHoverEvent) => void;
  onRelayout?: (e: P.PlotRelayoutEvent) => void;
  /** Garis penuntun horizontal di nilai Y ini (overlay HTML, tanpa menggambar ulang plot). */
  guideY?: number | null;
};

/** Pembungkus tipis Plotly: Plotly.react setiap data/layout berubah. */
export default function PlotlyChart({ data, layout, config, onHover, onRelayout, guideY }: Props) {
  const ref = useRef<PlotEl>(null);
  const guideRef = useRef<HTMLDivElement>(null);
  const hoverRef = useRef(onHover);
  const relayoutRef = useRef(onRelayout);
  const guideYRef = useRef(guideY);
  hoverRef.current = onHover;
  relayoutRef.current = onRelayout;
  guideYRef.current = guideY;

  const placeGuide = () => {
    const el = ref.current;
    const g = guideRef.current;
    const fl = el?._fullLayout;
    const y = guideYRef.current;
    if (!g) return;
    if (!fl || y === null || y === undefined) {
      g.style.display = "none";
      return;
    }
    const px = fl.yaxis.l2p(y);
    if (!(px >= 0 && px <= fl._size.h)) {
      g.style.display = "none";
      return;
    }
    g.style.display = "block";
    g.style.top = `${fl._size.t + px}px`;
    g.style.left = `${fl._size.l}px`;
    g.style.width = `${fl._size.w}px`;
  };

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    Plotly.react(el, data, layout, config).then(placeGuide);
  }, [data, layout, config]);

  useEffect(placeGuide, [guideY]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => Plotly.Plots.resize(el));
    ro.observe(el);
    // listener dipasang setelah plot pertama terbentuk
    const t = window.setTimeout(() => {
      el.on?.("plotly_hover", (e) => hoverRef.current?.(e as P.PlotHoverEvent));
      el.on?.("plotly_relayout", (e) => relayoutRef.current?.(e as P.PlotRelayoutEvent));
      el.on?.("plotly_afterplot", placeGuide);
    }, 0);
    return () => {
      window.clearTimeout(t);
      ro.disconnect();
      Plotly.purge(el);
    };
  }, []);

  return (
    <div className="plot-host">
      <div ref={ref} style={{ width: "100%" }} />
      <div ref={guideRef} className="plot-guide" aria-hidden="true" />
    </div>
  );
}
