import { resolveBasemapStyle } from './basemapStyle.js';
import { captureMapOverlays } from './mapDomExport.js';

const EXPORT_SCALE = 2;
const TILE_WAIT_MS = 8000;

function waitForImage(image, timeoutMs = TILE_WAIT_MS) {
  if (image.complete) return Promise.resolve(image.naturalWidth > 0);
  return new Promise((resolve) => {
    const timeout = window.setTimeout(() => resolve(false), timeoutMs);
    const finish = (loaded) => {
      window.clearTimeout(timeout);
      resolve(loaded);
    };
    image.addEventListener('load', () => finish(true), { once: true });
    image.addEventListener('error', () => finish(false), { once: true });
  });
}

function svgToImage(svg, width, height) {
  const clone = svg.cloneNode(true);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  // Leaflet positions its renderer SVG with a CSS translate while its viewBox
  // already uses map-layer coordinates.  getBoundingClientRect() below gives
  // us the translated screen position, so retaining this transform in the
  // serialized image would apply the same offset a second time.
  clone.style.transform = 'none';
  clone.style.left = '0';
  clone.style.top = '0';
  clone.setAttribute('width', String(width));
  clone.setAttribute('height', String(height));
  const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => { URL.revokeObjectURL(url); resolve(image); };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('The vector overlay could not be prepared for export.'));
    };
    image.src = url;
  });
}

function roundScaleDistance(maxMeters) {
  const power = 10 ** Math.floor(Math.log10(maxMeters));
  return [5, 2, 1]
    .map((factor) => factor * power)
    .find((distance) => distance <= maxMeters) || power;
}

export function getScaleBarDetails(map, requestedLengthKm, maximumPixelLength = 112) {
  if (!map) return null;
  const mapSize = map.getSize();
  const y = Math.max(0, mapSize.y - 70);
  const startLatLng = map.containerPointToLatLng([16, y]);
  const endLatLng = map.containerPointToLatLng([16 + maximumPixelLength, y]);
  const maximumMeters = map.distance(startLatLng, endLatLng);
  const requestedMeters = Number(requestedLengthKm) * 1000;
  const distanceMeters = requestedMeters > 0 && requestedMeters <= maximumMeters
    ? requestedMeters
    : roundScaleDistance(maximumMeters);
  const pixelLength = maximumPixelLength * (distanceMeters / maximumMeters);
  const label = distanceMeters >= 1000
    ? `${Number((distanceMeters / 1000).toFixed(1))} km`
    : `${Math.round(distanceMeters)} m`;
  return { distanceMeters, pixelLength, label };
}

export async function exportLeafletMap({
  map, basemapStyle = resolveBasemapStyle(), basemap,
}) {
  if (!map) throw new Error('The interactive map is not ready.');
  if (!['vector', 'raster'].includes(basemap?.kind)) throw new Error('Wait for the simplified basemap, or explicitly select the fallback before exporting.');
  const vectorCanvas = basemap?.kind === 'vector' ? await basemap.capture() : null;
  const startView = `${map.getCenter().toString()}-${map.getZoom()}-${map.getSize().toString()}`;
  const container = map.getContainer();
  const startBasemapKind = container.dataset.basemapKind;
  const mapRect = container.getBoundingClientRect();
  if (mapRect.width < 1 || mapRect.height < 1) throw new Error('The map has no visible export area.');

  const tiles = [...container.querySelectorAll('.leaflet-tile')];
  await Promise.all(tiles.map((tile) => waitForImage(tile)));
  const drawableTiles = tiles.filter((tile) => tile.complete && tile.naturalWidth > 0);
  if (!vectorCanvas && drawableTiles.length === 0) throw new Error('Basemap tiles are not ready. Check the network and try again.');

  const width = Math.round(mapRect.width);
  const mapHeight = Math.round(mapRect.height);
  const canvas = document.createElement('canvas');
  canvas.width = width * EXPORT_SCALE;
  canvas.height = mapHeight * EXPORT_SCALE;
  const context = canvas.getContext('2d');
  context.scale(EXPORT_SCALE, EXPORT_SCALE);
  context.clearRect(0, 0, width, mapHeight);
  const cornerRadius = parseFloat(getComputedStyle(container.parentElement).borderRadius)
    || parseFloat(getComputedStyle(container).borderRadius) || 0;
  context.beginPath();
  context.roundRect(0, 0, width, mapHeight, cornerRadius);
  context.clip();
  context.fillStyle = basemapStyle.background;
  context.fillRect(0, 0, width, mapHeight);
  context.save();
  context.filter = basemapStyle.filter;
  if (vectorCanvas) {
    const rect = vectorCanvas.getBoundingClientRect();
    context.drawImage(vectorCanvas, rect.left - mapRect.left, rect.top - mapRect.top, rect.width, rect.height);
  }
  drawableTiles.forEach((tile) => {
    const rect = tile.getBoundingClientRect();
    context.drawImage(tile, rect.left - mapRect.left, rect.top - mapRect.top, rect.width, rect.height);
  });
  context.restore();

  const svgOverlays = [...container.querySelectorAll('.leaflet-overlay-pane svg')];
  for (const svg of svgOverlays) {
    const rect = svg.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    const image = await svgToImage(svg, rect.width, rect.height);
    context.drawImage(image, rect.left - mapRect.left, rect.top - mapRect.top, rect.width, rect.height);
  }

  const overlays = await captureMapOverlays(container.parentElement, mapRect);
  context.drawImage(overlays, 0, 0, mapRect.width, mapRect.height);

  if (startView !== `${map.getCenter().toString()}-${map.getZoom()}-${map.getSize().toString()}`
    || startBasemapKind !== container.dataset.basemapKind) {
    throw new Error('The map moved during export. Please try again.');
  }
  try {
    return canvas.toDataURL('image/png');
  } catch {
    throw new Error('The browser blocked basemap export. Reload the map and try again.');
  }
}

export function pngFilename(title) {
  return `${String(title || 'hong-kong-map').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'hong-kong-map'}.png`;
}

export function createPngObjectUrl(dataUrl) {
  const [metadata, encoded] = dataUrl.split(',');
  const mimeType = metadata.match(/^data:([^;]+)/)?.[1] || 'image/png';
  const bytes = Uint8Array.from(window.atob(encoded), (character) => character.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type: mimeType }));
}
