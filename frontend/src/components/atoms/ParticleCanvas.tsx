import { useRef, useEffect } from 'react';

const PALETTES: Record<string, string[]> = {
  obsidian:  ['#2a4a8a','#4060b0','#6080d0','#3050a0','#1a3070'],
  carbon:    ['#20a060','#30c080','#50e0a0','#18804a','#40d890'],
  amethyst:  ['#7030b0','#9050d0','#b070f0','#6020a0','#a060e0'],
  frost:     ['#3050c0','#4060e0','#5080ff','#2040a0','#6090ff'],
  sand:      ['#b08020','#c89830','#dab050','#a07018','#d0a040'],
  blossom:   ['#c02060','#d84080','#f060a0','#a01848','#e85098'],
};

const COUNT = 80;
const FIELD = 3;

interface Particle {
  x: number; y: number; r: number;
  dx: number; dy: number; opacity: number;
  rgb: [number, number, number];
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

interface ParticleCanvasProps {
  theme: string;
}

export function ParticleCanvas({ theme }: ParticleCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let W = 0, H = 0;
    const particles: Particle[] = [];
    let animId: number;

    function resize() {
      W = canvas!.width = window.innerWidth;
      H = canvas!.height = window.innerHeight;
    }

    function spawn(i: number, scatter: boolean) {
      const pal = PALETTES[theme] ?? PALETTES.obsidian;
      const color = pal[Math.floor(Math.random() * pal.length)];
      const rgb = hexToRgb(color);
      const r = Math.random() * 1.2 + 0.3;
      particles[i] = {
        x: Math.random() * W,
        y: scatter ? Math.random() * H * FIELD : -(Math.random() * H * 0.5),
        r, dx: (Math.random() - 0.5) * 0.06,
        dy: Math.random() * 0.12 + 0.04,
        opacity: Math.random() * 0.3 + 0.08, rgb,
      };
    }

    function draw() {
      ctx!.clearRect(0, 0, W, H);
      for (let i = 0; i < COUNT; i++) {
        const p = particles[i];
        p.x += p.dx; p.y += p.dy;
        if (p.y > H * FIELD) spawn(i, false);
        const screenY = ((p.y % (H * FIELD)) + H * FIELD) % (H * FIELD) - H;
        if (screenY > -10 && screenY < H + 10) {
          ctx!.beginPath();
          ctx!.arc(p.x, screenY, p.r, 0, Math.PI * 2);
          ctx!.fillStyle = `rgba(${p.rgb[0]},${p.rgb[1]},${p.rgb[2]},${p.opacity})`;
          ctx!.fill();
        }
      }
      animId = requestAnimationFrame(draw);
    }

    resize();
    for (let i = 0; i < COUNT; i++) spawn(i, true);
    draw();
    window.addEventListener('resize', resize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, [theme]);

  return <canvas ref={canvasRef} className="fixed inset-0 pointer-events-none z-0" />;
}
