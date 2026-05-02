import { type ReactNode } from "react";
import { useTheme } from "../hooks/useTheme";
import { ParticleCanvas } from "../components/atoms/ParticleCanvas";
import { Icon } from "../components/atoms/Icon";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h2 className="text-xs font-semibold text-[var(--accent)] uppercase tracking-widest mb-2">
        {title}
      </h2>
      <div className="text-sm text-[var(--text-muted)] leading-relaxed space-y-2">
        {children}
      </div>
    </section>
  );
}

export function SupportPage() {
  const { theme } = useTheme();

  return (
    <div
      className="min-h-screen flex items-start justify-center bg-[var(--bg-base)] py-12 px-4"
      data-theme={theme.id}
    >
      <ParticleCanvas theme={theme.id} />
      <div className="relative z-10 w-full max-w-xl">
        <div className="bg-[var(--glass-bg-solid)] backdrop-blur-xl border border-[var(--accent)] rounded-2xl p-8 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
          <h1 className="text-2xl font-bold text-[var(--text)] text-center mb-1 tracking-widest uppercase flex items-center justify-center">
            AT
            <Icon name="atom" size={24} className="inline-block mx-[-1px]" />
            MIC CHAT
          </h1>
          <p className="text-sm text-[var(--text-muted)] text-center mb-8">
            Support
          </p>

          <Section title="Contact">
            <p>
              For questions, bug reports, or feature requests, email{" "}
              <a
                href="mailto:ericm2009@gmail.com"
                className="text-[var(--accent)] hover:underline"
              >
                ericm2009@gmail.com
              </a>
              . Include your operating system and a description of the issue.
            </p>
          </Section>

          <Section title="Agent not connecting">
            <p>
              If the desktop agent fails to connect after login, try the
              following:
            </p>
            <ul className="list-disc list-inside space-y-1 text-sm text-[var(--text-muted)]">
              <li>Check your internet connection.</li>
              <li>
                Delete the credentials file and re-authenticate. On Windows:{" "}
                <code className="inline-block font-mono text-xs text-[var(--text)] bg-[var(--msg-user)] border border-[var(--glass-border)] rounded px-2 py-0.5 whitespace-nowrap">
                  %APPDATA%\AtomicChat\credentials.json
                </code>
                . On macOS / Linux:{" "}
                <code className="inline-block font-mono text-xs text-[var(--text)] bg-[var(--msg-user)] border border-[var(--glass-border)] rounded px-2 py-0.5 whitespace-nowrap">
                  ~/.config/atomic_chat/credentials.json
                </code>
                .
              </li>
              <li>Verify that your firewall allows outbound WebSocket connections.</li>
            </ul>
          </Section>

          <Section title="Allowed paths">
            <p>
              The agent can only access folders listed in{" "}
              <code className="inline-block font-mono text-xs text-[var(--text)] bg-[var(--msg-user)] border border-[var(--glass-border)] rounded px-2 py-0.5 whitespace-nowrap">
                ALLOWED_PATHS
              </code>{" "}
              inside your{" "}
              <code className="inline-block font-mono text-xs text-[var(--text)] bg-[var(--msg-user)] border border-[var(--glass-border)] rounded px-2 py-0.5 whitespace-nowrap">
                .env.client
              </code>{" "}
              file. Edit that file to add or restrict folders, then restart the
              agent.
            </p>
          </Section>

          <Section title="Uninstalling">
            <p>
              Uninstall via <strong className="text-[var(--text)]">Add or Remove Programs</strong> on
              Windows. To fully remove user data, also delete:
            </p>
            <code className="inline-block font-mono text-xs text-[var(--text)] bg-[var(--msg-user)] border border-[var(--glass-border)] rounded px-2 py-0.5 whitespace-nowrap">
              %APPDATA%\AtomicChat\
            </code>
          </Section>

          <div className="border-t border-[var(--glass-border)] pt-4 mt-2">
            <p className="text-xs text-[var(--text-muted)] text-center">
              Last updated: May 2026
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
