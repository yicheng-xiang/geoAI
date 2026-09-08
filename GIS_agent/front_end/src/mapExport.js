import { resolveBasemapStyle } from './basemapStyle.js';

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

function drawRoundedBox(context, x, y, width, height, radius = 8) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
  context.fill();
  context.stroke();
}

function drawFloatingCard(context, x, y, width, height, radius = 8) {
  context.save();
  context.fillStyle = 'rgba(255, 255, 255, 0.95)';
  context.strokeStyle = 'rgba(148, 163, 184, 0.55)';
  context.lineWidth = 1;
  context.shadowColor = 'rgba(15, 23, 42, 0.14)';
  context.shadowBlur = 12;
  context.shadowOffsetY = 4;
  drawRoundedBox(context, x, y, width, height, radius);
  context.restore();
}

function drawMapHeading(context, width, heading) {
  const title = heading?.title || 'Hong Kong Spatial Analysis';
  const subtitle = heading?.subtitle || '';
  context.save();
  context.font = '700 18px Arial, sans-serif';
  const titleWidth = context.measureText(title).width;
  context.font = '12px Arial, sans-serif';
  const subtitleWidth = subtitle ? context.measureText(subtitle).width : 0;
  const compact = width < 560;
  const availableWidth = compact ? width - 32 : width - 280;
  const boxWidth = Math.min(availableWidth, Math.max(250, titleWidth, subtitleWidth) + 34);
  const boxHeight = subtitle ? 57 : 39;
  const x = (width - boxWidth) / 2;
  const y = compact ? 40 : 14;
  drawFloatingCard(context, x, y, boxWidth, boxHeight, 9);
  context.fillStyle = '#172033';
  context.font = '700 18px Arial, sans-serif';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(title, width / 2, y + (subtitle ? 19 : boxHeight / 2), boxWidth - 28);
  if (subtitle) {
    context.fillStyle = '#64748b';
    context.font = '12px Arial, sans-serif';
    context.fillText(subtitle, width / 2, y + 40, boxWidth - 28);
  }
  context.restore();
}

function drawSchoolSymbol(context, centerX, centerY, size, color, strokeColor = '#ffffff') {
  const scale = size / 28;
  context.save();
  context.translate(centerX - (size / 2), centerY - (size / 2));
  context.scale(scale, scale);
  context.fillStyle = color;
  context.strokeStyle = strokeColor;
  context.lineWidth = 1.15 / scale;
  context.beginPath();
  context.moveTo(14, 1.8); context.lineTo(25, 6.9); context.lineTo(25, 15.8);
  context.bezierCurveTo(25, 20.9, 20.7, 24.6, 14, 26.2);
  context.bezierCurveTo(7.3, 24.6, 3, 20.9, 3, 15.8);
  context.lineTo(3, 6.9); context.closePath(); context.fill(); context.stroke();
  context.strokeStyle = '#ffffff';
  context.lineWidth = 1.55;
  context.lineCap = 'round'; context.lineJoin = 'round';
  context.beginPath();
  context.moveTo(7.4, 11.1); context.lineTo(14, 7.5); context.lineTo(20.6, 11.1);
  [9.4, 12.4, 15.6, 18.6].forEach((x) => { context.moveTo(x, 12.3); context.lineTo(x, 18.5); });
  context.moveTo(7.8, 19); context.lineTo(20.2, 19); context.stroke();
  context.restore();
}

