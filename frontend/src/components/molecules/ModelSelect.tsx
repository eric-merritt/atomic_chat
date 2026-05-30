import { Select } from '../atoms/Select';
import { StatusText } from '../atoms/StatusText';
import { useModels } from '../../hooks/useModels';
import { modelId } from '../../atoms/model';

const Spinner = () => (
  <svg className="animate-spin h-4 w-4 text-[var(--accent)]" viewBox="0 0 24 24" fill="none">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
  </svg>
)

export function ModelSelect() {
  const { models, current, selectModel, loading, swapping } = useModels();

  if (loading) return <StatusText>Loading models...</StatusText>;

  const options = models.map((m) => ({
    value: modelId(m),
    label: m.devTeam ? `${m.devTeam}/${m.name}:${m.numParams}` : `${m.name}:${m.numParams}`,
  }));

  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        <Select
          value={current ? modelId(current) : ''}
          onChange={(val) => {
            if (swapping) return;
            const model = models.find((m) => modelId(m) === val);
            if (model) selectModel(model);
          }}
          options={[{ value: '', label: 'Select model...' }, ...options]}
          className={swapping ? 'opacity-50 pointer-events-none' : ''}
        />
      </div>
      {swapping
        ? <div className="flex items-center gap-1.5 text-[var(--text-muted)] text-sm"><Spinner /><span>Loading model...</span></div>
        : <StatusText>{current ? `${current.name}:${current.numParams}` : 'No model selected'}</StatusText>
      }
    </div>
  );
}
