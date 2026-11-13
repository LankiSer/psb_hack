"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, API_URL, getToken } from "@/shared/api/client";
import Icon from "@/shared/ui/Icon";

export type Upload = { id: string; filename: string; size: number; status: string; progress: number; kind: string; document_id: string; error: string; chunk_count: number };
type Transfer = { id: string; filename: string; progress: number; error?: string };
const labels: Record<string,string> = { queued: "В очереди", parsing: "Распознаём текст", embedding: "Добавляем в поиск", ready: "Готов к поиску", error: "Нужна проверка" };
export function useKnowledgeUploads(onChanged: () => void) {
  const [items, setItems] = useState<Upload[]>([]);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sending, setSending] = useState(false);
  const [acting, setActing] = useState<string | null>(null);
  const readyKey = useRef("");
  const sendingRef = useRef(false);
  const refresh = useCallback(async () => {
    if (!getToken()) { setLoading(false); return; }
    try {
      const rows = await api<Upload[]>("/api/knowledge/uploads");
      setItems(rows); setError("");
      const key = rows.filter(r => r.status === "ready").map(r => r.id).sort().join(",");
      if (key !== readyKey.current) { readyKey.current = key; onChanged(); }
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось обновить список"); }
    finally { setLoading(false); }
  }, [onChanged]);
  useEffect(() => { void refresh(); }, [refresh]);
  const active = items.filter(r => !["ready", "error"].includes(r.status)).length;
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void refresh(), 2500);
    return () => clearInterval(timer);
  }, [active, refresh]);

  async function add(files: File[]) {
    if (sendingRef.current || !files.length) return;
    sendingRef.current = true; setSending(true); setNotice(""); setError("");
    const batch = files.slice(0, 10).map(file => ({ file, id: crypto.randomUUID() }));
    if (files.length > 10) setNotice("За один раз можно добавить 10 файлов. Остальные загрузите следующей партией.");
    setTransfers(prev => [...prev, ...batch.map(({file,id}) => ({ id, filename: file.name, progress: 0 }))]);
    try {
      for (const {file,id} of batch) {
        try {
          if (!/\.(pdf|docx|txt|md)$/i.test(file.name)) throw new Error("Поддерживаются PDF, DOCX, TXT и MD.");
          if (file.size > 25 * 1024 * 1024) throw new Error("Файл больше 25 МБ.");
          if (!file.size) throw new Error("Файл пуст.");
          const result = await new Promise<Upload & {duplicate?: boolean}>((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", `${API_URL}/api/knowledge/uploads`); xhr.timeout = 120000;
            const token = getToken(); if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
            xhr.upload.onprogress = event => { if (event.lengthComputable) setTransfers(prev => prev.map(t => t.id === id ? {...t, progress: Math.round(100 * event.loaded / event.total)} : t)); };
            xhr.onerror = () => reject(new Error("Нет связи с сервером. Проверьте подключение и выберите файл снова."));
            xhr.ontimeout = () => reject(new Error("Сервер не ответил вовремя. Выберите файл снова — дубликат не создастся."));
            xhr.onload = () => {
              try { const data = JSON.parse(xhr.responseText); if (xhr.status >= 200 && xhr.status < 300) resolve(data); else reject(new Error(typeof data.detail === "string" ? data.detail : "Не удалось загрузить файл")); }
              catch { reject(new Error("Не удалось прочитать ответ сервера")); }
            };
            const form = new FormData(); form.append("file", file); xhr.send(form);
          });
          setItems(prev => [result, ...prev.filter(r => r.id !== result.id)]);
          setTransfers(prev => prev.filter(t => t.id !== id));
          if (result.duplicate) setNotice(`«${file.name}» уже добавлен. Вторую копию не создаём.`);
          await refresh();
        } catch (e) { setTransfers(prev => prev.map(t => t.id === id ? {...t, error: e instanceof Error ? e.message : "Ошибка загрузки"} : t)); }
      }
    } finally { sendingRef.current = false; setSending(false); }
  }
  async function action(row: Upload, kind: "retry" | "delete") {
    setActing(row.id); setError("");
    try {
      await api(`/api/knowledge/uploads/${row.id}${kind === "retry" ? "/retry" : ""}`, {method: kind === "retry" ? "POST" : "DELETE"});
      await refresh(); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось выполнить действие"); }
    finally { setActing(null); }
  }
  return { items, transfers, loading, error, notice, sending, acting, active, refresh, add, action, dismiss: (id: string) => setTransfers(prev => prev.filter(t => t.id !== id)) };
}

