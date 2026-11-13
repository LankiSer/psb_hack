"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, getToken, setToken } from "@/shared/api/client";
import Brand from "@/shared/ui/Brand";
import Icon from "@/shared/ui/Icon";
import AccountDialog from "@/shared/ui/AccountDialog";

type Doc = { id: string; title: string; category: string; text?: string; line_count: number };
type Source = { id: string; document_id: string; title: string; quote: string; line_start: number; line_end: number };
type Reply = { answer: string; status: string; sources: Source[] };
type Turn = { id: number; question: string; reply?: Reply; error?: string };
const examples = ["Какая арендная плата по договору с Северным Складом?", "Как изменился порядок согласования договоров в 2025 году?", "Какой срок оплаты по договору П-17/2024 после допсоглашения?"];

export default function KnowledgePage() {
  const router = useRouter();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [selected, setSelected] = useState<Doc | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [query, setQuery] = useState("");
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLElement>(null);
  const sequence = useRef(0);
  const loadSequence = useRef(0);
  const messagesEnd = useRef<HTMLDivElement>(null);
  const evidenceRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => { document.documentElement.dataset.reduceMotion = localStorage.getItem("ai-docs-reduce-motion") || "false"; }, []);
  useEffect(() => {
    if (!menuOpen) return;
    drawer.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setMenuOpen(false); menuButton.current?.focus(); }
      if (event.key === "Tab") {
        const controls = drawer.current?.querySelectorAll<HTMLElement>('button, a, input');
        if (!controls?.length) return;
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);
  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    api<Doc[]>("/api/knowledge/documents").then(setDocs).catch(e => {
      if (e instanceof ApiError && e.status === 401) router.replace("/login");
      else setError(e.message);
    }).finally(() => setLoading(false));
  }, [router]);
  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns, busy]);
  useEffect(() => { evidenceRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [selected, source]);

  async function openDocument(id: string, evidence: Source | null = null) {
    const request = ++loadSequence.current;
    setError("");
    try {
      const doc = await api<Doc>(`/api/knowledge/documents/${id}`);
      if (request === loadSequence.current) { setSelected(doc); setSource(evidence); setMenuOpen(false); }
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось открыть документ"); }
  }
  async function ask(value = question) {
    if (!value.trim() || busy) return;
    const id = ++sequence.current;
    const history = turns.filter(t => t.reply).slice(-4).flatMap(t => [{ role: "user", text: t.question }, { role: "assistant", text: t.reply!.answer }]);
    setTurns(prev => [...prev, { id, question: value.trim() }]); setQuestion(""); setBusy(true);
    try {
      const reply = await api<Reply>("/api/knowledge/ask", { method: "POST", body: JSON.stringify({ question: value.trim(), history }) });
      setTurns(prev => prev.map(t => t.id === id ? { ...t, reply } : t));
    } catch (e) { setTurns(prev => prev.map(t => t.id === id ? { ...t, error: e instanceof Error ? e.message : "Не удалось получить ответ" } : t)); }
    finally { setBusy(false); }
  }
  function answer(reply: Reply) {
    return reply.answer.split(/(\[[^\]]+\])/g).map((part, index) => {
      const citation = reply.sources.find(s => `[${s.id}]` === part);
      return citation ? <button key={index} className="kb-citation" title={citation.title} onClick={() => void openDocument(citation.document_id, citation)}>{reply.sources.indexOf(citation) + 1}</button> : part;
    });
  }
  return <main className="kb-app">
    <header className="kb-header"><button ref={menuButton} className="icon-button" aria-label="Открыть меню" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}><Icon name="menu"/></button><Link href="/knowledge"><Brand/></Link><nav><Link className="active" href="/knowledge">База знаний</Link></nav><span className="kb-case-label">Юридический ассистент</span></header>
    {menuOpen && <div className="kb-menu-overlay"><button className="kb-menu-backdrop" aria-label="Закрыть меню" onClick={() => { setMenuOpen(false); menuButton.current?.focus(); }}/><aside className="kb-menu" ref={drawer} role="dialog" aria-modal="true" aria-label="Меню рабочего пространства"><header><Brand/><button className="icon-button" aria-label="Закрыть навигацию" onClick={() => { setMenuOpen(false); menuButton.current?.focus(); }}><Icon name="close"/></button></header><button className="button primary kb-new-chat" disabled={busy} onClick={() => { setTurns([]); setMenuOpen(false); }}><Icon name="plus" size={18}/>Новый диалог</button><Link className="nav-item active" href="/knowledge" onClick={() => setMenuOpen(false)}><Icon name="doc"/>База знаний</Link><div className="kb-mobile-docs"><h3>Документы базы</h3>{docs.map(d => <button key={d.id} onClick={() => void openDocument(d.id)}>{d.title}</button>)}</div><footer><button className="nav-item" onClick={() => { setMenuOpen(false); setAccountOpen(true); }}><Icon name="settings"/>Настройки аккаунта</button><button className="nav-item" onClick={() => { setToken(null); router.replace("/login"); }}><Icon name="exit"/>Выйти</button></footer></aside></div>}
    {accountOpen && <AccountDialog onClose={() => { setAccountOpen(false); menuButton.current?.focus(); }}/>}
    <div className="kb-layout">
      <aside className="kb-library"><h2>Источники <span>{docs.length}</span></h2><label className="kb-search"><Icon name="search" size={16}/><input aria-label="Найти документ" placeholder="Найти документ" value={query} onChange={e => setQuery(e.target.value)}/></label>
        {loading && <p role="status">Загружаем базу…</p>}
        {["Документы компании", "Законы"].map(category => <section key={category}><h3>{category}</h3>{docs.filter(d => d.category === category && d.title.toLowerCase().includes(query.toLowerCase())).map(d => <button key={d.id} className={selected?.id === d.id ? "active" : ""} onClick={() => void openDocument(d.id)}><Icon name="doc" size={16}/><span>{d.title}</span></button>)}</section>)}
        {!loading && !docs.some(d => d.title.toLowerCase().includes(query.toLowerCase())) && <p>Документы не найдены</p>}
        <p className="kb-library-note">Учебная база кейса. Законы представлены только в предоставленной редакции.</p>
      </aside>
      <section className={`kb-reader ${selected ? "has-document" : ""}`} aria-label="Просмотр источника">
        {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")}>Закрыть</button></div>}
        {selected ? <><header><div><small>{selected.category}</small><h1>{selected.title}</h1></div><button className="icon-button" aria-label="Закрыть документ" onClick={() => { setSelected(null); setSource(null); }}><Icon name="close"/></button></header><article className="kb-paper">{selected.text?.split("\n").map((line, i) => <p key={`${selected.id}-${i}`} ref={i + 1 === source?.line_start ? evidenceRef : undefined} className={source && i + 1 >= source.line_start && i + 1 <= source.line_end ? "kb-highlight" : ""}><span className="kb-line">{i + 1}</span>{line || "\u00a0"}</p>)}</article></> : <div className="kb-welcome"><span className="kb-welcome-icon"><Icon name="doc" size={32}/></span><span className="landing-eyebrow">ОТ ВОПРОСА К ОСНОВАНИЮ</span><h1>Правовой вывод.<br/>Проверяемый источник.</h1><p>Спросите о договоре, норме или регламенте. Здесь откроется документ с положениями, на которых основан ответ.</p><div className="kb-facts"><span><strong>21</strong>документ базы</span><span><strong>2</strong>редакции регламента</span><span><strong>0</strong>внешних источников</span></div><p className="kb-muted">Откройте документ слева или задайте вопрос в чате.</p></div>}
      </section>
      <section className="kb-chat" aria-label="Чат по базе знаний"><header><Icon name="spark" size={18}/><div><strong>Юридический помощник</strong><small>Ответы по базе кейса</small></div><button className="icon-button" disabled={busy || !turns.length} aria-label="Новый диалог" title="Новый диалог" onClick={() => setTurns([])}><Icon name="plus"/></button></header><div className="kb-messages" aria-live="polite">
        {!turns.length && <div className="kb-starters"><h2>Что нужно проверить?</h2><p>Укажите договор, дату события и вопрос — это поможет выбрать нужную редакцию.</p>{examples.map(q => <button key={q} onClick={() => void ask(q)}>{q}<span>↗</span></button>)}</div>}
        {turns.map(t => <div key={t.id} className="kb-turn"><div className="kb-user">{t.question}</div>{t.reply && <div className="kb-answer"><span className="kb-status">{({ answer: "Ответ с источниками", insufficient: "Недостаточно данных", clarification: "Нужно уточнение", out_of_scope: "Вне базы знаний" })[t.reply.status]}</span><p>{answer(t.reply)}</p>{t.reply.sources.length > 0 && <details><summary>Подтверждающие положения · {t.reply.sources.length}</summary>{t.reply.sources.map((s, i) => <button key={`${s.id}-${i}`} onClick={() => void openDocument(s.document_id, s)}><strong>{i+1}. {s.title}</strong><blockquote>{s.quote}</blockquote><small>Открыть в документе ↗</small></button>)}</details>}</div>}{t.error && <div role="alert" className="kb-error">{t.error}<button disabled={busy} onClick={() => void ask(t.question)}>Повторить</button></div>}</div>)}
        {busy && <div className="kb-progress" role="status"><span className="spinner"/>Ищу положения и проверяю ссылки…</div>}<div ref={messagesEnd}/>
      </div><form className="kb-composer" onSubmit={e => { e.preventDefault(); void ask(); }}><textarea aria-label="Вопрос по базе знаний" placeholder="Спросите по документам…" value={question} maxLength={4000} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void ask(); } }}/><div><small>Только предоставленные источники</small><button className="button primary" disabled={busy || !question.trim()} aria-label="Отправить вопрос">↑</button></div></form></section>
    </div>
  </main>;
}
