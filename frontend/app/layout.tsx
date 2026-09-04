import type { Metadata } from "next";
import "../styles/globals.scss";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import PageTransition from "@/components/layout/PageTransition";

export const metadata: Metadata = {
  title: "Indus Route — Industrial Approval & Compliance Platform",
  description:
    "An intelligent industrial approval and compliance management platform. Rules decide; AI explains.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <PageTransition>{children}</PageTransition>
        <Footer />
      </body>
    </html>
  );
}