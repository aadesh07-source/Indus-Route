// @ts-nocheck
"use client";
import { Row, Col, Card, ListGroup, Badge } from "react-bootstrap";
import { FileCheck2, CheckCircle2, Clock, RefreshCw, Workflow } from "lucide-react";
import StatCard from "@/components/ui/StatCard";
import GaugeChart from "@/components/ui/GaugeChart";
import ApprovalDag from "@/components/workflow/ApprovalDag";
import type { Checklist, ChecklistApproval } from "@/lib/api";

type AppRow = {
  id: string; status: string; approval_name: string; approval_code: string;
  department: string; sla_days: number; readiness_score: number;
  sla: { state: string; remaining_hours: number | null }; green_channel: boolean;
  provisional_certificate: any; documents?: any[];
};

export default function OverviewTab({ apps, checklist, avgReadiness, approved, pending, renewals }: {
  apps: AppRow[]; checklist: Checklist | null; avgReadiness: number; approved: number; pending: number; renewals: number;
}) {
  return (
    <Row className="g-3 mb-4">
      <Col md={3} sm={6}><StatCard icon={FileCheck2} label="Applications" value={apps.length} spark={[2,3,3,4,5,6,6]} /></Col>
      <Col md={3} sm={6}><StatCard icon={CheckCircle2} label="Approved" value={approved} spark={[0,1,1,2,2,3,3]} /></Col>
      <Col md={3} sm={6}><StatCard icon={Clock} label="Pending" value={pending} spark={[3,4,4,3,5,4,4]} /></Col>
      <Col md={3} sm={6}><StatCard icon={RefreshCw} label="Renewals due" value={renewals} spark={[1,1,2,2,1,2,2]} /></Col>
      <Col lg={5}>
        <Card className="stat-card h-100">
          <Card.Body className="d-flex flex-column align-items-center text-center gap-3 py-4">
            <span className="kicker">Readiness Score</span>
            <GaugeChart value={avgReadiness} size={200} strokeWidth={12} />
            <div className="w-100">
              <ListGroup variant="flush" className="text-start">
                {apps.filter(a => (a.readiness_score || 0) < 80).slice(0, 4).map(a => (
                  <ListGroup.Item key={a.id} className="px-0 d-flex justify-content-between" style={{ borderBottom: "1px solid #ecece8" }}>
                    <span className="mono" style={{ fontSize: ".72rem" }}>{a.approval_code}</span>
                    <span style={{ fontSize: ".72rem", color: "#6d6d6d" }}>−{100 - (a.readiness_score || 0)} missing</span>
                  </ListGroup.Item>
                ))}
                {apps.length === 0 && (
                  <ListGroup.Item className="px-0 text-center" style={{ color: "#6d6d6d", fontSize: ".8rem" }}>No applications yet.</ListGroup.Item>
                )}
              </ListGroup>
            </div>
          </Card.Body>
        </Card>
      </Col>
      <Col lg={7}>
        <Card className="stat-card h-100">
          <Card.Body>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <div>
                <span className="kicker">Approval Journey</span>
                <h4 className="fw-bolder mb-0 mt-1" style={{ letterSpacing: "-0.02em" }}>DAG workflow</h4>
              </div>
              {checklist && (
                <Badge className="mono" style={{ background: "#f6f6f4", color: "#000", border: "1.5px solid #000" }}>
                  {checklist.approvals.length} approvals
                </Badge>
              )}
            </div>
            {checklist && checklist.approvals.length > 0 ? (
              <ApprovalDag checklist={checklist} statusOf={(a: ChecklistApproval) => {
                const app = apps.find(x => x.approval_id === a.id);
                if (!app) return "pending";
                return app.status === "approved" || app.status === "provisionally_cleared" ? "approved" : "pending";
              }} />
            ) : (
              <div className="text-center py-5" style={{ color: "#6d6d6d" }}>
                <Workflow size={32} strokeWidth={1.2} className="mb-2" />
                <p style={{ fontSize: ".82rem" }}>Save your checklist to see the DAG.</p>
              </div>
            )}
          </Card.Body>
        </Card>
      </Col>
    </Row>
  );
}
