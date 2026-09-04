// @ts-nocheck
"use client";
import { Card } from "react-bootstrap";
import Link from "next/link";
import { Upload } from "lucide-react";

export default function DocumentsTab() {
  return (
    <Card className="stat-card">
      <Card.Body className="text-center py-5">
        <Upload size={40} strokeWidth={1.2} className="mb-3" />
        <h3 className="fw-bolder mb-2">Document Upload & Pre-Validation</h3>
        <p style={{ color: "#6d6d6d", maxWidth: 440, margin: "0 auto 1.5rem" }}>
          Upload documents for any application. They are pre-validated against deterministic rules.
        </p>
        <Link href="/applicant/upload" className="btn btn-mono">
          <Upload size={14} strokeWidth={2} /> Go to Upload Centre
        </Link>
      </Card.Body>
    </Card>
  );
}