export default function KnowledgeUploads({ state, onClose, onOpen }: {state: ReturnType<typeof useKnowledgeUploads>; onClose: () => void; onOpen: (id: string) => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  return <dialog ref={dialog} className="kb-upload-dialog" onCancel={e => { e.preventDefault(); onClose(); }} onClick={e => { if (e.target === e.currentTarget) onClose(); }} aria-labelledby="upload-title">
    <div className="kb-upload-content">
      <header><div><span className="kb-status">ВАША БАЗА ЗНАНИЙ</span><h2 id="upload-title">Добавить документы</h2><p>Загрузите файл — помощник сможет находить в нём ответы и ссылаться на нужные положения.</p></div><button className="icon-button" aria-label="Закрыть загрузку" onClick={onClose}><Icon name="close"/></button></header>
      <input ref={input} type="file" multiple accept=".pdf,.docx,.txt,.md" className="sr-only" tabIndex={-1} onChange={e => { void state.add(Array.from(e.target.files || [])); e.target.value = ""; }}/>
      <button className={`kb-dropzone ${dragging ? "dragging" : ""}`} disabled={state.sending} onClick={() => input.current?.click()} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); if (!state.sending) void state.add(Array.from(e.dataTransfer.files)); }}>
        <span className="kb-drop-icon"><Icon name="upload" size={24}/></span><strong>{state.sending ? "Загружаем файлы…" : "Перетащите файлы сюда"}</strong><span>{state.sending ? "Можно закрыть это окно — обработка продолжится" : "или нажмите, чтобы выбрать на компьютере"}</span><small>PDF, DOCX, TXT, MD · до 25 МБ · до 10 файлов за раз</small>
      </button>
      <div className="kb-upload-steps"><span><b>1</b>Загрузка</span><span><b>2</b>Распознавание</span><span><b>3</b>Готов к поиску</span></div>
      {state.error && <div className="kb-error" role="alert">{state.error}<button onClick={() => void state.refresh()}>Обновить список</button></div>}
      {state.notice && <p className="kb-upload-notice" role="status">{state.notice}</p>}
      <div className="kb-upload-list" aria-label="Состояние документов">
        {state.loading && <div className="kb-skeleton" role="status" aria-label="Загрузка списка документов"/>}
        {state.transfers.map(t => <div key={t.id} className="kb-upload-row"><Icon name="doc"/><div className="kb-upload-info"><strong>{t.filename}</strong><small role="status">{t.error || (t.progress === 100 ? "Сохраняем файл…" : `Загрузка · ${t.progress}%`)}</small>{!t.error && <progress max={100} value={t.progress} aria-label={`Загрузка ${t.filename}`}/>}</div>{t.error ? <button className="icon-button" aria-label={`Убрать ошибку ${t.filename}`} onClick={() => state.dismiss(t.id)}><Icon name="close" size={16}/></button> : <span className="spinner"/>}</div>)}
        {state.items.map(row => <div key={row.id} className={`kb-upload-row ${row.status}`}><span className="kb-file-mark"><Icon name={row.status === "ready" ? "check" : "doc"}/></span><div className="kb-upload-info"><strong title={row.filename}>{row.filename}</strong><small>{row.kind} · {(row.size / 1024).toFixed(0)} КБ</small><span className="kb-upload-state" role="status">{labels[row.status] || row.status}{row.status === "ready" ? ` · ${row.chunk_count} фрагм.` : ""}</span>{!["ready", "error"].includes(row.status) && <progress value={row.progress} max={100} aria-label={`Обработка ${row.filename}`}/>} {row.error && <p className="kb-upload-failure">{row.error}</p>}
          {confirmDelete === row.id && <div className="kb-delete-confirm"><span>Удалить файл и исключить его из ответов?</span><button disabled={state.acting === row.id} onClick={() => { void state.action(row, "delete"); setConfirmDelete(null); }}>Удалить</button><button onClick={() => setConfirmDelete(null)}>Отмена</button></div>}
        </div><div className="kb-upload-actions">{row.status === "ready" && <button className="kb-text-button" onClick={() => { onOpen(row.document_id); onClose(); }}>Открыть</button>}{row.status === "error" && <button className="kb-text-button" disabled={state.acting === row.id} onClick={() => void state.action(row,"retry")}>Повторить</button>}{!["ready","error"].includes(row.status) && <span className="spinner"/>}<button className="icon-button" disabled={state.acting === row.id} aria-label={`Удалить ${row.filename}`} onClick={() => setConfirmDelete(row.id)}><Icon name="trash" size={16}/></button></div></div>)}
        {!state.loading && !state.items.length && !state.transfers.length && <p className="kb-upload-empty">Здесь появятся загруженные файлы и ход их обработки.</p>}
      </div>
      <footer><Icon name="check" size={14}/><span>Файлы доступны только вашему аккаунту. PDF-сканы без текстового слоя сначала нужно распознать.</span><button className="button" onClick={onClose}>Готово</button></footer>
    </div>
  </dialog>;
}
