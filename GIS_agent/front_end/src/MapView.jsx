import {
  forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState,
} from 'react';
import L from 'leaflet';
import { GeoJSON, MapContainer, useMap } from 'react-leaflet';
import Basemap from './Basemap.jsx';
import { bindRoadInteraction } from './roadInteraction.js';
import { framingOptions, HONG_KONG_BOUNDS } from './mapFraming.js';
import { exportLeafletMap, getScaleBarDetails } from './mapExport.js';
import { resolveBasemapStyle } from './basemapStyle.js';
import {
  createLayerPresentation,
  getDisplayName,
  normalizeMapLayers,
  resolveMapHeading,
} from './mapPresentation.js';
import 'leaflet/dist/leaflet.css';

const HONG_KONG_CENTER = [22.3193, 114.1694];

function ViewportMetadata({ requestedScaleKm, onChange }) {
  const map = useMap();

  useEffect(() => {
    const update = () => {
      const bounds = map.getBounds();
      const coordinate = (latitude, longitude) => (
        `${Math.abs(latitude).toFixed(2)}°${latitude >= 0 ? 'N' : 'S'} / `
        + `${Math.abs(longitude).toFixed(2)}°${longitude >= 0 ? 'E' : 'W'}`
      );
      onChange({
        corners: {
          northwest: coordinate(bounds.getNorth(), bounds.getWest()),
          northeast: coordinate(bounds.getNorth(), bounds.getEast()),
          southwest: coordinate(bounds.getSouth(), bounds.getWest()),
          southeast: coordinate(bounds.getSouth(), bounds.getEast()),
        },
        scale: getScaleBarDetails(map, requestedScaleKm, 112),
      });
    };

    update();
    map.on('moveend zoomend resize', update);
    return () => {
      map.off('moveend zoomend resize', update);
    };
  }, [map, onChange, requestedScaleKm]);

  return null;
}

function MapBridge({ onReady }) {
  const map = useMap();
  useEffect(() => {
    onReady(map);
    return () => onReady(null);
  }, [map, onReady]);
  return null;
}

function FitLayers({ layers, resultVersion }) {
  const map = useMap();
  useEffect(() => {
    const featureCollections = layers.map((layer) => layer.geojson).filter(Boolean);
    const group = L.featureGroup(featureCollections.map((data) => L.geoJSON(data)));
    const dataBounds = group.getBounds();
    const bounds = dataBounds.isValid() ? dataBounds : L.latLngBounds(HONG_KONG_BOUNDS);
    const fit = () => {
      map.invalidateSize({ pan: false });
      const size = map.getSize();
      if (size.x > 0 && size.y > 0) map.fitBounds(bounds, framingOptions(size.x, size.y));
    };
    let frame = requestAnimationFrame(fit);
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(fit);
    });
    observer.observe(map.getContainer());
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [layers, map, resultVersion]);
  return null;
}

function titleCaseDistrictName(value) {
  return String(value || '')
    .toLocaleLowerCase('en')
    .replace(/\b[a-z]/g, (letter) => letter.toLocaleUpperCase('en'));
}

function districtLabelLines(value) {
  const label = titleCaseDistrictName(value);
  if (label.length <= 14 || !label.includes(' ')) return [label];
  const words = label.split(/\s+/);
  let bestSplit = 1;
  let bestScore = Number.POSITIVE_INFINITY;
  for (let index = 1; index < words.length; index += 1) {
    const first = words.slice(0, index).join(' ');
    const second = words.slice(index).join(' ');
    const score = Math.max(first.length, second.length) + (Math.abs(first.length - second.length) * 0.35);
    if (score < bestScore) {
      bestScore = score;
      bestSplit = index;
    }
  }
  return [words.slice(0, bestSplit).join(' '), words.slice(bestSplit).join(' ')];
}

function labelDimensions(lines) {
  const longestLine = Math.max(...lines.map((line) => line.length));
  return {
    width: Math.min(108, Math.max(46, Math.round((longestLine * 5.4) + 10))),
    height: lines.length > 1 ? 28 : 18,
  };
}

