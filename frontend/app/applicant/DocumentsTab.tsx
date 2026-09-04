// @ts-nocheck
"use client";
import { useEffect, useState } from "react";
import { Card, ListGroup, Badge } from "react-bootstrap";
import Link from "next/link";
import { Upload, ScanLine, FileCheck2 } from "lucide-react";
import { listApplications } from "@/lib/api";

export default function DocumentsTab() {
  const [apps, setApps] = useState<any[]>([]);

  useEffect(() => {
    listApplications()
      .then((r) => setApps(r.applications || []))
      .catch(() => {});
  }, []);

  return (
    <Card className="stat-card">
      <Card.Body>
        <div className="d-flex justify-content-between align-items-start flex-wrap gap-2">
          <div>
            <span className="kicker">Documents</span>
            <h4 className="fw-bolder mb-1 mt-1">Upload & Pre-Validation</h4>
            <p style={{ color: "#6d6d6d", fontSize: ".82rem", maxWidth: 520 }}>
              Upload a PDF or a scanned image (PNG/JPG) for each application. Every file is verified
              against deterministic statutory checks. Documents marked <strong>Verify Pending</strong>{" "}
              must pass before your application is fully ready for the officer.
            </p>
          </div>
          <Link href="/applicant/upload" className="btn btn-mono">
            <Upload size={14} strokeWidth={2} /> Go to Upload Centre
          </Link>
        </div>
        <ListGroup variant="flush" className="mt-3">
          {apps.length === 0 && (
            <ListGroup.Item className="px-0 text-center py-4" style={{ color: "#6d6d6d" }}>
              No applications yet — create one from the checklist first.
            </ListGroup.Item>
          )}
          {apps.map((a) => {
            const pending = a.docs_pending;
            return (
              <ListGroup.Item key={a.id} className="px-0 py-3" style={{ borderBottom: "1px solid #ecece8" }}>
                <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
                  <div>
                    <span className="fw-bold">{a.approval_code}</span>
                    <span style={{ color: "#6d6d6d", fontSize: ".76rem" }}> · {a.department}</span>
                    <div className="mono" style={{ fontSize: ".7rem", color: "#9a9a94" }}>{a.id.slice(-8)}</div>
                  </div>
                  <div className="d-flex align-items-center gap-2">
                    {pending ? (
                      <Badge style={{ background: "transparent", color: "#ff9f0a", border: "1.5px solid #ff9f0a", fontSize: ".64rem", fontWeight: 700, letterSpacing: ".06em" }}>
                        <ScanLine size={11} className="me-1" />VERIFY PENDING
                      </Badge>
                    ) : a.docs_count ? (
                      <Badge style={{ background: "#000", color: "#fff", fontSize: ".64rem", fontWeight: 700, letterSpacing: ".06em" }}>
                        <FileCheck2 size={11} className="me-1" />VERIFIED ✓ {a.docs_passed}/{a.docs_total}
                      </Badge>
                    ) : (
                      <Badge style={{ background: "transparent", color: "#6d6d6d", border: "1.5px solid #ccc", fontSize: ".64rem", fontWeight: 700, letterSpacing: ".06em" }}>NO DOCS</Badge>
                    )}
                    <Link href={`/applicant/upload?app=${a.id}`} className="btn btn-mono btn-outline-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }}>
                      {pending ? "Verify docs" : "Add / view"}
                    </Link>
                  </div>
                </div>
              </ListGroup.Item>
            );
          })}
        </ListGroup>
      </Card.Body>
    </Card>
  );
}
