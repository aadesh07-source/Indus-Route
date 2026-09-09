// @ts-nocheck
"use client";
import { useEffect, useRef, useState } from "react";
import { Card, Button, Form, Badge } from "react-bootstrap";
import { motion } from "motion/react";
import { Send, Bot, User as UserIcon } from "lucide-react";
import {
  assistantStream, assistantHistory,
  getChatSession, setChatSession, type ChatMsg,
} from "@/lib/api";
import MarkdownLite from "@/components/MarkdownLite";

const QUICK_PROMPTS = [
  "Why was my application returned?",
  "What mistakes did my application make?",
  "What documents am I missing?",
  "Which MPCB consent do I need before construction?",
  "What is my application status?",
];

const INTENT_LABEL: Record<string, string> = {
  diagnose: "ISSUE DIAGNOSIS", status: "STATUS LOOKUP",
  documents: "DOCUMENT CHECK", general: "REGULATORY Q&A",
};

export default function QaTab() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const sid = getChatSession();
    if (!sid) return;
    assistantHistory(sid).then((r) => setMessages(r.messages || [])).catch(() => {});
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  function send(text?: string) {
    const msg = (text ?? input).trim();
    if (!msg || streaming) return;
    setError("");
    setInput("");
    setStreaming(true);
    setMessages((m) => [...m, { role: "user", content: msg }, { role: "assistant", content: "" }]);

    const patchLast = (fn: (last: ChatMsg) => ChatMsg) =>
      setMessages((all) => all.map((m, i) => (i === all.length - 1 ? fn(m) : m)));

    assistantStream(
      msg, getChatSession(),
      (delta) => patchLast((last) => ({ ...last, content: last.content + delta })),
      (meta) => {
        if (meta.session_id) setChatSession(meta.session_id);
        patchLast((last) => ({
          ...last,
          intent: meta.intent || last.intent,
          citations: meta.citations || last.citations,
        }));
        setStreaming(false);
      },
    ).catch((e) => {
      setError(e?.message || "Assistant unavailable.");
      setStreaming(false);
    });
  }
  return (
    <Card className="stat-card">
      <Card.Body style={{ display: "flex", flexDirection: "column", minHeight: 560 }}>
        <span className="kicker">AI Assistant · 1:1 Chat</span>
        <h4 className="fw-bolder mb-0 mt-1" style={{ letterSpacing: "-0.02em" }}>
          IndusRoute Assistant
        </h4>
        <p style={{ color: "#6d6d6d", fontSize: ".8rem", marginBottom: 12 }}>
          Knows your live application — diagnoses issues, explains mistakes, cites rule
          sources. Advisory only; officers make every decision.
        </p>

        <div style={{
          flex: 1, overflowY: "auto", background: "#fafaf8", border: "1px solid #e4e4e0",
          borderRadius: 8, padding: "1rem", display: "flex", flexDirection: "column", gap: ".7rem",
        }}>
          {messages.length === 0 && !streaming && (
            <div style={{ textAlign: "center", padding: "2rem 1rem", color: "#6d6d6d" }}>
              <Bot size={30} strokeWidth={1.5} style={{ marginBottom: ".6rem" }} />
              <p style={{ fontSize: ".85rem", marginBottom: "1rem" }}>
                Hi! Ask me anything about your application — I can tell you exactly
                what&apos;s wrong and how to fix it.
              </p>
              <div className="d-flex flex-wrap justify-content-center gap-2">
                {QUICK_PROMPTS.map((p) => (
                  <Button key={p} size="sm" className="btn-mono btn-outline-mono"
                    style={{ fontSize: ".7rem" }} onClick={() => send(p)}>
                    {p}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              style={{
                maxWidth: "92%", alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                background: m.role === "user" ? "#000" : "#fff",
                color: m.role === "user" ? "#fff" : "#000",
                borderRadius: 12, padding: ".8rem 1rem", fontSize: ".85rem",
                border: m.role === "assistant" ? "1px solid #e4e4e0" : "1px solid #000",
                borderLeft: m.role === "assistant" ? "4px solid #000" : undefined,
                boxShadow: m.role === "assistant" ? "0 1px 3px rgba(0,0,0,.05)" : undefined,
              }}>
              <div className="d-flex align-items-center gap-1 mb-1"
                style={{ opacity: .55, fontSize: ".62rem", letterSpacing: ".08em" }}>
                {m.role === "user" ? <UserIcon size={11} /> : <Bot size={11} />}
                {m.role === "user" ? "YOU" : "INDUSROUTE ASSISTANT"}
                {m.role === "assistant" && m.intent && INTENT_LABEL[m.intent] && (
                  <Badge bg="dark" style={{ fontSize: ".55rem", marginLeft: 4 }}>
                    {INTENT_LABEL[m.intent]}
                  </Badge>
                )}
              </div>
              {m.role === "assistant"
                ? <MarkdownLite text={m.content} />
                : <div style={{ lineHeight: 1.5 }}>{m.content}</div>}
              {m.role === "assistant" && streaming && i === messages.length - 1 && !m.content && (
                <span style={{ opacity: .5 }}>● ● ●</span>
              )}
              {m.role === "assistant" && !streaming && m.citations?.length > 0 && (
                <div className="d-flex flex-wrap gap-1 mt-2 pt-2"
                  style={{ borderTop: "1px solid #eee", fontSize: ".66rem" }}>
                  <span style={{ opacity: .5, alignSelf: "center", letterSpacing: ".08em" }}>SOURCES</span>
                  {m.citations.slice(0, 4).map((c: any, ci: number) => (
                    <span key={ci} title={c.source || c.title}
                      style={{ background: "#000", color: "#fff", borderRadius: 4,
                               padding: "2px 8px", fontSize: ".62rem", maxWidth: 260,
                               overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {c.title || c.source}
                    </span>
                  ))}
                </div>
              )}
            </motion.div>
          ))}
          <div ref={endRef} />
        </div>

        {error && <p className="mt-2 mb-0" style={{ color: "#c22", fontSize: ".78rem" }}>{error}</p>}

        <Form className="d-flex gap-2 mt-3" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <Form.Control value={input} onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your application, documents, or regulations…"
            disabled={streaming} maxLength={1000} />
          <Button type="submit" className="btn-mono flex-shrink-0" disabled={streaming || !input.trim()}>
            {streaming ? "…" : <><Send size={14} strokeWidth={2} /> Send</>}
          </Button>
        </Form>
      </Card.Body>
    </Card>
  );
}
