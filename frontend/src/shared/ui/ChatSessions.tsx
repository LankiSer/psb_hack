"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "@/shared/api/client";
import Icon from "@/shared/ui/Icon";

export type Source = { id: string; document_id: string; title: string; quote: string; line_start: number; line_end: number };
export type Reply = { answer: string; status: string; sources: Source[]; retrieval_warning?: string };
type Turn = { id: string; question: string; reply?: Reply; error?: string };
type Session = { id: string; title: string; draft: string; turns: Turn[]; busy?: boolean };
const initial: Session = { id: "initial", title: "Новый диалог", draft: "", turns: [] };
export function reducedMotion() { return document.documentElement.dataset.reduceMotion === "true" || matchMedia("(prefers-reduced-motion: reduce)").matches; }

export function useChatSessions() {
  const [sessions, setSessions] = useState<Session[]>([initial]);
  const [activeId, setActiveId] = useState(initial.id);
  const [storageKey, setStorageKey] = useState("");
  const [ready, setReady] = useState(false);
  const [lastClosed, setLastClosed] = useState<Session | null>(null);
  const [notice, setNotice] = useState("");
  const requests = useRef(new Map<string, AbortController>());
  const active = sessions.find(s => s.id === activeId) || sessions[0];
  useEffect(() => {
    let alive = true;
    // История разделена по аккаунтам; токен и документы целиком не сохраняем.
    void api<{ id: number }>("/api/auth/me").then(user => {
      if (!alive) return;
      const key = `psb-dialogs-v1:${user.id}`;
      try {
        const saved = JSON.parse(localStorage.getItem(key) || "null");
        if (saved?.sessions?.length && saved.sessions.every((s: Session) => typeof s.id === "string" && typeof s.title === "string" && typeof s.draft === "string" && Array.isArray(s.turns))) {
          const restored: Session[] = saved.sessions.map((s: Session) => ({ ...s, busy: false, turns: s.turns.map(t => !t.reply && !t.error ? { ...t, error: "Запрос прерван при закрытии страницы. Повторите вопрос." } : t) }));
          setSessions(restored); setActiveId(restored.some(s => s.id === saved.activeId) ? saved.activeId : restored[0].id);
        }
      } catch { setNotice("Не удалось восстановить историю в этом браузере."); }
      setStorageKey(key);
    }).catch(() => { if (alive) setNotice("История временно не сохраняется. Обновите страницу после восстановления соединения."); }).finally(() => { if (alive) setReady(true); });
    const pending = requests.current;
    return () => { alive = false; pending.forEach(c => c.abort()); pending.clear(); };
  }, []);
  useEffect(() => {
    if (!storageKey) return;
    const timer = setTimeout(() => {
      try { localStorage.setItem(storageKey, JSON.stringify({ sessions, activeId })); }
      catch { setNotice("Не хватает места для истории в браузере. Закройте ненужные диалоги."); }
    }, 250);
    return () => clearTimeout(timer);
  }, [sessions, activeId, storageKey]);
  function update(id: string, change: (s: Session) => Session) { setSessions(prev => prev.map(s => s.id === id ? change(s) : s)); }
  function create() {
    const id = crypto.randomUUID();
    setSessions(prev => [...prev, { ...initial, id }]); setActiveId(id);
  }
  function close(id: string) {
    requests.current.get(id)?.abort(); requests.current.delete(id);
    const closing = sessions.find(s => s.id === id);
    if (closing) setLastClosed({ ...closing, busy: false, turns: closing.turns.map(t => !t.reply && !t.error ? { ...t, error: "Запрос остановлен при закрытии диалога. Повторите вопрос." } : t) });
    const remaining = sessions.filter(s => s.id !== id);
    if (!remaining.length) { const next = { ...initial, id: crypto.randomUUID() }; setSessions([next]); setActiveId(next.id); }
    else { setSessions(remaining); if (id === activeId) setActiveId(remaining[Math.max(0, sessions.findIndex(s => s.id === id) - 1)].id); }
  }
  function move(id: string, target: string) {
    setSessions(prev => {
      const from = prev.findIndex(s => s.id === id), to = prev.findIndex(s => s.id === target);
      if (from < 0 || to < 0 || from === to) return prev;
      const next = [...prev]; next.splice(to, 0, next.splice(from, 1)[0]); return next;
    });
  }
  async function ask(value = active.draft) {
    const text = value.trim(), session = active;
    if (!ready || !text || requests.current.has(session.id)) return;
    const controller = new AbortController(), id = crypto.randomUUID();
    requests.current.set(session.id, controller);
    const history = session.turns.filter(t => t.reply).slice(-4).flatMap(t => [{ role: "user", text: t.question }, { role: "assistant", text: t.reply!.answer }]);
    update(session.id, s => ({ ...s, title: s.turns.length ? s.title : text.slice(0, 60), draft: "", busy: true, turns: [...s.turns, { id, question: text }] }));
    try {
      const reply = await api<Reply>("/api/knowledge/ask", { method: "POST", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(180000)]), body: JSON.stringify({ question: text, history }) });
      update(session.id, s => ({ ...s, turns: s.turns.map(t => t.id === id ? { ...t, reply } : t) }));
    } catch (e) {
      if (!controller.signal.aborted) update(session.id, s => ({ ...s, turns: s.turns.map(t => t.id === id ? { ...t, error: e instanceof Error ? e.message : "Не удалось получить ответ" } : t) }));
    } finally { requests.current.delete(session.id); update(session.id, s => ({ ...s, busy: false })); }
  }
  function restore() {
    if (!lastClosed) return;
    setSessions(prev => [...prev, lastClosed]); setActiveId(lastClosed.id); setLastClosed(null);
  }
  return { sessions, active, activeId, select: setActiveId, create, close, move, ask, notice, ready, lastClosed, restore,
    setDraft: (draft: string) => update(active.id, s => ({ ...s, draft })) };
}

