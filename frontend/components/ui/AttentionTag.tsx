type Props = {
  level: "low" | "medium" | "high" | string;
};

const MAP: Record<string, { cls: string; text: string }> = {
  low: { cls: "att-low", text: "LOW" },
  medium: { cls: "att-medium", text: "MEDIUM" },
  high: { cls: "att-high", text: "HIGH" },
};

/**
 * Attention Level — bold text tag, no fills. Black / amber / red text only.
 */
export default function AttentionTag({ level }: Props) {
  const m = MAP[level] ?? { cls: "att-low", text: level.toUpperCase() };
  return <span className={`attention-tag ${m.cls}`}>{m.text}</span>;
}