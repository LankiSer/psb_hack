import type { Metadata } from "next";
import "./globals.css";
import "./psb.css";

export const metadata: Metadata = {
  title: "ПСБ Банк Docs",
  description: "Документы, проекты и AI-помощник: работа с текстом и ответы по вашим материалам",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body className="antialiased">{children}</body>
    </html>
  );
}
