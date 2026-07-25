import { ImageResponse } from "next/og";
import type { NextRequest } from "next/server";

export const runtime = "edge";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const home = params.get("home") ?? "Home";
  const away = params.get("away") ?? "Away";
  const score = params.get("score") ?? "vs";
  const league = params.get("league") ?? "";
  const homeColor = params.get("homeColor") ?? "#22c55e";
  const awayColor = params.get("awayColor") ?? "#38bdf8";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          background: "linear-gradient(135deg, #07131f 0%, #020617 100%)",
          color: "#f8fafc",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18, fontSize: 30, color: "#a3e635", fontWeight: 700, letterSpacing: 4 }}>
          PLAYBACK90 · MATCH ANALYSIS
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 44, marginTop: 40 }}>
          <div style={{ display: "flex", fontSize: 64, fontWeight: 800, color: homeColor }}>{home}</div>
          <div
            style={{
              display: "flex",
              fontSize: 72,
              fontWeight: 900,
              padding: "8px 36px",
              borderRadius: 20,
              background: "rgba(163,230,53,0.12)",
              border: "2px solid rgba(163,230,53,0.4)",
            }}
          >
            {score}
          </div>
          <div style={{ display: "flex", fontSize: 64, fontWeight: 800, color: awayColor }}>{away}</div>
        </div>
        {league ? (
          <div style={{ display: "flex", marginTop: 36, fontSize: 28, color: "#9eb0c4", textTransform: "capitalize" }}>
            {league.replace(/-/g, " ")}
          </div>
        ) : null}
        <div style={{ display: "flex", marginTop: 44, fontSize: 22, color: "#64748b" }}>
          xG · pass networks · duels · set pieces · AI insights
        </div>
      </div>
    ),
    { width: 1200, height: 630 }
  );
}
