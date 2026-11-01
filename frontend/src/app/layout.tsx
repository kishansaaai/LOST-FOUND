import type { Metadata } from "next";
import { Suspense } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Navbar } from "@/components/navbar";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Lost & Found", template: "%s · Lost & Found" },
  description: "Report lost and found items. Smart text-and-photo matching reunites people with their belongings.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="flex min-h-full flex-col">
        <Providers>
          <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2">Skip to content</a>
          <Suspense fallback={<div className="h-16 border-b" />}><Navbar /></Suspense>
          <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-5 py-10 sm:px-8 sm:py-14"><Suspense>{children}</Suspense></main>
          <footer className="border-t"><div className="mx-auto flex max-w-6xl flex-col gap-1 px-5 py-8 text-xs text-muted-foreground sm:flex-row sm:justify-between sm:px-8"><span className="eyebrow">Lost &amp; Found</span><span>Postgres, pgvector, Qdrant, MongoDB, Redis</span></div></footer>
        </Providers>
      </body>
    </html>
  );
}
