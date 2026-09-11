const CATEGORY_COLORS = ['#2563eb', '#dc2626', '#16a34a', '#9333ea', '#ea580c', '#0891b2'];
const SEQUENTIAL_COLORS = ['#fee8d2', '#fdbb84', '#fc8d59', '#e34a33', '#b30000'];
const ZERO_COLOR = '#e2e8f0';
const NO_DATA_COLOR = '#f8fafc';

export function getDisplayName(properties = {}) {
  return properties.district_name
    || properties.NAME
    || properties.name
    || properties.ENAME
    || properties.Name
    || properties.FACILITY_TYPE
    || properties.facility_type
    || 'Spatial feature';
}

function hashCategory(value) {
  return [...String(value)].reduce((hash, char) => ((hash * 31) + char.charCodeAt(0)) | 0, 0);
}

function categoryColor(value) {
  return CATEGORY_COLORS[Math.abs(hashCategory(value)) % CATEGORY_COLORS.length];
}

function paletteColor(palette, index, count) {
  if (!Array.isArray(palette) || palette.length === 0) return numericColor(index, count);
  if (palette.length === 1 || count <= 1) return palette[Math.floor((palette.length - 1) / 2)];
  const paletteIndex = Math.round((index / (count - 1)) * (palette.length - 1));
  return palette[Math.max(0, Math.min(palette.length - 1, paletteIndex))];
}

function configuredCategoryColor(analysis, value) {
  const configured = analysis.category_colors?.[String(value)];
  return typeof configured === 'string' && configured.trim() ? configured : categoryColor(value);
}

function metricFormatOptions(metric, fractionDigits) {
  if (metric === 'count') return { maximumFractionDigits: 0 };
  if (metric === 'density_per_km2') {
    const digits = fractionDigits || 2;
    return { minimumFractionDigits: digits, maximumFractionDigits: digits };
  }
  return { maximumFractionDigits: 2 };
}

function formatMetricValue(value, metric, fractionDigits) {
  return Number(value).toLocaleString(undefined, metricFormatOptions(metric, fractionDigits));
}

function quantileBreaks(values, requestedBins) {
  if (values.length === 0) return [];
  const sorted = [...values].sort((a, b) => a - b);
  const uniqueCount = new Set(sorted).size;
  const binCount = Math.max(1, Math.min(Number(requestedBins) || 5, uniqueCount));
  const breaks = [];
  for (let index = 1; index <= binCount; index += 1) {
    const position = Math.max(0, Math.ceil((index * sorted.length) / binCount) - 1);
    const value = sorted[position];
    if (breaks.at(-1) !== value) breaks.push(value);
  }
  return breaks;
}

function equalIntervalCountBreaks(values, requestedBins) {
  if (values.length === 0) return [];
  const minimum = Math.min(...values.map(Math.round));
  const maximum = Math.max(...values.map(Math.round));
  const integerSpan = maximum - minimum + 1;
  const requested = Math.min(3, Math.max(1, Number(requestedBins) || 3));
  const binCount = Math.min(requested, Math.max(1, Math.floor(integerSpan / 2)));
  const baseSize = Math.floor(integerSpan / binCount);
  const remainder = integerSpan % binCount;
  const breaks = [];
  let cursor = minimum;
  for (let index = 0; index < binCount; index += 1) {
    cursor += baseSize + (index < remainder ? 1 : 0) - 1;
    breaks.push(cursor);
    cursor += 1;
  }
  return breaks;
}

function numericColor(index, count) {
  if (count <= 1) return SEQUENTIAL_COLORS[2];
  const paletteIndex = Math.round((index / (count - 1)) * (SEQUENTIAL_COLORS.length - 1));
  return SEQUENTIAL_COLORS[paletteIndex];
}

