"use client";
import { motion } from "motion/react";
import { usePathname } from "next/navigation";

/**
 * Motion.dev page transition — 200–300ms fade + 8px vertical slide, ease-out.
 */
export default function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <motion.div
      key={pathname}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}