import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shortlist",
  description: "Personalized ranking for new-grad job postings",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 antialiased">
        <header className="border-b bg-white">
          <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
            <Link href="/" className="text-lg font-semibold">
              Shortlist
            </Link>
            <Link href="/" className="text-sm text-gray-600 hover:text-gray-900">
              Feed
            </Link>
            <Link href="/profile" className="text-sm text-gray-600 hover:text-gray-900">
              Profile
            </Link>
          </nav>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
