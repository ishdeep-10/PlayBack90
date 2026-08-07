"use client";

import { type ChangeEvent, type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import {
  createLiveScrapeJob,
  createStatsBombImportJob,
  createStatsBombSampleImportJob,
  createWyscoutImportJob,
  type StatsBombSampleMatch,
} from "../lib/api";
import { capture } from "../lib/posthog";

const MAX_WYSCOUT_FILE_BYTES = 75 * 1024 * 1024;
const MAX_STATSBOMB_FILE_BYTES = 75 * 1024 * 1024;
type ImportMode = "whoscored" | "wyscout" | "statsbomb";

const STATSBOMB_SAMPLE_MATCHES: StatsBombSampleMatch[] = [
  {
    id: "euro-2024-final",
    match_id: 3943043,
    competition_id: 55,
    season_id: 282,
    competition: "UEFA Euro",
    season: "2024",
    country: "Europe",
    match_date: "2024-07-14",
    home_team: "Spain",
    away_team: "England",
    score: "2-1",
    stage: "Final",
  },
  {
    id: "copa-america-2024-final",
    match_id: 3943077,
    competition_id: 223,
    season_id: 282,
    competition: "Copa America",
    season: "2024",
    country: "South America",
    match_date: "2024-07-15",
    home_team: "Argentina",
    away_team: "Colombia",
    score: "1-0",
    stage: "Final",
  },
  {
    id: "afcon-2023-final",
    match_id: 3923881,
    competition_id: 1267,
    season_id: 107,
    competition: "African Cup of Nations",
    season: "2023",
    country: "Africa",
    match_date: "2024-02-11",
    home_team: "Nigeria",
    away_team: "Cote d'Ivoire",
    score: "1-2",
    stage: "Final",
  },
  {
    id: "bundesliga-2023-24-leverkusen-augsburg",
    match_id: 3895348,
    competition_id: 9,
    season_id: 281,
    competition: "1. Bundesliga",
    season: "2023/2024",
    country: "Germany",
    match_date: "2024-05-18",
    home_team: "Bayer Leverkusen",
    away_team: "Augsburg",
    score: "2-1",
    stage: "Regular Season",
  },
  {
    id: "ligue-1-2022-23-psg-clermont",
    match_id: 3838017,
    competition_id: 7,
    season_id: 235,
    competition: "Ligue 1",
    season: "2022/2023",
    country: "France",
    match_date: "2023-06-03",
    home_team: "Paris Saint-Germain",
    away_team: "Clermont Foot",
    score: "2-3",
    stage: "Regular Season",
  },
  {
    id: "mls-2023-lafc-inter-miami",
    match_id: 3877090,
    competition_id: 44,
    season_id: 107,
    competition: "Major League Soccer",
    season: "2023",
    country: "United States of America",
    match_date: "2023-09-04",
    home_team: "LAFC",
    away_team: "Inter Miami",
    score: "1-3",
    stage: "Regular Season",
  },
  {
    id: "womens-world-cup-2023-final",
    match_id: 3906390,
    competition_id: 72,
    season_id: 107,
    competition: "Women's World Cup",
    season: "2023",
    country: "International",
    match_date: "2023-08-20",
    home_team: "Spain Women's",
    away_team: "England Women's",
    score: "1-0",
    stage: "Final",
  },
  {
    id: "womens-euro-2025-final",
    match_id: 4020846,
    competition_id: 53,
    season_id: 315,
    competition: "UEFA Women's Euro",
    season: "2025",
    country: "Europe",
    match_date: "2025-07-27",
    home_team: "England Women's",
    away_team: "Spain Women's",
    score: "1-1",
    stage: "Final",
  },
  {
    id: "wsl-2023-24-man-united-chelsea",
    match_id: 3913187,
    competition_id: 37,
    season_id: 281,
    competition: "FA Women's Super League",
    season: "2023/2024",
    country: "England",
    match_date: "2024-05-18",
    home_team: "Manchester United W",
    away_team: "Chelsea FCW",
    score: "0-6",
    stage: "Regular Season",
  },
  {
    id: "liga-f-2023-24-valencia-barcelona",
    match_id: 3911643,
    competition_id: 182,
    season_id: 281,
    competition: "Liga F",
    season: "2023/2024",
    country: "Spain",
    match_date: "2024-06-16",
    home_team: "Valencia CF",
    away_team: "Barcelona WFC",
    score: "0-3",
    stage: "Regular Season",
  },
];

function formatFileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 MB";
  return `${(bytes / (1024 * 1024)).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
}

function validateWyscoutPayload(payload: unknown) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Upload a Wyscout match export JSON object.");
  }
  const value = payload as { events?: unknown; match?: unknown };
  if (!Array.isArray(value.events) || value.events.length === 0) {
    throw new Error("This JSON does not include a non-empty Wyscout events array.");
  }
  if (!value.match || typeof value.match !== "object" || Array.isArray(value.match)) {
    throw new Error("This JSON does not include Wyscout match metadata.");
  }
}

function validateStatsBombPayload(payload: unknown) {
  const events = Array.isArray(payload)
    ? payload
    : payload && typeof payload === "object" && !Array.isArray(payload)
      ? (payload as { events?: unknown }).events
      : null;
  if (!Array.isArray(events) || events.length === 0) {
    throw new Error("Upload a StatsBomb events JSON array or a bundled object with an events array.");
  }
  const firstEvent = events.find((item) => item && typeof item === "object") as { type?: unknown } | undefined;
  if (!firstEvent || !firstEvent.type) {
    throw new Error("This JSON does not look like a StatsBomb events export.");
  }
}

function filenameMatchId(fileName: string) {
  const stem = fileName.replace(/\.[^.]+$/, "");
  return /^\d+$/.test(stem) ? Number(stem) : null;
}

async function readJsonFile(file: File) {
  try {
    return JSON.parse(await file.text()) as unknown;
  } catch {
    throw new Error(`${file.name} is not valid JSON.`);
  }
}

function looksLikeStatsBombEventArray(payload: unknown) {
  const firstEvent = Array.isArray(payload)
    ? payload.find((item) => item && typeof item === "object")
    : undefined;
  return Boolean(firstEvent && typeof firstEvent === "object" && (firstEvent as { type?: unknown }).type);
}

function looksLikeStatsBombLineups(payload: unknown) {
  const firstTeam = Array.isArray(payload)
    ? payload.find((item) => item && typeof item === "object")
    : undefined;
  return Boolean(firstTeam && typeof firstTeam === "object" && Array.isArray((firstTeam as { lineup?: unknown }).lineup));
}

function pickMatchMetadata(payload: unknown, matchIdHint: number | null) {
  if (payload && typeof payload === "object" && !Array.isArray(payload) && "match_id" in payload && "home_team" in payload) {
    return payload;
  }
  if (!Array.isArray(payload)) return null;
  const matches = payload.filter((item) => item && typeof item === "object" && "match_id" in item);
  if (!matches.length) return null;
  if (matchIdHint !== null) {
    const matched = matches.find((item) => Number((item as { match_id?: unknown }).match_id) === matchIdHint);
    if (matched) return matched;
  }
  return matches.length === 1 ? matches[0] : null;
}

async function buildStatsBombPayloadFromFiles(files: File[]) {
  if (files.length === 1) {
    const payload = await readJsonFile(files[0]);
    validateStatsBombPayload(payload);
    return payload;
  }

  let events: unknown[] | null = null;
  let lineups: unknown[] | null = null;
  let match: unknown = null;
  let matchIdHint: number | null = null;
  const parsed = await Promise.all(files.map(async (file) => ({ file, payload: await readJsonFile(file) })));

  for (const { file, payload } of parsed) {
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      const bundled = payload as { events?: unknown; lineups?: unknown; match?: unknown };
      if (!events && Array.isArray(bundled.events)) {
        events = bundled.events;
        matchIdHint = filenameMatchId(file.name) ?? matchIdHint;
      }
      if (!lineups && Array.isArray(bundled.lineups)) lineups = bundled.lineups;
      if (!match && bundled.match && typeof bundled.match === "object" && !Array.isArray(bundled.match)) match = bundled.match;
    }
    if (!events && looksLikeStatsBombEventArray(payload)) {
      events = payload as unknown[];
      matchIdHint = filenameMatchId(file.name) ?? matchIdHint;
      continue;
    }
    if (!lineups && looksLikeStatsBombLineups(payload)) {
      lineups = payload as unknown[];
      matchIdHint = matchIdHint ?? filenameMatchId(file.name);
      continue;
    }
  }

  for (const { payload } of parsed) {
    if (!match) match = pickMatchMetadata(payload, matchIdHint);
  }

  const payload = { events, lineups: lineups ?? undefined, match: match ?? undefined };
  validateStatsBombPayload(payload);
  return payload;
}

export function LiveScrapeForm() {
  const router = useRouter();
  const [mode, setMode] = useState<ImportMode>("wyscout");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [fileName, setFileName] = useState("");
  const [fileMeta, setFileMeta] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sampleLoadingId, setSampleLoadingId] = useState<string | null>(null);

  function selectMode(nextMode: ImportMode) {
    setMode(nextMode);
    setError(null);
    setStatus(null);
  }

  async function handleWhoScoredSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setStatus("Queuing scrape...");

    try {
      const job = await createLiveScrapeJob(url);
      setStatus("Opening analysis...");
      router.push(`/analysis/live/${job.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create scrape job.");
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleWyscoutUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError(null);
    setStatus(null);
    setFileName(file.name);
    setFileMeta(`${formatFileSize(file.size)} JSON`);

    if (file.size > MAX_WYSCOUT_FILE_BYTES) {
      setError(`This file is ${formatFileSize(file.size)}. Upload a JSON file under ${formatFileSize(MAX_WYSCOUT_FILE_BYTES)}.`);
      event.target.value = "";
      return;
    }

    const looksLikeJson = file.name.toLowerCase().endsWith(".json") || file.type === "application/json" || file.type === "";
    if (!looksLikeJson) {
      setError("Upload a .json file exported from Wyscout.");
      event.target.value = "";
      return;
    }

    setLoading(true);
    setStatus("Reading file...");
    capture("import_started", { provider: "wyscout" });

    try {
      const text = await file.text();
      let payload: unknown;
      try {
        payload = JSON.parse(text);
      } catch {
        throw new Error("That file is not valid JSON.");
      }
      validateWyscoutPayload(payload);
      setStatus("Normalizing Wyscout match...");
      const job = await createWyscoutImportJob(payload);
      if (job.status === "failed") {
        throw new Error(job.error ?? "Unable to import Wyscout JSON.");
      }
      const matchId = job.context?.match_id ?? job.match_id;
      if (!matchId) {
        throw new Error("Wyscout import completed without a match id.");
      }
      setStatus("Opening analysis...");
      capture("import_completed", { provider: "wyscout" });
      router.push(`/analysis/${matchId}?source=import&jobId=${encodeURIComponent(job.job_id)}&provider=wyscout`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to import Wyscout JSON.");
      setStatus(null);
      capture("import_failed", { provider: "wyscout" });
    } finally {
      setLoading(false);
      event.target.value = "";
    }
  }

  async function handleStatsBombUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    setError(null);
    setStatus(null);
    const totalSize = files.reduce((total, file) => total + file.size, 0);
    setFileName(files.length === 1 ? files[0].name : `${files.length} files selected`);
    setFileMeta(`${formatFileSize(totalSize)} JSON`);

    if (totalSize > MAX_STATSBOMB_FILE_BYTES) {
      setError(`These files total ${formatFileSize(totalSize)}. Upload JSON files under ${formatFileSize(MAX_STATSBOMB_FILE_BYTES)}.`);
      event.target.value = "";
      return;
    }

    const invalidFile = files.find((file) => !(file.name.toLowerCase().endsWith(".json") || file.type === "application/json" || file.type === ""));
    if (invalidFile) {
      setError(`${invalidFile.name} is not a .json file exported from StatsBomb.`);
      event.target.value = "";
      return;
    }

    setLoading(true);
    setStatus("Reading file...");
    capture("import_started", { provider: "statsbomb" });

    try {
      const payload = await buildStatsBombPayloadFromFiles(files);
      setStatus("Normalizing StatsBomb match...");
      const job = await createStatsBombImportJob(payload);
      if (job.status === "failed") {
        throw new Error(job.error ?? "Unable to import StatsBomb JSON.");
      }
      const matchId = job.context?.match_id ?? job.match_id;
      if (!matchId) {
        throw new Error("StatsBomb import completed without a match id.");
      }
      setStatus("Opening analysis...");
      capture("import_completed", { provider: "statsbomb" });
      router.push(`/analysis/${matchId}?source=import&jobId=${encodeURIComponent(job.job_id)}&provider=statsbomb`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to import StatsBomb JSON.");
      setStatus(null);
      capture("import_failed", { provider: "statsbomb" });
    } finally {
      setLoading(false);
      event.target.value = "";
    }
  }

  async function handleStatsBombSample(sample: StatsBombSampleMatch) {
    setError(null);
    setStatus(`Loading ${sample.home_team} vs ${sample.away_team}...`);
    setLoading(true);
    setSampleLoadingId(sample.id);
    capture("import_started", { provider: "statsbomb_sample" });

    try {
      const job = await createStatsBombSampleImportJob(sample.id);
      if (job.status === "failed") {
        throw new Error(job.error ?? "Unable to import StatsBomb sample.");
      }
      const matchId = job.context?.match_id ?? job.match_id;
      if (!matchId) {
        throw new Error("StatsBomb sample imported without a match id.");
      }
      setStatus("Opening analysis...");
      capture("import_completed", { provider: "statsbomb_sample" });
      router.push(`/analysis/${matchId}?source=import&jobId=${encodeURIComponent(job.job_id)}&provider=statsbomb`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to import StatsBomb sample.");
      setStatus(null);
      capture("import_failed", { provider: "statsbomb_sample" });
    } finally {
      setLoading(false);
      setSampleLoadingId(null);
    }
  }

  return (
    <div className="stack">
      <div className="segmented-control" role="tablist" aria-label="Import source">
        <button
          type="button"
          className={mode === "whoscored" ? "active" : ""}
          onClick={undefined}
          disabled
          title="Live WhoScored scraping is temporarily unavailable in this beta."
        >
          WhoScored URL (unavailable)
        </button>
        <button
          type="button"
          className={mode === "wyscout" ? "active" : ""}
          onClick={() => selectMode("wyscout")}
        >
          Wyscout JSON
        </button>
        <button
          type="button"
          className={mode === "statsbomb" ? "active" : ""}
          onClick={() => selectMode("statsbomb")}
        >
          StatsBomb JSON
        </button>
      </div>

      {mode === "whoscored" ? (
        <form className="stack" onSubmit={handleWhoScoredSubmit}>
          <input
            className="input"
            type="url"
            placeholder="https://www.whoscored.com/Matches/..."
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            required
          />
          <div className="row">
            <button className="button" disabled={loading} type="submit">
              {loading ? status ?? "Queuing scrape..." : "Start Live Scrape"}
            </button>
            <span className="muted">Live match scraping runs asynchronously through the worker service.</span>
          </div>
        </form>
      ) : mode === "wyscout" ? (
        <div className="stack">
          <label className={`input file-input ${loading ? "is-loading" : ""}`}>
            <input
              type="file"
              accept="application/json,.json"
              disabled={loading}
              onChange={handleWyscoutUpload}
            />
            <span>{loading ? status ?? "Importing Wyscout match..." : fileName || "Choose Wyscout JSON"}</span>
          </label>
          <div className="import-meta-row">
            <span className="muted">{fileMeta || "Wyscout match export JSON"}</span>
            <span className="muted">Expires after 60 minutes</span>
          </div>
        </div>
      ) : (
        <div className="stack">
          <label className={`input file-input ${loading ? "is-loading" : ""}`}>
            <input
              type="file"
              accept="application/json,.json"
              multiple
              disabled={loading}
              onChange={handleStatsBombUpload}
            />
            <span>{loading ? status ?? "Importing StatsBomb match..." : fileName || "Choose StatsBomb JSON files"}</span>
          </label>
          <div className="import-meta-row">
            <span className="muted">{fileMeta || "Events JSON, bundled JSON, or events + lineups + matches"}</span>
            <span className="muted">Expires after 60 minutes</span>
          </div>
          <div className="statsbomb-samples">
            <div className="import-meta-row">
              <span className="muted">Official StatsBomb Open Data samples</span>
              <span className="muted">{STATSBOMB_SAMPLE_MATCHES.length} matches</span>
            </div>
            <div className="statsbomb-sample-grid">
              {STATSBOMB_SAMPLE_MATCHES.map((sample) => (
                <button
                  key={sample.id}
                  className="statsbomb-sample-card"
                  type="button"
                  disabled={loading}
                  onClick={() => handleStatsBombSample(sample)}
                >
                  <span className="sample-competition">{sample.competition} · {sample.season}</span>
                  <span className="sample-match">{sample.home_team} vs {sample.away_team}</span>
                  <span className="sample-meta">{sample.score} · {sample.stage} · {sample.match_date}</span>
                  <span className="sample-action">
                    {sampleLoadingId === sample.id ? "Importing..." : "Open sample"}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {status && !loading ? <p className="import-message" role="status">{status}</p> : null}
      {error ? <p className="import-message is-error" role="alert">{error}</p> : null}
    </div>
  );
}
