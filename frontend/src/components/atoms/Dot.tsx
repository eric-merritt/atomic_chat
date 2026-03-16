export function Dot({ delay = '0s', className = '' }: { delay?: string; className?: string }) {
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse ${className}`}
      style={{ animationDelay: delay }}
    />
  );
}
