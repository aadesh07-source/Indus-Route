// @ts-nocheck
"use client";
import { useState } from "react";
import { Card, Button, Form } from "react-bootstrap";
import { motion } from "motion/react";
import { Send } from "lucide-react";
import { askRegulatoryQuestion } from "@/lib/api";

export default function QaTab() {
  const [q, setQ] = useState("What approvals do I need for a food processing factory?");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  async function ask() { setBusy(true); try { setRes(await askRegulatoryQuestion(q)); } finally { setBusy(false); } }
  return (
    <Card className="stat-card">
      <Card.Body>
        <span className="kicker">Regulatory Q&A</span>
        <h4 className="fw-bolder mb-1 mt-1" style={{ letterSpacing: "-0.02em" }}>Ask · RAG-grounded · Cites sources</h4>
        <p style={{ color: "#6d6d6d", fontSize: ".82rem" }}>Answers are generated from the regulatory knowledge base. Always advisory.</p>
        <div className="d-flex gap-2 mt-3">
          <Form.Control value={q} onChange={e => setQ(e.target.value)} placeholder="Ask a regulatory question…" />
          <Button className="btn-mono flex-shrink-0" onClick={ask} disabled={busy}>
            {busy ? "Thinking…" : <><Send size={14} strokeWidth={2} /> Ask</>}
          </Button>
        </div>
        {res && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="mt-4 p-3" style={{ background: "#f6f6f4", borderRadius: 6, borderLeft: "4px solid #000" }}>
            <p className="mb-2" style={{ fontSize: ".88rem" }}>{res.answer}</p>
            {res.citations?.length > 0 && <div style={{ fontSize: ".72rem", color: "#6d6d6d" }}>Sources: {res.citations.map((c: any) => c.source).join(" · ")}</div>}
          </motion.div>
        )}
      </Card.Body>
    </Card>
  );
}
