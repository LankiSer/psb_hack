"use client";
import { useEffect, useState } from "react";

// Оставляем панель в DOM на время её закрытия.
export default function usePresence(open: boolean) {
  const [mounted, setMounted] = useState(open);
  useEffect(() => {
    if (open) { setMounted(true); return; }
    const timer = setTimeout(() => setMounted(false), 200);
    return () => clearTimeout(timer);
  }, [open]);
  return open || mounted;
}
