import { ModelSelect } from '../molecules/ModelSelect';
import { Select } from '../atoms/Select';
import { Icon } from '../atoms/Icon';
import { useTheme } from '../../hooks/useTheme';

export function TopBar() {
  const { theme, setTheme, themes } = useTheme();

  const themeOptions = themes.map((t) => ({
    value: t.id,
    label: t.label,
    group: t.mode === 'dark' ? 'Dark' : 'Light',
  }));

  return (
    <div className="flex items-center gap-3 px-4 h-12 bg-[var(--glass-bg-solid)] backdrop-blur-xl border-b border-[var(--glass-border)]">
      <div className="flex items-center gap-2 text-[var(--text)] font-medium text-sm">
        <Icon name="globe" size={18} />
        Agentic Chat
      </div>
      <ModelSelect />
      <div className="flex-1" />
      <Select value={theme.id} onChange={setTheme} options={themeOptions} />
    </div>
  );
}
