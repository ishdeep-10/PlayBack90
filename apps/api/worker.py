from app.services.live_scrape import run_live_scrape


def main() -> None:
    raise SystemExit(
        "Phase 1 uses in-process background jobs for local development. "
        "Promote run_live_scrape into a separate queue worker for production deployment."
    )


if __name__ == "__main__":
    main()
