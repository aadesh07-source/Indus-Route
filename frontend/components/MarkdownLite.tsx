// @ts-nocheck
"use client";
import React from "react";

/** Inline markdown: **bold**, *italic*, and `code`. */
function inline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`)/g;
  let last = 0, m, k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const t = m[0];
    k += 1;
    if (t.startsWith("**")) {
      nodes.push(<strong key={k} style={{ fontWeight: 700 }}>{t.slice(2, -2)}</strong>);
    } else if (t.startsWith("`")) {
      nodes.push(<code key={k} style={{ background: "#f0f0ec", padding: "1px 5px", borderRadius: 3, fontSize: ".84em" }}>{t.slice(1, -1)}</code>);
    } else {
      nodes.push(<em key={k} style={{ opacity: .7 }}>{t.slice(1, -1)}</em>);
    }
    last = m.index + t.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const BADGE: React.CSSProperties = {
  minWidth: 21, height: 21, borderRadius: 999, background: "#000", color: "#fff",
  fontSize: ".66rem", fontWeight: 700, display: "inline-flex",
  alignItems: "center", justifyContent: "center", marginTop: 1, flexShrink: 0,
};
const DOT: React.CSSProperties = {
  width: 6, height: 6, borderRadius: 999, background: "#000",
  marginTop: 8, flexShrink: 0,
};

/**
 * Dependency-free markdown renderer for chat answers, step-first layout:
 * - ordered lists  -> numbered step badges with indented sub-lines
 * - bullet lists   -> dot rows
 * - lines starting with "→" or indented 2+ spaces -> sub-line of the
 *   previous step ("→ **Fix:** ..." gets highlighted)
 * - headings (#), paragraphs, **bold**, *italic*, `code`
 */
export default function MarkdownLite({ text }: { text: string }) {
  const lines = (text || "").replace(/\r/g, "").split("\n");
  const blocks: React.ReactNode[] = [];
  let steps: { main: string; subs: string[] }[] = [];
  let ordered = false;
  let para: string[] = [];
  let key = 0;

  const flushSteps = () => {
    if (!steps.length) return;
    const rows = steps.map((it, i) => (
      <div key={i} style={{ display: "flex", gap: 9, marginBottom: 12, alignItems: "flex-start" }}>
        {ordered
          ? <span style={BADGE}>{i + 1}</span>
          : <span style={DOT} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ lineHeight: 1.55 }}>{inline(it.main)}</div>
          {it.subs.map((s, si) => {
            const t = s.trim();
            const isFix = t.startsWith("→") || /^fix\b/i.test(t);
            return (
              <div key={si} style={{
                marginTop: 4, fontSize: ".78rem", lineHeight: 1.5,
                color: isFix ? "#000" : "#5a5a56",
                fontWeight: isFix ? 600 : 400,
                paddingLeft: 9, borderLeft: "2px solid " + (isFix ? "#000" : "#e2e2de"),
              }}>
                {inline(t)}
              </div>
            );
          })}
        </div>
      </div>
    ));
    blocks.push(<div key={"s" + (key++)} style={{ margin: "8px 0" }}>{rows}</div>);
    steps = [];
  };
  const flushPara = () => {
    if (!para.length) return;
    blocks.push(<p key={"p" + (key++)} style={{ margin: "6px 0", lineHeight: 1.6 }}>{inline(para.join(" "))}</p>);
    para = [];
  };

  for (const raw of lines) {
    const t = raw.trim();
    if (!t) { flushPara(); flushSteps(); continue; }
    const hm = t.match(/^#{1,4}\s+(.*)$/);
    if (hm) {
      flushPara(); flushSteps();
      blocks.push(
        <div key={"h" + (key++)} style={{ fontWeight: 700, fontSize: ".9rem", margin: "12px 0 4px", letterSpacing: "-0.01em" }}>
          {inline(hm[1])}
        </div>);
      continue;
    }
    const ol = t.match(/^(\d+)[.)]\s+(.*)$/);
    if (ol) {
      flushPara();
      if (!steps.length || !ordered) { flushSteps(); ordered = true; }
      steps.push({ main: ol[2], subs: [] });
      continue;
    }
    const ul = t.match(/^[-•]\s+(.*)$/);
    if (ul) {
      flushPara();
      if (!steps.length || ordered) { flushSteps(); ordered = false; }
      steps.push({ main: ul[1], subs: [] });
      continue;
    }
    // continuation of the previous step: "→ Fix: ..." or 2+ space indented line
    if (steps.length && (t.startsWith("→") || /^\s{2,}\S/.test(raw))) {
      steps[steps.length - 1].subs.push(t);
      continue;
    }
    flushSteps();
    para.push(t);
  }
  flushPara();
  flushSteps();
  return <div style={{ fontSize: ".85rem" }}>{blocks}</div>;
}