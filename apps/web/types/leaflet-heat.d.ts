import * as L from "leaflet";

declare module "leaflet" {
  interface HeatLayerOptions {
    minOpacity?: number;
    maxZoom?: number;
    max?: number;
    radius?: number;
    blur?: number;
    gradient?: Record<number, string>;
  }
  interface HeatLayer extends L.Layer {
    setLatLngs(latlngs: Array<[number, number] | [number, number, number]>): this;
    addLatLng(latlng: [number, number] | [number, number, number]): this;
    setOptions(options: HeatLayerOptions): this;
    redraw(): this;
  }
  function heatLayer(
    latlngs: Array<[number, number] | [number, number, number]>,
    options?: HeatLayerOptions
  ): HeatLayer;
}

declare module "leaflet.heat";
