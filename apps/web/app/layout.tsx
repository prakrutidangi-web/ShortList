import type { Metadata } from "next";
import { Nav } from "./nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shortlist",
  description: "Personalized ranking for new-grad job postings",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <Nav />
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