function legendTitle(analysis = {}, kind = 'polygon') {
  if (analysis.method === 'network_distance') return analysis.visual_role === 'buffer_center' ? 'Analysis center' : 'Facilities in range';
  if (analysis.method === 'network_service_area') return kind === 'point'
    ? (analysis.visual_role === 'network_targets' ? 'Facilities in range' : 'Analysis origins') : 'Estimated driving coverage';
  if (analysis.method === 'buffer_coverage') {
    if (analysis.visual_role === 'buffer_area') return 'Coverage area';
    if (analysis.visual_role === 'buffer_center') return 'Analysis center';
    if (analysis.visual_role === 'matched_facilities') return 'Facilities in range';
  }
  if (kind === 'point') return 'Facility type';
  if (analysis.metric === 'density_per_km2') return 'Facility density';
  if (analysis.metric === 'count') return 'Facility count';
  return analysis.column ? String(analysis.column).replaceAll('_', ' ') : 'Map values';
}

function legendUnit(analysis = {}, kind = 'polygon') {
  if (analysis.method === 'network_service_area') return `${analysis.time_minutes} min · ${analysis.speed_kmh} km/h scenario`;
  if (analysis.method === 'buffer_coverage') {
    if (analysis.visual_role === 'buffer_area') return `${Number(analysis.radius_m).toLocaleString()} m radius`;
    if (analysis.visual_role === 'matched_facilities') {
      return `${Number(analysis.matched_count || 0).toLocaleString()} matched point${Number(analysis.matched_count) === 1 ? '' : 's'}`;
    }
    if (analysis.sources?.length) return 'Official CSDI facility location';
    return analysis.geocoding ? 'Official LandsD location' : 'User-specified coordinate';
  }
  if (kind === 'point') return 'Point locations';
  if (analysis.metric === 'density_per_km2') return 'Facilities per km²';
  if (analysis.metric === 'count') return 'Number of facilities';
  return '';
}

function facilityLabel(analysis = {}) {
  const facilityTypes = Array.isArray(analysis.facility_types)
    ? analysis.facility_types.filter(Boolean)
    : [];
  if (analysis.dataset_id === 'session_upload') return 'Uploaded Facilities';
  if (facilityTypes.length === 1) {
    const label = String(facilityTypes[0]);
    return /s$/i.test(label) ? label : `${label}s`;
  }
  if (facilityTypes.length > 1) return `${facilityTypes[0]} and Other Facilities`;
  return 'Facilities';
}

function numericMetricValue(properties = {}) {
  const rawValue = properties.metric_value;
  if (rawValue === null || rawValue === undefined || rawValue === '') return null;
  const value = Number(rawValue);
  return Number.isFinite(value) ? value : null;
}

function numericRangeLabel(lowerBound, upperBound, metric, isFirst, fractionDigits) {
  if (metric === 'count') {
    const lower = Math.round(lowerBound) + (isFirst ? 0 : 1);
    const upper = Math.round(upperBound);
    if (lower >= upper) return formatMetricValue(upper, metric);
    return `${formatMetricValue(lower, metric)} – ${formatMetricValue(upper, metric)}`;
  }
  const lower = formatMetricValue(lowerBound, metric, fractionDigits);
  const upper = formatMetricValue(upperBound, metric, fractionDigits);
  return lower === upper ? upper : `${lower} – ${upper}`;
}

function pointCategory(properties = {}) {
  return properties.FACILITY_TYPE
    || properties.facility_type
    || properties.FacilityType
    || 'Facilities';
}

function pointRadiusForFeatureCount(featureCount) {
  if (featureCount > 2000) return 1.8;
  if (featureCount > 500) return 2.2;
  if (featureCount > 200) return 2.7;
  if (featureCount > 75) return 3.1;
  if (featureCount > 30) return 3.4;
  return 3.8;
}

export function normalizeMapLayers(mapLayers, geojson, analysis) {
  if (Array.isArray(mapLayers) && mapLayers.length > 0) return mapLayers;
  if (!geojson?.features?.length) return [];
  const geometryType = geojson.features[0]?.geometry?.type || '';
  return [{
    id: 'analysis_result',
    kind: geometryType.includes('Point') ? 'point' : 'polygon',
    geojson,
    analysis: analysis || {},
  }];
}

