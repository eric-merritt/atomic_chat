import { useState, useEffect, useCallback } from 'react';
import {
  fetchWorkflowGroups, fetchGateStatus, acceptGate, selectGroup,
  type WorkflowGroup,
} from '../../api/workflowGroups';
import { GroupCard } from '../molecules/GroupCard';
import { useWorkspace } from '../../hooks/useWorkspace';

interface GateBlockProps {
  gate: 'waiver' | 'age';
  onAccepted: () => void;
}

function WaiverGate({ onAccepted }: { onAccepted: () => void }) {
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleAccept = async () => {
    if (!checked) return;
    setSubmitting(true);
    await acceptGate('waiver');
    onAccepted();
  };

  return (
    <div className="bg-[var(--glass-bg-solid)] border border-[var(--glass-border)] rounded-lg p-4 space-y-3">
      <p className="text-xs font-semibold text-[var(--accent)] uppercase tracking-widest">
        Security Research Tools — Waiver Required
      </p>
      <p className="text-sm text-[var(--text-muted)] leading-relaxed">
        These tools are for authorized security research and penetration testing only. By
        enabling them you confirm that:
      </p>
      <ul className="text-sm text-[var(--text-muted)] list-disc list-inside space-y-1">
        <li>You will only test systems you own or have explicit written authorization to test.</li>
        <li>You understand that unauthorized testing is illegal in most jurisdictions.</li>
        <li>You accept sole responsibility for any use of these tools.</li>
      </ul>
      <label className="flex items-start gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
          className="mt-0.5 accent-[var(--accent)]"
        />
        <span className="text-sm text-[var(--text)]">
          I understand and accept these terms.
        </span>
      </label>
      <button
        onClick={handleAccept}
        disabled={!checked || submitting}
        className="w-full py-2 rounded-lg text-sm font-semibold bg-[var(--accent)] text-[var(--bg-base)] hover:brightness-110 transition-all disabled:opacity-40 cursor-pointer"
      >
        {submitting ? '…' : 'Unlock Security Research Tools'}
      </button>
    </div>
  );
}

function AgeGate({ onAccepted }: { onAccepted: () => void }) {
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleAccept = async () => {
    if (!checked) return;
    setSubmitting(true);
    await acceptGate('age');
    onAccepted();
  };

  return (
    <div className="bg-[var(--glass-bg-solid)] border border-[var(--glass-border)] rounded-lg p-4 space-y-3">
      <p className="text-xs font-semibold text-[var(--accent)] uppercase tracking-widest">
        OnlyFans Tools — Age Verification Required
      </p>
      <p className="text-sm text-[var(--text-muted)] leading-relaxed">
        These tools interact with adult content platforms. Access is restricted to users who are
        18 years of age or older.
      </p>
      <label className="flex items-start gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
          className="mt-0.5 accent-[var(--accent)]"
        />
        <span className="text-sm text-[var(--text)]">
          I confirm that I am 18 years of age or older.
        </span>
      </label>
      <button
        onClick={handleAccept}
        disabled={!checked || submitting}
        className="w-full py-2 rounded-lg text-sm font-semibold bg-[var(--accent)] text-[var(--bg-base)] hover:brightness-110 transition-all disabled:opacity-40 cursor-pointer"
      >
        {submitting ? '…' : 'Unlock OnlyFans Tools'}
      </button>
    </div>
  );
}

function GateBlock({ gate, onAccepted }: GateBlockProps) {
  if (gate === 'waiver') return <WaiverGate onAccepted={onAccepted} />;
  return <AgeGate onAccepted={onAccepted} />;
}

export function RestrictedToolsPanel() {
  const { refreshGroups } = useWorkspace();
  const [groups, setGroups] = useState<WorkflowGroup[]>([]);
  const [gateStatus, setGateStatus] = useState<Record<string, boolean>>({});
  const [activeGroups, setActiveGroups] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const [wf, status] = await Promise.all([fetchWorkflowGroups(), fetchGateStatus()]);
    setGroups(wf.restricted);
    setGateStatus(status);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleGateAccepted = useCallback(async (gate: string) => {
    setGateStatus((s) => ({ ...s, [gate]: true }));
    await refreshGroups();
  }, [refreshGroups]);

  const handleToggle = useCallback(async (name: string) => {
    const willBeActive = !activeGroups.includes(name);
    setActiveGroups((prev) =>
      willBeActive ? [...prev, name] : prev.filter((g) => g !== name)
    );
    try {
      await selectGroup(name, willBeActive);
    } catch {
      setActiveGroups((prev) =>
        willBeActive ? prev.filter((g) => g !== name) : [...prev, name]
      );
    }
  }, [activeGroups]);

  if (loading) {
    return <p className="text-sm text-[var(--text-muted)]">Loading…</p>;
  }

  const waiverGroups = groups.filter((g) => g.gate === 'waiver');
  const ageGroups = groups.filter((g) => g.gate === 'age');

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-[var(--text)]">Restricted Tools</h2>

      {waiverGroups.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-widest">
            Security Research
          </p>
          {!gateStatus['waiver'] ? (
            <GateBlock gate="waiver" onAccepted={() => handleGateAccepted('waiver')} />
          ) : (
            <div className="grid grid-cols-1 gap-2">
              {waiverGroups.map((g) => (
                <GroupCard
                  key={g.name}
                  name={g.name}
                  tooltip={g.tooltip}
                  tools={g.tools}
                  active={activeGroups.includes(g.name)}
                  onToggle={handleToggle}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {ageGroups.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-widest">
            OnlyFans
          </p>
          {!gateStatus['age'] ? (
            <GateBlock gate="age" onAccepted={() => handleGateAccepted('age')} />
          ) : (
            <div className="grid grid-cols-1 gap-2">
              {ageGroups.map((g) => (
                <GroupCard
                  key={g.name}
                  name={g.name}
                  tooltip={g.tooltip}
                  tools={g.tools}
                  active={activeGroups.includes(g.name)}
                  onToggle={handleToggle}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
