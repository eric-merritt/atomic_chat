import { ModelSelect } from '../molecules/ModelSelect';
import { Select } from '../atoms/Select';
import { Icon } from '../atoms/Icon';
import { useTheme } from '../../hooks/useTheme';
import { UserMenu } from '../molecules/UserMenu';

export function TopBar() {
  const { theme, setTheme, themes } = useTheme();

  const themeOptions = themes.map((t) => ({
    value: t.id,
    label: t.label,
    group: t.mode === 'dark' ? 'Dark' : 'Light',
  }));

  return (
    <div className="flex items-center gap-3 px-4 h-12 bg-[var(--glass-bg-solid)] backdrop-blur-xl border-b border-[var(--glass-border)]">
      <div className="flex items-center text-[var(--text)] font-bold text-xl tracking-[0.175em] uppercase">
        AT<Icon name="atom" size={24} className="inline-block mx-[-1px]" /><span className="ml-1">MIC</span><span className="ml-2">CHAT</span>
      </div>
      <ModelSelect />
      <div className="flex-1" />
      <span className="text-xs text-[var(--text)]">Theme:</span>
      <Select value={theme.id} onChange={setTheme} options={themeOptions} />
      <UserMenu />
    </div>
  );
}
