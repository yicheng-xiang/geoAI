import { useEffect, useMemo, useRef, useState } from 'react';
import { draggedPanelHeight, panelHeight } from './panelResize.js';
import { columnsFor, csvText, displayValue, layerStatus, PAGE_SIZE, tableRows } from './resultsModel.js';
import './ResultsPanel.css';
const EMPTY_VIEW = {};

export default function ResultsPanel({ controller, layers, onRestore, busy }) {
  const { state, dispatch } = controller;
  const [collapsed, setCollapsed] = useState(true);
  const [height, setHeight] = useState(280);
  const [message, setMessage] = useState('');
  const drag = useRef(null);
  const panel = useRef(null);
  useEffect(() => {
    const resize = () => { drag.current = null; setHeight((h) => panelHeight(h, window.innerHeight)); };
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  const result = state.results.find((r) => r.id === state.active);
  const view = state.views[state.active] || EMPTY_VIEW;
  const columns = useMemo(() => columnsFor(result), [result]);
  const rows = useMemo(() => tableRows(result, view), [result, view]);
  const page = Math.min(view.page || 0, Math.max(0, Math.ceil(rows.length / PAGE_SIZE) - 1));
  const status = layerStatus(result, layers);
  const select = (row) => {
    if (!row.feature_id) {
      dispatch({ type: 'clear' });
      return setMessage('No linked map feature is available for this record.');
    }
    if (!layers.some((l) => (l.instance_id || l.id) === row.layer_id)) {
      dispatch({ type: 'clear' });
      return setMessage('Show this result on the map before selecting its records.');
    }
    setMessage('');
    dispatch({ type: 'select', selection: { resultId: result.id, rowId: row.id, featureId: row.feature_id, focus: true, token: crypto.randomUUID() } });
  };
  const exportCsv = () => {
    const url = URL.createObjectURL(new Blob([csvText(rows, columns)], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `results-${result.id}.csv`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <section ref={panel} className="results-panel" style={{ height: collapsed ? 42 : height }} aria-label="Analysis results">
    <header className="results-header">
      <strong>Results</strong>
      <select aria-label="Result list" value="" onChange={(e) => { dispatch({ type: 'open', id: e.target.value }); setCollapsed(false); setMessage(''); }}>
        <option value="">Result list ({state.results.length})</option>
        {state.results.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
      </select>
      <button aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}>{collapsed ? 'Show table' : 'Hide table'}</button>
    </header>
    {!collapsed && <>
      <div className="result-tabs" role="tablist" aria-label="Result tabs">
        {state.tabs.map((id) => { const r = state.results.find((item) => item.id === id); return r && <div key={id} className={id === state.active ? 'active' : ''}>
          <button role="tab" aria-selected={id === state.active} onClick={() => { dispatch({ type: 'open', id }); setMessage(''); }}>{r.title}</button>
          <button aria-label={`Close ${r.title}`} onClick={() => dispatch({ type: 'close', id })}>×</button>
        </div>; })}
      </div>
      {!result ? <p className="result-empty">Run an analysis or reopen a result from the result list.</p> : <>
        <div className="result-metadata">
          <span>{status.label} · {result.analysis.method}</span>
          {status.shown < status.total && <button disabled={busy} onClick={async () => { try { await onRestore(result.id); setMessage(''); } catch (e) { setMessage(e.message); } }}>Show on map</button>}
          <details><summary>Parameters & sources</summary>
            <p>{JSON.stringify(Object.fromEntries(Object.entries(result.analysis).filter(([k]) => ['dataset_id', 'facility_types', 'radius_m', 'distance_m', 'travel_mode', 'access_distance_included', 'time_minutes', 'speed_kmh', 'metric', 'origin_name', 'location_name', 'exclude_origin'].includes(k))))}</p>
            {result.sources.map((source, i) => <p key={i}>{Object.entries(source).filter(([, v]) => v != null).map(([k, v]) => `${k}: ${displayValue(v)}`).join(' · ')}</p>)}
            <p>Result created: {result.created_at}. Source time is shown only when provided.</p>
          </details>
        </div>
        <div className="result-toolbar">
          <input aria-label="Search result records" placeholder="Search records…" value={view.query || ''} onChange={(e) => dispatch({ type: 'view', patch: { query: e.target.value, page: 0 } })} />
          <button onClick={() => dispatch({ type: 'clear' })}>Clear selection</button>
          <button onClick={exportCsv}>Export filtered CSV</button>
        </div>
        {state.hidden && <div role="status">This record does not match the current filter. <button onClick={() => dispatch({ type: 'map', ...state.hidden, clearFilter: true, token: crypto.randomUUID() })}>Clear filter and view</button></div>}
        {message && <div role="status">{message}</div>}
        <div className="result-table-scroll">
          <table><thead><tr>{columns.map((c) => <th key={c.key} aria-sort={view.sort === c.key ? (view.direction === 'desc' ? 'descending' : 'ascending') : 'none'}>
            <button onClick={() => dispatch({ type: 'view', patch: { sort: c.key, direction: view.sort === c.key && view.direction !== 'desc' ? 'desc' : 'asc', page: 0 } })}>{c.label}{view.sort === c.key ? (view.direction === 'desc' ? ' ↓' : ' ↑') : ''}</button>
          </th>)}<th>Map link</th></tr></thead><tbody>
            {rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((r) => <tr key={r.id} tabIndex={0} aria-selected={state.selection?.rowId === r.id}
              onClick={() => select(r)} onKeyDown={(e) => { if (e.key === 'Enter') select(r); }}>
              {columns.map((c) => <td key={c.key} title={displayValue(r.values[c.key])}>{displayValue(r.values[c.key])}</td>)}<td>{r.feature_id ? 'Linked' : 'No linked map feature'}</td>
            </tr>)}
          </tbody></table>
          {!rows.length && <p className="result-empty">{result.rows.length ? 'No records match the current search.' : 'No matching facilities or result records.'}</p>}
        </div>
        <footer className="result-toolbar"><span>{result.rows.length} total · {rows.length} filtered · {rows.length ? page * PAGE_SIZE + 1 : 0}–{Math.min((page + 1) * PAGE_SIZE, rows.length)}</span>
          <button disabled={!page} onClick={() => dispatch({ type: 'view', patch: { page: page - 1 } })}>Previous</button>
          <button disabled={(page + 1) * PAGE_SIZE >= rows.length} onClick={() => dispatch({ type: 'view', patch: { page: page + 1 } })}>Next</button>
        </footer>
      </>}
    </>}
    {!collapsed && <div className="results-resizer" role="separator" aria-label="Resize results panel"
      title="Drag down to increase table height" aria-orientation="horizontal" tabIndex={0}
      aria-valuemin={240} aria-valuemax={panelHeight(Infinity, window.innerHeight)} aria-valuenow={height}
      onKeyDown={(e) => {
        if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        setHeight((h) => panelHeight(e.key === 'Home' ? 240 : e.key === 'End' ? Infinity : h + (e.key === 'ArrowDown' ? 30 : -30), window.innerHeight));
      }}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        drag.current = { y: e.clientY, height: panel.current.getBoundingClientRect().height, id: e.pointerId };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (drag.current?.id !== e.pointerId) return;
        e.preventDefault();
        const next = draggedPanelHeight(drag.current, e.clientY, window.innerHeight);
        setHeight(next);
        // Rebase at the clamped height so reversing direction responds at once.
        drag.current = { y: e.clientY, height: next, id: e.pointerId };
      }}
      onPointerUp={(e) => {
        drag.current = null;
        if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
      }}
      onLostPointerCapture={() => { drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }} />}
  </section>;
}