export function createLayerPresentation(layer) {
  const features = layer.geojson?.features || [];
  const analysis = layer.analysis || {};
  if (layer.kind === 'line') {
    if (analysis.visual_role === 'shortest_routes') {
      const categories = [...new Set(features.map(f => pointCategory(f.properties)))];
      return { ...layer, pointStyle: null,
        style: (feature) => ({ color: configuredCategoryColor(analysis, pointCategory(feature.properties)), weight: 2.5, opacity: .8, fill: false }),
        legend: { title: 'Shortest routes', subtitle: `${features.length} routes · Access connectors included`,
          entries: categories.map(category => ({color: configuredCategoryColor(analysis, category), label: category, shape: 'line'})), overflowCount: 0 } };
    }
    return { ...layer, pointStyle: null,
      style: () => ({ color: '#287e9c', weight: 1.5, opacity: 0.8, fill: false }),
      legend: { title: 'Reachable roads', subtitle: 'Directed network travel',
        entries: [{ color: '#287e9c', label: 'Reachable road segments', shape: 'square' }], overflowCount: 0 } };
  }
  const isPointLayer = layer.kind === 'point'
    || features.every((feature) => feature.geometry?.type?.includes('Point'));

  if (isPointLayer) {
    const categories = [...new Set(features.map((feature) => pointCategory(feature.properties)))];
    const configuredPointStyle = analysis.point_style || {};
    const requestedPointSymbol = String(configuredPointStyle.symbol || '').toLowerCase();
    const pointSymbol = ['school', 'facility', 'location'].includes(requestedPointSymbol)
      ? requestedPointSymbol
      : null;
    const allowsTransparentFill = analysis.visual_role === 'buffer_center';
    const baseRadius = Number(configuredPointStyle.radius_px)
      || pointRadiusForFeatureCount(features.length);
    const configuredFillOpacity = Number(configuredPointStyle.fill_opacity);
    const fillOpacity = Math.min(
      1,
      Math.max(
        allowsTransparentFill ? 0 : 0.78,
        Number.isFinite(configuredFillOpacity) ? configuredFillOpacity : 0.78,
      ),
    );
    const strokeColor = configuredPointStyle.stroke_color || '#334155';
    const strokeOpacity = Math.min(1, Math.max(0.95, Number(configuredPointStyle.stroke_opacity) || 0.95));
    const strokeWidth = Math.max(1, Number(configuredPointStyle.stroke_width_px) || 1);
    const pointStyle = (feature, zoomLevel = 10) => {
      const zoomAdjustment = Math.max(-0.12, Math.min(0.24, (Number(zoomLevel) - 10) * 0.08));
      return {
        radius: Number((baseRadius * (1 + zoomAdjustment)).toFixed(2)),
        color: strokeColor,
        opacity: strokeOpacity,
        weight: strokeWidth,
        fillColor: configuredCategoryColor(analysis, pointCategory(feature.properties)),
        fillOpacity,
      };
    };
    return {
      ...layer,
      style: (feature) => pointStyle(feature),
      pointStyle,
      pointSymbol,
      legend: {
        title: legendTitle(analysis, 'point'),
        subtitle: legendUnit(analysis, 'point'),
        entries: categories.slice(0, 8).map((category) => ({
          color: configuredCategoryColor(analysis, category),
          label: String(category),
          shape: 'circle',
          symbol: pointSymbol,
          fillOpacity,
          strokeColor,
          strokeOpacity,
          strokeWidth,
        })),
        overflowCount: Math.max(0, categories.length - 8),
      },
    };
  }

  const featureValues = features.map((feature) => numericMetricValue(feature.properties));
  const numericValues = featureValues.filter((value) => value !== null);

  if (numericValues.length > 0) {
    const isMappedMetric = ['count', 'density_per_km2'].includes(analysis.metric);
    const classificationValues = isMappedMetric
      ? numericValues.filter((value) => value > 0)
      : numericValues;
    const configuredBreaks = Array.isArray(analysis.classification_breaks)
      ? analysis.classification_breaks.map(Number).filter(Number.isFinite)
      : [];
    const breaks = configuredBreaks.length > 0
      ? configuredBreaks
      : analysis.metric === 'count'
        ? equalIntervalCountBreaks(classificationValues, analysis.classification_intervals)
        : quantileBreaks(classificationValues, Math.min(4, analysis.classification_intervals || 4));
    const configuredPalette = Array.isArray(analysis.palette)
      ? analysis.palette.filter((color) => typeof color === 'string' && color.trim())
      : [];
    const minimum = classificationValues.length > 0 ? Math.min(...classificationValues) : 0;
    const hasZero = isMappedMetric && numericValues.includes(0);
    const hasNoData = featureValues.includes(null);
    const fractionDigits = analysis.metric === 'density_per_km2'
      && numericValues.some((value) => Math.abs(value) > 0 && Math.abs(value) < 0.01)
      ? 3
      : 2;
    const colorForValue = (value) => {
      if (value === null) return NO_DATA_COLOR;
      if (isMappedMetric && value === 0) return analysis.zero_color || ZERO_COLOR;
      const foundIndex = breaks.findIndex((upperBound) => value <= upperBound);
      const index = foundIndex === -1 ? breaks.length - 1 : foundIndex;
      return paletteColor(
        configuredPalette,
        Math.max(0, index),
        Math.max(1, breaks.length),
      );
    };
    const classifiedEntries = breaks.map((upperBound, index) => ({
      color: paletteColor(configuredPalette, index, breaks.length),
      label: numericRangeLabel(
        index === 0 ? minimum : breaks[index - 1],
        upperBound,
        analysis.metric,
        index === 0,
        fractionDigits,
      ),
      shape: 'square',
    }));
    const entries = [
      ...(hasZero ? [{ color: analysis.zero_color || ZERO_COLOR, label: '0', shape: 'square', pattern: 'zero' }] : []),
      ...classifiedEntries,
      ...(hasNoData ? [{ color: NO_DATA_COLOR, label: 'No data', shape: 'square', pattern: 'no-data' }] : []),
    ];
    const classificationName = analysis.metric === 'count' ? 'Equal interval' : 'Quantile';
    return {
      ...layer,
      style: (feature) => {
        const value = numericMetricValue(feature.properties);
        return {
          color: value === null ? '#94a3b8' : '#475569',
          weight: value === null ? 1.2 : 0.9,
          dashArray: value === null ? '4 3' : undefined,
          fillColor: colorForValue(value),
          fillOpacity: value === null ? 0.72 : 0.78,
        };
      },
      pointStyle: null,
      legend: {
        title: legendTitle(analysis),
        subtitle: legendUnit(analysis),
        note: breaks.length > 0 ? `${breaks.length} classes · ${classificationName}` : '',
        entries,
        overflowCount: 0,
      },
    };
  }

  const categoryField = analysis.column;
  const categoryForFeature = (feature) => feature.properties?.[categoryField]
    ?? getDisplayName(feature.properties);
  const categories = [...new Set(features.map(categoryForFeature))];
  const configuredPolygonStyle = analysis.polygon_style || {};
  const polygonFillOpacity = Math.min(
    1,
    Math.max(0, Number(configuredPolygonStyle.fill_opacity ?? 0.7)),
  );
  const polygonStrokeOpacity = Math.min(
    1,
    Math.max(0, Number(configuredPolygonStyle.stroke_opacity ?? 1)),
  );
  const polygonStrokeWidth = Math.max(0, Number(configuredPolygonStyle.stroke_width_px ?? 1));
  const polygonStrokeColor = configuredPolygonStyle.stroke_color || '#475569';
  return {
    ...layer,
    style: (feature) => ({
      color: polygonStrokeColor,
      opacity: polygonStrokeOpacity,
      weight: polygonStrokeWidth,
      dashArray: configuredPolygonStyle.dash_array,
      className: analysis.visual_role === 'buffer_area' ? 'geoai-buffer-area' : undefined,
      fillColor: configuredCategoryColor(analysis, categoryForFeature(feature)),
      fillOpacity: polygonFillOpacity,
    }),
    pointStyle: null,
    legend: {
      title: legendTitle(analysis),
      subtitle: legendUnit(analysis),
      entries: categories.slice(0, 8).map((category) => ({
        color: configuredCategoryColor(analysis, category),
        label: analysis.visual_role === 'buffer_area' ? 'Search radius' : String(category),
        shape: 'square',
        fillOpacity: polygonFillOpacity,
        strokeColor: polygonStrokeColor,
      })),
      overflowCount: Math.max(0, categories.length - 8),
    },
  };
}

