export const PAGE_SIZE = 50;
export function displayValue(value) {
  return value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
}
export function tableRows(result, view = {}) {
  const query = (view.query || '').trim().toLocaleLowerCase();
  const rows = (result?.rows || []).filter((r) => !query || Object.values(r.values)
    .some((v) => displayValue(v).toLocaleLowerCase().includes(query)));
  if (view.sort) rows.sort((a, b) => {
    const x = a.values[view.sort], y = b.values[view.sort];
    const order = typeof x === 'number' && typeof y === 'number' ? x - y
      : displayValue(x).localeCompare(displayValue(y), 'en', { numeric: true });
    return order * (view.direction === 'desc' ? -1 : 1);
  });
  return rows;
}
const LABELS = { NAME: 'Name', name: 'Name', FACILITY_TYPE: 'Type', facility_type: 'Type',
  district_name: 'District', district_id: 'District ID', facility_count: 'Facility count',
  area_km2: 'Area (km²)', density_per_km2: 'Facilities / km²', latitude: 'Latitude',
  longitude: 'Longitude', distance_m: 'Distance (m)', travel_seconds: 'Travel time (s)',
  status: 'Status', snap_distance_m: 'Road access (m)', network_distance_m: 'Network distance (m)' };
export function columnsFor(result) {
  const keys = new Set((result?.rows || []).flatMap((r) => Object.keys(r.values)));
  const rows = result?.rows || [];
  const coordinateAxis = (key) => key.replace(/^source\./, '').toLowerCase();
  const isCoordinate = (key) => ['latitude', 'longitude'].includes(coordinateAxis(key));
  // Hide only genuinely duplicated coordinates. Preserve divergent official
  // attributes (and rows with missing canonical values) for traceability.
  const duplicateCoordinate = (key) => {
    const axis = coordinateAxis(key);
    if (!isCoordinate(key) || key === axis || !keys.has(axis)) return false;
    return rows.every(({ values }) => values[key] == null || values[key] === '' ||
      (values[axis] != null && values[axis] !== '' && Number.isFinite(Number(values[key])) &&
        Number(values[key]) === Number(values[axis])));
  };
  const preferred = ['district_name', 'facility_count', 'area_km2', 'density_per_km2',
    'NAME', 'name', 'FACILITY_TYPE', 'facility_type', 'distance_m', 'status',
    'snap_distance_m', 'travel_seconds', 'latitude', 'longitude'];
  return [...preferred.filter((k) => keys.has(k)), ...[...keys].filter((k) => !preferred.includes(k))]
    .filter((k) => !k.startsWith('_') && !['geometry', 'analysis_role'].includes(k))
    .filter((k) => !duplicateCoordinate(k))
    .map((key) => ({ key, label: isCoordinate(key)
      ? `${LABELS[coordinateAxis(key)]}${key === coordinateAxis(key) ? ' (map)' : ` (source: ${key})`}`
      : LABELS[key] || key.replaceAll('_', ' ') }));
}
export function csvText(rows, columns) {
  const cell = (value) => {
    let text = displayValue(value);
    // Excel may interpret leading whitespace followed by a formula as executable.
    if (typeof value === 'string' && (/^[\s\uFEFF]*[=+@-]/u.test(text) || /^[\t\r\n]/u.test(text))) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  return '\uFEFF' + [columns.map((c) => cell(c.label)).join(','),
    ...rows.map((r) => columns.map((c) => cell(r.values[c.key])).join(','))].join('\r\n');
}
export function layerStatus(result, layers) {
  const ids = new Set(layers.map((l) => l.instance_id || l.id));
  const total = result?.layers.length || 0;
  const shown = result?.layers.filter((l) => ids.has(l.instance_id)).length || 0;
  return { shown, total, label: shown === 0 ? 'Not displayed on map' : shown < total ? 'Partially displayed on map' : 'Displayed on map' };
}