function rectanglesOverlap(first, second, padding = 3) {
  return !(
    first.right + padding <= second.left
    || first.left >= second.right + padding
    || first.bottom + padding <= second.top
    || first.top >= second.bottom + padding
  );
}

function overlapArea(first, second) {
  const width = Math.max(0, Math.min(first.right, second.right) - Math.max(first.left, second.left));
  const height = Math.max(0, Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top));
  return width * height;
}

function labelCandidates(anchor, dimensions) {
  const candidates = [{ x: anchor.x, y: anchor.y }];
  const minimumRadius = Math.max(20, (Math.max(dimensions.width, dimensions.height) / 2) + 8);
  const angles = [-90, 90, 0, 180, -45, 45, -135, 135];
  [minimumRadius, minimumRadius + 18, minimumRadius + 36, minimumRadius + 54].forEach((radius) => {
    angles.forEach((angle) => {
      const radians = (angle * Math.PI) / 180;
      candidates.push({
        x: anchor.x + (Math.cos(radians) * radius),
        y: anchor.y + (Math.sin(radians) * radius),
      });
    });
  });
  return candidates;
}

function candidateRectangle(candidate, dimensions) {
  return {
    left: candidate.x - (dimensions.width / 2),
    right: candidate.x + (dimensions.width / 2),
    top: candidate.y - (dimensions.height / 2),
    bottom: candidate.y + (dimensions.height / 2),
  };
}

function chooseLabelPosition(anchor, dimensions, occupied, mapSize) {
  const safeBounds = {
    left: 12,
    right: mapSize.x - 12,
    top: 82,
    bottom: mapSize.y - 34,
  };
  const candidates = labelCandidates(anchor, dimensions)
    .map((candidate) => ({
      ...candidate,
      rectangle: candidateRectangle(candidate, dimensions),
      distance: Math.hypot(candidate.x - anchor.x, candidate.y - anchor.y),
    }))
    .filter(({ rectangle }) => (
      rectangle.left >= safeBounds.left
      && rectangle.right <= safeBounds.right
      && rectangle.top >= safeBounds.top
      && rectangle.bottom <= safeBounds.bottom
    ));

  const clearCandidate = candidates.find(({ rectangle }) => (
    occupied.every((placed) => !rectanglesOverlap(rectangle, placed))
  ));
  if (clearCandidate) return clearCandidate;

  return candidates.sort((first, second) => {
    const firstOverlap = occupied.reduce((area, placed) => area + overlapArea(first.rectangle, placed), 0);
    const secondOverlap = occupied.reduce((area, placed) => area + overlapArea(second.rectangle, placed), 0);
    return (firstOverlap - secondOverlap) || (first.distance - second.distance);
  })[0] || {
    ...anchor,
    rectangle: candidateRectangle(anchor, dimensions),
    distance: 0,
  };
}

