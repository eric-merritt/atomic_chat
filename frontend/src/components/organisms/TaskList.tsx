import { useState, useEffect, useCallback, useRef } from 'react';
import { useChat } from '../../hooks/useChat';
import { getConversationTasks, createConversationTask, updateConversationTask, deleteConversationTask, createConversation, type ConversationTaskDTO } from '../../api/conversations';
import { CSSProperties } from 'react';

const STATUS_ICONS: Record<string, string> = {
  pending: '\u25CB',
  done: '\u25CF',
};

function ChecklistIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="-4 -8 56 52"
      fill="none"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ width: '3.1rem', height: '2.5rem', flexShrink: 0, margin: '-0.2rem 0' }}
    >
      {/* Row 1: checked — bright green */}
      <rect x="3" y="3" width="8" height="8" rx="0" stroke="#00ff40" />
      <path d="M1 3l6 5 6-11" strokeWidth="2" stroke="#00ff40" />
      <line x1="16" y1="7" x2="46" y2="7" stroke="#00ff40" />

      {/* Row 2: in-progress — bright yellow */}
      <rect x="3" y="17" width="8" height="8" rx="0" stroke="#ffdd00" />
      <line x1="16" y1="21" x2="46" y2="21" stroke="#ffdd00" />

      {/* Row 3: pending — bright red */}
      <rect x="3" y="31" width="8" height="8" rx="0" stroke="#ff2020" />
      <line x1="16" y1="35" x2="46" y2="35" stroke="#ff2020" />
    </svg>
  );
}

/** Build a map of task id → list of tasks that depend on it */
function buildDependencyMap(tasks: ConversationTaskDTO[]) {
  const map = new Map<string, string[]>();
  for (const t of tasks) {
    if (t.depends_on) {
      const deps = map.get(t.depends_on) ?? [];
      deps.push(t.id);
      map.set(t.depends_on, deps);
    }
  }
  return map;
}

interface TaskListProps {
  sidebarExpanded: boolean;
  style: CSSProperties;
}

const TEST_TASKS = [
  `Use a javascript capable  web fetch method to go to https://gayporntube.com with the following cookies set:{
        "name": "kt_rt_rtaoverlay",
        "value": "hid_rtaOverlay",
        "domain": "www.gayporntube.com",
        "hostOnly": true,
        "path": "/",
        "secure": false,
        "httpOnly": false,
        "sameSite": null,
        "session": false,
        "firstPartyDomain": "",
        "partitionKey": null,
        "expirationDate": 1807343348,
        "storeId": null},{"name": "kt_rt_user",
        "value": "true",
        "domain": "www.gayporntube.com",
        "hostOnly": true,
        "path": "/",
        "secure": false,
        "httpOnly": false,
        "sameSite": null,
        "session": false,
        "firstPartyDomain": "",
        "partitionKey": null,
        "expirationDate": 1777121378.891,
        "storeId": null
    },{"name": "kt_member",
        "value": "0a74b6ff1ccfecc2ca658240fee5e211",
        "domain": ".gayporntube.com",
        "hostOnly": false,
        "path": "/",
        "secure": false,
        "httpOnly": false,
        "sameSite": "lax",
        "session": false,
        "firstPartyDomain": "",
        "partitionKey": null,
        "expirationDate": 1778399378.89,
        "storeId": null
    },{"name": "kt_remote_ips",
        "value": "%2C50.246.208.70%7C%7Ce52525d84fc17cc6ce453fe08e7e3a4d",
        "domain": ".gayporntube.com",
        "hostOnly": false,
        "path": "/",
        "secure": false,
        "httpOnly": false,
        "sameSite": "lax",
        "session": false,
        "firstPartyDomain": "",
        "partitionKey": null,
        "expirationDate": 1775811021.608,
        "storeId": null
    },{"name": "kt_rt_adv_player_vast_count",
        "value": "3",
        "domain": "www.gayporntube.com",
        "hostOnly": true,
        "path": "/",
        "secure": false,
        "httpOnly": false,
        "sameSite": null,
        "session": false,
        "firstPartyDomain": "",
        "partitionKey": null,
        "expirationDate": 1775810983,
        "storeId": null
    },{"name": "kt_tcookie",
        "value": "1",
        "domain": "www.gayporntube.com",
        "hostOnly": true,
        "path": "/",
        "secure": false,
        "httpOnly": false,
        "sameSite": "lax",
        "session": false,
        "firstPartyDomain": "",
        "partitionKey": null,
        "expirationDate": 1776412183,
        "storeId": null
    },{"name": "PHPSESSID",
        "value": "38d6v8kp3534ol28tg248tjnk1",
        "domain": ".gayporntube.com",
        "hostOnly": false,
        "path": "/",
        "secure": false,
        "httpOnly": false,
        "sameSite": "lax",
        "session": true,
        "firstPartyDomain": "",
        "partitionKey": null,
        "storeId": null }]`,
  "Extract all of the img.lazyloaded elements, gathering the href from the a element that wraps them. (lazy-loaded so wait for dom to load).",
  "Use the list of href values to navigate to video pages and download videos to ~/agent_downloads (be sure to not download videos we already have (list that dir first so you knoow what to filter out)"
]

