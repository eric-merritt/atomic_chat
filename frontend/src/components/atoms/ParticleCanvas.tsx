import { useRef, useEffect } from 'react';

const PALETTES: Record<string, string[]> = {
  obsidian:  ['#2a4a8a','#4060b0','#6080d0','#3050a0','#1a3070'],
  carbon:    ['#20a060','#30c080','#50e0a0','#18804a','#40d890'],
  amethyst:  ['#7030b0','#9050d0','#b070f0','#6020a0','#a060e0'],
  frost:     ['#1a3080','#203890','#284098','#152870','#1e3488'],
  sand:      ['#6a4810','#7a5418','#886020','#5c3c0a','#704c14'],
  blossom:   ['#801040','#901850','#a02060','#700830','#882048'],
};

const COUNT = 150;
const FIELD = 6;

interface Particle {
  x: number; baseX: number; y: number; r: number;
  swayAmp: number; swaySpeed: number; swayPhase: number;
  dy: number; opacity: number;
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
      const r = Math.random() * 13 + 5;
      const baseX = Math.random() * W;
      particles[i] = {
        x: baseX, baseX,
        y: scatter ? Math.random() * H * FIELD : -(Math.random() * H * 0.5),
        r,
        swayAmp: Math.random() * 40 + 20,
        swaySpeed: Math.random() * 0.008 + 0.003,
        swayPhase: Math.random() * Math.PI * 2,
        dy: 0, // set below
        opacity: Math.random() * 0.10 + 0.25, rgb,
      };
      // Fall speed must always exceed peak sway speed
      const peakSway = particles[i].swayAmp * particles[i].swaySpeed;
      particles[i].dy = peakSway + Math.random() * 0.5 + 0.1;
    }

    // Sort indices by radius so smallest draw first (behind), largest last (in front)
    const sortedIndices: number[] = [];

    function rebuildSortOrder() {
      sortedIndices.length = 0;
      for (let i = 0; i < COUNT; i++) sortedIndices.push(i);
      sortedIndices.sort((a, b) => particles[a].r - particles[b].r);
    }

    let frame = 0;

    function draw() {
      frame++;
      ctx!.clearRect(0, 0, W, H);
      for (const i of sortedIndices) {
        const p = particles[i];
        p.y += p.dy;
        if (p.y > H * FIELD) {
          spawn(i, false);
          continue;
        }
        p.x = p.baseX + Math.sin(frame * p.swaySpeed + p.swayPhase) * p.swayAmp;
        // Wrap x
        if (p.x < -p.r) p.x += W + p.r * 2;
        else if (p.x > W + p.r) p.x -= W + p.r * 2;
        const screenY = ((p.y % (H * FIELD)) + H * FIELD) % (H * FIELD) - H;
        if (screenY > -10 && screenY < H + 10) {
          const grad = ctx!.createRadialGradient(p.x, screenY, 0, p.x, screenY, p.r);
          grad.addColorStop(0, `rgba(${p.rgb[0]},${p.rgb[1]},${p.rgb[2]},${p.opacity})`);
          grad.addColorStop(0.6, `rgba(${p.rgb[0]},${p.rgb[1]},${p.rgb[2]},${p.opacity * 0.5})`);
          grad.addColorStop(1, `rgba(${p.rgb[0]},${p.rgb[1]},${p.rgb[2]},0)`);
          ctx!.beginPath();
          ctx!.arc(p.x, screenY, p.r, 0, Math.PI * 2);
          ctx!.fillStyle = grad;
          ctx!.fill();
        }
      }
      animId = requestAnimationFrame(draw);
    }

    resize();
    // Grid-jittered initial placement for even distribution
    const cols = Math.ceil(Math.sqrt(COUNT * (W / (H * FIELD))));
    const rows = Math.ceil(COUNT / cols);
    const cellW = W / cols;
    const cellH = (H * FIELD) / rows;
    for (let i = 0; i < COUNT; i++) {
      const col = i % cols;
      const row = Math.floor(i / cols);
      spawn(i, true);
      const jitteredX = col * cellW + Math.random() * cellW;
      particles[i].x = jitteredX;
      particles[i].baseX = jitteredX;
      particles[i].y = row * cellH + Math.random() * cellH;
    }
    rebuildSortOrder();
    draw();
    window.addEventListener('resize', resize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, [theme]);

  return <canvas ref={canvasRef} className="fixed inset-0 pointer-events-none z-0" />;
}