function DistrictLabels({ layer, resultVersion }) {
  const map = useMap();

  useEffect(() => {
    if (!layer?.geojson?.features?.length) return undefined;
    if (!map.getPane('districtLabelsPane')) {
      const pane = map.createPane('districtLabelsPane');
      pane.style.zIndex = '450';
      pane.style.pointerEvents = 'none';
    }

    const labelGroup = L.layerGroup().addTo(map);
    const drawLabels = () => {
      labelGroup.clearLayers();
      const mapSize = map.getSize();
      const labelItems = layer.geojson.features
        .filter((feature) => (
          feature.properties?.district_name && feature.geometry?.type?.includes('Polygon')
        ))
        .map((feature) => {
          const bounds = L.geoJSON(feature).getBounds();
          const lines = districtLabelLines(feature.properties.district_name);
          return {
            feature,
            bounds,
            lines,
            dimensions: labelDimensions(lines),
            projectedArea: bounds.isValid()
              ? Math.abs(
                (map.latLngToContainerPoint(bounds.getNorthEast()).x
                  - map.latLngToContainerPoint(bounds.getSouthWest()).x)
                * (map.latLngToContainerPoint(bounds.getNorthEast()).y
                  - map.latLngToContainerPoint(bounds.getSouthWest()).y),
              )
              : Number.POSITIVE_INFINITY,
          };
        })
        .filter((item) => item.bounds.isValid())
        .sort((first, second) => first.projectedArea - second.projectedArea);

      const occupied = [];
      labelItems.forEach((item) => {
        const anchorLatLng = item.bounds.getCenter();
        const anchor = map.latLngToContainerPoint(anchorLatLng);
        const position = chooseLabelPosition(anchor, item.dimensions, occupied, mapSize);
        occupied.push(position.rectangle);
        const labelLatLng = map.containerPointToLatLng([position.x, position.y]);

        if (position.distance > 12) {
          L.polyline([anchorLatLng, labelLatLng], {
            pane: 'overlayPane',
            color: '#64748b',
            weight: 0.8,
            opacity: 0.72,
            dashArray: '2 3',
            interactive: false,
          }).addTo(labelGroup);
        }

        const text = document.createElement('span');
        text.className = 'district-map-label-text';
        item.lines.forEach((line) => {
          const lineElement = document.createElement('span');
          lineElement.className = 'district-map-label-line';
          lineElement.textContent = line;
          text.appendChild(lineElement);
        });
        L.marker(labelLatLng, {
          pane: 'districtLabelsPane',
          interactive: false,
          keyboard: false,
          alt: '',
          icon: L.divIcon({
            className: 'district-map-label',
            html: text,
            iconSize: [item.dimensions.width, item.dimensions.height],
            iconAnchor: [item.dimensions.width / 2, item.dimensions.height / 2],
          }),
        }).addTo(labelGroup);
      });
    };

    drawLabels();
    map.on('moveend zoomend resize', drawLabels);
    return () => {
      map.off('moveend zoomend resize', drawLabels);
      labelGroup.remove();
    };
  }, [layer, map, resultVersion]);

  return null;
}

function popupContent(properties = {}, analysis = {}) {
  const container = document.createElement('div');
  container.className = 'feature-popup';
  const heading = document.createElement('strong');
  heading.textContent = getDisplayName(properties);
  container.appendChild(heading);

  const preferredFields = [
    ['snap_distance_m', 'Road snap distance (m)'],
    ['status', 'Network match status'],
    ['radius_m', 'Buffer radius (m)'],
    ['matched_count', 'Facilities in range'],
    ['distance_m', 'Distance from center (m)'],
    ['latitude', 'Latitude'],
    ['longitude', 'Longitude'],
    ['geocoder_source', 'Location source'],
    ['FACILITY_TYPE', 'Facility type'],
    ['facility_type', 'Facility type'],
    ['FacilityType', 'Facility type'],
    ['count', 'Facility count'],
    ['facility_count', 'Facility count'],
    ['density_per_km2', 'Density (facilities/km²)'],
    ['area_km2', 'Area (km²)'],
    ['metric_value', analysis.metric === 'density_per_km2' ? 'Current density' : 'Current value'],
  ];
  const shown = new Set();
  preferredFields.forEach(([field, label]) => {
    const value = properties[field];
    if (value === undefined || value === null || shown.has(label)) return;
    const row = document.createElement('div');
    const formatted = typeof value === 'number'
      ? value.toLocaleString(undefined, { maximumFractionDigits: 3 })
      : value;
    row.textContent = `${label}: ${formatted}`;
    container.appendChild(row);
    shown.add(label);
  });
  return container;
}

