from __future__ import annotations

from io import BytesIO

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle
from mplsoccer import VerticalPitch
import pandas as pd

from app.schemas import MatchContext

from app.services.matches import (
    build_player_stats,
    build_shot_player_summary,
    build_summary_cards,
    build_team_summaries,
    filter_shots,
)


matplotlib.use("Agg")


def _plot_goalmouth(ax, shots_df: pd.DataFrame, team_color: str, text_color: str, selected_player: str | None) -> None:
    goal_left = 30.8
    goal_width = 6.4
    goal_height = 35
    ax.set_facecolor("#08131f")
    ax.plot([30, 38], [0, 0], color=text_color, linewidth=1.5)
    ax.plot([goal_left, goal_left + goal_width], [goal_height, goal_height], color=text_color, linewidth=3)
    ax.plot([goal_left + goal_width, goal_left + goal_width], [0, goal_height], color=text_color, linewidth=3)
    ax.plot([goal_left, goal_left], [0, goal_height], color=text_color, linewidth=3)
    ax.add_patch(
        Rectangle((goal_left, 0), goal_width, goal_height, fill=False, edgecolor=text_color, hatch="+", alpha=0.2)
    )

    if not shots_df.empty:
        shots_df = shots_df.copy()
        shots_df["x_inv"] = goal_left + goal_width - (pd.to_numeric(shots_df["goalMouthY"], errors="coerce") - goal_left)
        shots_df["goal_z"] = pd.to_numeric(shots_df["goalMouthZ"], errors="coerce")
        shots_df = shots_df.dropna(subset=["x_inv", "goal_z"])

        for _, row in shots_df.iterrows():
            alpha = 0.95 if not selected_player or row.get("playerName") == selected_player else 0.22
            is_goal = row.get("type") == "Goal"
            color = team_color if is_goal else text_color
            size = 1600 if is_goal else 1200
            ax.scatter(
                row["x_inv"],
                row["goal_z"],
                s=size * max(float(row.get("xG", 0.05)), 0.05),
                color=color,
                edgecolor=text_color,
                linewidth=1.8,
                alpha=alpha,
                zorder=3,
            )

    ax.set_xlim(28, 40)
    ax.set_ylim(-1, 37)
    ax.axis("off")


def _plot_pitch_shots(ax, shots_df: pd.DataFrame, team_color: str, text_color: str, selected_player: str | None) -> None:
    pitch = VerticalPitch(
        pitch_type="uefa",
        half=True,
        pitch_color="#08131f",
        line_color=text_color,
        linewidth=1.2,
        pad_bottom=-8,
    )
    pitch.draw(ax=ax)
    ax.set_facecolor("#08131f")

    if shots_df.empty or "x" not in shots_df.columns or "y" not in shots_df.columns:
        return

    shots_df = shots_df.copy()
    shots_df["x"] = pd.to_numeric(shots_df["x"], errors="coerce")
    shots_df["y"] = pd.to_numeric(shots_df["y"], errors="coerce")
    shots_df = shots_df.dropna(subset=["x", "y"])

    marker_map = {
        "Goal": ("o", team_color, text_color, 2.2),
        "SavedShot": ("o", team_color, "white", 2.2),
        "MissedShots": ("o", "#08131f", team_color, 2.2),
        "ShotOnPost": ("o", team_color, "#34d399", 2.4),
    }

    for shot_type, type_df in shots_df.groupby("type"):
        marker, facecolor, edgecolor, linewidth = marker_map.get(shot_type, ("o", team_color, text_color, 2.0))
        selected_df = type_df if not selected_player else type_df[type_df["playerName"] == selected_player]
        other_df = type_df.iloc[0:0] if not selected_player else type_df[type_df["playerName"] != selected_player]

        if not other_df.empty:
            pitch.scatter(
                other_df["y"],
                other_df["x"],
                ax=ax,
                marker=marker,
                s=6500 * other_df["xG"].clip(lower=0.05),
                c=facecolor,
                edgecolors=edgecolor,
                linewidth=linewidth,
                alpha=0.18,
                zorder=3,
            )
        if not selected_df.empty:
            pitch.scatter(
                selected_df["y"],
                selected_df["x"],
                ax=ax,
                marker=marker,
                s=6500 * selected_df["xG"].clip(lower=0.05),
                c=facecolor,
                edgecolors=edgecolor,
                linewidth=linewidth,
                alpha=0.95,
                zorder=4,
            )


