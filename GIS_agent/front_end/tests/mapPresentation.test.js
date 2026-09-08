import assert from 'node:assert/strict';
import test from 'node:test';

import { createLayerPresentation, resolveMapHeading } from '../src/mapPresentation.js';
import { simplifyBasemap, resolveBasemapStyle } from '../src/basemapStyle.js';
import { framingOptions } from '../src/mapFraming.js';
import { bindRoadInteraction, roadInteractionStyle } from '../src/roadInteraction.js';

test('cross-dataset driving heading states the target count and outbound direction', () => {
  const heading = resolveMapHeading({}, [{ analysis: { method: 'network_service_area',
    matched_facilities: 2, time_minutes: 5, speed_kmh: 30, target_category: 'Ambulance Depot',
    facility_name: 'Test Sports Centre' } }]);
  assert.match(heading.title, /Ambulance Depot within 5 min of Test Sports Centre/);
  assert.match(heading.subtitle, /2 reachable · From selected origin/);
});

test('road selection survives mouseout and resets when its popup closes', () => {
  const base = { color: '#287e9c', weight: 1.5, opacity: 0.8, fill: false };
  let events;
  let style;
  bindRoadInteraction({ on: (handlers) => { events = handlers; },
    setStyle: (next) => { style = next; } }, base);
  events.mouseover();
  assert.notEqual(style.color, base.color);
  events.popupopen();
  const selected = style.color;
  assert.equal(selected, '#ea580c');
  events.mouseout();
  assert.equal(style.color, selected);
  events.popupclose();
  assert.deepEqual(style, base);
  assert.equal(base.color, '#287e9c');
});

test('selected and unselected networks have independent visual states', () => {
  const base = { color: '#287e9c', weight: 1.5, opacity: 0.8, fill: false };
  const selected = roadInteractionStyle(base, true, true);
  const normal = roadInteractionStyle(base);
  assert.notEqual(selected.color, normal.color);
  assert.ok(selected.weight > normal.weight);
  assert.equal(selected.fill, false);
});

function feature(geometryType, properties) {
  return {
    type: 'Feature',
    properties,
    geometry: {
      type: geometryType,
      coordinates: geometryType === 'Point'
        ? [114.1, 22.3]
        : [[[114, 22], [114.2, 22], [114.2, 22.2], [114, 22]]],
    },
  };
}

test('network coverage keeps road lines unfilled and reports excluded origins', () => {
  const analysis = { method: 'network_service_area', time_minutes: 5, speed_kmh: 30,
    matched_origins: 43, excluded_origins: 1, facility_types: ['Ambulance Depot'] };
  const roads = createLayerPresentation({ kind: 'line', analysis,
    geojson: { features: [{ type: 'Feature', properties: {}, geometry: {
      type: 'LineString', coordinates: [[114.1, 22.3], [114.2, 22.3]],
    } }] } });
  assert.equal(roads.style().fill, false);
  assert.equal(roads.legend.entries[0].color, roads.style().color);
  const heading = resolveMapHeading({}, [{ analysis }]);
  assert.match(heading.title, /5-Minute Driving Coverage/);
  assert.match(heading.subtitle, /43 matched · 1 excluded/);
  assert.match(heading.subtitle, /Not emergency response time/);
});

test('network corridor stays translucent and origin icons match the legend', () => {
  const area = feature('Polygon', { coverage: 'Approximate service area' });
  const analysis = { method: 'network_service_area', column: 'coverage',
    category_colors: { 'Approximate service area': '#60a5fa' },
    polygon_style: { fill_opacity: 0.18, stroke_width_px: 0, stroke_opacity: 0 } };
  const layer = createLayerPresentation({ kind: 'polygon', analysis, geojson: { features: [area] } });
  assert.equal(layer.style(area).fillOpacity, 0.18);
  assert.equal(layer.style(area).weight, 0);
  const origin = feature('Point', { FACILITY_TYPE: 'Unmatched origin' });
  const points = createLayerPresentation({ kind: 'point', geojson: { features: [origin] },
    analysis: { method: 'network_service_area', category_colors: { 'Unmatched origin': '#9ca3af' },
      point_style: { symbol: 'location', stroke_color: '#ffffff' } } });
  assert.equal(points.pointSymbol, 'location');
  assert.equal(points.legend.entries[0].color, points.pointStyle(origin).fillColor);
});

