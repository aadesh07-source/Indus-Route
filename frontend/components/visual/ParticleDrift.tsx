"use client";
import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

function Particles({ count = 160 }: { count?: number }) {
  const points = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 26;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 16;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 12;
    }
    return arr;
  }, [count]);

  useFrame((state) => {
    const pts = points.current;
    if (!pts) return;
    pts.rotation.y = state.clock.elapsedTime * 0.02;
    pts.position.y =
      Math.sin(state.clock.elapsedTime * 0.12) * 0.4;
  });

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial color="#8f8f8f" size={0.045} sizeAttenuation transparent opacity={0.32} />
    </points>
  );
}

/**
 * Extremely subtle particle drift for black analytics surfaces only.
 */
export default function ParticleDrift({ opacity = 1 }: { opacity?: number }) {
  return (
    <div
      aria-hidden
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        opacity,
        zIndex: 0,
      }}
    >
      <Canvas dpr={[1, 1.4]} camera={{ position: [0, 0, 10], fov: 60 }}>
        <Particles />
      </Canvas>
    </div>
  );
}