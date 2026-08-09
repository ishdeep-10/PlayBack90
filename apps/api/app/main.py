from __future__ import annotations

from io import BytesIO
from time import monotonic

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.middleware.gzip import GZipMiddleware

from app.auth import require_auth_middleware
from app.config import settings
from app.domain import LEAGUE_DISPLAY_MAP
from app.schemas import (
    AnalysisResponse,
    AnalysisViewRequest,
    AnalysisViewResponse,
    FixtureHubResponse,
    FixtureListResponse,
    FixtureRoundListResponse,
    FixtureRoundResponse,
    ImportJobResponse,
    LeagueSummary,
    LiveScrapeJobCreate,
    MatchByFileResponse,
    OppositionDossierResponse,
    OppositionFoundationResponse,
    SeasonList,
    StandingsResponse,
)
from app.services import fixture_rounds, live_scrape, r2
from app.services.rate_limit import enforce_rate_limit
from app.services.import_jobs import import_job_store
from app.services.live_jobs import job_store
from app.services.providers.statsbomb import StatsBombImportError, normalize_statsbomb_match
from app.services.providers.whoscored_html import WhoScoredHtmlImportError, normalize_whoscored_html
from app.services.providers.statsbomb_samples import (
    StatsBombSampleError,
    fetch_statsbomb_open_data_sample,
    list_statsbomb_open_data_samples,
)
from app.services.providers.wyscout import WyscoutImportError, normalize_wyscout_match
from app.services.matches import (
    build_available_filters,
    build_event_timeline,
    build_match_summary_view,
    build_match_dynamics,
    build_player_comparison,
    build_player_stats,
    build_shot_details,
    build_shot_events,
    build_shot_player_summary,
    build_summary_cards,
    build_team_summaries,
    derive_match_context,
    filter_shots,
    get_match_by_file,
)
from app.services.views.defensive_actions import build_defensive_actions_view
from app.services.views.duels_transitions import build_duels_transitions_view
from app.services.views.entries import build_territory_entries
from app.services.views.pass_network import (
    build_channel_analysis,
    build_in_possession_actions_view,
    build_in_possession_player_metrics,
    build_pass_network,
)
from app.services.views.player_analysis import build_player_analysis_view, build_player_history_view
from app.services.views.goalkeeper import build_goalkeeper_view
from app.services.views.set_pieces import build_set_pieces_view
from app.services.views.shots import build_shots_sca_view
from app.services import season_stats as ss
from app.services.standings import StandingsProviderError, standings_service
from app.services.schedules import provider_season_keys, schedule_service
from app.services.season_baseline import build_season_baseline_view
from app.services import opposition as opp_svc
from app.services.opposition_foundation import build_opposition_foundation
from app.services.opposition_dossier import build_opposition_dossier

if settings.sentry_dsn:
    import sentry_sdk

    try:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, send_default_pii=False)
    except Exception:  # noqa: BLE001 - a bad DSN must never prevent the app from starting
        pass


app = FastAPI(title=settings.app_name)
app.middleware("http")(require_auth_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):30\d{2}$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1_000, compresslevel=5)

_ANALYSIS_VIEW_CACHE: dict[tuple[str, ...], tuple[float, dict]] = {}
_ANALYSIS_VIEW_CACHE_TTL_SECONDS = 900
_ANALYSIS_VIEW_CACHE_MAX_ITEMS = 96


def _cached_payload(key: tuple[str, ...], builder):
    now = monotonic()
    cached = _ANALYSIS_VIEW_CACHE.get(key)
    if cached and now - cached[0] < _ANALYSIS_VIEW_CACHE_TTL_SECONDS:
        return cached[1]
    payload = builder()
    if len(_ANALYSIS_VIEW_CACHE) >= _ANALYSIS_VIEW_CACHE_MAX_ITEMS:
        oldest_key = min(_ANALYSIS_VIEW_CACHE, key=lambda item: _ANALYSIS_VIEW_CACHE[item][0])
        _ANALYSIS_VIEW_CACHE.pop(oldest_key, None)
    _ANALYSIS_VIEW_CACHE[key] = (now, payload)
    return payload