def _build_shot_map_png(
    df: pd.DataFrame,
    context: MatchContext,
    team: str | None,
    situation: str | None,
    player: str | None,
) -> bytes:
    team_name = team or context.home_team
    team_color = "#60a5fa"
    text_color = "white"
    shots_df = filter_shots(df, team=team_name, situation=situation, player=None)

    figure, (ax_goal, ax_pitch) = plt.subplots(
        2,
        1,
        figsize=(10, 11),
        gridspec_kw={"height_ratios": [2, 3.2]},
    )
    figure.patch.set_facecolor("#08131f")
    ax_goal.set_facecolor("#08131f")
    ax_pitch.set_facecolor("#08131f")

    _plot_goalmouth(ax_goal, shots_df, team_color, text_color, player)
    _plot_pitch_shots(ax_pitch, shots_df, team_color, text_color, player)

    figure.suptitle(
        f"{team_name} Shot Map",
        color=text_color,
        fontsize=22,
        y=0.98,
    )
    subtitle = f"Situation: {situation or 'All'}"
    if player:
        subtitle += f" · Highlighted player: {player}"
    figure.text(0.5, 0.945, subtitle, ha="center", color="#9eb0c4", fontsize=11)

    buffer = BytesIO()
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    figure.savefig(buffer, format="png", dpi=180, bbox_inches="tight")
    plt.close(figure)
    return buffer.getvalue()


def build_asset_png(
    df: pd.DataFrame,
    context: MatchContext,
    asset_id: str,
    team: str | None = None,
    situation: str | None = None,
    player: str | None = None,
    half: str = "Full 90",
    duel_type: str = "Total",
    transition_type: str = "Offensive",
    sub_window: int = 0,
) -> bytes:
    if asset_id == "shot-map":
        return _build_shot_map_png(df, context, team, situation, player)

    figure, axis = plt.subplots(figsize=(9, 5))
    figure.patch.set_facecolor("#08131f")
    axis.set_facecolor("#08131f")
    axis.tick_params(colors="white")
    axis.spines[:].set_visible(False)
    axis.title.set_color("white")

    if asset_id == "pass-network" and "teamName" in df.columns:
        team_df = df if not team else df[df["teamName"] == team]
        if "minute" in team_df.columns:
            counts = (
                pd.to_numeric(team_df["minute"], errors="coerce")
                .dropna()
                .astype(int)
                .value_counts()
                .sort_index()
            )
            axis.plot(counts.index, counts.values, color="#34d399", linewidth=2.5)
            axis.fill_between(counts.index, counts.values, color="#34d399", alpha=0.2)
        axis.set_title(f"Event Flow: {team or context.home_team}")
        axis.set_xlabel("Minute")
        axis.set_ylabel("Events")
    else:
        axis.text(
            0.5,
            0.5,
            f"{asset_id} asset is not available for this match yet.",
            ha="center",
            va="center",
            color="white",
            fontsize=16,
        )
        axis.set_xticks([])
        axis.set_yticks([])

    buffer = BytesIO()
    plt.tight_layout()
    figure.savefig(buffer, format="png", dpi=160, bbox_inches="tight")
    plt.close(figure)
    return buffer.getvalue()


def _pdf_chart_page(
    pdf: PdfPages,
    df: pd.DataFrame,
    context: MatchContext,
    asset_id: str,
    title: str,
    team: str | None = None,
) -> None:
    """Render a native chart asset and embed it as a full PDF page."""
    try:
        png_bytes = build_asset_png(df, context, asset_id, team=team)
        import io
        from PIL import Image as PILImage
        img = PILImage.open(io.BytesIO(png_bytes))
        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        fig.patch.set_facecolor("#010b14")
        ax.set_facecolor("#010b14")
        ax.axis("off")
        ax.imshow(img)
        ax.set_title(title, color="white", fontsize=14, pad=8)
        pdf.savefig(fig, bbox_inches="tight", facecolor="#010b14")
        plt.close(fig)
    except Exception:
        # If chart fails (e.g. missing fonts) just skip the page
        pass


