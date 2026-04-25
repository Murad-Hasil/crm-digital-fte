import { ImageResponse } from "next/og";

export const runtime = "edge";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const TECH = [
  "Groq LLaMA 3.3",
  "FastAPI",
  "Apache Kafka",
  "PostgreSQL + pgvector",
  "Next.js 15",
  "Kubernetes",
];

const STATS = [
  { value: "3", label: "Channels" },
  { value: "5", label: "Agent Tools" },
  { value: "45", label: "Tests" },
  { value: "8", label: "DB Tables" },
];

export default function OGImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          background: "linear-gradient(135deg, #080812 0%, #12062a 45%, #060e24 100%)",
          padding: "56px 64px",
          position: "relative",
          fontFamily: "system-ui, -apple-system, sans-serif",
          overflow: "hidden",
        }}
      >
        {/* Violet glow — top right */}
        <div
          style={{
            position: "absolute",
            top: -120,
            right: -80,
            width: 480,
            height: 480,
            borderRadius: "50%",
            background:
              "radial-gradient(circle, rgba(139,92,246,0.35) 0%, transparent 68%)",
          }}
        />
        {/* Indigo glow — bottom left */}
        <div
          style={{
            position: "absolute",
            bottom: -160,
            left: -100,
            width: 560,
            height: 560,
            borderRadius: "50%",
            background:
              "radial-gradient(circle, rgba(79,70,229,0.25) 0%, transparent 68%)",
          }}
        />
        {/* Subtle grid lines */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }}
        />

        {/* ── Badges ── */}
        <div style={{ display: "flex", gap: "12px", marginBottom: "30px" }}>
          <div
            style={{
              background: "rgba(139,92,246,0.18)",
              border: "1px solid rgba(139,92,246,0.55)",
              borderRadius: "8px",
              padding: "7px 18px",
              color: "#c4b5fd",
              fontSize: "13px",
              fontWeight: 700,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              display: "flex",
              alignItems: "center",
            }}
          >
            HACKATHON 5
          </div>
          <div
            style={{
              background: "rgba(16,185,129,0.12)",
              border: "1px solid rgba(16,185,129,0.45)",
              borderRadius: "8px",
              padding: "7px 18px",
              color: "#6ee7b7",
              fontSize: "13px",
              fontWeight: 700,
              letterSpacing: "0.05em",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <span style={{ color: "#34d399", fontSize: "14px" }}>✓</span> PRODUCTION READY
          </div>
          <div
            style={{
              background: "rgba(251,191,36,0.1)",
              border: "1px solid rgba(251,191,36,0.35)",
              borderRadius: "8px",
              padding: "7px 18px",
              color: "#fcd34d",
              fontSize: "13px",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
            }}
          >
            🤖 AI FTE
          </div>
        </div>

        {/* ── Main title ── */}
        <div style={{ display: "flex", flexDirection: "column", marginBottom: "8px" }}>
          <div
            style={{
              fontSize: "68px",
              fontWeight: 800,
              lineHeight: 1.05,
              letterSpacing: "-0.025em",
              color: "#ffffff",
              display: "flex",
              flexWrap: "wrap",
            }}
          >
            CRM Digital&nbsp;
            <span
              style={{
                background: "linear-gradient(90deg, #a78bfa 0%, #818cf8 100%)",
                backgroundClip: "text",
                color: "transparent",
              }}
            >
              FTE Factory
            </span>
          </div>

          <div
            style={{
              fontSize: "26px",
              color: "#94a3b8",
              fontWeight: 400,
              marginTop: "10px",
            }}
          >
            AI-Powered 24/7 Customer Success Agent
          </div>

          <div
            style={{
              fontSize: "17px",
              color: "#475569",
              marginTop: "10px",
              lineHeight: 1.5,
            }}
          >
            3-channel intake (Gmail · WhatsApp · Web Form) — autonomous ticket creation,
            knowledge retrieval, escalation & response
          </div>
        </div>

        {/* ── Tech stack pills ── */}
        <div style={{ display: "flex", gap: "10px", marginTop: "28px", flexWrap: "wrap" }}>
          {TECH.map((t) => (
            <div
              key={t}
              style={{
                background: "rgba(255,255,255,0.055)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "8px",
                padding: "8px 16px",
                color: "#cbd5e1",
                fontSize: "14px",
                fontWeight: 500,
                display: "flex",
                alignItems: "center",
              }}
            >
              {t}
            </div>
          ))}
        </div>

        {/* ── Footer ── */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginTop: "auto",
            paddingTop: "28px",
            borderTop: "1px solid rgba(255,255,255,0.07)",
          }}
        >
          {/* Author */}
          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "50%",
                background: "linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "white",
                fontSize: "20px",
                fontWeight: 800,
                border: "2px solid rgba(139,92,246,0.5)",
              }}
            >
              M
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              <span style={{ color: "#f1f5f9", fontSize: "17px", fontWeight: 700 }}>
                Murad Hasil
              </span>
              <span style={{ color: "#64748b", fontSize: "13px" }}>
                AI Engineer · Portfolio Project
              </span>
            </div>
          </div>

          {/* Stats */}
          <div style={{ display: "flex", gap: "32px" }}>
            {STATS.map((s) => (
              <div
                key={s.label}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "2px",
                }}
              >
                <span
                  style={{
                    color: "#a78bfa",
                    fontSize: "26px",
                    fontWeight: 800,
                    lineHeight: 1,
                  }}
                >
                  {s.value}
                </span>
                <span style={{ color: "#64748b", fontSize: "12px", fontWeight: 500 }}>
                  {s.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    ),
    { width: 1200, height: 630 }
  );
}
