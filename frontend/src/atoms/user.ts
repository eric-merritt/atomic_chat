export type Role = 'admin' | 'user' | 'viewer';

export interface User {
  id: string;
  username: string;
  email: string | null;
  role: Role;
  avatar_url: string | null;
  auth_method: 'local' | 'oauth';
}