test('an explicit title overrides the generated analysis title', () => {
  const heading = resolveMapHeading(
    { title: 'HK fitness center distribution' },
    [{ analysis: { method: 'point_in_polygon', metric: 'count' } }],
  );

  assert.equal(heading.title, 'HK fitness center distribution');
  assert.equal(heading.subtitle, 'Facility count');
});

test('polygon fill and legend use the requested backend palette', () => {
  const low = feature('Polygon', { district_name: 'A', metric_value: 1 });
  const high = feature('Polygon', { district_name: 'B', metric_value: 5 });
  const presentation = createLayerPresentation({
    id: 'thematic_polygon',
    kind: 'polygon',
    geojson: { type: 'FeatureCollection', features: [low, high] },
    analysis: {
      method: 'point_in_polygon',
      metric: 'count',
      colormap: 'Blues',
      classification_breaks: [2, 5],
      classification_intervals: 2,
      palette: ['#9ecae1', '#08519c'],
    },
  });

  assert.deepEqual(
    presentation.legend.entries.map((entry) => entry.color),
    ['#9ecae1', '#08519c'],
  );
  assert.equal(presentation.style(low).fillColor, '#9ecae1');
  assert.equal(presentation.style(high).fillColor, '#08519c');
});

test('point symbols and legend use the same requested category color', () => {
  const ambulance = feature('Point', { FACILITY_TYPE: 'Ambulance Depot' });
  const presentation = createLayerPresentation({
    id: 'facility_points',
    kind: 'point',
    geojson: { type: 'FeatureCollection', features: [ambulance] },
    analysis: {
      method: 'facility_filter',
      colormap: 'blue',
      category_colors: { 'Ambulance Depot': '#0000ff' },
    },
  });

  assert.equal(presentation.pointStyle(ambulance).fillColor, '#0000ff');
  assert.ok(presentation.pointStyle(ambulance).radius < 5);
  assert.ok(presentation.pointStyle(ambulance, 13).radius > presentation.pointStyle(ambulance, 10).radius);
  assert.equal(presentation.pointStyle(ambulance).fillOpacity, 0.78);
  assert.equal(presentation.pointStyle(ambulance).color, '#334155');
  assert.ok(presentation.pointStyle(ambulance).weight <= 1);
  assert.equal(presentation.legend.entries[0].color, '#0000ff');
  assert.equal(presentation.legend.entries[0].fillOpacity, 0.78);
});

test('legacy pale point styles receive visible outlines without changing requested colors', () => {
  const point = feature('Point', { FACILITY_TYPE: 'Test' });
  const presentation = createLayerPresentation({
    kind: 'point', geojson: { features: [point] },
    analysis: { category_colors: { Test: '#82adc7' }, point_style: { fill_opacity: 0.6, stroke_opacity: 0.72, stroke_width_px: 0.8 } },
  });
  assert.equal(presentation.pointStyle(point).fillColor, '#82adc7');
  assert.equal(presentation.pointStyle(point).fillOpacity, 0.78);
  assert.equal(presentation.pointStyle(point).opacity, 0.95);
  assert.equal(presentation.pointStyle(point).weight, 1);
});