export function TaskList({sidebarExpanded, style }: TaskListProps) {
  const { conversationId, streaming, loadConversation } = useChat();
  const [tasks, setTasks] = useState<ConversationTaskDTO[]>([]);
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<string[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const draftRefs = useRef<Map<number, HTMLInputElement>>(new Map());
  const prevStreamingRef = useRef(streaming);

  const convIdRef = useRef(conversationId);
  convIdRef.current = conversationId;

  const load = useCallback(async (cid?: string) => {
    const id = cid ?? conversationId;
    if (!id) { setTasks([]); return; }
    const data = await getConversationTasks(id);
    setTasks(data.tasks);
  }, [conversationId]);

  const ensureConversation = useCallback(async (): Promise<string | null> => {
    if (convIdRef.current) return convIdRef.current;
    const resp = await createConversation('New task list');
    const id = resp?.conversation?.id;
    if (!id) return null;
    await loadConversation(id);
    convIdRef.current = id;
    return id;
  }, [loadConversation]);

  const submitDraft = useCallback(async (di: number, title: string) => {
    const trimmed = title.trim();
    if (!trimmed) {
      setDrafts(d => d.filter((_, i) => i !== di));
      return;
    }
    try {
      const cid = await ensureConversation();
      if (!cid) { console.error('TaskList: no conversation id'); return; }
      const result = await createConversationTask(cid, trimmed);
      console.log('TaskList: created task', result);
      setDrafts(d => d.filter((_, i) => i !== di));
      load(cid);
    } catch (err) {
      console.error('TaskList: submit failed', err);
    }
  }, [ensureConversation, load]);

  const startEditing = useCallback((task: ConversationTaskDTO) => {
    setEditingId(task.id);
    setEditingTitle(task.title);
  }, []);

  const submitEdit = useCallback(async (taskId: string) => {
    const trimmed = editingTitle.trim();
    if (!trimmed || !conversationId) { setEditingId(null); return; }
    try {
      await updateConversationTask(conversationId, taskId, { title: trimmed });
      setEditingId(null);
      load();
    } catch (err) {
      console.error('TaskList: edit failed', err);
    }
  }, [editingTitle, conversationId, load]);

  const deleteTask = useCallback(async (taskId: string) => {
    if (!conversationId) return;
    try {
      await deleteConversationTask(conversationId, taskId);
      load();
    } catch (err) {
      console.error('TaskList: delete failed', err);
    }
  }, [conversationId, load]);

  const toggleStatus = useCallback(async (task: ConversationTaskDTO) => {
    if (!conversationId) return;
    const newStatus = task.status === 'done' ? 'pending' : 'done';
    try {
      await updateConversationTask(conversationId, task.id, { status: newStatus });
      load();
    } catch (err) {
      console.error('TaskList: toggle status failed', err);
    }
  }, [conversationId, load]);

  useEffect(() => { load(); }, [load]);

  // Refresh when streaming finishes
  useEffect(() => {
    if (!streaming && prevStreamingRef.current) load();
    prevStreamingRef.current = streaming;
  }, [streaming, load]);

  // Close popover on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const taskCount = tasks.length;
  const doneCount = tasks.filter(t => t.status === 'done').length;
  const depMap = buildDependencyMap(tasks);
  const taskById = new Map(tasks.map(t => [t.id, t]));

  return (
    <div style={style}
      ref={popoverRef}
      className="relative flex items-center flex-1 bg-[var(--glass-bg-solid)] border border-[var(--accent)] rounded-xl z-10 w-full"
    >
      {/* Click target bar */}
      <button
        onClick={() => {
          setOpen(o => {
            if (!o) setDrafts(['']);
            return !o;
          });
        }}
        className={`flex items-center justify-center gap-2 w-full px-1 py-1 rounded-xl transition-colors cursor-pointer hover:brightness-110
          ${open ? 'brightness-110' : ''}`}
        title={taskCount > 0 ? `${taskCount} tasks (${doneCount} done)` : 'Add a task'}
      >
        <ChecklistIcon className="text-[var(--accent)] hover:brightness-125 transition-all" />

        {/* Collapsed: icon + m/n counter */}
        {!sidebarExpanded && taskCount > 0 && (
          <span className="text-[10px] font-mono font-bold text-[var(--accent)]">
            {doneCount}/{taskCount}
          </span>
        )}

        {/* Expanded: icon + progress circles */}
        {sidebarExpanded && taskCount > 0 && (
          <div className="flex items-center">
            {tasks.map((t) => (
              <span
                key={t.id}
                className="inline-block w-[10px] h-[10px] rounded-full border transition-all duration-300"
                style={t.status === 'done' ? {
                  borderColor: 'transparent',
                  background: 'radial-gradient(circle at 40% 35%, var(--accent), color-mix(in srgb, var(--accent) 30%, transparent))',
                  boxShadow: '0 0 6px color-mix(in srgb, var(--accent) 60%, transparent)',
                } : {
                  borderColor: 'color-mix(in srgb, var(--text-muted) 50%, transparent)',
                  background: 'transparent',
                }}
                title={t.title}
              />
            ))}
          </div>
        )}
      </button>

      {/* Popover */}
      {open && (
        <div
          className="absolute bottom-full left-[33%] mb-1
            rounded-xl overflow-hidden flex flex-col
            backdrop-blur-xl border border-[var(--glass-border)]
            shadow-[0_8px_32px_rgba(0,0,0,0.3)] z-50
            animate-[msgIn_0.15s_ease-out]"
          style={{
            width: '318px',
            height: '22vh',
            opacity: 0.95,
            backgroundColor: 'rgba(211,211,211,0.2)',
          }}
        >
          {/* Header */}
          <div className="flex flex-none" style={{ borderBottom: '1px solid var(--accent)' }}>
            <div className="w-8 shrink-0" />
            <div className="flex-1 relative flex items-center justify-center px-2 pt-2" style={{ borderLeft: '1px solid #ff2020' }}>
              <span className="text-sm font-mono font-semibold text-[var(--accent)]">Task List</span>
              {taskCount > 0 && (
                <span className="text-sm font-mono text-[var(--text-muted)] ml-2">{doneCount}/{taskCount}</span>
              )}
              <button
                onClick={() => setOpen(false)}
                className="absolute right-3 text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors cursor-pointer text-sm leading-none"
              >
                &times;
              </button>
            </div>
            <div className="w-8 shrink-0" />
          </div>

          {/* Body — scrollable task list */}
          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden flex">
            <div className="w-8 shrink-0" />
            <div className="flex-1" style={{ borderLeft: '1px solid #ff2020' }}>
            {tasks.map((t, idx) => {
              const blockedBy = t.depends_on ? taskById.get(t.depends_on) : null;
              const isBlocked = blockedBy && blockedBy.status !== 'done';
              const dependents = depMap.get(t.id);

              return (
                <div
                  key={t.id}
                  draggable
                  onDragStart={() => setDragIdx(idx)}
                  onDragOver={(e) => { e.preventDefault(); setDragOverIdx(idx); }}
                  onDragEnd={() => {
                    if (dragIdx !== null && dragOverIdx !== null && dragIdx !== dragOverIdx) {
                      const reordered = [...tasks];
                      const [moved] = reordered.splice(dragIdx, 1);
                      reordered.splice(dragOverIdx, 0, moved);
                      setTasks(reordered);
                    }
                    setDragIdx(null);
                    setDragOverIdx(null);
                  }}
                  className={`group/task flex flex-col gap-0.5 pt-1 pl-2 pr-2 border-b border-[var(--glass-border)] cursor-grab active:cursor-grabbing transition-opacity border-l border-l-[#ff2020] ml-[-1px]
                    ${dragIdx === idx ? 'opacity-40' : ''}
                    ${dragOverIdx === idx && dragIdx !== idx ? 'border-t-2 border-t-[var(--accent)]' : ''}`}
                >
                  <div className="flex items-center gap-2 overflow-hidden">
                    <span
                      className="shrink-0 font-mono"
                      style={{ color: t.status === 'done' ? 'var(--accent)' : isBlocked ? 'var(--danger, #ef4444)' : 'var(--text-muted)', fontSize: '10px' }}
                    >
                      {idx + 1}.
                    </span>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); toggleStatus(t); }}
                      className="shrink-0 cursor-pointer hover:brightness-150 transition-all"
                      style={{ color: t.status === 'done' ? 'var(--accent)' : isBlocked ? 'var(--danger, #ef4444)' : 'var(--text-muted)', fontSize: '10px', background: 'none', border: 'none', padding: 0 }}
                      title={t.status === 'done' ? 'Mark pending' : 'Mark done'}
                    >
                      {STATUS_ICONS[t.status] ?? '\u25CB'}
                    </button>
                    {editingId === t.id ? (
                      <form className="flex-1 flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); submitEdit(t.id); }}>
                        <input
                          type="text"
                          autoFocus
                          value={editingTitle}
                          onChange={(e) => setEditingTitle(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Escape') setEditingId(null); }}
                          className="flex-1 bg-transparent outline-none font-mono text-[var(--accent)]"
                          style={{ fontSize: '10px' }}
                        />
                        <button type="submit" className="shrink-0 text-[#00ff40] hover:brightness-150 cursor-pointer transition-all" style={{ fontSize: '12px' }} title="Save">&#x2713;</button>
                        <button type="button" onClick={() => setEditingId(null)} className="shrink-0 text-[#ff2020] hover:brightness-150 cursor-pointer transition-all" style={{ fontSize: '12px' }} title="Cancel">&#x2717;</button>
                      </form>
                    ) : (
                      <>
                        <span
                          className="flex-1 overflow-hidden whitespace-nowrap min-w-0 group/marquee"
                          style={{ opacity: t.status === 'done' ? 0.5 : 1 }}
                        >
                          <span
                            className="inline-block font-mono text-[var(--text-primary)] group-hover/marquee:animate-[marquee_2.7s_linear_1.2s_infinite]"
                            style={{ fontSize: '10px' }}
                          >
                            {t.title}
                          </span>
                        </span>
                        <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover/task:opacity-100 transition-opacity">
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); startEditing(t); }}
                            className="text-[#ffdd00] hover:brightness-150 cursor-pointer transition-all"
                            style={{ fontSize: '12px' }}
                            title="Edit task"
                          >
                            &#x270E;
                          </button>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); deleteTask(t.id); }}
                            className="text-[#ff2020] hover:brightness-150 cursor-pointer transition-all"
                            style={{ fontSize: '12px' }}
                            title="Delete task"
                          >
                            &#x2717;
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                  {(isBlocked || (dependents && dependents.length > 0)) && (
                    <div className="ml-6 flex flex-col gap-0.5">
                      {isBlocked && blockedBy && (
                        <span className="font-mono text-[var(--danger, #ef4444)] opacity-80" style={{ fontSize: '9px' }}>
                          blocked by: {blockedBy.title}
                        </span>
                      )}
                      {dependents && dependents.length > 0 && (
                        <span className="font-mono text-[var(--text-muted)] opacity-60" style={{ fontSize: '9px' }}>
                          blocks: {dependents.map(id => taskById.get(id)?.title ?? id).join(', ')}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Draft rows */}
            {drafts.map((draft, di) => (
              <div key={`draft-${di}`} className="flex items-start gap-1 pt-1 pl-2 pr-2 border-b border-[var(--glass-border)] ml-[-1]">
                  <span className="shrink-0 font-mono text-[var(--text-muted)] mt-[1px]" style={{ fontSize: '10px' }}>
                    {taskCount + di + 1}.
                  </span>
                  <form
                    className="flex-1 min-w-0"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      submitDraft(di, draft);
                    }}
                  >
                    <textarea
                      ref={(el) => { if (el) draftRefs.current.set(di, el as unknown as HTMLInputElement); else draftRefs.current.delete(di); }}
                      autoFocus={di === drafts.length - 1}
                      value={draft}
                      rows={1}
                      onChange={(e) => {
                        e.target.style.height = 'auto';
                        e.target.style.height = e.target.scrollHeight + 'px';
                        setDrafts(d => d.map((v, i) => i === di ? e.target.value : v));
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape') {
                          setDrafts(d => d.filter((_, i) => i !== di));
                        } else if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          const trimmed = draft.trim();
                          if (trimmed) {
                            ensureConversation().then(cid => {
                              if (!cid) return;
                              createConversationTask(cid, trimmed).then(() => load(cid));
                            });
                          }
                          setDrafts(d => {
                            const next = [...d];
                            next[di] = '';
                            return next;
                          });
                        }
                      }}
                      placeholder="New task..."
                      className="w-full bg-transparent outline-none font-mono text-[var(--accent)] placeholder:text-[var(--text-muted)] resize-none overflow-hidden"
                      style={{ fontSize: '10px', padding: 0, lineHeight: '1.4' }}
                    />
                  </form>
                  <button
                    type="button"
                    onClick={() => submitDraft(di, draft)}
                    className="shrink-0 text-[#00ff40] hover:brightness-150 cursor-pointer transition-all"
                    style={{ fontSize: '12px' }}
                    title="Submit task"
                  >
                    &#x2713;
                  </button>
                  <button
                    type="button"
                    onClick={() => setDrafts(d => d.filter((_, i) => i !== di))}
                    className="shrink-0 text-[#ff2020] hover:brightness-150 cursor-pointer transition-all"
                    style={{ fontSize: '12px' }}
                    title="Cancel"
                  >
                    &#x2717;
                  </button>
              </div>
            ))}
            </div>
            <div className="w-8 shrink-0" />
          </div>

          {/* Footer — always visible add button */}
          <div className="flex flex-none relative z-10">
            <div className="w-8 shrink-0" />
            <div className="flex-1 flex items-center justify-center gap-2 py-1" style={{ borderLeft: '1px solid #ff2020' }}>
              <div
                className="flex items-center justify-center w-fit cursor-pointer rounded-lg border border-[var(--glass-border)] hover:bg-[var(--accent)] hover:text-[var(--bg-base)] transition-colors px-2 py-0.5 group z-20"
                onClick={() => setDrafts(d => [...d, ''])}
              >
                <span className="font-mono text-[var(--accent)] group-hover:text-[var(--bg-base)] transition-colors" style={{ fontSize: '12px' }}>+ Add a task...</span>
              </div>
              <div
                className="flex items-center justify-center w-fit cursor-pointer rounded-lg border border-[var(--glass-border)] hover:bg-[var(--accent)] hover:text-[var(--bg-base)] transition-colors px-2 py-0.5 group z-20"
                onClick={async () => {
                  const cid = await ensureConversation();
                  if (!cid) return;
                  for (const title of TEST_TASKS) {
                    await createConversationTask(cid, title);
                  }
                  load(cid);
                }}
              >
                <span className="font-mono text-[var(--accent)] group-hover:text-[var(--bg-base)] transition-colors" style={{ fontSize: '12px' }}>+7</span>
              </div>
            </div>
            <div className="w-8 shrink-0" />
          </div>
        </div>
      )}
    </div>
  );
}