function drawLocationSymbol(context, centerX, centerY, size, color, strokeColor = '#ffffff') {
  const scale = size / 38;
  context.save();
  const halo = context.createRadialGradient(centerX, centerY - (5 * scale), 1, centerX, centerY - (5 * scale), size * 0.55);
  halo.addColorStop(0, 'rgba(56, 189, 248, 0.28)');
  halo.addColorStop(1, 'rgba(56, 189, 248, 0)');
  context.fillStyle = halo;
  context.beginPath(); context.arc(centerX, centerY - (5 * scale), size * 0.55, 0, Math.PI * 2); context.fill();
  context.translate(centerX - (16 * scale), centerY - (19 * scale));
  context.scale(scale, scale);
  context.fillStyle = color; context.strokeStyle = strokeColor; context.lineWidth = 1.4 / scale;
  context.beginPath();
  context.moveTo(16, 2.5);
  context.bezierCurveTo(9.65, 2.5, 4.5, 7.65, 4.5, 14);
  context.bezierCurveTo(4.5, 22.8, 16, 34.8, 16, 34.8);
  context.bezierCurveTo(16, 34.8, 27.5, 22.8, 27.5, 14);
  context.bezierCurveTo(27.5, 7.65, 22.35, 2.5, 16, 2.5);
  context.closePath(); context.fill(); context.stroke();
  context.fillStyle = '#ffffff'; context.beginPath(); context.arc(16, 14, 4.2, 0, Math.PI * 2); context.fill();
  context.fillStyle = color; context.beginPath(); context.arc(16, 14, 1.65, 0, Math.PI * 2); context.fill();
  context.restore();
}

function drawFacilitySymbol(context, centerX, centerY, size, color, strokeColor = '#ffffff') {
  context.save();
  context.fillStyle = color; context.strokeStyle = strokeColor; context.lineWidth = 1.1;
  context.beginPath();
  context.roundRect(centerX - (size / 2), centerY - (size / 2), size, size, size * 0.25);
  context.fill(); context.stroke();
  context.strokeStyle = '#ffffff'; context.lineWidth = 1.5; context.lineCap = 'round';
  context.beginPath();
  context.moveTo(centerX, centerY - (size * 0.25)); context.lineTo(centerX, centerY + (size * 0.25));
  context.moveTo(centerX - (size * 0.25), centerY); context.lineTo(centerX + (size * 0.25), centerY);
  context.stroke(); context.restore();
}

function drawPointSymbol(context, symbol, centerX, centerY, size, color, strokeColor) {
  if (symbol === 'school') drawSchoolSymbol(context, centerX, centerY, size, color, strokeColor);
  else if (symbol === 'location') drawLocationSymbol(context, centerX, centerY, size, color, strokeColor);
  else drawFacilitySymbol(context, centerX, centerY, size, color, strokeColor);
}

function drawLegend(context, width, height, legendGroups) {
  const groups = legendGroups.filter((group) => group.entries.length > 0);
  if (groups.length === 0) return;
  const rows = groups.reduce((count, group) => (
    count + group.entries.length + 1 + (group.subtitle ? 1 : 0)
      + (group.note ? 1 : 0) + (group.overflowCount ? 1 : 0)
  ), 0);
  const boxWidth = Math.min(260, width * 0.36);
  const boxHeight = Math.min(height - 96, 20 + (rows * 20));
  const x = width - boxWidth - 16;
  const y = height - boxHeight - (width < 560 ? 126 : 42);

  context.save();
  drawFloatingCard(context, x, y, boxWidth, boxHeight);
  context.beginPath();
  context.rect(x, y, boxWidth, boxHeight);
  context.clip();
  let cursorY = y + 21;
  groups.forEach((group) => {
    context.fillStyle = '#1e293b';
    context.font = '600 13px Arial, sans-serif';
    context.fillText(group.title, x + 12, cursorY);
    cursorY += 18;
    if (group.subtitle) {
      context.fillStyle = '#64748b';
      context.font = '11px Arial, sans-serif';
      context.fillText(group.subtitle, x + 12, cursorY);
      cursorY += 18;
    }
    if (group.note) {
      context.fillStyle = '#94a3b8';
      context.font = '10px Arial, sans-serif';
      context.fillText(group.note, x + 12, cursorY);
      cursorY += 18;
    }
    group.entries.forEach((entry) => {
      context.fillStyle = entry.color;
      if (entry.shape === 'circle' && entry.symbol) {
        drawPointSymbol(context, entry.symbol, x + 19, cursorY - 4, entry.symbol === 'location' ? 15 : 14,
          entry.color, entry.strokeColor);
      } else if (entry.shape === 'circle') {
        context.save();
        context.globalAlpha = Number(entry.fillOpacity) || 0.6;
        context.beginPath();
        context.arc(x + 19, cursorY - 4, 4, 0, Math.PI * 2);
        context.fill();
        context.globalAlpha = entry.strokeOpacity ?? 0.95;
        context.strokeStyle = entry.strokeColor || '#334155';
        context.lineWidth = entry.strokeWidth ?? 1;
        context.stroke();
        context.restore();
      } else {
        context.save();
        context.globalAlpha = entry.fillOpacity ?? 1;
        context.fillRect(x + 14, cursorY - 10, 11, 11);
        context.restore();
        context.save();
        context.strokeStyle = entry.pattern === 'no-data' ? '#94a3b8' : 'rgba(71, 85, 105, 0.35)';
        context.lineWidth = 1;
        if (entry.pattern === 'no-data') context.setLineDash([2, 2]);
        context.strokeRect(x + 14, cursorY - 10, 11, 11);
        if (entry.pattern === 'no-data') {
          context.beginPath();
          context.moveTo(x + 14, cursorY);
          context.lineTo(x + 24, cursorY - 10);
          context.stroke();
        }
        context.restore();
      }
      context.fillStyle = '#334155';
      context.font = '12px Arial, sans-serif';
      context.fillText(entry.label, x + 32, cursorY);
      cursorY += 19;
    });
    if (group.overflowCount) {
      context.fillStyle = '#64748b';
      context.font = 'italic 11px Arial, sans-serif';
      context.fillText(`+ ${group.overflowCount} more categories`, x + 14, cursorY);
      cursorY += 19;
    }
  });
  context.restore();
}

