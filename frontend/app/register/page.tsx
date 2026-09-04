// @ts-nocheck
"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { Card, Button, Form } from "react-bootstrap";
import { api, setToken, setUser } from "@/lib/api";
import { ArrowRight, KeyRound } from "lucide-react";

const INVITE_HINT = "MAHARASHTRA-2026";

export default function Register() {
  const router = useRouter();
  const [form, setForm] = useState({
    name: "",
    phone: "",
    email: "",
    password: "",
    role: "applicant",
    invite_code: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function set(k: string, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data = await api.post("/auth/register", form);
      setToken(data.token);
      setUser(data.user);
      router.push(form.role === "officer" || form.role === "admin" ? `/${form.role}` : "/applicant");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const isOfficial = form.role === "officer" || form.role === "admin";

  return (
    <div className="auth-shell py-5">
      <div className="auth-card" style={{ maxWidth: 520 }}>
        <Card>
          <Card.Body className="p-4 p-lg-5">
            <div className="kicker mb-3">Register</div>
            <h1 className="display-7 mb-1">Join the route.</h1>
            <p style={{ color: "#6d6d6d", marginBottom: "1.6rem" }}>
              Officials need a department invite code — stronger auth, by design.
            </p>
            <Form onSubmit={submit}>
              <Form.Group className="mb-3" controlId="reg-name">
                <Form.Label className="text-uppercase" style={{ fontSize: ".7rem", letterSpacing: ".16em", fontWeight: 700 }}>
                  Full name
                </Form.Label>
                <Form.Control value={form.name} onChange={(e) => set("name", e.target.value)} required minLength={2} />
              </Form.Group>
              <div className="row g-3">
                <div className="col-12 col-sm-6">
                  <Form.Group controlId="reg-phone">
                    <Form.Label className="text-uppercase" style={{ fontSize: ".7rem", letterSpacing: ".16em", fontWeight: 700 }}>
                      Phone
                    </Form.Label>
                    <Form.Control value={form.phone} onChange={(e) => set("phone", e.target.value)} required minLength={10} />
                  </Form.Group>
                </div>
                <div className="col-12 col-sm-6">
                  <Form.Group controlId="reg-email">
                    <Form.Label className="text-uppercase" style={{ fontSize: ".7rem", letterSpacing: ".16em", fontWeight: 700 }}>
                      Email (opt)
                    </Form.Label>
                    <Form.Control type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
                  </Form.Group>
                </div>
              </div>
              <Form.Group className="my-3" controlId="reg-pw">
                <Form.Label className="text-uppercase" style={{ fontSize: ".7rem", letterSpacing: ".16em", fontWeight: 700 }}>
                  Password
                </Form.Label>
                <Form.Control type="password" value={form.password} onChange={(e) => set("password", e.target.value)} required minLength={8} />
              </Form.Group>
              <Form.Group className="mb-3" controlId="reg-role">
                <Form.Label className="text-uppercase" style={{ fontSize: ".7rem", letterSpacing: ".16em", fontWeight: 700 }}>
                  Role
                </Form.Label>
                <Form.Select value={form.role} onChange={(e) => set("role", e.target.value)}>
                  <option value="applicant">Applicant (Entrepreneur)</option>
                  <option value="officer">Government Officer</option>
                  <option value="admin">Government Admin</option>
                </Form.Select>
              </Form.Group>
              {isOfficial && (
                <Form.Group className="mb-3" controlId="reg-invite">
                  <Form.Label className="text-uppercase" style={{ fontSize: ".7rem", letterSpacing: ".16em", fontWeight: 700 }}>
                    <KeyRound size={12} /> Department invite code
                  </Form.Label>
                  <Form.Control
                    value={form.invite_code}
                    onChange={(e) => set("invite_code", e.target.value)}
                    placeholder={INVITE_HINT}
                  />
                </Form.Group>
              )}
              {error && (
                <div className="alert alert-danger py-2" style={{ borderLeft: "4px solid #ff3b30" }}>
                  {error}
                </div>
              )}
              <Button type="submit" className="btn-mono w-100" disabled={busy}>
                {busy ? "Creating…" : "Create account"} <ArrowRight size={15} strokeWidth={2.4} />
              </Button>
            </Form>
            <div className="auth-side-note mt-3">
              Already registered? <Link href="/login">Sign in →</Link>
            </div>
          </Card.Body>
        </Card>
      </div>
    </div>
  );
}