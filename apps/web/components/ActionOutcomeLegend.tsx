import type { CSSProperties } from "react";


type Props = {
  color: string;
  unsuccessfulColor: string;
};

export function ActionOutcomeLegend({ color, unsuccessfulColor }: Props) {
  return (
    <div
      className="action-outcome-legend"
      style={{
        "--action-outcome-color": color,
        "--action-unsuccessful-color": unsuccessfulColor,
      } as CSSProperties}
      aria-label="Action outcome legend"
    >
      <span><i className="is-successful" />Successful</span>
      <span><i className="is-unsuccessful" />Unsuccessful</span>
    </div>
  );
}
