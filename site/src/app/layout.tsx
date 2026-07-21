import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Pulse",
  description: "Automated AI news, aggregated and summarized.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <header className="border-b-2 border-blue-600 bg-white p-4 flex gap-4 items-center shadow-sm">
          <Link href="/" className="font-bold text-lg text-blue-700">
            AI Pulse
          </Link>
          <Link href="/" className="text-sm text-slate-600 hover:text-blue-600">
            Essential
          </Link>
          <Link href="/latest" className="text-sm text-slate-600 hover:text-blue-600">
            Latest
          </Link>
        </header>
        <main className="max-w-3xl mx-auto p-4">{children}</main>
      </body>
    </html>
  );
}
