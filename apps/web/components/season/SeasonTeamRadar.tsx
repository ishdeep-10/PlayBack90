"use client";

import { useMemo, useState } from "react";

import type { SeasonTeamMetrics } from "../../lib/api";
import { LEAGUE_PRESENTATION } from "../../lib/leagues";
import { Plot } from "../../lib/plotly";
import { CHART_FONT_FAMILY } from "../../lib/theme";
import { DownloadPngButton } from "../DownloadPngButton";
import { groupMetrics } from "./MetricSelect";
import { renderRadarPng } from "./radarExport";
import { fmtNum, useChartFrame } from "./useSeasonChart";

type Props = { data: SeasonTeamMetrics };

const COLORS = ["#a3e635", "#38bdf8", "#f472b6", "#f59e0b"];
const PRESETS: Record<string, string[]> = {
  Balanced: ["xg_for", "xg_against", "xg_per_shot", "shots", "average_ppda", "avg_tempo", "continuity_for", "duel_win_rate", "crosses", "directness_index"],
  Attack: ["xg_for", "xg_per_shot", "shots", "xg_open_play", "xg_set_piece", "crosses", "xg_from_crosses", "continuity_for"],
  Defence: ["xg_against", "xg_per_shot_conceded", "shots_conceded", "average_ppda", "duel_win_rate", "sca_conceded_per_match", "off_provoked", "blocked_pct"],
  Style: ["avg_tempo", "directness_index", "long_ball_ratio", "passes_per_possession_final3", "continuity_for", "average_ppda", "avg_action_width", "buildup_completion_pct"],
};
const plotConfig = { responsive: true, displayModeBar: false };

