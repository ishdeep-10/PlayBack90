declare module "react-simple-maps" {
  import type { GeoProjection } from "d3-geo";
  import type { ComponentType, ReactNode, SVGProps } from "react";

  type GeographyObject = {
    rsmKey: string;
    properties: Record<string, unknown>;
  };

  export const ComposableMap: ComponentType<
    SVGProps<SVGSVGElement> & {
      projection?: string | GeoProjection;
      projectionConfig?: Record<string, unknown>;
      children?: ReactNode;
    }
  >;

  export const Geographies: ComponentType<{
    geography: string | Record<string, unknown>;
    children: (props: { geographies: GeographyObject[] }) => ReactNode;
  }>;

  export const Geography: ComponentType<
    SVGProps<SVGPathElement> & {
      geography: GeographyObject;
    }
  >;

  export const Marker: ComponentType<{
    coordinates: [number, number];
    children?: ReactNode;
  }>;

  export const ZoomableGroup: ComponentType<{
    center?: [number, number];
    zoom?: number;
    minZoom?: number;
    maxZoom?: number;
    onMoveEnd?: (position: { coordinates: [number, number]; zoom: number }) => void;
    children?: ReactNode;
  }>;
}
