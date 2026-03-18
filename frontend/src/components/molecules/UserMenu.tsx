import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar } from '../atoms/Avatar';
import { DropdownMenu } from '../atoms/DropdownMenu';
import { useAuth } from '../../hooks/useAuth';

export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="cursor-pointer">
        <Avatar src={user?.avatar_url} alt={user?.username} size={32} />
      </button>
      <DropdownMenu
        open={open}
        onClose={() => setOpen(false)}
        className="right-0 top-10 min-w-[140px]"
        items={[
          { label: 'Dashboard', onClick: () => navigate('/dashboard') },
          { label: 'Logout', onClick: logout },
        ]}
      />
    </div>
  );
}
