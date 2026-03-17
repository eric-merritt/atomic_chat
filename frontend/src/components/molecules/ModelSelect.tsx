import { Select } from '../atoms/Select';
import { StatusText } from '../atoms/StatusText';
import { useModels } from '../../hooks/useModels';
import { modelId } from '../../atoms/model';

export function ModelSelect() {
  const { models, current, selectModel, loading } = useModels();

  if (loading) return <StatusText>Loading models...</StatusText>;

  const options = models.map((m) => ({
    value: modelId(m),
    label: m.devTeam ? `${m.devTeam}/${m.name}:${m.numParams}` : `${m.name}:${m.numParams}`,
  }));

  return (
    <div className="flex items-center gap-2">
      <Select
        value={current ? modelId(current) : ''}
        onChange={(val) => {
          const model = models.find((m) => modelId(m) === val);
          if (model) selectModel(model);
        }}
        options={[{ value: '', label: 'Select model...' }, ...options]}
      />
      <StatusText>
        {current ? `${current.name}:${current.numParams}` : 'No model selected'}
      </StatusText>
    </div>
  );
}