def resolve_analysis_source(
    *,
    source: str,
    match_id: str | None = None,
    league: str | None = None,
    season: str | None = None,
    job_id: str | None = None,
):
    if source == "live":
        if not job_id:
            raise HTTPException(status_code=400, detail="job_id is required for live analysis.")
        job = job_store.get_job(job_id)
        if not job or job.data is None or job.data.empty:
            raise HTTPException(status_code=404, detail="Live job data is not available.")
        context = derive_match_context(job.data, file_path=None, source="live")
        return job.data, context

    if source == "import":
        if not job_id:
            raise HTTPException(status_code=400, detail="job_id is required for imported analysis.")
        job = import_job_store.get(job_id)
        if not job or job.data is None or job.data.empty:
            raise HTTPException(status_code=404, detail="Imported match data is not available.")
        context = derive_match_context(job.data, file_path=None, source="import")
        return job.data, context

    if not match_id or not league or not season:
        raise HTTPException(status_code=400, detail="match_id, league, and season are required for historical analysis.")

    file_path = r2.find_file_path(league, season, match_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Match not found.")

    df, context = get_match_by_file(file_path)
    if df.empty:
        raise HTTPException(status_code=404, detail="Match not found.")
    return df, context


@app.get("/health")
def healthcheck() -> dict[str, object]:
    return {
        "ok": True,
        "environment": settings.environment,
        "r2_configured": settings.has_r2_credentials,
        "official_standings_configured": bool(settings.football_data_api_key),
        "api_sports_configured": bool(settings.api_sports_key),
        "redis_configured": bool(settings.redis_url),
        "database_configured": bool(settings.database_url),
        "sentry_configured": bool(settings.sentry_dsn),
    }


def _auth_is_ready() -> bool:
    if not settings.auth_required:
        return True
    has_provider = bool(settings.clerk_jwks_url and settings.clerk_issuer)
    has_allowlist = bool(settings.auth_allowed_emails or settings.auth_allowed_user_ids)
    return has_provider and has_allowlist


def _readiness_checks() -> dict[str, bool]:
    return {
        "r2": settings.has_r2_credentials,
        "redis": bool(settings.redis_url),
        "database": bool(settings.database_url),
        "auth": _auth_is_ready(),
    }


@app.get("/ready")
def readiness() -> JSONResponse:
    checks = _readiness_checks()
    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "ok": ready,
            "environment": settings.environment,
            "checks": checks,
        },
    )


@app.get(f"{settings.api_prefix}/leagues", response_model=list[LeagueSummary])
def list_leagues() -> list[LeagueSummary]:
    return [LeagueSummary(key=key, name=name) for key, name in LEAGUE_DISPLAY_MAP.items()]


@app.get(f"{settings.api_prefix}/players/images")
def get_player_images(names: str, team: str | None = None) -> dict[str, str | None]:
    from app.services.player_images import resolve_player_images

    wanted = [name.strip() for name in names.split(",") if name.strip()][:80]
    return resolve_player_images(wanted, team=team)


_IMAGE_PROXY_CACHE: dict[str, tuple[bytes, str]] = {}
_IMAGE_PROXY_ALLOWED_HOSTS = {"cdn.soccerwiki.org", "raw.githubusercontent.com"}


