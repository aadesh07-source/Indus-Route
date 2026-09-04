"use client";
import { useRef, useState } from "react";
import { motion } from "motion/react";
import { UploadCloud, FileUp } from "lucide-react";

type Props = {
  onFile: (file: File) => void;
  busy?: boolean;
  label?: string;
  accept?: string;
};

/**
 * Bold dashed-border dropzone (custom — not Bootstrap's file input).
 * Scales/lifts on drag-hover via motion.dev, 120ms snappy transition.
 */
export default function Dropzone({
  onFile,
  busy = false,
  label = "Drop a document here, or click to browse",
  accept = ".pdf,.png,.jpg,.jpeg,.txt",
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleFile(f: File | undefined | null) {
    if (!f || busy) return;
    onFile(f);
  }

  return (
    <motion.div
      className={`dropzone ${dragging ? "dz-dragging" : ""}`}
      animate={{ scale: dragging ? 1.02 : 1 }}
      transition={{ duration: 0.12, ease: [0, 0, 0.2, 1] }}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        handleFile(e.dataTransfer.files?.[0]);
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
    >
      <div className="dz-icon">
        {busy ? <FileUp size={24} strokeWidth={1.5} /> : <UploadCloud size={24} strokeWidth={1.5} />}
      </div>
      <h5 className="fw-bold mb-1" style={{ letterSpacing: "-0.02em" }}>
        {busy ? "Validating…" : label}
      </h5>
      <p className="mono mb-0" style={{ color: "#6d6d6d", fontSize: ".72rem" }}>
        PDF · PNG · JPG · TXT — max 10 MB — magic-byte checked server-side
      </p>
      <input
        ref={inputRef}
        type="file"
        hidden
        accept={accept}
        onChange={(e) => {
          handleFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </motion.div>
  );
}