// @ts-nocheck
"use client";
import { useEffect, useState } from "react";
import { Card, ListGroup } from "react-bootstrap";
import { motion } from "motion/react";
import { CheckCircle2, Sparkles } from "lucide-react";
import { getSchemeRecommendations } from "@/lib/api";

export default function SchemesTab() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { getSchemeRecommendations().then(setData).catch(() => {}); }, []);
  if (!data) return (
    <Card><Card.Body className="text-center py-5" style={{ color: "#6d6d6d" }}>
      <Sparkles size={28} strokeWidth={1.2} className="mb-2" /><p>Save your profile to see scheme recommendations.</p>
    </Card.Body></Card>
  );
  return (
    <div className="row g-3">
      <div className="col-lg-8">
        <Card className="stat-card">
          <Card.Body>
            <span className="kicker">Eligible Schemes</span>
            <h4 className="fw-bolder mb-3 mt-1" style={{ letterSpacing: "-0.02em" }}>{data.eligible.length} matches for your profile</h4>
            <ListGroup variant="flush">
              {data.eligible.map((s: any) => (
                <ListGroup.Item key={s.id} className="px-0 py-3" style={{ borderBottom: "1px solid #ecece8" }}>
                  <div className="d-flex align-items-start gap-2">
                    <CheckCircle2 size={16} strokeWidth={2} style={{ color: "#000", marginTop: 2 }} />
                    <div>
                      <div className="fw-bold">{s.name}</div>
                      <div style={{ color: "#6d6d6d", fontSize: ".78rem" }}>{s.description}</div>
                      <div style={{ fontSize: ".74rem", color: "#000", fontWeight: 600 }}>{s.benefits}</div>
                    </div>
                  </div>
                </ListGroup.Item>
              ))}
              {data.eligible.length === 0 && <ListGroup.Item className="px-0 text-center py-4" style={{ color: "#6d6d6d" }}>No eligible schemes yet.</ListGroup.Item>}
            </ListGroup>
          </Card.Body>
        </Card>
      </div>
      <div className="col-lg-4">
        <Card className="stat-card">
          <Card.Body>
            <h5 className="fw-bold mb-2">Not yet eligible</h5>
            {data.others.slice(0, 5).map((s: any) => (
              <div key={s.id} className="py-2" style={{ borderBottom: "1px solid #ecece8", fontSize: ".78rem" }}>
                <div className="fw-bold">{s.name}</div><div style={{ color: "#6d6d6d", fontSize: ".72rem" }}>{s.explanation}</div>
              </div>
            ))}
            <div className="principle-bar mt-3"><strong>Rule-based only</strong> — advisory, not a scheme guarantee.</div>
          </Card.Body>
        </Card>
      </div>
    </div>
  );
}