test('buffer coverage uses metric-buffer styling and a traceable heading', () => {
  const buffer = feature('Polygon', { analysis_role: 'buffer_area', radius_m: 500 });
  const presentation = createLayerPresentation({
    id: 'buffer_area',
    kind: 'polygon',
    geojson: { type: 'FeatureCollection', features: [buffer] },
    analysis: {
      method: 'buffer_coverage',
      visual_role: 'buffer_area',
      column: 'analysis_role',
      radius_m: 500,
      matched_count: 3,
      category_colors: { buffer_area: '#93c5fd' },
      polygon_style: {
        fill_opacity: 0.05,
        stroke_color: '#60a5fa',
        stroke_opacity: 0.22,
        stroke_width_px: 1,
      },
    },
  });
  const heading = resolveMapHeading({}, [{ analysis: {
    method: 'buffer_coverage',
    dataset_id: 'all_facilities',
    facility_types: ['Ambulance Depot'],
    location_name: 'City Hall',
    radius_m: 500,
    matched_count: 3,
  } }]);

  assert.equal(presentation.style(buffer).fillOpacity, 0.05);
  assert.equal(presentation.style(buffer).color, '#60a5fa');
  assert.equal(presentation.style(buffer).dashArray, undefined);
  assert.equal(presentation.style(buffer).className, 'geoai-buffer-area');
  assert.equal(presentation.legend.title, 'Coverage area');
  assert.equal(presentation.legend.subtitle, '500 m radius');
  assert.equal(heading.title, 'Ambulance Depots within 500 m of City Hall');
  assert.equal(heading.subtitle, '3 matched facilities');
});

test('buffer center uses a dedicated glowing location symbol', () => {
  const center = feature('Point', { FACILITY_TYPE: 'Analysis center' });
  const presentation = createLayerPresentation({
    id: 'buffer_center',
    kind: 'point',
    geojson: { type: 'FeatureCollection', features: [center] },
    analysis: {
      method: 'buffer_coverage',
      visual_role: 'buffer_center',
      category_colors: { 'Analysis center': '#3b9ab2' },
      point_style: {
        symbol: 'location',
        radius_px: 8,
        fill_opacity: 1,
        stroke_color: '#ffffff',
        stroke_width_px: 1.5,
      },
    },
  });

  assert.equal(presentation.pointSymbol, 'location');
  assert.equal(presentation.pointStyle(center).fillOpacity, 1);
  assert.equal(presentation.pointStyle(center).fillColor, '#3b9ab2');
  assert.equal(presentation.pointStyle(center).color, '#ffffff');
  assert.equal(presentation.pointStyle(center).radius, 8);
  assert.equal(presentation.legend.entries[0].symbol, 'location');
});

test('matched schools use the school badge in both map and legend', () => {
  const school = feature('Point', { FACILITY_TYPE: 'Primary School' });
  const presentation = createLayerPresentation({
    id: 'buffer_facilities',
    kind: 'point',
    geojson: { type: 'FeatureCollection', features: [school] },
    analysis: {
      visual_role: 'matched_facilities',
      category_colors: { 'Primary School': '#d97772' },
      point_style: { symbol: 'school', stroke_color: '#ffffff' },
    },
  });

  assert.equal(presentation.pointSymbol, 'school');
  assert.equal(presentation.pointStyle(school).fillColor, '#d97772');
  assert.equal(presentation.legend.entries[0].symbol, 'school');
});

test('simplified vector style keeps blue water, defers road clutter and uses English labels', () => {
  const source = { version: 8, layers: [
    { id: 'water', type: 'fill', paint: { 'fill-color': 'gray' } },
    { id: 'road_minor', type: 'line', 'source-layer': 'transportation' },
    { id: 'road_name', type: 'symbol', 'source-layer': 'transportation_name', layout: { 'text-field': '{name}' } },
    { id: 'label_city', type: 'symbol', 'source-layer': 'place', layout: { 'text-field': '{name}' } },
  ] };
  const style = simplifyBasemap(source);
  assert.equal(style.layers[0].paint['fill-color'], '#c5e3ed');
  assert.equal(style.layers[1].minzoom, 13);
  assert.equal(style.layers[2].minzoom, 14);
  assert.equal(style.layers[3].layout['text-allow-overlap'], false);
  assert.equal(style.layers[3].layout['text-field'][1][1], 'name:en');
  assert.equal(source.layers[0].paint['fill-color'], 'gray');
  assert.equal(resolveBasemapStyle().filter, 'none');
});

test('framing reserves heading space with smaller responsive side margins', () => {
  const desktop = framingOptions(1400, 800);
  const mobile = framingOptions(360, 500);
  assert.deepEqual(desktop.paddingTopLeft, [36, 96]);
  assert.equal(mobile.paddingTopLeft[0], 20);
  assert.ok(mobile.paddingTopLeft[1] < 96);
  assert.equal(desktop.animate, false);
});