function drawCustomPointMarkers(context, container, mapRect) {
  const markers = [...container.querySelectorAll('.geoai-point-marker')];
  markers.forEach((marker) => {
    const rect = marker.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const styleHost = marker.firstElementChild;
    const styles = styleHost ? window.getComputedStyle(styleHost) : null;
    const color = styles?.getPropertyValue('--symbol-color').trim() || '#d97772';
    const strokeColor = styles?.getPropertyValue('--symbol-stroke').trim() || '#ffffff';
    const symbol = marker.classList.contains('geoai-location-marker')
      ? 'location' : marker.classList.contains('geoai-school-marker') ? 'school' : 'facility';
    const centerX = rect.left - mapRect.left + (rect.width / 2);
    const centerY = rect.top - mapRect.top + (rect.height / 2);
    drawPointSymbol(context, symbol, centerX, centerY, Math.max(rect.width, rect.height), color, strokeColor);
  });
}

function drawCompass(context, width) {
  const x = width - 38;
  const y = width < 560 ? 122 : 76;
  context.save();
  context.fillStyle = 'rgba(255, 255, 255, 0.92)';
  context.strokeStyle = 'rgba(148, 163, 184, 0.55)';
  context.lineWidth = 1;
  context.beginPath();
  context.roundRect(x - 20, y - 20, 40, 58, 8);
  context.fill();
  context.stroke();
  context.fillStyle = '#1e293b';
  context.strokeStyle = '#1e293b';
  context.lineWidth = 1.7;
  context.font = '700 13px Arial, sans-serif';
  context.textAlign = 'center';
  context.fillText('N', x, y - 7);
  context.beginPath();
  context.moveTo(x, y);
  context.lineTo(x - 8, y + 25);
  context.lineTo(x, y + 20);
  context.lineTo(x + 8, y + 25);
  context.closePath();
  context.stroke();
  context.beginPath();
  context.moveTo(x, y); context.lineTo(x, y + 20); context.stroke();
  context.restore();
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

function drawReferenceCard(
  context, map, mapHeight, requestedLengthKm, vectorBasemap, dataSourceAttribution,
) {
  const scale = getScaleBarDetails(map, requestedLengthKm, 112);
  if (!scale) return;
  const boxWidth = 224;
  const baseHeight = vectorBasemap ? 92 : 76;
  const boxHeight = baseHeight + (dataSourceAttribution ? 16 : 0);
  const x = 16;
  const y = mapHeight - boxHeight - 42;

  context.save();
  drawFloatingCard(context, x, y, boxWidth, boxHeight);
  context.strokeStyle = '#333333';
  context.lineWidth = 1.5;
  const barX = x + 14;
  const barY = y + 27;
  context.beginPath();
  context.moveTo(barX, barY - 5); context.lineTo(barX, barY + 3);
  context.moveTo(barX, barY); context.lineTo(barX + scale.pixelLength, barY);
  context.moveTo(barX + scale.pixelLength, barY - 5); context.lineTo(barX + scale.pixelLength, barY + 3);
  context.stroke();
  context.fillStyle = '#334155';
  context.font = '600 10px Arial, sans-serif';
  context.textAlign = 'left';
  context.fillText(scale.label, barX, y + 15);
  context.fillStyle = '#64748b';
  context.font = '10px Arial, sans-serif';
  context.fillText('WGS 84 · EPSG:4326', barX, y + 48);
  if (vectorBasemap) context.fillText('OpenFreeMap · © OpenMapTiles', barX, y + 64);
  context.fillText('© OpenStreetMap contributors', barX, y + (vectorBasemap ? 80 : 64));
  if (dataSourceAttribution) {
    context.fillText(dataSourceAttribution, barX, y + (vectorBasemap ? 96 : 80));
  }
  context.restore();
}

function formatCoordinate(latitude, longitude) {
  return `${Math.abs(latitude).toFixed(2)}°${latitude >= 0 ? 'N' : 'S'} / `
    + `${Math.abs(longitude).toFixed(2)}°${longitude >= 0 ? 'E' : 'W'}`;
}

function drawCornerCoordinates(context, map, width, height) {
  const bounds = map.getBounds();
  const corners = [
    [formatCoordinate(bounds.getNorth(), bounds.getWest()), 16, 16, 'left', 'top'],
    [formatCoordinate(bounds.getNorth(), bounds.getEast()), width - 16, 16, 'right', 'top'],
    [formatCoordinate(bounds.getSouth(), bounds.getWest()), 16, height - 14, 'left', 'alphabetic'],
    [formatCoordinate(bounds.getSouth(), bounds.getEast()), width - 16, height - 14, 'right', 'alphabetic'],
  ];
  context.save();
  context.font = '9px Arial, sans-serif';
  corners.forEach(([label, x, y, align, baseline]) => {
    context.textAlign = align;
    context.textBaseline = baseline;
    const measured = context.measureText(label).width;
    const backgroundX = align === 'right' ? x - measured - 5 : x - 5;
    context.fillStyle = 'rgba(255, 255, 255, 0.58)';
    context.fillRect(backgroundX, baseline === 'top' ? y - 3 : y - 11, measured + 10, 15);
    context.fillStyle = '#7b8798';
    context.fillText(label, x, y);
  });
  context.restore();
}

function drawDistrictLabels(context, container, mapRect) {
  const labels = [...container.querySelectorAll('.district-map-label-line')];
  context.save();
  context.font = '650 9px Arial, sans-serif';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.lineJoin = 'round';
  context.strokeStyle = 'rgba(255, 255, 255, 0.96)';
  context.lineWidth = 2.5;
  context.fillStyle = '#334155';
  labels.forEach((label) => {
    const rect = label.getBoundingClientRect();
    const x = rect.left - mapRect.left + (rect.width / 2);
    const y = rect.top - mapRect.top + (rect.height / 2);
    const text = label.textContent.trim();
    if (!text || x < 0 || y < 0 || x > mapRect.width || y > mapRect.height) return;
    context.strokeText(text, x, y, Math.max(40, rect.width));
    context.fillText(text, x, y, Math.max(40, rect.width));
  });
  context.restore();
}

export async function exportLeafletMap({
  map, heading, legendGroups, presentation = {}, basemapStyle = resolveBasemapStyle(), basemap,
  dataSourceAttribution,
}) {
  if (!map) throw new Error('The interactive map is not ready.');
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
  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, width, mapHeight);
  context.beginPath(); context.rect(0, 0, width, mapHeight); context.clip();
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

  drawCustomPointMarkers(context, container, mapRect);

  drawDistrictLabels(context, container, mapRect);
  drawMapHeading(context, width, heading);
  drawCornerCoordinates(context, map, width, mapHeight);
  if (presentation.show_compass) drawCompass(context, width);
  drawReferenceCard(
    context,
    map,
    mapHeight,
    presentation.scale_bar_km,
    Boolean(vectorCanvas),
    dataSourceAttribution,
  );
  drawLegend(context, width, mapHeight, legendGroups);

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