function markerSvg(symbol) {
  if (symbol === 'location') {
    return `<span class="geoai-symbol-shell geoai-location-symbol" aria-hidden="true">
      <svg viewBox="0 0 32 38" focusable="false">
        <path class="geoai-symbol-fill" d="M16 2.5A11.5 11.5 0 0 0 4.5 14c0 8.8 11.5 20.8 11.5 20.8S27.5 22.8 27.5 14A11.5 11.5 0 0 0 16 2.5Z" />
        <circle cx="16" cy="14" r="4.2" fill="#fff" />
        <circle cx="16" cy="14" r="1.65" class="geoai-symbol-core" />
      </svg>
    </span>`;
  }
  if (symbol === 'school') {
    return `<span class="geoai-symbol-shell geoai-school-symbol" aria-hidden="true">
      <svg viewBox="0 0 28 28" focusable="false">
        <path class="geoai-symbol-fill" d="M14 1.8 25 6.9v8.9c0 5.1-4.3 8.8-11 10.4C7.3 24.6 3 20.9 3 15.8V6.9Z" />
        <path class="geoai-symbol-line" d="m7.4 11.1 6.6-3.6 6.6 3.6M9.4 12.3v6.2m3-6.2v6.2m3.2-6.2v6.2m3-6.2v6.2M7.8 19h12.4" />
      </svg>
    </span>`;
  }
  return `<span class="geoai-symbol-shell geoai-facility-symbol" aria-hidden="true">
    <svg viewBox="0 0 28 28" focusable="false">
      <rect class="geoai-symbol-fill" x="3" y="3" width="22" height="22" rx="7" />
      <path class="geoai-symbol-line" d="M14 8v12M8 14h12" />
    </svg>
  </span>`;
}

function safeMarkerColor(value, fallback) {
  return /^#[0-9a-f]{3,8}$/i.test(String(value || '')) ? value : fallback;
}

function createPointIcon(symbol, pointStyle) {
  const isLocation = symbol === 'location';
  const size = isLocation ? [32, 38] : [22, 22];
  const wrapper = document.createElement('div');
  wrapper.innerHTML = markerSvg(symbol);
  wrapper.style.setProperty('--symbol-color', safeMarkerColor(pointStyle.fillColor, '#d97772'));
  wrapper.style.setProperty('--symbol-stroke', safeMarkerColor(pointStyle.color, '#ffffff'));
  return L.divIcon({
    className: `geoai-point-marker geoai-${symbol}-marker`,
    html: wrapper,
    iconSize: size,
    iconAnchor: isLocation ? [16, 34] : [11, 11],
    popupAnchor: isLocation ? [0, -31] : [0, -11],
    tooltipAnchor: isLocation ? [0, -28] : [0, -10],
  });
}

