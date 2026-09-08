export const SIMPLE_BASEMAP_URL = 'https://tiles.openfreemap.org/styles/positron';

export function resolveBasemapStyle() {
  return { filter: 'none', background: '#c5e3ed' };
}

// Style actual vector features instead of fading the entire map image.
export function simplifyBasemap(source) {
  const style = structuredClone(source);
  style.layers = style.layers.filter((layer) => layer.type !== 'raster').map((layer) => {
    layer.paint ||= {};
    if (layer.id === 'background') layer.paint['background-color'] = '#f7f7f2';
    if (layer.id === 'water') layer.paint['fill-color'] = '#c5e3ed';
    if (layer.id === 'park' || layer.id === 'landcover_wood') layer.paint['fill-color'] = '#dfebd8';
    if (layer['source-layer'] === 'transportation') {
      if (/minor|path|track|service|rail/i.test(layer.id)) layer.minzoom = Math.max(layer.minzoom || 0, 13);
      if (layer.type === 'line') layer.paint['line-opacity'] = 0.55;
    }
    if (layer.type === 'symbol') {
      layer.layout ||= {};
      if (layer.layout['text-field']) {
        layer.layout['text-field'] = ['coalesce', ['get', 'name:en'], ['get', 'name_en'], ['get', 'name:latin'], ['get', 'name']];
        layer.layout['text-allow-overlap'] = false;
        layer.layout['text-padding'] = 10;
        layer.paint['text-color'] = '#526474';
      }
      if (layer['source-layer'] !== 'place') layer.minzoom = Math.max(layer.minzoom || 0, 14);
      if (/village|suburb|neighbourhood/i.test(layer.id)) layer.minzoom = Math.max(layer.minzoom || 0, 12);
    }
    return layer;
  });
  return style;
}
