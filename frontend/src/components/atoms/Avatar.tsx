import { Icon } from './Icon';

interface AvatarProps {
  src?: string | null;
  alt?: string;
  size?: number;
  className?: string;
}

export function Avatar({ src, alt = '', size = 32, className = '' }: AvatarProps) {
  if (src) {
    return <img src={src} alt={alt} width={size} height={size} className={`rounded-full object-cover ${className}`} />;
  }
  return (
    <div
      className={`rounded-full bg-[var(--msg-user)] flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
    >
      <Icon name="user" size={size * 0.6} className="text-[var(--accent)]" />
    </div>
  );
}
