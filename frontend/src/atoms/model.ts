export interface Model {
  devTeam: string | null;
  name: string;
  numParams: string;
  available: boolean;
  format: string | null;
  maker: string | null;
  year: number | null;
  description: string | null;
  goodAt: string[] | null;
  notSoGoodAt: string[] | null;
  idealUseCases: string[] | null;
  contextWindow: number | null;
}

export function modelId(m: Model): string {
  const base = m.devTeam ? `${m.devTeam}/${m.name}` : m.name;
  return `${base}:${m.numParams}`;
}

export function parseModelString(s: string): Model {
  let devTeam: string | null = null;
  let rest = s;

  const slashIdx = s.indexOf('/');
  if (slashIdx !== -1) {
    devTeam = s.slice(0, slashIdx);
    rest = s.slice(slashIdx + 1);
  }

  const colonIdx = rest.lastIndexOf(':');
  const name = colonIdx !== -1 ? rest.slice(0, colonIdx) : rest;
  const numParams = colonIdx !== -1 ? rest.slice(colonIdx + 1) : '';

  return {
    devTeam, name, numParams, available: true,
    format: null, maker: null, year: null, description: null,
    goodAt: null, notSoGoodAt: null, idealUseCases: null, contextWindow: null,
  };
}