function InteractiveLayer({ layer, resultVersion }) {
  const map = useMap();
  const geoJsonLayerRef = useRef(null);

  const applyPointStyle = (feature, leafletLayer) => {
    if (!layer.pointStyle) return;
    const pointStyle = layer.pointStyle(feature, map.getZoom());
    if (layer.pointSymbol && leafletLayer.setIcon) {
      leafletLayer.setIcon(createPointIcon(layer.pointSymbol, pointStyle));
      return;
    }
    leafletLayer.setStyle?.(pointStyle);
    if (Number.isFinite(pointStyle.radius)) leafletLayer.setRadius?.(pointStyle.radius);
  };

  useEffect(() => {
    if (!layer.pointStyle) return undefined;
    const updatePointSymbols = () => {
      geoJsonLayerRef.current?.eachLayer((leafletLayer) => {
        if (leafletLayer.feature) applyPointStyle(leafletLayer.feature, leafletLayer);
      });
    };
    updatePointSymbols();
    map.on('zoomend', updatePointSymbols);
    return () => map.off('zoomend', updatePointSymbols);
  });

  const onEachFeature = (feature, leafletLayer) => {
    const properties = feature.properties || {};
    const isBufferArea = layer.analysis?.visual_role === 'buffer_area';
    const displayName = getDisplayName(properties);
    if (!isBufferArea) {
      leafletLayer.bindTooltip(displayName, { sticky: true, direction: 'top' });
    }
    leafletLayer.bindPopup(popupContent(properties, layer.analysis));
    if (layer.kind === 'line') {
      bindRoadInteraction(leafletLayer, layer.style(feature));
      return;
    }
    if (layer.pointSymbol) {
      leafletLayer.on('add', () => {
        const element = leafletLayer.getElement?.();
        element?.setAttribute('aria-label', displayName);
        element?.setAttribute('title', displayName);
      });
    }
    leafletLayer.on({
      mouseover: () => {
        if (layer.pointSymbol) {
          leafletLayer.getElement()?.classList.add('is-hovered');
          leafletLayer.setZIndexOffset?.(1000);
        } else if (layer.pointStyle) {
          const baseStyle = layer.pointStyle(feature, map.getZoom());
          leafletLayer.setStyle?.({
            ...baseStyle,
            weight: Math.max(1.15, baseStyle.weight + 0.35),
            opacity: 0.9,
            fillOpacity: Math.min(1, baseStyle.fillOpacity + 0.12),
          });
          leafletLayer.setRadius?.(baseStyle.radius + 0.9);
          leafletLayer.bringToFront?.();
        } else if (layer.analysis?.method === 'network_service_area') {
          leafletLayer.setStyle?.({ ...layer.style(feature), weight: layer.kind === 'line' ? 2 : 0 });
        } else if (isBufferArea) {
          const baseStyle = layer.style(feature);
          leafletLayer.setStyle?.({
            ...baseStyle,
            weight: Math.max(1.8, Number(baseStyle.weight) || 0),
            fillOpacity: Math.min(0.09, (Number(baseStyle.fillOpacity) || 0) + 0.035),
          });
        } else {
          leafletLayer.setStyle?.({ weight: 1.8, fillOpacity: 0.88 });
        }
      },
      mouseout: () => {
        if (layer.pointSymbol) {
          leafletLayer.getElement()?.classList.remove('is-hovered');
          leafletLayer.setZIndexOffset?.(0);
        } else if (layer.pointStyle) applyPointStyle(feature, leafletLayer);
        else leafletLayer.setStyle?.(layer.style(feature));
      },
    });
  };

  return (
    <GeoJSON
      ref={geoJsonLayerRef}
      key={`${layer.id}-${resultVersion}`}
      data={layer.geojson}
      style={layer.style}
      pointToLayer={layer.pointStyle
        ? (feature, latlng) => (layer.pointSymbol
          ? L.marker(latlng, {
            icon: createPointIcon(layer.pointSymbol, layer.pointStyle(feature)),
            keyboard: true,
            riseOnHover: true,
            title: getDisplayName(feature.properties),
            alt: getDisplayName(feature.properties),
          })
          : L.circleMarker(latlng, layer.pointStyle(feature)))
        : undefined}
      onEachFeature={onEachFeature}
    />
  );
}

function LegendPointSymbol({ entry }) {
  if (entry.symbol === 'school') {
    return <svg className="legend-icon-svg" viewBox="0 0 28 28" aria-hidden="true">
      <path d="M14 1.8 25 6.9v8.9c0 5.1-4.3 8.8-11 10.4C7.3 24.6 3 20.9 3 15.8V6.9Z"
        fill={entry.color} stroke={entry.strokeColor} strokeWidth="1.15" />
      <path d="m7.4 11.1 6.6-3.6 6.6 3.6M9.4 12.3v6.2m3-6.2v6.2m3.2-6.2v6.2m3-6.2v6.2M7.8 19h12.4"
        fill="none" stroke="#fff" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" />
    </svg>;
  }
  if (entry.symbol === 'location') {
    return <svg className="legend-icon-svg" viewBox="0 0 32 38" aria-hidden="true">
      <path d="M16 2.5A11.5 11.5 0 0 0 4.5 14c0 8.8 11.5 20.8 11.5 20.8S27.5 22.8 27.5 14A11.5 11.5 0 0 0 16 2.5Z"
        fill={entry.color} stroke={entry.strokeColor} strokeWidth="1.4" />
      <circle cx="16" cy="14" r="4.2" fill="#fff" />
      <circle cx="16" cy="14" r="1.65" fill={entry.color} />
    </svg>;
  }
  if (entry.symbol === 'facility') {
    return <svg className="legend-icon-svg" viewBox="0 0 28 28" aria-hidden="true">
      <rect x="3" y="3" width="22" height="22" rx="7" fill={entry.color}
        stroke={entry.strokeColor} strokeWidth="1.15" />
      <path d="M14 8v12M8 14h12" fill="none" stroke="#fff" strokeWidth="1.55" strokeLinecap="round" />
    </svg>;
  }
  return <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" style={{ flexShrink: 0 }}>
    <circle cx="6" cy="6" r="4" fill={entry.color} fillOpacity={entry.fillOpacity}
      stroke={entry.strokeColor} strokeOpacity={entry.strokeOpacity} strokeWidth={entry.strokeWidth} />
  </svg>;
}

