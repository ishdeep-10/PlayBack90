import { notFound } from "next/navigation";

import { getAdminMetrics, type AdminMetrics } from "../../lib/api";
import { getServerAuthToken } from "../../lib/serverAuth";

export const metadata = { title: "Admin | PlayBack90", robots: { index: false, follow: false } };
export const dynamic = "force-dynamic";

const usd = (n: number) => `$${n.toFixed(2)}`;

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card stack" style={{ gap: 4 }}>
      <span className="muted">{label}</span>
      <strong style={{ fontSize: 28 }}>{value}</strong>
      {sub ? <span className="muted">{sub}</span> : null}
    </div>
  );
}

function Failed({ name, error }: { name: string; error: string }) {
  return <Tile label={name} value="unavailable" sub={error} />;
}

export default async function AdminPage() {
  let m: AdminMetrics;
  try {
    m = await getAdminMetrics(await getServerAuthToken());
  } catch {
    notFound();
  }

  const ageHours = (Date.now() - new Date(m.generated_at).getTime()) / 3_600_000;
  const aws = "error" in m.aws ? null : m.aws;
  const r2 = "error" in m.r2 ? null : m.r2;
  const users = "error" in m.users ? null : m.users;
  const site = "error" in m.site ? null : m.site;
  const bq = "error" in m.bigquery ? null : m.bigquery;
  const thisMonth = aws?.months.at(-1);
  // Storage growth: today against the oldest snapshot that is at least a week old.
  const hist = (m.history ?? []).filter((h) => h.r2_gb !== undefined);
  const latest = hist.at(-1);
  const base = [...hist].reverse().find((h) => latest && (new Date(latest.date).getTime() - new Date(h.date).getTime()) / 86_400_000 >= 7);
  const growth = latest && base ? { gb: (latest.r2_gb ?? 0) - (base.r2_gb ?? 0), objects: (latest.objects ?? 0) - (base.objects ?? 0), since: base.date } : null;
  const vendor = bq?.competitions && !("error" in bq.competitions) ? bq.competitions : null;

  return (
    <main className="stack" style={{ marginTop: 24 }}>
      <section className="card stack">
        <h1>Owner dashboard</h1>
        <p className="muted">
          Snapshot from {new Date(m.generated_at).toLocaleString()}
          {ageHours > 36 ? ` (${Math.round(ageHours)} hours old: run scripts/collect_metrics.py and upload it)` : ""}
        </p>
      </section>

      <h2>Users</h2>
      <section className="grid grid-3">
        {users ? (
          <>
            <Tile label="Accounts" value={String(users.total_users)} />
            <Tile label="Signed in, last 30 days" value={String(users.signed_in_last_30d)} />
            <Tile
              label="Sign-ups, latest week"
              value={String(users.signups_per_week.at(-1)?.signups ?? 0)}
              sub={users.signups_per_week.at(-1)?.week}
            />
          </>
        ) : (
          <Failed name="Users" error={"error" in m.users ? m.users.error : ""} />
        )}
      </section>

      <h2>Costs</h2>
      <section className="grid grid-3">
        <Tile label="Data (Dribble Pro)" value={usd(m.fixed_costs_usd_month.dribble_pro)} sub="per month, fixed" />
        {aws && thisMonth ? (
          <>
            <Tile label={`AWS ${thisMonth.month}, gross`} value={usd(thisMonth.gross_usd)} sub={`net ${usd(thisMonth.net_usd)} after credits`} />
            <Tile label="AWS credits used so far" value={usd(aws.credits_used_total_usd)} sub="balance and expiry: console, Billing > Credits" />
          </>
        ) : (
          <Failed name="AWS" error={"error" in m.aws ? m.aws.error : ""} />
        )}
      </section>
      {aws ? (
        <section className="card stack">
          <table>
            <thead>
              <tr><th align="left">Month</th><th align="right">Gross</th><th align="right">Credits</th><th align="right">Net</th></tr>
            </thead>
            <tbody>
              {aws.months.map((row) => (
                <tr key={row.month}>
                  <td>{row.month}</td>
                  <td align="right">{usd(row.gross_usd)}</td>
                  <td align="right">{usd(row.credits_used_usd)}</td>
                  <td align="right">{usd(row.net_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            Budgets: {aws.budgets.map((b) => `${b.name} ${usd(b.actual_usd)} of ${usd(b.limit_usd)}`).join(" · ")}
          </p>
        </section>
      ) : null}

      <h2>Health and data</h2>
      <section className="grid grid-3">
        {site ? (
          <Tile label="Site /health" value={site.health_status === 200 ? "up" : `HTTP ${site.health_status}`} sub={`${site.health_ms} ms`} />
        ) : (
          <Failed name="Site" error={"error" in m.site ? m.site.error : ""} />
        )}
        {r2 ? (
          <Tile label="Cloudflare R2 storage" value={`${r2.total_gb.toFixed(2)} GB`} sub={`${((r2.total_gb / r2.free_tier_gb) * 100).toFixed(0)}% of the ${r2.free_tier_gb} GB free tier`} />
        ) : (
          <Failed name="R2" error={"error" in m.r2 ? m.r2.error : ""} />
        )}
        {bq ? (
          <Tile label="BigQuery this month" value={`${bq.month_bytes_billed_gb} GB`} sub={`${bq.cap_used_pct}% of ${bq.cap_tib} TiB cap, ${bq.month_queries} queries`} />
        ) : (
          <Failed name="BigQuery" error={"error" in m.bigquery ? m.bigquery.error : ""} />
        )}
      </section>
      {r2 ? (
        <section className="grid grid-3">
          <Tile label="R2 objects" value={(r2.objects ?? 0).toLocaleString()} sub="files in the bucket" />
          <Tile label="R2 cost this month (est.)" value={usd(r2.est_monthly_usd ?? 0)} sub="storage beyond the free tier, $0.015 per GB" />
          <Tile label="R2 growth, last 7 days" value={growth ? `${growth.gb >= 0 ? "+" : ""}${growth.gb.toFixed(2)} GB` : "n/a"} sub={growth ? `${growth.objects >= 0 ? "+" : ""}${growth.objects.toLocaleString()} objects since ${growth.since}` : "needs a week of snapshots"} />
        </section>
      ) : null}
      {r2?.areas?.length ? (
        <section className="card stack">
          <div style={{ display: "flex", height: 14, borderRadius: 7, overflow: "hidden", background: "var(--bg-subtle)" }} aria-hidden="true">
            {r2.areas.map((a, i) => (
              <div key={a.area} title={`${a.area}: ${a.mb} MB`} style={{ width: `${(a.mb / (r2.total_gb * 1000)) * 100}%`, background: ["#a3e635", "#38bdf8", "#f472b6", "#f59e0b", "#94a3b8", "#34d399"][i % 6] }} />
            ))}
          </div>
          <table>
            <thead>
              <tr><th align="left">Storage area</th><th align="right">MB</th><th align="right">Files</th><th align="right">Share</th></tr>
            </thead>
            <tbody>
              {r2.areas.map((a) => (
                <tr key={a.area}>
                  <td>{a.area}</td>
                  <td align="right">{a.mb}</td>
                  <td align="right">{a.files.toLocaleString()}</td>
                  <td align="right">{((a.mb / (r2.total_gb * 1000)) * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">Requests, bandwidth and operations need a Cloudflare API token, which is not configured yet.</p>
        </section>
      ) : null}
      {r2 ? (
        <section className="card stack">
          <table>
            <thead>
              <tr><th align="left">Prefix</th><th align="right">MB</th><th align="right">Files</th><th align="right">Last write</th></tr>
            </thead>
            <tbody>
              {r2.prefixes.map((p) => (
                <tr key={p.prefix}>
                  <td>{p.prefix}</td>
                  <td align="right">{p.mb}</td>
                  <td align="right">{p.files}</td>
                  <td align="right">{p.last_modified.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <h2>Data coverage</h2>
      {r2 ? (
        <section className="card stack">
          <table>
            <thead>
              <tr>
                <th align="left">Competition</th>
                <th align="right">Loaded</th>
                <th align="right">Latest loaded</th>
                <th align="right">Played at Dribble</th>
                <th align="right">Latest played</th>
                <th align="right">Upcoming</th>
              </tr>
            </thead>
            <tbody>
              {(vendor ?? []).length
                ? vendor!.map((v) => {
                    const mine = v.key ? r2.coverage.find((c) => c.league === v.key) : undefined;
                    const behind = mine ? v.played - mine.matches : v.played;
                    return (
                      <tr key={`${v.league_id}-${v.season}`}>
                        <td>{v.league} {v.season}{v.key ? "" : " (not loaded)"}</td>
                        <td align="right">{mine?.matches ?? 0}</td>
                        <td align="right">{mine?.latest_match ?? "-"}</td>
                        <td align="right">{v.played}{behind > 0 && v.key ? ` (${behind} not loaded)` : ""}</td>
                        <td align="right">{v.latest_played ?? "-"}</td>
                        <td align="right">{v.upcoming}</td>
                      </tr>
                    );
                  })
                : r2.coverage.map((c) => (
                    <tr key={`${c.league}-${c.season}`}>
                      <td>{c.league} {c.season}</td>
                      <td align="right">{c.matches}</td>
                      <td align="right">{c.latest_match}</td>
                      <td align="right" colSpan={3} className="muted">Dribble comparison needs a BigQuery login</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <h2>Season analysis</h2>
      {r2?.season_analysis?.length ? (
        <section className="card stack">
          <table>
            <thead>
              <tr>
                <th align="left">Competition</th>
                <th align="right">Matches built</th>
                <th align="right">Matches loaded</th>
                <th align="right">Built</th>
                <th align="right">Players with age</th>
              </tr>
            </thead>
            <tbody>
              {r2.season_analysis.map((a) => {
                const loaded = r2.coverage.find((c) => c.league === a.league)?.matches;
                const behind = loaded !== undefined ? loaded - a.matches : 0;
                return (
                  <tr key={`${a.league}-${a.season}`}>
                    <td>{a.league} {a.season}</td>
                    <td align="right">{a.matches}{behind > 0 ? ` (${behind} behind)` : ""}</td>
                    <td align="right">{loaded ?? "-"}</td>
                    <td align="right">{a.built_at.slice(0, 16).replace("T", " ")}</td>
                    <td align="right">{a.players_with_age} of {a.players} ({a.players ? Math.round((a.players_with_age / a.players) * 100) : 0}%)</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="muted">"Behind" means matches were synced after the last season-analysis build: run scripts/refresh_season_data.py.</p>
        </section>
      ) : (
        <section className="card"><p className="muted">No season-analysis builds in the snapshot yet.</p></section>
      )}

      <h2>Revenue</h2>
      <section className="card">
        <p className="muted">{m.revenue.status}</p>
      </section>
    </main>
  );
}
