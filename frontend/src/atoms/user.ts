export type Role = 'admin' | 'user' | 'viewer';
export type SaveMode = 'auto' | 'prompt' | 'never';

export interface Preferences {
  save_mode?: SaveMode;
  theme?: string;
  selected_tools?: string[];
}

export interface User {
  id: string;
  username: string;
  email: string | null;
  role: Role;
  avatar_url: string | null;
  auth_method: 'local' | 'oauth';
  preferences?: Preferences;
}
