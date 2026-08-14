"""Canonical league identifiers and their upstream competition mappings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueSource:
    key: str
    country: str
    provider_competition: str


LEAGUE_SOURCES: dict[str, LeagueSource] = {
    "premier-league": LeagueSource("premier-league", "england", "england-premier-league"),
    "laliga": LeagueSource("laliga", "spain", "spain-laliga"),
    "bundesliga": LeagueSource("bundesliga", "germany", "germany-bundesliga"),
    "serie-a": LeagueSource("serie-a", "italy", "italy-serie-a"),
    "ligue-1": LeagueSource("ligue-1", "france", "france-ligue-1"),
    "mls": LeagueSource("mls", "usa", "usa-major-league-soccer"),
}


def resolve_league_source(country: str, league: str) -> LeagueSource:
    """Resolve a canonical storage key to its provider competition identifier.

    Unknown leagues retain the legacy ``{country}-{league}`` behavior so this
    mapping can be introduced without breaking ad-hoc ingestion commands.
    """
    country_key = country.strip().lower()
    league_key = league.strip().lower()
    source = LEAGUE_SOURCES.get(league_key)
    if source is None:
        return LeagueSource(league_key, country_key, f"{country_key}-{league_key}")
    if source.country != country_key:
        raise ValueError(
            f"League {league_key!r} is configured for country {source.country!r}, "
            f"not {country_key!r}."
        )
    return source