export default function ChatSessions({ chat }: { chat: ReturnType<typeof useChatSessions> }) {
  const list = useRef<HTMLDivElement>(null);
  const positions = useRef(new Map<string, number>());
  const [dragging, setDragging] = useState<string | null>(null);
  useLayoutEffect(() => {
    const next = new Map<string, number>();
    list.current?.querySelectorAll<HTMLElement>("[data-session]").forEach(node => {
      const id = node.dataset.session!, left = node.offsetLeft, old = positions.current.get(id);
      if (old !== undefined && old !== left && !reducedMotion()) node.animate([{ transform: `translateX(${old - left}px)` }, { transform: "translateX(0)" }], { duration: 200, easing: "ease-out" });
      next.set(id, left);
    }); positions.current = next;
  }, [chat.sessions]);
  useEffect(() => { list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: reducedMotion() ? "auto" : "smooth" }); }, [chat.activeId]);
  return <div className="kb-session-bar"><div ref={list} className="kb-session-tabs" role="tablist" aria-label="Диалоги — Alt и стрелки меняют порядок">
    {chat.sessions.map((session, index) => <div key={session.id} data-session={session.id} className={`kb-session ${chat.activeId === session.id ? "active" : ""} ${dragging === session.id ? "dragging" : ""}`}
      draggable onDragStart={e => { setDragging(session.id); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", session.id); }} onDragEnd={() => setDragging(null)}
      onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }} onDrop={e => { e.preventDefault(); chat.move(e.dataTransfer.getData("text/plain"), session.id); setDragging(null); }}>
      <button role="tab" id={`tab-${session.id}`} aria-controls="chat-panel" aria-selected={session.id === chat.activeId} tabIndex={session.id === chat.activeId ? 0 : -1} title={session.title}
        onClick={() => chat.select(session.id)} onKeyDown={e => {
          if (e.key === "Delete") { e.preventDefault(); chat.close(session.id); return; }
          const target = e.key === "ArrowLeft" ? index - 1 : e.key === "ArrowRight" ? index + 1 : e.key === "Home" ? 0 : e.key === "End" ? chat.sessions.length - 1 : -1;
          if (target < 0 || target >= chat.sessions.length) return;
          e.preventDefault(); if (e.altKey) chat.move(session.id, chat.sessions[target].id); else { chat.select(chat.sessions[target].id); document.getElementById(`tab-${chat.sessions[target].id}`)?.focus(); }
        }}>{session.busy ? <span className="spinner"/> : <Icon name="doc" size={13}/>}<span>{session.title}</span></button>
      <button className="kb-session-close" aria-label={`Закрыть диалог: ${session.title}`} title="Закрыть диалог" onClick={() => chat.close(session.id)}><Icon name="close" size={12}/></button>
    </div>)}
  </div>{chat.lastClosed && <button className="icon-button" aria-label="Вернуть закрытый диалог" title="Вернуть закрытый диалог" onClick={chat.restore}><Icon name="clock" size={16}/></button>}<button className="icon-button" disabled={!chat.ready} aria-label="Новый диалог" title="Новый диалог" onClick={chat.create}><Icon name="plus" size={17}/></button></div>;
}
