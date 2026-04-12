import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CloudScale AI Support",
  description: "AI-powered 24/7 customer support",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
