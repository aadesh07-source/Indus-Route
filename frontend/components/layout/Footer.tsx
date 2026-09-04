// @ts-nocheck
import { Container, Row, Col } from "react-bootstrap";

export default function Footer() {
  return (
    <footer className="ir-footer">
      <Container fluid="xxl" className="py-5">
        <Row className="g-4">
          <Col md={5} lg={4}>
            <div className="fw-bold mb-3">
              Indus Route
            </div>
            <p style={{ color: "#8f8f8f", maxWidth: 320 }}>
              Intelligent industrial approval &amp; compliance management platform.
            </p>
          </Col>
          <Col md={3} lg={2} className="offset-lg-1">
            <div className="govt-mark mb-2">Portal</div>
            <ul className="list-unstyled d-grid gap-2">
              <li><a href="/applicant">Applicant</a></li>
              <li><a href="/officer">Officer</a></li>
              <li><a href="/admin">Admin</a></li>
            </ul>
          </Col>
          <Col md={3} lg={2}>
            <div className="govt-mark mb-2">Principles</div>
            <ul className="list-unstyled d-grid gap-2">
              <li>
                <span style={{ color: "#8f8f8f" }}>
                  Rules decide · AI explains
                </span>
              </li>
              <li>
                <span style={{ color: "#8f8f8f" }}>Human-in-the-loop</span>
              </li>
              <li>
                <span style={{ color: "#8f8f8f" }}>Auditable by design</span>
              </li>
            </ul>
          </Col>
        </Row>
      </Container>
      <div className="footer-line">
        <Container fluid="xxl" className="py-3 d-flex flex-wrap justify-content-between">
          <span>Indus Route</span>
          <span className="mono">ver 2.0 · demo build — not legally binding</span>
        </Container>
      </div>
    </footer>
  );
}