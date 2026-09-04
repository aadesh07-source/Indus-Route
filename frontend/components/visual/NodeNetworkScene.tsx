// @ts-nocheck
"use client";
import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float } from "@react-three/drei";
import * as THREE from "three";

// ── Deterministic pseudo-random (stable across renders) ──────
function hash(n: number): number {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return s - Math.floor(s);
}

type Edge = { from: THREE.Vector3; to: THREE.Vector3; verified: boolean };

function buildNetwork() {
  const positions: THREE.Vector3[] = [];
  const verified = [3, 9, 14, 21]; // a few nodes "verified" → electric green
  const count = 26;

  for (let i = 0; i < count; i++) {
    const radius = 3.2 + hash(i + 90) * 1.6;
    const theta = hash(i + 2) * Math.PI * 2;
    const phi = Math.acos(2 * hash(i + 5) - 1);
    positions.push(
      new THREE.Vector3(
        radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.cos(phi) * 0.9,
        radius * Math.sin(phi) * Math.sin(theta) * 0.7
      )
    );
  }

  const edges: Edge[] = [];
  for (let i = 0; i < count; i++) {
    for (let j = i + 1; j < count; j++) {
      const d = positions[i].distanceTo(positions[j]);
      if (d < 2.6) {
        edges.push({
          from: positions[i],
          to: positions[j],
          verified: verified.includes(i) && verified.includes(j),
        });
      }
    }
  }
  return { positions, edges, verified };
}

function GraphNode({
  pos,
  isVerified,
  delay,
}: {
  pos: THREE.Vector3;
  isVerified: boolean;
  delay: number;
}) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const mesh = ref.current;
    if (!mesh) return;
    const appear = Math.min(1, Math.max(0, (t - delay) / 1.6));
    const pulse = isVerified
      ? 1 + 0.14 * Math.sin(t * 3.2)
      : 1 + 0.05 * Math.sin(t * 2);
    mesh.scale.setScalar(pulse * appear);
  });
  return (
    <mesh ref={ref} position={pos}>
      <sphereGeometry args={[0.16, 20, 20]} />
      <meshBasicMaterial color={isVerified ? "#ffffff" : "#ffffff"} toneMapped={false} transparent />
    </mesh>
  );
}

function DrawLine({ edge, delay }: { edge: Edge; delay: number }) {
  const ref = useRef<THREE.Line>(null);
  useFrame((state) => {
    const t = Math.min(1, Math.max(0, (state.clock.elapsedTime - delay) / 1.5));
    const line = ref.current;
    if (!line) return;
    const steps = 34;
    const drawn = Math.max(1, Math.ceil(steps * t));
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i <= drawn; i++) {
      pts.push(new THREE.Vector3().lerpVectors(edge.from, edge.to, i / steps));
    }
    const geom = line.geometry as THREE.BufferGeometry;
    if (geom.getAttribute("position")) geom.deleteAttribute("position");
    geom.setFromPoints(pts);
  });
  return (
    <line ref={ref}>
      <lineBasicMaterial color={edge.verified ? "#ffffff" : "#d9d9d4"} transparent opacity={edge.verified ? 0.95 : 0.45} />
    </line>
  );
}

function Network() {
  const group = useRef<THREE.Group>(null);
  const net = useMemo(buildNetwork, []);
  const { positions, edges, verified } = net;

  useFrame((_, delta) => {
    if (group.current) group.current.rotation.y += delta * 0.075;
  });

  return (
    <group ref={group} rotation={[0.25, 0, 0]}>
      {positions.map((pos, i) => {
        const isVerified = verified.includes(i);
        const neighbors = edges.filter(e => e.from === pos || e.to === pos);
        return (
          <GraphNode key={i} pos={pos} isVerified={isVerified} delay={0.3 + i * 0.06} />
        );
      })}
      {edges.map((e, i) => (
        <DrawLine key={i} edge={e} delay={0.8 + i * 0.04} />
      ))}
    </group>
  );
}

export default function NodeNetworkScene({ className = "" }: { className?: string }) {
  return (
    <div className={className} style={{ position: "absolute", inset: 0 }}>
      <Canvas
        dpr={[1, 1.5]}
        camera={{ position: [0, 0, 11.5], fov: 48 }}
        gl={{ antialias: true, alpha: true }}
      >
        <color attach="background" args={["#000000"]} />
        <Float speed={1.1} rotationIntensity={0.18} floatIntensity={0.6} floatingRange={[-0.2, .2]}>
          <Network />
        </Float>
      </Canvas>
    </div>
  );
}