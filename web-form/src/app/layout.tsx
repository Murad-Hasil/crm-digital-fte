import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://web-form-rouge.vercel.app"),

  title: {
    default: "CRM Digital FTE Factory — AI Customer Success Agent | Murad Hasil",
    template: "%s | CRM Digital FTE Factory",
  },
  description:
    "Production-grade AI Digital FTE that autonomously handles 24/7 customer support across Gmail, WhatsApp & Web Form. Built with OpenAI Agents SDK (Groq LLaMA 3.3), FastAPI, Apache Kafka, PostgreSQL + pgvector, and Next.js 15.",

  keywords: [
    "AI Customer Success",
    "Digital FTE",
    "OpenAI Agents SDK",
    "Groq LLaMA",
    "FastAPI",
    "Apache Kafka",
    "pgvector",
    "Multi-channel AI",
    "CRM Automation",
    "AI Support Agent",
    "Hackathon Project",
    "Murad Hasil",
    "AI Engineer",
  ],

  authors: [{ name: "Murad Hasil", url: "https://web-form-rouge.vercel.app" }],
  creator: "Murad Hasil",
  publisher: "Murad Hasil",

  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large" },
  },

  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://web-form-rouge.vercel.app",
    siteName: "CRM Digital FTE Factory",
    title: "CRM Digital FTE Factory — AI Customer Success Agent",
    description:
      "24/7 AI agent handling customer support across Gmail, WhatsApp & Web Form. Groq LLaMA 3.3 · FastAPI · Kafka · pgvector · Kubernetes · 45 tests.",
  },

  twitter: {
    card: "summary_large_image",
    title: "CRM Digital FTE Factory — AI Customer Success Agent",
    description:
      "24/7 AI FTE across Gmail, WhatsApp & Web Form. OpenAI Agents SDK · Groq · FastAPI · Kafka · pgvector. By Murad Hasil.",
    creator: "@muradhasil",
  },

  alternates: {
    canonical: "https://web-form-rouge.vercel.app",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
