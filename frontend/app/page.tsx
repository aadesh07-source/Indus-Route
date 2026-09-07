// @ts-nocheck
"use client";
import { useEffect, useState } from "react";
import { Container, Row, Col } from "react-bootstrap";
import Link from "next/link";
import { motion } from "motion/react";
import {
  UserRound,
  ShieldCheck,
  BarChart3,
  ArrowRight,
  FileCheck2,
  ScanLine,
  Workflow,
  Gauge,
  BellRing,
} from "lucide-react";
import NodeNetworkScene from "@/components/visual/NodeNetworkScene";
import { health } from "@/lib/api";

const personas = [
  {
    icon: UserRound,
    title: "Applicant",
    copy: "Personalised approval checklist, guided documentation, live SLA tracking — one end-to-end journey instead of six desks.",
    href: "/applicant",
    cta: "Open applicant portal",
  },
  {
    icon: ShieldCheck,
    title: "Officer",
    copy: "A prioritised queue with rubric-based readiness, AI pre-scrutiny and one-click verify / clarify / decide — human judgement always in control.",
    href: "/officer",
    cta: "Open officer desk",
  },
  {
    icon: BarChart3,
    title: "Admin",
    copy: "State-level KPIs, bottleneck detection, deficiency analytics and the immutable audit trail.",
    href: "/admin",
    cta: "Open command centre",
  },
];

const process = [
  { icon: UserRound, title: "Profile", copy: "One profile feeds every approval — no re-entry." },
  { icon: Workflow, title: "Checklist", copy: "Deterministic rules generate your approvals & parallel paths." },
  { icon: ScanLine, title: "Validate", copy: "Documents pre-validated against statutory checks." },
  { icon: Gauge, title: "Submit", copy: "One submission reached a ready, explainable score." },
  { icon: FileCheck2, title: "Approve", copy: "Officer decides within SLA; system never auto-decides." },
];

const principles = [
  {
    icon: ShieldCheck,
    tag:"Rule 01",
    title:"Rules decide.",
    copy:"AI only explains, extracts, flags, drafts and summarizes — it never decides.",
  },
  {
    icon: Workflow,
    tag:"Engine 02",
    title:"Deterministic by design.",
    copy:"Applicable approvals come from a deterministic rule engine — zero guesses, zero I/O.",
  },
  {
    icon: Gauge,
    tag:"Score 03",
    title:"Readiness is a rubric.",
    copy:"A completeness score — never a risk score or an approval probability.",
  },
  {
    icon: BellRing,
    tag:"Green Channel 04",
    title:"Provisional only.",
    copy:"Issues provisional clearance, always paired with a mandatory post-facto audit.",
  },
];

// Word-by-word scroll reveal for headings / hero copy.