function MapLegend({ groups }) {
  const visibleGroups = groups.filter((group) => group.entries.length > 0);
  if (visibleGroups.length === 0) return null;
  return (
    <aside className="map-legend" aria-label="Map legend">
      {visibleGroups.map((group, groupIndex) => (
        <div className="legend-group" key={`${group.title}-${groupIndex}`}>
          <h3>{group.title}</h3>
          {group.subtitle && <p className="legend-subtitle">{group.subtitle}</p>}
          {group.note && <p className="legend-note">{group.note}</p>}
          {group.entries.map((entry) => (
            <div className="legend-entry" key={`${entry.label}-${entry.color}`}>
              {entry.shape === 'circle' ? <LegendPointSymbol entry={entry} /> : <span
                className={`legend-symbol is-${entry.shape} ${entry.pattern ? `is-${entry.pattern}` : ''}`}
                style={{
                  backgroundColor: entry.color,
                  borderColor: entry.strokeColor,
                  opacity: entry.fillOpacity,
                }}
                aria-hidden="true"
              />}
              <span>{entry.label}</span>
            </div>
          ))}
          {group.overflowCount > 0 && <p>+ {group.overflowCount} more categories</p>}
        </div>
      ))}
    </aside>
  );
}

function CornerCoordinates({ corners }) {
  if (!corners) return null;
  return Object.entries(corners).map(([position, label]) => (
    <span className={`map-coordinate is-${position}`} key={position}>{label}</span>
  ));
}

function MapReferenceCard({ scale, vectorBasemap, locationAttribution }) {
  if (!scale) return null;
  return (
    <aside className="map-reference-card" aria-label="Map scale, coordinate reference system, and source">
      <div className="map-scale">
        <span className="map-scale-label">{scale.label}</span>
        <span className="map-scale-line" style={{ width: `${scale.pixelLength}px` }} aria-hidden="true" />
      </div>
      <span>WGS 84 · EPSG:4326</span>
      {vectorBasemap && <span><a href="https://openfreemap.org/" target="_blank" rel="noreferrer">OpenFreeMap</a> · <a href="https://openmaptiles.org/" target="_blank" rel="noreferrer">© OpenMapTiles</a></span>}
      <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
        © OpenStreetMap contributors
      </a>
      {locationAttribution && (
        <a href={locationAttribution.url} target="_blank" rel="noreferrer">
          {locationAttribution.label}
        </a>
      )}
    </aside>
  );
}

function Compass() {
  return (
    <div className="map-compass" aria-label="North arrow">
      <svg viewBox="0 0 44 62" role="img" aria-hidden="true">
        <text x="22" y="13" textAnchor="middle">N</text>
        <path d="M22 19 L12 48 L22 42 L32 48 Z" />
        <path d="M22 19 V42" />
      </svg>
    </div>
  );
}