export function SeasonTeamRadar({ data }: Props) {
  const { themeColors, width, setHost, compact } = useChartFrame();
  const byKey = useMemo(() => Object.fromEntries(data.metrics.map((m) => [m.key, m])), [data.metrics]);
  const valid = (keys: string[]) => keys.filter((k) => k in byKey);
  const teams = useMemo(() => data.teams.map((t) => t.team).sort((a, b) => a.localeCompare(b)), [data.teams]);
  const bestAttack = useMemo(
    () => [...data.teams].sort((a, b) => Number(b.xg_for ?? 0) - Number(a.xg_for ?? 0)).map((t) => t.team),
    [data.teams],
  );

  const [selected, setSelected] = useState<string[]>([bestAttack[0] ?? teams[0], bestAttack[1] ?? teams[1]].filter(Boolean));
  const [metricKeys, setMetricKeys] = useState<string[]>(valid(PRESETS.Balanced));

  const setTeam = (i: number, name: string) =>
    setSelected((prev) => {
      const next = [...prev];
      if (name) next[i] = name;
      else next.splice(i, 1);
      return next.filter(Boolean);
    });
  const toggleMetric = (key: string) =>
    setMetricKeys((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  // Percentile of each team among the league for each metric: 100 = best (flipped where lower is better).
  const percentile = useMemo(() => {
    const out: Record<string, Record<string, number>> = {};
    for (const m of data.metrics) {
      const vals = data.teams.map((t) => ({ team: t.team, v: t[m.key] })).filter((r): r is { team: string; v: number } => typeof r.v === "number");
      for (const r of vals) {
        const below = vals.filter((o) => (m.higher_is_better ? o.v < r.v : o.v > r.v)).length;
        const equal = vals.filter((o) => o.v === r.v).length;
        (out[r.team] ??= {})[m.key] = ((below + (equal - 1) / 2) / Math.max(vals.length - 1, 1)) * 100;
      }
    }
    return out;
  }, [data]);

  const keys = valid(metricKeys);
  const figure = useMemo(() => {
    if (keys.length < 3 || !selected.length) return null;
    const theta = keys.map((k) => byKey[k].label.replace(/ \(.*\)/, ""));
    const closed = (a: unknown[]) => [...a, a[0]];
    const traces = selected.map((team, i) => {
      const row = data.teams.find((t) => t.team === team);
      const r = keys.map((k) => percentile[team]?.[k] ?? 0);
      return {
        type: "scatterpolar",
        name: team,
        r: closed(r),
        theta: closed(theta),
        fill: "toself",
        fillcolor: `${COLORS[i]}33`,
        line: { color: COLORS[i], width: 2.5 },
        hovertext: closed(keys.map((k, j) => `<b>${team}</b><br>${byKey[k].label}: ${typeof row?.[k] === "number" ? fmtNum(row[k] as number) : "-"}<br>Percentile: ${r[j].toFixed(0)}`)),
        hoverinfo: "text",
      };
    });
    return {
      data: traces,
      layout: {
        width,
        height: compact ? 440 : 560,
        margin: { l: compact ? 50 : 90, r: compact ? 50 : 90, t: 30, b: 30 },
        paper_bgcolor: "rgba(0,0,0,0)",
        font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 10 : 12 },
        legend: { orientation: "h", y: 1.1, x: 0.5, xanchor: "center", font: { color: themeColors.text, family: CHART_FONT_FAMILY } },
        polar: {
          bgcolor: themeColors.surface,
          radialaxis: { range: [0, 100], tickvals: [25, 50, 75], gridcolor: themeColors.pitchLine, tickfont: { color: themeColors.muted, size: 9 }, linecolor: themeColors.pitchLine },
          angularaxis: { gridcolor: themeColors.pitchLine, tickfont: { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 9 : 11 } },
        },
      },
    };
  }, [keys, selected, percentile, data.teams, byKey, themeColors, width, compact]);

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <h2>Team profile vs the league</h2>
          <p className="muted">
            Percentile rank of up to four teams on each metric (100 = best in the league, 50 = league middle; metrics where
            lower is better are flipped).
          </p>
        </div>
        <DownloadPngButton
          filename={`${data.league}-team-profile`}
          title={`${data.league_name}: ${selected.join(" vs ")}`}
          filters={() => [...selected, `${keys.length} metrics`, "League percentile"]}
          renderImage={() => {
            const leagueInfo = LEAGUE_PRESENTATION[data.league];
            return renderRadarPng({
              title: selected.join(" vs "),
              subtitle: ["League percentile", `${keys.length} metrics`, `${data.league_name} ${data.season.replace("_", "/")}`].join("  |  "),
              leagueLogo: leagueInfo?.logo,
              axes: keys.map((k) => byKey[k].label.replace(/ \(.*\)/, "")),
              series: selected.map((team, i) => ({ name: team, color: COLORS[i], values: keys.map((k) => percentile[team]?.[k] ?? 0) })),
            });
          }}
        />
      </div>

      <div className="season-scatter-controls">
        {[0, 1, 2, 3].map((i) => (
          <label key={i}>
            <span>Team {i + 1}</span>
            <select className="select" value={selected[i] ?? ""} onChange={(e) => setTeam(i, e.target.value)}>
              <option value="">{i < 2 ? "Choose a team" : "None"}</option>
              {teams.map((t) => (
                <option key={t} value={t} disabled={selected.includes(t) && selected[i] !== t}>{t}</option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <div className="season-chip-row" role="group" aria-label="Metric set">
        {Object.entries(PRESETS).map(([name, list]) => (
          <button key={name} type="button" className="season-chip is-on" style={{ "--chip": "var(--accent)" } as React.CSSProperties} onClick={() => setMetricKeys(valid(list))}>
            {name}
          </button>
        ))}
        <span className="muted season-count">{keys.length} metrics</span>
      </div>
      {groupMetrics(data.metrics).map(([category, list]) => (
        <div key={category} className="season-chip-row" role="group" aria-label={category}>
          <span className="muted season-filter-label">{category}</span>
          {list.map((m) => (
            <button
              key={m.key}
              type="button"
              className={`season-chip${keys.includes(m.key) ? " is-on" : ""}`}
              style={{ "--chip": "var(--accent-2, var(--accent))" } as React.CSSProperties}
              onClick={() => toggleMetric(m.key)}
              aria-pressed={keys.includes(m.key)}
            >
              {m.label.replace(/ \(.*\)/, "")}
            </button>
          ))}
        </div>
      ))}

      <div ref={setHost} className="plotly-chart-shell season-scatter-shell">
        {figure ? (
          <Plot data={figure.data} layout={figure.layout} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: compact ? 440 : 560 }} />
        ) : (
          <p className="muted">Choose at least one team and three metrics.</p>
        )}
      </div>
    </section>
  );
}