@app.get(f"{settings.api_prefix}/players/image-proxy")
def proxy_player_image(url: str) -> Response:
    """CORS-friendly proxy so exports can draw headshots onto a canvas."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _IMAGE_PROXY_ALLOWED_HOSTS:
        raise HTTPException(status_code=400, detail="URL not allowed.")
    cached = _IMAGE_PROXY_CACHE.get(url)
    if cached is None:
        import requests as _requests

        try:
            upstream = _requests.get(url, timeout=10)
            upstream.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail="Upstream image fetch failed.") from exc
        cached = (upstream.content, upstream.headers.get("Content-Type", "image/png"))
        if len(_IMAGE_PROXY_CACHE) >= 512:
            _IMAGE_PROXY_CACHE.pop(next(iter(_IMAGE_PROXY_CACHE)), None)
        _IMAGE_PROXY_CACHE[url] = cached
    content, media_type = cached
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})


@app.get(f"{settings.api_prefix}/leagues/{{league}}/seasons", response_model=SeasonList)
def list_seasons(league: str) -> SeasonList:
    seasons = sorted(set(r2.list_league_seasons(league) + provider_season_keys(league)), reverse=True)
    return SeasonList(league=league, seasons=seasons)


@app.get(f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/fixtures", response_model=FixtureListResponse)
def list_fixtures(league: str, season: str, offset: int = 0, limit: int = 10) -> FixtureListResponse:
    hub = schedule_service.build_fixture_hub(league, season, state="all")
    fixtures = hub.get("fixtures", [])[offset : offset + limit]
    return FixtureListResponse(league=league, season=season, offset=offset, limit=limit, fixtures=fixtures)


@app.get(f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/fixture-hub", response_model=FixtureHubResponse)
def get_fixture_hub(
    league: str,
    season: str,
    state: str = Query(default="all", pattern="^(all|completed|upcoming|postponed|cancelled|live|unknown)$"),
    round_id: str | None = Query(default=None, alias="round"),
) -> FixtureHubResponse:
    return schedule_service.build_fixture_hub(league, season, state=state, round_id=round_id)


@app.get(
    f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/rounds",
    response_model=FixtureRoundListResponse,
)
def list_fixture_rounds(league: str, season: str) -> FixtureRoundListResponse:
    rounds = fixture_rounds.list_fixture_rounds(league, season)
    summaries = [{key: value for key, value in item.items() if key != "fixtures"} for item in rounds]
    return FixtureRoundListResponse(
        league=league,
        season=season,
        latest_round_id=str(rounds[0]["id"]) if rounds else None,
        rounds=summaries,
    )


@app.get(
    f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/rounds/{{round_id}}",
    response_model=FixtureRoundResponse,
)
def get_fixture_round(league: str, season: str, round_id: str) -> FixtureRoundResponse:
    rounds = fixture_rounds.list_fixture_rounds(league, season)
    selected = next((item for item in rounds if item["id"] == round_id), None)
    if selected is None:
        raise HTTPException(status_code=404, detail="Fixture round not found.")
    summary = {key: value for key, value in selected.items() if key != "fixtures"}
    return FixtureRoundResponse(
        league=league,
        season=season,
        round=summary,
        fixtures=selected["fixtures"],
    )


@app.get(f"{settings.api_prefix}/matches/by-file", response_model=MatchByFileResponse)
def get_match_by_file_endpoint(file_path: str = Query(..., alias="file_path")) -> MatchByFileResponse:
    df, context = get_match_by_file(file_path)
    if df.empty:
        raise HTTPException(status_code=404, detail="Match file not found or empty.")
    return MatchByFileResponse(
        context=context,
        event_count=int(len(df)),
        columns=df.columns.astype(str).tolist(),
        preview_rows=df.head(20).fillna("").to_dict(orient="records"),
    )


@app.get(f"{settings.api_prefix}/analysis/{{match_id}}", response_model=AnalysisResponse)
def get_analysis(
    match_id: str,
    league: str | None = Query(default=None),
    season: str | None = Query(default=None),
    source: str = Query(default="r2"),
    job_id: str | None = Query(default=None, alias="job_id"),
) -> AnalysisResponse:
    df, context = resolve_analysis_source(source=source, match_id=match_id, league=league, season=season, job_id=job_id)
    if source not in {"live", "import"} and context.match_id != match_id:
        raise HTTPException(status_code=400, detail="match_id does not match the supplied file.")

    return AnalysisResponse(
        context=context,
        summary_cards=build_summary_cards(df),
        team_summaries=build_team_summaries(df),
        available_filters=build_available_filters(df),
    )


@app.post(f"{settings.api_prefix}/analysis/views/{{view_id}}", response_model=AnalysisViewResponse)
def get_analysis_view(view_id: str, request: AnalysisViewRequest) -> AnalysisViewResponse:
    file_path: str | None = None
    if request.source in {"live", "import"}:
        job_id = request.filters.get("job_id")
        if not isinstance(job_id, str):
            raise HTTPException(status_code=400, detail="job_id is required for transient analysis views.")
        job = job_store.get_job(job_id) if request.source == "live" else import_job_store.get(job_id)
        df = job.data if job and job.data is not None else None
        context = derive_match_context(df, file_path=None, source=request.source) if df is not None else None
    else:
        if not request.league or not request.season:
            raise HTTPException(status_code=400, detail="league and season are required for historical matches.")
        file_path = r2.find_file_path(request.league, request.season, request.match_id)
        if not file_path:
            raise HTTPException(status_code=404, detail="Match not found.")
        df, context = get_match_by_file(file_path)

    if df is None or df.empty or context is None:
        raise HTTPException(status_code=404, detail="Analysis data is not available.")

    team = request.filters.get("team")
    situation = request.filters.get("situation")
    player = request.filters.get("player")
    players = request.filters.get("players")
    sub_window = request.filters.get("subWindow")
    score_state = request.filters.get("gameState")
    time_range = request.filters.get("timeRange")

    if view_id == "match-summary":
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload=build_match_summary_view(df),
        )

    if view_id == "season-baseline":
        if request.source in {"live", "import"}:
            return AnalysisViewResponse(
                view_id=view_id,
                context=context,
                kind="message",
                payload={"message": "Season context is not available for transient imports."},
            )
        cache_token = file_path or f"live:{context.match_id}"
        payload = _cached_payload(
            ("season-baseline-v7-gk", cache_token),
            lambda: build_season_baseline_view(df, context),
        )
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload=payload,
        )

    if view_id == "match-dynamics":
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=build_match_dynamics(df),
        )

    if view_id == "team-stats":
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload={"rows": [row.model_dump() for row in build_team_summaries(df)]},
        )

    if view_id == "player-stats":
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload={"rows": build_player_stats(df, team=team)},
        )

    if view_id == "pass-network":
        third = request.filters.get("third")
        if request.source == "r2":
            payload = _cached_payload(
                ("pass-network", file_path or "", str(team or ""), str(sub_window or "0"), str(score_state or "all"), str(time_range or "all"), str(third or "all")),
                lambda: build_pass_network(df, team=team, sub_window=sub_window, score_state=score_state, time_range=time_range, third=third),
            )
        else:
            payload = build_pass_network(df, team=team, sub_window=sub_window, score_state=score_state, time_range=time_range, third=third)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "in-possession-player-metrics":
        if request.source == "r2":
            payload = _cached_payload(
                ("in-possession-player-metrics-v2-epv", file_path or "", str(team or ""), str(sub_window or "all"), str(score_state or "all"), str(time_range or "all")),
                lambda: build_in_possession_player_metrics(df, team=team, sub_window=sub_window, score_state=score_state, time_range=time_range),
            )
        else:
            payload = build_in_possession_player_metrics(df, team=team, sub_window=sub_window, score_state=score_state, time_range=time_range)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload=payload,
        )

    if view_id == "player-history":
        if request.source in {"live", "import"}:
            return AnalysisViewResponse(
                view_id=view_id,
                context=context,
                kind="message",
                payload={"message": "Player history is not available for transient imports."},
            )
        player_b = request.filters.get("playerB")
        payload = _cached_payload(
            ("player-history", file_path or "", str(player or ""), str(player_b or ""), request.match_id),
            lambda: build_player_history_view(file_path, player, request.match_id, player_b),
        )
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload=payload,
        )

    if view_id == "goalkeeper":
        if request.source == "r2":
            payload = _cached_payload(
                ("goalkeeper-v2-actions-shots", file_path or "", str(team or "")),
                lambda: build_goalkeeper_view(df, team=team),
            )
        else:
            payload = build_goalkeeper_view(df, team=team)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "set-pieces":
        if request.source == "r2":
            payload = _cached_payload(
                ("set-pieces", file_path or "", str(team or ""), str(score_state or "all"), str(time_range or "all")),
                lambda: build_set_pieces_view(df, team=team, score_state=score_state, time_range=time_range),
            )
        else:
            payload = build_set_pieces_view(df, team=team, score_state=score_state, time_range=time_range)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "territory-entries":
        if request.source == "r2":
            payload = _cached_payload(
                ("territory-entries", file_path or "", str(team or ""), str(time_range or "all")),
                lambda: build_territory_entries(df, team=team, time_range=time_range),
            )
        else:
            payload = build_territory_entries(df, team=team, time_range=time_range)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "channel-analysis":
        if request.source == "r2":
            payload = _cached_payload(
                ("channel-analysis", file_path or "", str(team or ""), str(score_state or "all"), str(time_range or "all")),
                lambda: build_channel_analysis(df, team=team, score_state=score_state, time_range=time_range),
            )
        else:
            payload = build_channel_analysis(df, team=team, score_state=score_state, time_range=time_range)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "in-possession-actions":
        third = request.filters.get("third")
        if request.source == "r2":
            payload = _cached_payload(
                ("in-possession-actions-v2-epv", file_path or "", str(team or ""), str(sub_window or "0"), str(score_state or "all"), str(time_range or "all"), str(third or "all")),
                lambda: build_in_possession_actions_view(df, team=team, sub_window=sub_window, score_state=score_state, time_range=time_range, third=third),
            )
        else:
            payload = build_in_possession_actions_view(df, team=team, sub_window=sub_window, score_state=score_state, time_range=time_range, third=third)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "defensive-actions":
        if request.source == "r2":
            payload = _cached_payload(
                ("defensive-actions-v2-transitions", file_path or "", str(team or ""), str(score_state or "all"), str(time_range or "all")),
                lambda: build_defensive_actions_view(df, team=team, score_state=score_state, time_range=time_range),
            )
        else:
            payload = build_defensive_actions_view(df, team=team, score_state=score_state, time_range=time_range)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "duels-transitions":
        duel_type = request.filters.get("duelType")
        transition_type = request.filters.get("transitionType")
        if request.source == "r2":
            payload = _cached_payload(
                (
                    "duels-transitions",
                    file_path or "",
                    str(team or ""),
                    str(duel_type or "Total"),
                    str(transition_type or "Offensive"),
                    str(score_state or "all"),
                    str(time_range or "all"),
                ),
                lambda: build_duels_transitions_view(
                    df,
                    team=team,
                    duel_type=duel_type,
                    transition_type=transition_type,
                    score_state=score_state,
                    time_range=time_range,
                ),
            )
        else:
            payload = build_duels_transitions_view(
                df,
                team=team,
                duel_type=duel_type,
                transition_type=transition_type,
                score_state=score_state,
                time_range=time_range,
            )
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "player-analysis":
        if request.source == "r2":
            payload = _cached_payload(
                ("player-analysis-v16-position", file_path or "", str(team or ""), str(score_state or "all"), str(time_range or "all")),
                lambda: build_player_analysis_view(df, team=team, score_state=score_state, time_range=time_range),
            )
        else:
            payload = build_player_analysis_view(df, team=team, score_state=score_state, time_range=time_range)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "shot-summary":
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload={"rows": build_shot_events(filter_shots(df, team=team, situation=situation, player=player))},
        )

    if view_id == "shot-player-summary":
        if request.source == "r2":
            payload = _cached_payload(
                ("shot-player-summary-v2-xgot", file_path or "", str(team or ""), str(situation or "All")),
                lambda: {"rows": build_shot_player_summary(df, team=team, situation=situation)},
            )
        else:
            payload = {"rows": build_shot_player_summary(df, team=team, situation=situation)}
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload=payload,
        )

    if view_id == "shot-details":
        if request.source == "r2":
            payload = _cached_payload(
                ("shot-details-v2-xgot", file_path or "", str(team or ""), str(situation or "All"), str(player or "")),
                lambda: {"rows": build_shot_details(df, team=team, situation=situation, player=player)},
            )
        else:
            payload = {"rows": build_shot_details(df, team=team, situation=situation, player=player)}
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload=payload,
        )

    if view_id == "shots-sca":
        if request.source == "r2":
            payload = _cached_payload(
                ("shots-sca-v2-xgot", file_path or "", str(situation or "All")),
                lambda: build_shots_sca_view(df, situation=situation),
            )
        else:
            payload = build_shots_sca_view(df, situation=situation)
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload=payload,
        )

    if view_id == "event-timeline":
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="chart",
            payload={"points": build_event_timeline(df, team=team)},
        )

    if view_id == "player-comparison":
        player_list = [item for item in players if isinstance(item, str)] if isinstance(players, list) else None
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="table",
            payload={"rows": build_player_comparison(df, players=player_list)},
        )

    if view_id in {"shot-map", "transitions"}:
        query = f"source={context.source}"
        if context.source == "r2" and request.league and request.season:
            query += f"&league={request.league}&season={request.season}"
        if context.source == "live":
            job_id = request.filters.get("job_id")
            if isinstance(job_id, str):
                query += f"&job_id={job_id}"
        if context.source == "import":
            job_id = request.filters.get("job_id")
            if isinstance(job_id, str):
                query += f"&job_id={job_id}"
        team = request.filters.get("team")
        if team:
            query += f"&team={team}"
        if isinstance(situation, str) and situation:
            query += f"&situation={situation}"
        if isinstance(player, str) and player:
            query += f"&player={player}"
        return AnalysisViewResponse(
            view_id=view_id,
            context=context,
            kind="asset",
            payload={"asset_url": f"{settings.api_prefix}/analysis/{context.match_id}/assets/{view_id}.png?{query}"},
        )

    return AnalysisViewResponse(
        view_id=view_id,
        context=context,
        kind="message",
        payload={"message": f"{view_id} has not been implemented yet."},
    )


@app.post(f"{settings.api_prefix}/analysis/ai/insights")
def get_ai_insights(
    request: AnalysisViewRequest,
    view: str = Query(default="match-dynamics"),
    mode: str = Query(default="baseline"),
) -> StreamingResponse:
    from app.services import ai_analyst, insights

    if request.source in {"live", "import"}:
        job_id = request.filters.get("job_id")
        if request.source == "live":
            job = job_store.get_job(job_id) if isinstance(job_id, str) else None
        else:
            job = import_job_store.get(job_id) if isinstance(job_id, str) else None
        df = job.data if job and job.data is not None else None
        file_path = None
    else:
        if not request.league or not request.season:
            raise HTTPException(status_code=400, detail="league and season are required.")
        file_path = r2.find_file_path(request.league, request.season, request.match_id)
        if not file_path:
            raise HTTPException(status_code=404, detail="Match not found.")
        df, _context = get_match_by_file(file_path)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="Analysis data is not available.")

    team = request.filters.get("team")
    ai_available = ai_analyst.insights_available()
    headers = {"X-AI-Available": "1" if ai_available else "0"}

    if mode == "ai" and ai_available:
        digest = ai_analyst.build_view_digest(df, view, team, file_path)
        cache_key = ai_analyst.make_cache_key(file_path, view, team)
        return StreamingResponse(
            ai_analyst.stream_insights(digest, cache_key), media_type="text/plain", headers=headers
        )

    bullets = insights.build_deterministic_insights(df, view, team)
    if not bullets:
        raise HTTPException(status_code=404, detail="No insights available for this view.")
    body = "\n".join(f"- {bullet}" for bullet in bullets)
    return StreamingResponse(iter([body]), media_type="text/plain", headers=headers)


@app.get(f"{settings.api_prefix}/analysis/{{match_id}}/assets/{{asset_id}}.png")
def get_analysis_asset(
    http_request: Request,
    match_id: str,
    asset_id: str,
    league: str | None = Query(default=None),
    season: str | None = Query(default=None),
    source: str = Query(default="r2"),
    job_id: str | None = Query(default=None, alias="job_id"),
    team: str | None = None,
    situation: str | None = None,
    player: str | None = None,
    half: str = "Full 90",
    duel_type: str = "Total",
    transition_type: str = "Offensive",
    sub_window: int = Query(default=0, alias="sub_window"),
) -> Response:
    from app.services.visuals import build_asset_png

    enforce_rate_limit(http_request, bucket="asset-png", limit=60, window_seconds=60)
    df, context = resolve_analysis_source(source=source, match_id=match_id, league=league, season=season, job_id=job_id)
    if df.empty or (source not in {"live", "import"} and context.match_id != match_id):
        raise HTTPException(status_code=404, detail="Asset source data not found.")
    image_bytes = build_asset_png(
        df,
        context,
        asset_id=asset_id,
        team=team,
        situation=situation,
        player=player,
        half=half,
        duel_type=duel_type,
        transition_type=transition_type,
        sub_window=sub_window,
    )
    return Response(content=image_bytes, media_type="image/png")


@app.post(f"{settings.api_prefix}/analysis/report-jobs")
def create_report_job(http_request: Request, request: AnalysisViewRequest) -> dict[str, str]:
    from app.services.report_jobs import report_job_store

    enforce_rate_limit(http_request, bucket="report-pdf", limit=5, window_seconds=60)
    if not request.league or not request.season:
        raise HTTPException(status_code=400, detail="league and season are required.")
    file_path = r2.find_file_path(request.league, request.season, request.match_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Match not found.")
    job = report_job_store.create()
    report_job_store.submit(job.job_id, file_path)
    return {"job_id": job.job_id, "status": job.status}


@app.get(f"{settings.api_prefix}/analysis/report-jobs/{{job_id}}")
def get_report_job(job_id: str) -> dict[str, str | None]:
    from app.services.report_jobs import report_job_store

    job = report_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Report job not found.")
    return {"job_id": job.job_id, "status": job.status, "message": job.message}


@app.get(f"{settings.api_prefix}/analysis/report-jobs/{{job_id}}/download")
def download_report_job(job_id: str) -> Response:
    from app.services.report_jobs import report_job_store

    job = report_job_store.get(job_id)
    if not job or job.status != "completed" or not job.pdf_bytes:
        raise HTTPException(status_code=404, detail="Report is not ready.")
    return Response(
        content=job.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{job.filename}"'},
    )


@app.get(f"{settings.api_prefix}/analysis/{{match_id}}/report.pdf")
def get_match_report(
    http_request: Request,
    match_id: str,
    league: str | None = Query(default=None),
    season: str | None = Query(default=None),
    source: str = Query(default="r2"),
    job_id: str | None = Query(default=None, alias="job_id"),
) -> StreamingResponse:
    from app.services.visuals import build_match_report_pdf

    enforce_rate_limit(http_request, bucket="report-pdf", limit=5, window_seconds=60)
    df, context = resolve_analysis_source(source=source, match_id=match_id, league=league, season=season, job_id=job_id)
    if df.empty or (source not in {"live", "import"} and context.match_id != match_id):
        raise HTTPException(status_code=404, detail="Match data not found.")
    pdf_bytes = build_match_report_pdf(df, context)
    filename = f"playback90-{match_id}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Season Stats ──────────────────────────────────────────────────────────────

def _get_standings(league: str, season: str) -> dict:
    team_df = ss.load_team_season_stats(league, season)
    local_rows = ss.build_league_table(team_df)
    try:
        return standings_service.build_payload(league, season, local_rows)
    except (StandingsProviderError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/standings",
    response_model=StandingsResponse,
)
def get_standings(league: str, season: str) -> dict:
    return _get_standings(league, season)


@app.get(
    f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/league-table",
    response_model=StandingsResponse,
    include_in_schema=False,
)
def get_league_table(league: str, season: str) -> dict:
    return _get_standings(league, season)


@app.get(f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/team-form/{{team}}")
def get_team_form(league: str, season: str, team: str, window: int = Query(default=5)) -> dict:
    team_df = ss.load_team_season_stats(league, season)
    return ss.build_team_form(team_df, team, window=window)


@app.get(f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/player-leaderboard")
def get_player_leaderboard(
    league: str,
    season: str,
    sort_by: str = Query(default="xG"),
    min_mins: int = Query(default=0),
) -> dict:
    player_df = ss.load_player_season_stats(league, season)
    if player_df.empty:
        raise HTTPException(status_code=404, detail="Player season stats not found.")
    return {"rows": ss.build_player_leaderboard(player_df, sort_by=sort_by, min_mins=min_mins)}


@app.get(f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/season-assets/{{asset_id}}.png")
def get_season_asset(
    league: str,
    season: str,
    asset_id: str,
    team: str | None = None,
) -> Response:
    team_df = ss.load_team_season_stats(league, season)
    player_df = ss.load_player_season_stats(league, season)
    image_bytes = ss.build_season_asset(team_df, player_df, asset_id, team=team)
    return Response(content=image_bytes, media_type="image/png")


# ── Opposition Analysis ───────────────────────────────────────────────────────

def _require_opposition_analysis_enabled() -> None:
    if not settings.opposition_analysis_enabled:
        raise HTTPException(status_code=404, detail="Opposition Analysis is not available yet.")


@app.get(f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/opposition/{{team}}/report")
def get_opposition_report(league: str, season: str, team: str) -> dict:
    _require_opposition_analysis_enabled()
    team_df = ss.load_team_season_stats(league, season)
    player_df = ss.load_player_season_stats(league, season)
    if team_df.empty:
        raise HTTPException(status_code=404, detail="Season stats not found.")
    return opp_svc.build_opposition_report(team_df, player_df, team, league, season)


@app.get(
    f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/opposition/{{opponent_team}}/foundation",
    response_model=OppositionFoundationResponse,
)
def get_opposition_foundation(
    league: str,
    season: str,
    opponent_team: str,
    reference_team: str = Query(..., alias="reference_team"),
    sample_size: int = Query(default=5, ge=3, le=10),
) -> OppositionFoundationResponse:
    _require_opposition_analysis_enabled()
    payload = build_opposition_foundation(
        league=league,
        season=season,
        opponent_team=opponent_team,
        reference_team=reference_team,
        sample_size=sample_size,
    )
    if not payload["sample_matches"] and any("not available" in warning for warning in payload["warnings"]):
        raise HTTPException(status_code=404, detail="Opposition foundation data is not available.")
    return payload


@app.get(
    f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/opposition/{{opponent_team}}/dossier",
    response_model=OppositionDossierResponse,
)
def get_opposition_dossier(
    league: str,
    season: str,
    opponent_team: str,
    reference_team: str = Query(..., alias="referenceTeam"),
    fixture_id: str | None = Query(default=None, alias="fixtureId"),
    home_team: str | None = Query(default=None, alias="home"),
    away_team: str | None = Query(default=None, alias="away"),
    sample_size: int = Query(default=5, ge=3, le=10, alias="sampleSize"),
) -> OppositionDossierResponse:
    _require_opposition_analysis_enabled()
    payload = build_opposition_dossier(
        league=league,
        season=season,
        opponent_team=opponent_team,
        reference_team=reference_team,
        fixture_id=fixture_id,
        home_team=home_team,
        away_team=away_team,
        sample_size=sample_size,
    )
    if not payload["sampleContext"]["sample_matches"]:
        raise HTTPException(status_code=404, detail="Opposition dossier data is not available.")
    return payload


@app.get(f"{settings.api_prefix}/leagues/{{league}}/seasons/{{season}}/opposition/{{team}}/assets/{{asset_id}}.png")
def get_opposition_asset(league: str, season: str, team: str, asset_id: str) -> Response:
    _require_opposition_analysis_enabled()
    team_df = ss.load_team_season_stats(league, season)
    player_df = ss.load_player_season_stats(league, season)
    image_bytes = opp_svc.build_opposition_asset(team_df, player_df, team, asset_id)
    return Response(content=image_bytes, media_type="image/png")


@app.post(f"{settings.api_prefix}/live-scrape-jobs")
def create_live_scrape_job(http_request: Request, request: LiveScrapeJobCreate):
    if not settings.live_scrape_enabled:
        raise HTTPException(status_code=404, detail="Live WhoScored scraping is not available yet.")
    enforce_rate_limit(
        http_request,
        bucket="live-scrape",
        limit=settings.live_scrape_rate_limit_per_minute,
        window_seconds=60,
    )
    job = job_store.create_job(str(request.url))
    job_store.submit(job.job_id, live_scrape.run_live_scrape, str(request.url))
    return job_store.to_response(job.job_id)


@app.get(f"{settings.api_prefix}/live-scrape-jobs/{{job_id}}")
def get_live_scrape_job(job_id: str):
    try:
        return job_store.to_response(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc


MAX_WHOSCORED_HTML_BYTES = 20 * 1024 * 1024


@app.post(f"{settings.api_prefix}/import-jobs/whoscored-html", response_model=ImportJobResponse)
async def create_whoscored_html_import_job(http_request: Request):
    enforce_rate_limit(http_request, bucket="import", limit=10, window_seconds=60)
    body = await http_request.body()
    job = import_job_store.create("whoscored")
    import_job_store.update(job.job_id, status="running", message="Reading saved WhoScored match data")

    if len(body) > MAX_WHOSCORED_HTML_BYTES:
        import_job_store.update(
            job.job_id,
            status="failed",
            error="The WhoScored HTML file must be 20 MB or smaller.",
        )
        return import_job_store.to_response(job.job_id)

    try:
        html = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        import_job_store.update(
            job.job_id,
            status="failed",
            error="The uploaded file is not readable UTF-8 HTML.",
        )
        return import_job_store.to_response(job.job_id)

    try:
        df = normalize_whoscored_html(html)
        if df.empty:
            raise WhoScoredHtmlImportError("No events were returned from the WhoScored HTML import.")
        match_id = str(df["matchId"].dropna().iloc[0]) if "matchId" in df.columns and not df["matchId"].dropna().empty else None
        import_job_store.update(
            job.job_id,
            status="completed",
            message="WhoScored HTML import completed",
            match_id=match_id,
            data=df,
        )
        return import_job_store.to_response(job.job_id)
    except WhoScoredHtmlImportError as exc:
        import_job_store.update(job.job_id, status="failed", error=str(exc))
        return import_job_store.to_response(job.job_id)
    except Exception as exc:
        import_job_store.update(job.job_id, status="failed", error="Unable to process the WhoScored HTML file.")
        raise HTTPException(status_code=400, detail="Unable to process the WhoScored HTML file.") from exc


@app.post(f"{settings.api_prefix}/import-jobs/wyscout", response_model=ImportJobResponse)
def create_wyscout_import_job(http_request: Request, payload: dict = Body(...)):
    enforce_rate_limit(http_request, bucket="import", limit=10, window_seconds=60)
    job = import_job_store.create("wyscout")
    import_job_store.update(job.job_id, status="running", message="Normalizing Wyscout match data")
    try:
        df = normalize_wyscout_match(payload)
        if df.empty:
            import_job_store.update(
                job.job_id,
                status="failed",
                error="No events were returned from the Wyscout import.",
            )
            return import_job_store.to_response(job.job_id)

        match_id = str(df["matchId"].dropna().iloc[0]) if "matchId" in df.columns and not df["matchId"].dropna().empty else None
        import_job_store.update(
            job.job_id,
            status="completed",
            message="Wyscout import completed",
            match_id=match_id,
            data=df,
        )
        return import_job_store.to_response(job.job_id)
    except WyscoutImportError as exc:
        import_job_store.update(job.job_id, status="failed", error=str(exc))
        return import_job_store.to_response(job.job_id)
    except Exception as exc:
        import_job_store.update(job.job_id, status="failed", error="Unable to process Wyscout import.")
        raise HTTPException(status_code=400, detail="Unable to process Wyscout import.") from exc


@app.post(f"{settings.api_prefix}/import-jobs/statsbomb", response_model=ImportJobResponse)
def create_statsbomb_import_job(http_request: Request, payload: object = Body(...)):
    enforce_rate_limit(http_request, bucket="import", limit=10, window_seconds=60)
    return _create_statsbomb_import_job(payload, message="StatsBomb import completed")


def _create_statsbomb_import_job(payload: object, *, message: str) -> ImportJobResponse:
    job = import_job_store.create("statsbomb")
    import_job_store.update(job.job_id, status="running", message="Normalizing StatsBomb match data")
    try:
        df = normalize_statsbomb_match(payload)
        if df.empty:
            import_job_store.update(
                job.job_id,
                status="failed",
                error="No events were returned from the StatsBomb import.",
            )
            return import_job_store.to_response(job.job_id)

        match_id = str(df["matchId"].dropna().iloc[0]) if "matchId" in df.columns and not df["matchId"].dropna().empty else None
        import_job_store.update(
            job.job_id,
            status="completed",
            message=message,
            match_id=match_id,
            data=df,
        )
        return import_job_store.to_response(job.job_id)
    except StatsBombImportError as exc:
        import_job_store.update(job.job_id, status="failed", error=str(exc))
        return import_job_store.to_response(job.job_id)
    except Exception as exc:
        import_job_store.update(job.job_id, status="failed", error="Unable to process StatsBomb import.")
        raise HTTPException(status_code=400, detail="Unable to process StatsBomb import.") from exc


@app.get(f"{settings.api_prefix}/import-jobs/statsbomb/samples")
def list_statsbomb_sample_matches() -> dict[str, list[dict[str, object]]]:
    return {"samples": list_statsbomb_open_data_samples()}


@app.post(f"{settings.api_prefix}/import-jobs/statsbomb/samples/{{sample_id}}", response_model=ImportJobResponse)
def create_statsbomb_sample_import_job(http_request: Request, sample_id: str):
    enforce_rate_limit(http_request, bucket="import", limit=10, window_seconds=60)
    try:
        payload = fetch_statsbomb_open_data_sample(sample_id)
    except StatsBombSampleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _create_statsbomb_import_job(payload, message="StatsBomb Open Data sample imported")


@app.get(f"{settings.api_prefix}/import-jobs/{{job_id}}", response_model=ImportJobResponse)
def get_import_job(job_id: str):
    try:
        return import_job_store.to_response(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Import job not found.") from exc


@app.delete(f"{settings.api_prefix}/import-jobs/{{job_id}}")
def delete_import_job(job_id: str) -> dict[str, bool]:
    return {"deleted": import_job_store.delete(job_id)}
