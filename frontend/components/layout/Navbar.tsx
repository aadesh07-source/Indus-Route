// @ts-nocheck
"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Container, Nav, Navbar as BsNavbar, NavDropdown } from "react-bootstrap";
import { User, ArrowUpRight, LogOut } from "lucide-react";
import { getUser, logout } from "@/lib/api";

type Props = {
  dark?: boolean;
};

export default function Navbar({ dark = false }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  // Hydration-safe: localStorage is only read after mount, so the
  // server-rendered markup always matches the first client render.
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => { setUser(getUser()); }, []);

  const portalLinks = [
    { href: "/applicant", label: "Applicant" },
    { href: "/officer", label: "Officer" },
    { href: "/admin", label: "Admin" },
  ];

  function signOut() {
    logout();
    setUser(null);
    router.push("/");
  }

  return (
    <BsNavbar expand="lg" sticky="top" className={dark ? "ir-nav ir-nav--dark" : "ir-nav"}>
      <Container fluid="xxl">
        <BsNavbar.Brand href="/" className="navbar-brand">
          <span>Indus Route</span>
        </BsNavbar.Brand>
        <BsNavbar.Toggle aria-controls="ir-nav-no-collapse" className="border-0" />
        <BsNavbar.Collapse id="ir-nav-no-collapse">
          <Nav className="ms-auto align-items-lg-center gap-lg-3">
            {portalLinks.map((l) => (
              <Nav.Link
                key={l.href}
                as={Link}
                href={l.href}
                className={pathname.startsWith(l.href) ? "active" : ""}
              >
                {l.label}
              </Nav.Link>
            ))}
            {user ? (
              <NavDropdown
                title={
                  <span className="d-inline-flex align-items-center gap-2 text-uppercase">
                    <User size={14} strokeWidth={1.75} /> {user.role}
                  </span>
                }
                id="user-menu"
                align="end"
              >
                <NavDropdown.Item className="muted">{user.name}</NavDropdown.Item>
                <NavDropdown.Divider />
                <NavDropdown.Item onClick={signOut}>
                  <LogOut size={13} style={{ marginRight: 6 }} /> Sign out
                </NavDropdown.Item>
              </NavDropdown>
            ) : (
              <Nav.Link as={Link} href="/login" className="nav-cta">
                Sign in <ArrowUpRight size={13} strokeWidth={2.5} />
              </Nav.Link>
            )}
          </Nav>
        </BsNavbar.Collapse>
      </Container>
    </BsNavbar>
  );
}