def build_match_report_pdf(df: pd.DataFrame, context: MatchContext, narrative: str | None = None) -> bytes:
    buffer = BytesIO()
    summary = build_summary_cards(df)
    teams = build_team_summaries(df)
    players = build_player_stats(df)
    home_shot_summary = build_shot_player_summary(df, team=context.home_team)
    away_shot_summary = build_shot_player_summary(df, team=context.away_team)

    bg = "#010b14"
    fg = "white"
    muted = "#9eb0c4"

    with PdfPages(buffer) as pdf:

        # ── Page 1: Title / match overview ──────────────────────────────
        fig1, ax1 = plt.subplots(figsize=(11.69, 8.27))
        fig1.patch.set_facecolor(bg)
        ax1.set_facecolor(bg)
        ax1.axis("off")
        ax1.text(0.5, 0.88, "PlayBack90", fontsize=32, weight="bold", color="#67e8f9", ha="center", transform=ax1.transAxes)
        ax1.text(0.5, 0.78, "Match Report", fontsize=18, color=muted, ha="center", transform=ax1.transAxes)
        ax1.text(0.5, 0.64, f"{context.home_team}  vs  {context.away_team}", fontsize=22, weight="bold", color=fg, ha="center", transform=ax1.transAxes)
        ax1.text(0.5, 0.54, f"Score: {context.score or 'N/A'}", fontsize=18, color=fg, ha="center", transform=ax1.transAxes)
        ax1.text(0.5, 0.42, f"Events: {summary['events']}    Shots: {summary['shots']}    Goals: {summary['goals']}    xG: {summary['xg_total']}    xGOT: {summary.get('xgot_total', 0.0)}", fontsize=13, color=muted, ha="center", transform=ax1.transAxes)
        if context.league:
            ax1.text(0.5, 0.32, f"{context.league}  ·  {context.season or ''}", fontsize=11, color=muted, ha="center", transform=ax1.transAxes)
        pdf.savefig(fig1, bbox_inches="tight", facecolor=bg)
        plt.close(fig1)

        # ── Optional: AI analyst narrative page ──────────────────────────
        if narrative:
            import textwrap as _tw

            fig_n, ax_n = plt.subplots(figsize=(11.69, 8.27))
            fig_n.patch.set_facecolor(bg)
            ax_n.set_facecolor(bg)
            ax_n.axis("off")
            ax_n.text(0.06, 0.93, "AI Analyst — Key Takeaways", fontsize=20, weight="bold", color="#a3e635", transform=ax_n.transAxes)
            y_pos = 0.84
            for raw_line in narrative.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                for wrapped_index, wrapped in enumerate(_tw.wrap(line, width=96)):
                    ax_n.text(0.06, y_pos, wrapped if wrapped_index else wrapped, fontsize=12, color=fg, transform=ax_n.transAxes)
                    y_pos -= 0.055
                y_pos -= 0.02
                if y_pos < 0.05:
                    break
            pdf.savefig(fig_n, bbox_inches="tight", facecolor=bg)
            plt.close(fig_n)

        # ── Page 2: Team summaries + player stats ────────────────────────
        fig2, ax2 = plt.subplots(figsize=(11.69, 8.27))
        fig2.patch.set_facecolor(bg)
        ax2.set_facecolor(bg)
        ax2.axis("off")
        ax2.text(0.05, 0.94, "Team Summary", fontsize=18, weight="bold", color=fg, transform=ax2.transAxes)
        y = 0.86
        headers = "Team                Goals  Shots  xG     Pass Acc"
        ax2.text(0.05, y, headers, fontsize=10, color=muted, transform=ax2.transAxes, family="monospace")
        y -= 0.06
        for row in teams:
            line = f"{row.team:<20} {row.goals:<6} {row.shots:<6} {row.xg:<6} {(str(row.pass_accuracy) + '%') if row.pass_accuracy else 'N/A'}"
            ax2.text(0.05, y, line, fontsize=11, color=fg, transform=ax2.transAxes, family="monospace")
            y -= 0.07

        y -= 0.04
        ax2.text(0.05, y, "Top Players", fontsize=16, weight="bold", color=fg, transform=ax2.transAxes)
        y -= 0.07
        player_header = "Player                    Team             Goals  Shots  xG"
        ax2.text(0.05, y, player_header, fontsize=9, color=muted, transform=ax2.transAxes, family="monospace")
        y -= 0.055
        for row in players[:12]:
            line = f"{str(row['player']):<26} {str(row.get('team','')):<16} {row['goals']:<6} {row['shots']:<6} {row['xg']}"
            ax2.text(0.05, max(0.03, y), line, fontsize=9, color=fg, transform=ax2.transAxes, family="monospace")
            y -= 0.055
            if y < 0.05:
                break
        pdf.savefig(fig2, bbox_inches="tight", facecolor=bg)
        plt.close(fig2)

        # ── Pages 3-5: Native match charts ────────────────────────────────
        _pdf_chart_page(pdf, df, context, "shot-map", f"{context.home_team} — Shot Map", context.home_team)
        _pdf_chart_page(pdf, df, context, "shot-map", f"{context.away_team} — Shot Map", context.away_team)
        _pdf_chart_page(pdf, df, context, "pass-network", f"{context.home_team} — Event Flow", context.home_team)

        # ── Page 6: Shot leaders table (both teams) ────────────────────────
        fig8, ax8 = plt.subplots(figsize=(11.69, 8.27))
        fig8.patch.set_facecolor(bg)
        ax8.set_facecolor(bg)
        ax8.axis("off")
        ax8.text(0.05, 0.94, "Shot Leaders", fontsize=18, weight="bold", color=fg, transform=ax8.transAxes)
        y = 0.86
        for team_name, shot_rows in [(context.home_team, home_shot_summary), (context.away_team, away_shot_summary)]:
            ax8.text(0.05, y, team_name, fontsize=14, weight="bold", color="#67e8f9", transform=ax8.transAxes)
            y -= 0.055
            header = "Player                   Shots  Goals  xG     xGOT   xG/Shot"
            ax8.text(0.05, y, header, fontsize=8, color=muted, transform=ax8.transAxes, family="monospace")
            y -= 0.048
            for row in (shot_rows or [])[:8]:
                line = f"{str(row['playerName']):<25} {row['Total Shots']:<6} {row['Goals']:<6} {row['Total xG']:<6} {row.get('Total xGOT', 0):<6} {row['xG/Shot']}"
                ax8.text(0.05, max(0.03, y), line, fontsize=9, color=fg, transform=ax8.transAxes, family="monospace")
                y -= 0.048
                if y < 0.05:
                    break
            y -= 0.04
        pdf.savefig(fig8, bbox_inches="tight", facecolor=bg)
        plt.close(fig8)

    return buffer.getvalue()
