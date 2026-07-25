type Props = {
  label?: string;
  size?: number;
};

export function OrbLoader({ label = "Analysing match data", size = 96 }: Props) {
  return (
    <div className="orb-loader" role="status" aria-label={label}>
      <div className="orb-stage" style={{ width: size, height: size }}>
        <span className="orb-ring" />
        <span className="orb-ring orb-ring-2" />
        <span className="orb-core" />
        <span className="orb-satellite s1" />
        <span className="orb-satellite s2" />
        <span className="orb-satellite s3" />
      </div>
      <span className="orb-label ai-shimmer">{label}</span>
    </div>
  );
}