function AnimatedWords({ text, delay =  0, stagger =  0.06 }: { text: string; delay?: number; stagger?: number }) {
  const words = text.split(" ");
   return (
    <span className="aw-wrap">
      {words.map((w,i) => (
        <motion.span
          key={i}
          className="aw-word"
          initial={{ opacity: 0, y: 16, filter: "blur(6px)" }}
          whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.45, delay: delay + i * stagger, ease: "easeOut" }}
        >
          {w}
        </motion.span>
      ))}
    </span>
  );
}
function scrollReveal(i: number) {
  return {
    initial: { opacity: 0, y: 20 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-60px" },
    transition: { duration: 0.4, delay: i * 0.06, ease: "easeOut" as const },
  };
}

export default function Landing() {
  const [backend, setBackend] = useState<string>("connecting");

  useEffect(() => {
    let alive = true;
    health()
      .then((h) => alive && setBackend(h.status === "ok" ? "online" : "degraded"))
      .catch(() => alive && setBackend("offline"));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
      {/* ── HERO · black surface · R3F node network ─────────────── */}
      <section className="hero">
        <NodeNetworkScene className="hero-canvas" />
        <div className="hero-scrim" />
        <Container fluid="xxl" style={{ position: "relative", zIndex: 2 }}>
          <Row className="align-items-center" style={{ minHeight: "86vh" }}>
            <Col lg={8} xl={7}>
              <motion.div
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease: "easeOut" }}
              >
                <div className="kicker text-white">
                  Industrial Approval &amp; Compliance Platform
                </div>
                <h1 className="hero-title">
                  Compliance
                  <br />
                  Resolved.
                </h1>
                <p className="hero-sub">
                  One intelligent platform for the entire industrial approval life
                  cycle — personalised checklists, pre-validation, parallel
                  workflows, SLA discipline and post-approval compliance.
                </p>
                <div className="mt-4 d-flex flex-wrap gap-3">
                  <Link href="/applicant" className="btn btn-mono btn-light-invert">
                    Enter the portal <ArrowRight size={15} strokeWidth={2.6} />
                  </Link>
                  <Link href="/login" className="btn btn-mono btn-outline-mono-light">
                    Sign in
                  </Link>
                </div>
              </motion.div>

              <motion.div
                className="hero-stats"
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, delay: 0.25, ease: "easeOut" }}
              >
                <Row className="g-4">
                  <Col xs={4}>
                    <div className="stat-num">5→1</div>
                    <div className="stat-lbl">Departments · one queue</div>
                  </Col>
                  <Col xs={4}>
                    <div className="stat-num">100%</div>
                    <div className="stat-lbl">Deterministic checks</div>
                  </Col>
                  <Col xs={4}>
                    <div className="stat-num">
                      {backend === "online" ? (
                        <span style={{ color: "#ffffff" }}>●</span>
                      ) : backend === "offline" ? (
                        <span style={{ color: "#ff3b30" }}>●</span>
                      ) : (
                        <span style={{ color: "#ff9f0a" }}>●</span>
                      )}{" "}
                      API
                    </div>
                    <div className="stat-lbl">Backend {backend}</div>
                  </Col>
                </Row>
              </motion.div>
            </Col>
          </Row>
        </Container>
        <div className="scroll-hint">Scroll</div>
      </section>

      {/* ── PRINCIPLE ──────────────────────────────────────────── */}
      <section className="py-5" style={{ background: "#fff" }}>
        <Container fluid="xxl" className="py-4">
          <motion.div {...scrollReveal(0)} className="text-center mb-4">
            <span className="kicker justify-content-center">How this system behaves</span>
            <h2 className="display-7 mt-2">Built on principles, not probability.</h2>
          </motion.div>
          <Row className="g-4">
            {principles.map((f, i) => (
              <Col md={6} lg={3} key={f.tag}>
                <motion.div
                  className="h-100"
                  initial={{ opacity: 0, y:  40, rotateY:  10 }}
                  whileInView={{ opacity:  1, y:  0, rotateY:  0 }}
                  viewport={{ once: true, margin: "-60px" }}
                  transition={{ duration:  0.5, delay: i *  0.1, ease: "easeOut" }}
                >
<motion.div
                    className="h-100"
                    animate={{ y: [0, -7, 0] }}
                    transition={{ duration: 4.5 + i * 0.7, repeat: Infinity, ease: "easeInOut" }}
                  >
                    <div
                      className={"flash-card h-100" + (i === 0 || i === 2 ? " is-dark" : "")}
                      data-n={i + 1}
                    >
                      <div className="flash-tag">{f.tag}</div>
                      <div className="flash-icon"><f.icon size={26} strokeWidth={1.4} /></div>
                      <h3 className="flash-title">{f.title}</h3>
                      <p className="flash-copy">{f.copy}</p>
                    </div>
                  </motion.div>
                </motion.div>
              </Col>
            ))}
          </Row>
        </Container>
      </section>

      {/* ── PERSONA CARDS · white surface ──────────────────────── */}
      <section className="py-5" style={{ background: "#fff", borderTop: "1.5px solid #000" }}>
        <Container fluid="xxl">
          <motion.div {...scrollReveal(0)}>
            <span className="kicker">Three desks, one system</span>
            <h2 className="display-6 mt-2 mb-4" style={{ maxWidth: 640 }}>
              Built for the people who carry the approval journey.
            </h2>
          </motion.div>
          <Row className="g-4">
            {personas.map((p, i) => (
              <Col md={6} lg={4} key={p.title}>
                <motion.div {...scrollReveal(i)} className="h-100">
                  <Link href={p.href} style={{ textDecoration: "none" }}>
                    <div className="card persona-card h-100">
                      <div className="card-body d-flex flex-column gap-3">
                        <span className="icon-frame">
                          <p.icon size={20} strokeWidth={1.6} />
                        </span>
                        <h3 style={{ fontSize: "1.35rem", fontWeight: 850, letterSpacing: "-0.03em" }}>
                          {p.title}
                        </h3>
                        <p style={{ color: "inherit", opacity: 0.72, fontSize: ".92rem" }}>{p.copy}</p>
                        <span
                          className="mt-auto d-inline-flex align-items-center gap-2 fw-bold text-uppercase"
                          style={{ fontSize: ".72rem", letterSpacing: ".16em" }}
                        >
                          {p.cta} <ArrowRight size={14} strokeWidth={2.4} />
                        </span>
                      </div>
                    </div>
                  </Link>
                </motion.div>
              </Col>
            ))}
          </Row>
        </Container>
      </section>

      {/* ── PROCESS TIMELINE ───────────────────────────────────── */}
      <section className="py-5" style={{ background: "#fff", borderTop: "1.5px solid #000" }}>
        <Container fluid="xxl">
          <motion.div {...scrollReveal(0)} className="text-center mb-5">
            <span className="kicker justify-content-center">The journey</span>
            <h2 className="display-6 mt-2">
                <AnimatedWords text="Five steps. Zero dead ends." delay={0.12} />
              </h2>
          </motion.div>
          <div className="timeline d-none d-md-block">
            <div className="timeline-track">
              <motion.div
                className="timeline-fill"
                initial={{ scaleX: 0 }}
                whileInView={{ scaleX: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 1.1, ease: "easeOut" }}
              />
            </div>
            <Row>
              {process.map((s, i) => (
                <Col key={s.title} md={4} lg={2}>
                  <motion.div
                    className="timeline-node"
                    {...scrollReveal(i)}
                    transition={{ duration: 0.4, delay: i * 0.12, ease: "easeOut" }}
                  >
                    <div className="node-dot">
                      <s.icon size={20} strokeWidth={1.6} />
                    </div>
                    <h5>{s.title}</h5>
                    <p>{s.copy}</p>
                  </motion.div>
                </Col>
              ))}
            </Row>
          </div>

          {/* Mobile: stacked compact list */}
          <div className="d-md-none">
            {process.map((s, i) => (
              <motion.div
                key={s.title}
                {...scrollReveal(i)}
                className="d-flex gap-3 py-3"
                style={{ borderBottom: "1px solid #ecede9" }}
              >
                <span className="icon-frame flex-shrink-0" style={{ width: 42, height: 42 }}>
                  <s.icon size={17} strokeWidth={1.6} />
                </span>
                <div>
                  <strong>{s.title}</strong>
                  <div style={{ color: "#6d6d6d", fontSize: ".85rem" }}>{s.copy}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </Container>
      </section>

      {/* ── FINAL CTA ──────────────────────────────────────────── */}
      <section className="surface-black py-5">
        <Container fluid="xxl" className="py-5 text-center">
          <motion.div {...scrollReveal(0)}>
            <BellRing size={22} strokeWidth={1.5} style={{ marginBottom: 10 }} />
<h2 className="display-6 text-white" style={{ maxWidth: 720, margin: "0 auto" }}>
                <AnimatedWords text="Your approvals, coordinated. Your SLA, guaranteed. Your paperwork, done once." delay={0.05} stagger={0.04} />
              </h2>
            <Link href="/applicant" className="btn btn-mono btn-light-invert mt-4">
              Start your journey <ArrowRight size={15} strokeWidth={2.6} />
            </Link>
          </motion.div>
        </Container>
      </section>
    </>
  );
}