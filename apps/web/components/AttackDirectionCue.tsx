"use client";

type Props = {
  team: string;
  label?: string;
};

export function AttackDirectionCue({ team, label = "Attack direction" }: Props) {
  return (
    <div className="attack-direction-cue" aria-label={`${label}: ${team} attacks left to right`}>
      <span>{label}</span>
      <strong>{team}</strong>
      <i aria-hidden="true" />
    </div>
  );
}
