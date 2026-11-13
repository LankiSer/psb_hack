"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/shared/api/client";
// Корневой адрес только перенаправляет в приложение.
export default function EntryPage() {
  const router = useRouter();
  useEffect(() => { router.replace(getToken() ? "/knowledge" : "/login"); }, [router]);
  return <div className="psb-entry" role="status">Открываем ПСБ Банк Docs…</div>;
}
