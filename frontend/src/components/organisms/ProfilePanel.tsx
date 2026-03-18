import { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { updateProfile, changePassword } from '../../api/preferences';
import { Avatar } from '../atoms/Avatar';

export function ProfilePanel() {
  const { user } = useAuth();
  const [username, setUsername] = useState(user?.username || '');
  const [email, setEmail] = useState(user?.email || '');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [pwMessage, setPwMessage] = useState('');

  const handleSaveProfile = async () => {
    setSaving(true);
    setMessage('');
    const res = await updateProfile({ username, email });
    if (res.error) setMessage(res.error);
    else setMessage('Profile updated.');
    setSaving(false);
  };

  const handleChangePassword = async () => {
    setPwMessage('');
    const res = await changePassword(currentPw, newPw);
    if (res.error) setPwMessage(res.error);
    else { setPwMessage('Password changed.'); setCurrentPw(''); setNewPw(''); }
  };

  const inputClass = "w-full bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2 text-sm font-mono outline-none focus:border-[var(--accent)] transition-all";
  const btnClass = "px-4 py-2 text-sm rounded-lg bg-[var(--accent)] text-white hover:opacity-90 transition-opacity cursor-pointer";

  return (
    <div className="max-w-lg">
      <h2 className="text-lg font-semibold text-[var(--text)] mb-4">Profile</h2>

      <div className="flex items-center gap-4 mb-6">
        <Avatar src={user?.avatar_url} size={64} />
        <div>
          <div className="text-sm text-[var(--text)] font-medium">{user?.username}</div>
          <div className="text-xs text-[var(--text-muted)]">{user?.auth_method} account</div>
          <div className="text-xs text-[var(--text-muted)]">Role: {user?.role}</div>
        </div>
      </div>

      <div className="space-y-3 mb-6">
        <div>
          <label className="text-xs text-[var(--text-muted)] mb-1 block">Username</label>
          <input value={username} onChange={e => setUsername(e.target.value)} className={inputClass} />
        </div>
        <div>
          <label className="text-xs text-[var(--text-muted)] mb-1 block">Email</label>
          <input value={email} onChange={e => setEmail(e.target.value)} className={inputClass} />
        </div>
        <button onClick={handleSaveProfile} disabled={saving} className={btnClass}>
          {saving ? 'Saving...' : 'Save Profile'}
        </button>
        {message && <p className="text-xs text-[var(--text-muted)]">{message}</p>}
      </div>

      {user?.auth_method === 'local' && (
        <div className="border-t border-[var(--glass-border)] pt-4">
          <h3 className="text-sm font-medium text-[var(--text)] mb-3">Change Password</h3>
          <div className="space-y-3">
            <input type="password" placeholder="Current password" value={currentPw}
              onChange={e => setCurrentPw(e.target.value)} className={inputClass} />
            <input type="password" placeholder="New password (min 8 chars)" value={newPw}
              onChange={e => setNewPw(e.target.value)} className={inputClass} />
            <button onClick={handleChangePassword} className={btnClass}>Change Password</button>
            {pwMessage && <p className="text-xs text-[var(--text-muted)]">{pwMessage}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
