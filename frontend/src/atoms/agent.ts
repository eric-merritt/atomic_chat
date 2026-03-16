export type LoopStepKind = 'inference' | 'summarization' | 'definition' | 'execution';

export interface LoopStep {
  kind: LoopStepKind;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: string;
}

export interface Plan {
  id: string;
  steps: LoopStep[];
  createdAt: number;
}