export function resolveMapHeading(presentation = {}, layers = []) {
  const analysis = layers.at(-1)?.analysis || {};
  const label = facilityLabel(analysis);
  const explicitTitle = String(presentation.title || '').trim();
  const inferredSubtitle = analysis.metric === 'density_per_km2'
    ? 'Facilities per km²'
    : analysis.metric === 'count' ? 'Facility count' : '';

  if (explicitTitle) {
    const titleWithoutUnit = explicitTitle
      .replace(/\s*\((?:facilities?|points?)\s+per\s+km(?:²|2)\)\s*$/i, '')
      .trim();
    return {
      title: titleWithoutUnit || explicitTitle,
      subtitle: String(presentation.subtitle || inferredSubtitle).trim(),
    };
  }

  if (analysis.method === 'point_in_polygon') {
    return {
      title: analysis.metric === 'density_per_km2'
        ? `${label} Density by District`
        : `${label} by District`,
      subtitle: inferredSubtitle,
    };
  }

  if (analysis.method === 'facility_filter') {
    return { title: `${label} Locations in Hong Kong`, subtitle: 'Point locations' };
  }
  if (analysis.method === 'district_choropleth') {
    return { title: 'Hong Kong District Choropleth', subtitle: '' };
  }
  if (analysis.method === 'buffer_coverage') {
    const radius = Number(analysis.radius_m || 0).toLocaleString();
    const matched = Number(analysis.matched_count || 0).toLocaleString();
    const location = String(analysis.location_name || 'Selected location');
    return {
      title: `${label} within ${radius} m of ${location}`,
      subtitle: `${matched} matched facilit${Number(analysis.matched_count) === 1 ? 'y' : 'ies'}`,
    };
  }
  if (analysis.method === 'network_distance') return {
    title: `${label} within ${analysis.distance_m} m ${analysis.travel_mode === 'walk' ? 'walking' : 'driving'} distance of ${analysis.location_name}`,
    subtitle: `${analysis.matched_count} matched · Road distance + access connectors · Not a circular buffer`,
  };
  if (analysis.method === 'network_service_area') {
    if (analysis.matched_facilities !== undefined) return {
      title: `${analysis.target_category} within ${analysis.time_minutes} min of ${analysis.facility_name}`,
      subtitle: `${analysis.matched_facilities} reachable · From selected origin · ${analysis.speed_kmh} km/h estimate`,
    };
    return { title: `${analysis.facility_name || label}: ${analysis.time_minutes}-Minute Driving Coverage`,
      subtitle: `${analysis.matched_origins} matched · ${analysis.excluded_origins} excluded · ${analysis.speed_kmh} km/h estimate · Not emergency response time` };
  }
  return { title: 'Hong Kong Spatial Analysis', subtitle: 'Interactive WebGIS' };
}

export function resolveMapTitle(presentation = {}, layers = []) {
  return resolveMapHeading(presentation, layers).title;
}
