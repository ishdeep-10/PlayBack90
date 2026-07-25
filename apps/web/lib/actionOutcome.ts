import { colorWithAlpha } from "./theme";


export function actionOutcomeColor(
  baseColor: string,
  successful: boolean,
  successfulAlpha = 0.9,
  unsuccessfulAlpha = 0.42,
  unsuccessfulColor = baseColor,
) {
  return colorWithAlpha(
    successful ? baseColor : unsuccessfulColor,
    successful ? successfulAlpha : unsuccessfulAlpha,
  );
}

export function unsuccessfulActionColor(mode: "dark" | "light") {
  return mode === "dark" ? "#94a3b8" : "#475569";
}

export function actionEndpointSymbol(successful: boolean, successfulSymbol: string) {
  return successful ? successfulSymbol : "x-open";
}

export function actionStartSymbol(successful: boolean) {
  return successful ? "circle" : "circle-open";
}
