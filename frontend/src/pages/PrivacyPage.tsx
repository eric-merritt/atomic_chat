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

function Path({ children }: { children: string }) {
  return (
    <code className="inline-block font-mono text-xs text-[var(--text)] bg-[var(--msg-user)] border border-[var(--glass-border)] rounded px-2 py-0.5 whitespace-nowrap">
      {children}
    </code>
  );
}

export function PrivacyPage() {
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
            Privacy Policy
          </p>

          <Section title="Overview">
            <p>
              Atomic Chat Agent is a desktop bridge that connects your computer
              to the Atomic Chat service. This policy describes what data the
              agent accesses, transmits, and stores.
            </p>
          </Section>

          <Section title="Data the agent accesses">
            <p>
              The agent can read and write files and execute shell commands on
              your computer, within the folders you explicitly allow via the{" "}
              <code className="font-mono text-xs text-[var(--text)]">
                ALLOWED_PATHS
              </code>{" "}
              setting. No files are accessed outside those paths.
            </p>
          </Section>

          <Section title="Data transmitted to our servers">
            <p>
              File contents, directory listings, command output, and other tool
              results are sent to <Path>agent.eric-merritt.com</Path> over an
              encrypted WebSocket connection. This data is used only to fulfill
              your chat requests and is not sold or shared with third parties.
            </p>
          </Section>

          <Section title="Data stored locally">
            <p>A session credential is stored on your device at:</p>
            <p className="text-[var(--text-muted)] text-xs">
              <Path>%APPDATA%\AtomicChat\credentials.json</Path> - Windows
            </p>
            <p className="text-[var(--text-muted)] text-xs">
              <Path>~/.config/atomic_chat/credentials.json</Path> - macOS /
              Linux
            </p>
            <p className="mt-1">
              This file is readable only by your user account. No other personal
              data is persisted by the agent.
            </p>
          </Section>

          <Section title="Authentication">
            <p>
              On first run, the agent opens your browser for a one-time login.
              After approval, a session token is saved locally so subsequent
              runs connect automatically. You can revoke access at any time by
              deleting the credentials file or signing out from the web app.
            </p>
          </Section>

          <Section title="Data retention">
            <p className="font-medium text-[var(--text)]">
              Fully Local Install — Client Agent + Web UI
            </p>
            <p>
              Conversation history is stored in your own database (SQLite or
              JSONL, configured during setup) and is never uploaded to our
              servers. You control and can delete this data at any time.
            </p>
            <p className="font-medium text-[var(--text)] pt-1">
              Client Agent + Web Service
            </p>
            <p>
              Conversations are stored in the service database on our servers.
              You can delete your conversation history at any time from the web
              app.
            </p>
          </Section>

          <Section title="Third-party services">
            <p>
              The desktop agent contacts{" "}
              <code className="font-mono text-xs text-[var(--text)]">
                agent.eric-merritt.com
              </code>{" "}
              only and includes no third-party SDKs.
            </p>
            <p>
              The web application may display advertisements served by
              third-party ad networks. Those networks may use cookies or similar
              technologies to serve relevant ads. You can opt out through your
              browser's privacy controls or a standard opt-out mechanism such as
              the{" "}
              <a
                href="https://optout.aboutads.info"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[var(--accent)] hover:underline"
              >
                DAA opt-out
              </a>
              .
            </p>
          </Section>

          <Section title="Contact">
            <p>
              Questions about this policy?{" "}
              <a
                href="mailto:ericm2009@gmail.com"
                className="text-[var(--accent)] hover:underline"
              >
                ericm2009@gmail.com
              </a>
            </p>
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
