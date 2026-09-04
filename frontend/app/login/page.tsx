// @ts-nocheck
"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { Card, Button, Form } from "react-bootstrap";
import { api, setToken, setUser } from "@/lib/api";
import { ArrowRight, ShieldCheck } from "lucide-react";

const DEMO = [
  { label: "Applicant", id: "9000000001" },
  { label: "Officer", id: "9000000002" },
  { label: "Admin", id: "9000000003" },
];

export default function Login() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("9000000001");
  const [password, setPassword] = useState("Demo@123");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data = await api.post("/auth/login", { identifier, password });
      setToken(data.token);
      setUser(data.user);
      const role = data.user?.role;
      router.push(role === "officer" || role === "admin" ? `/${role}` : "/applicant");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell py-5">
      <div className="auth-card">
        <Card>
          <Card.Body className="p-4 p-lg-5">
            <div className="kicker mb-3">Sign in</div>
            <h1 className="display-7 mb-1">Back to work.</h1>
            <p style={{ color: "#6d6d6d", marginBottom: "1.6rem" }}>
              Your role determines what you see — applicant, officer or admin.
            </p>
            <Form onSubmit={submit}>
              <Form.Group className="mb-3" controlId="login-id">
                <Form.Label className="text-uppercase" style={{ fontSize: ".7rem", letterSpacing: ".16em", fontWeight: 700 }}>
                  Phone or email
                </Form.Label>
                <Form.Control
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                  autoFocus
                />
              </Form.Group>
              <Form.Group className="mb-4" controlId="login-pw">
                <Form.Label className="text-uppercase" style={{ fontSize: ".7rem", letterSpacing: ".16em", fontWeight: 700 }}>
                  Password
                </Form.Label>
                <Form.Control
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </Form.Group>
              {error && (
                <div className="alert alert-danger py-2" style={{ borderLeft: "4px solid #ff3b30" }}>
                  {error}
                </div>
              )}
              <Button type="submit" className="btn-mono w-100" disabled={busy}>
                {busy ? "Signing in…" : "Sign in"} <ArrowRight size={15} strokeWidth={2.4} />
              </Button>
            </Form>

            <hr className="my-4" />
            <div className="d-flex flex-column gap-2">
              <div className="d-flex align-items-center gap-2" style={{ color: "#6d6d6d", fontSize: ".78rem" }}>
                <ShieldCheck size={14} /> Demo accounts — password <span className="mono">Demo@123</span>
              </div>
              <div className="d-flex flex-wrap gap-2">
                {DEMO.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    className="badge border text-dark"
                    style={{ background: "#f6f6f4", cursor: "pointer", fontFamily: "monospace" }}
                    onClick={() => {
                      setIdentifier(d.id);
                      setPassword("Demo@123");
                    }}
                  >
                    {d.label} · {d.id}
                  </button>
                ))}
              </div>
            </div>
            <div className="auth-side-note mt-3">
              New user? <Link href="/register">Create an account →</Link>
            </div>
          </Card.Body>
        </Card>
      </div>
    </div>
  );
}