const MapView = forwardRef(function MapView({
  mapLayers,
  geojson,
  analysis,
  mapPresentation = {},
  resultVersion,
}, ref) {
  const [map, setMap] = useState(null);
  const [basemap, setBasemap] = useState(null);
  const [viewportMetadata, setViewportMetadata] = useState(null);
  const layers = useMemo(
    () => normalizeMapLayers(mapLayers, geojson, analysis),
    [mapLayers, geojson, analysis],
  );
  const presentedLayers = useMemo(() => layers.map(createLayerPresentation), [layers]);
  const basemapStyle = useMemo(() => resolveBasemapStyle(layers), [layers]);
  const effectiveBasemapStyle = useMemo(() => ({
    ...basemapStyle,
    filter: basemap?.kind === 'raster'
      ? 'saturate(0.68) contrast(0.9) brightness(1.08)'
      : basemapStyle.filter,
  }), [basemap?.kind, basemapStyle]);
  const effectivePresentation = useMemo(() => ({
    ...mapPresentation,
    show_compass: true,
    show_gridlines: false,
    scale_bar_km: Number(mapPresentation.scale_bar_km) || 10,
  }), [mapPresentation]);
  const heading = resolveMapHeading(effectivePresentation, presentedLayers);
  const legendGroups = presentedLayers.map((layer) => layer.legend);
  const locationAttribution = useMemo(() => {
    const geocoding = presentedLayers
      .map((layer) => layer.analysis?.geocoding)
      .find((value) => value?.provider_url);
    if (geocoding) return { label: `Location: ${geocoding.provider}`, url: geocoding.provider_url };
    return presentedLayers.some((layer) => layer.analysis?.sources?.length)
      ? { label: 'Data: CSDI / Hong Kong Government', url: 'https://portal.csdi.gov.hk/' } : null;
  }, [presentedLayers]);
  const districtLabelLayer = [...presentedLayers].reverse().find(
    (layer) => layer.geojson?.features?.some(
      (feature) => feature.geometry?.type?.includes('Polygon') && feature.properties?.district_name,
    ),
  );

  useImperativeHandle(ref, () => ({
    exportPng: () => exportLeafletMap({
      map,
      heading,
      legendGroups,
      presentation: effectivePresentation,
      basemapStyle: effectiveBasemapStyle,
      basemap,
      dataSourceAttribution: locationAttribution?.label,
    }),
    getTitle: () => heading.title,
  }), [
    effectivePresentation, heading, legendGroups, map, effectiveBasemapStyle,
    basemap, locationAttribution,
  ]);

  return (
    <div
      className="webgis-map"
      aria-label="Interactive map of Hong Kong"
      style={{
        '--basemap-filter': effectiveBasemapStyle.filter,
        '--basemap-background': effectiveBasemapStyle.background,
      }}
    >
      <MapContainer
        center={HONG_KONG_CENTER}
        zoom={10}
        zoomSnap={0.1}
        minZoom={2}
        scrollWheelZoom
        attributionControl={false}
        className="leaflet-map"
      >
        <Basemap onReady={setBasemap} />
        <MapBridge onReady={setMap} />
        <ViewportMetadata
          requestedScaleKm={effectivePresentation.scale_bar_km}
          onChange={setViewportMetadata}
        />
        {presentedLayers.map((layer) => (
          <InteractiveLayer key={layer.id} layer={layer} resultVersion={resultVersion} />
        ))}
        <DistrictLabels layer={districtLabelLayer} resultVersion={resultVersion} />
        <FitLayers layers={presentedLayers} resultVersion={resultVersion} />
      </MapContainer>
      <header className="map-title-card">
        <strong>{heading.title}</strong>
        {heading.subtitle && <span>{heading.subtitle}</span>}
      </header>
      <CornerCoordinates corners={viewportMetadata?.corners} />
      <MapLegend groups={legendGroups} />
      <MapReferenceCard
        scale={viewportMetadata?.scale}
        vectorBasemap={basemap?.kind === 'vector'}
        locationAttribution={locationAttribution}
      />
      {effectivePresentation.show_compass && <Compass />}
    </div>
  );
});

export default MapView;
