import { useEffect, useRef } from "react";
import * as THREE from "three";

type ParticleWaveProps = {
  amountX?: number;
  amountY?: number;
  /** 粒子颜色，如 0x7dd3fc */
  color?: number;
  className?: string;
};

const SEPARATION = 100;

const VERTEX_SHADER = `
  attribute float scale;
  void main() {
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = scale * (300.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const FRAGMENT_SHADER = `
  uniform vec3 color;
  void main() {
    if (length(gl_PointCoord - vec2(0.5, 0.5)) > 0.475) discard;
    gl_FragColor = vec4(color, 1.0);
  }
`;

function isWebGLAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext("webgl") || canvas.getContext("experimental-webgl"))
    );
  } catch {
    return false;
  }
}

/**
 * Three.js 粒子波浪背景（参考 Pointwave）。
 * - 无 WebGL / 系统「减少动态效果」时静默降级（仅保留页面底色）
 * - 移动端降低粒子密度
 * - 卸载时移除监听、停 RAF、dispose 几何/材质/渲染器
 */
export default function ParticleWave({
  amountX = 50,
  amountY = 50,
  color = 0x7dd3fc,
  className = "",
}: ParticleWaveProps) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    // 降级 1：系统减少动态效果
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    // 降级 2：浏览器不支持 WebGL
    if (!isWebGLAvailable()) {
      return;
    }

    // 降级 3：窄屏减少粒子
    const isMobile = window.matchMedia("(max-width: 768px)").matches;
    const cols = isMobile ? Math.min(amountX, 32) : amountX;
    const rows = isMobile ? Math.min(amountY, 32) : amountY;

    let count = 0;
    let mouseX = 0;
    let windowHalfX = window.innerWidth / 2;
    let rafId = 0;
    let disposed = false;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      // 降级 4：创建渲染器失败（驱动/上下文耗尽等）
      return;
    }

    const camera = new THREE.PerspectiveCamera(
      75,
      window.innerWidth / window.innerHeight,
      1,
      10000
    );
    camera.position.z = 1000;

    const scene = new THREE.Scene();

    const numParticles = cols * rows;
    const positions = new Float32Array(numParticles * 3);
    const scales = new Float32Array(numParticles);

    let i = 0;
    let j = 0;
    for (let ix = 0; ix < cols; ix++) {
      for (let iy = 0; iy < rows; iy++) {
        positions[i] = ix * SEPARATION - (cols * SEPARATION) / 2;
        positions[i + 1] = 0;
        positions[i + 2] = iy * SEPARATION - (rows * SEPARATION) / 2;
        scales[j] = 1;
        i += 3;
        j++;
      }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("scale", new THREE.BufferAttribute(scales, 1));

    const material = new THREE.ShaderMaterial({
      uniforms: {
        color: { value: new THREE.Color(color) },
      },
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 2));
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);

    const onMouseMove = (event: MouseEvent) => {
      mouseX = event.clientX - windowHalfX;
    };

    const onTouchStart = (event: TouchEvent) => {
      if (event.touches.length === 1) {
        mouseX = event.touches[0].pageX - windowHalfX;
      }
    };

    const onTouchMove = (event: TouchEvent) => {
      if (event.touches.length === 1) {
        mouseX = event.touches[0].pageX - windowHalfX;
      }
    };

    const onResize = () => {
      if (disposed) return;
      windowHalfX = window.innerWidth / 2;
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };

    const onContextLost = (event: Event) => {
      event.preventDefault();
      disposed = true;
      cancelAnimationFrame(rafId);
    };

    const renderFrame = () => {
      camera.position.x += (mouseX - camera.position.x) * 0.05;
      camera.position.y = 400;
      camera.lookAt(scene.position);

      const pos = particles.geometry.attributes.position.array as Float32Array;
      const scl = particles.geometry.attributes.scale.array as Float32Array;

      let pi = 0;
      let sj = 0;
      for (let ix = 0; ix < cols; ix++) {
        for (let iy = 0; iy < rows; iy++) {
          pos[pi + 1] =
            Math.sin((ix + count) * 0.2) * 100 + Math.sin((iy + count) * 0.35) * 100;
          scl[sj] =
            (Math.sin((ix + count) * 0.2) + 1) * 8 +
            (Math.sin((iy + count) * 0.35) + 1) * 8;
          pi += 3;
          sj++;
        }
      }

      particles.geometry.attributes.position.needsUpdate = true;
      particles.geometry.attributes.scale.needsUpdate = true;
      renderer.render(scene, camera);
      count += 0.045;
    };

    const animate = () => {
      if (disposed) return;
      rafId = requestAnimationFrame(animate);
      renderFrame();
    };

    window.addEventListener("resize", onResize);
    document.addEventListener("mousemove", onMouseMove, { passive: true });
    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchmove", onTouchMove, { passive: true });
    renderer.domElement.addEventListener("webglcontextlost", onContextLost, false);

    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(rafId);

      window.removeEventListener("resize", onResize);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchmove", onTouchMove);
      renderer.domElement.removeEventListener("webglcontextlost", onContextLost);

      scene.remove(particles);
      geometry.dispose();
      material.dispose();
      renderer.forceContextLoss();
      renderer.dispose();
      if (renderer.domElement.parentNode === host) {
        host.removeChild(renderer.domElement);
      }
    };
  }, [amountX, amountY, color]);

  return (
    <div
      ref={hostRef}
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      aria-hidden
    />
  );
}
