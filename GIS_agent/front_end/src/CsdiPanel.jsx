import { useEffect, useState } from 'react';

export default function CsdiPanel({ sessionId, revision, busy, onBusy, onPrompt }) {
  const [query, setQuery] = useState('');
  const [catalog, setCatalog] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [searching, setSearching] = useState(false);
  const [message, setMessage] = useState('Session-only snapshots. Local datasets remain unchanged.');
  const endpoint = 'http://127.0.0.1:5000/api/csdi';
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setSearching(true);
      fetch(`${endpoint}?session_id=${encodeURIComponent(sessionId)}&query=${encodeURIComponent(query.trim())}`, { signal: controller.signal })
        .then(async (r) => { const data = await r.json(); if (!r.ok) throw new Error(data.message || 'CSDI catalogue unavailable'); return data; })
        .then((data) => { if (!cancelled) {
          setCatalog(data.catalog || []); setDatasets(data.temporary_datasets || []);
          setMessage(query.trim() ? 'Official catalogue results. WFS compatibility is checked on download.' : 'Enter a keyword to discover official datasets.');
        } })
        .catch((error) => { if (!cancelled) { setCatalog([]); setMessage(`Catalogue search failed: ${error.message}`); } })
        .finally(() => { if (!cancelled) setSearching(false); });
    }, 450);
    return () => { cancelled = true; clearTimeout(timer); controller.abort(); };
  }, [sessionId, revision, query]);
  const download = async (id, refresh) => {
    onBusy(true);
    setMessage('Downloading and validating official WFS data...');
    try {
      const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, dataset_id: id, refresh }) });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.message || 'Download failed');
      setDatasets(data.data.temporary_datasets);
      setMessage(data.message);
    } catch (error) { setMessage(`Download failed: ${error.message}. Existing snapshots were kept.`); }
    finally { onBusy(false); }
  };
  const hasQuery = query.trim().length > 0;
  // The server owns multilingual aliases and catalogue ranking. A second raw
  // substring filter here would discard valid translated matches (消防站).
  const filtered = hasQuery ? catalog : [];
  return <section className="upload-box csdi-panel" aria-label="CSDI temporary datasets">
    <h2 className="section-title">CSDI temporary datasets</h2>
    <p className="upload-help">Discover official CSDI datasets. Compatible point WFS sources can be downloaded into this session.</p>
    <input aria-label="Search official CSDI datasets" placeholder="Search: badminton / swimming / 羽毛球" value={query}
      onChange={(event) => { setQuery(event.target.value); setCatalog([]); setSearching(true); }} />
    {hasQuery && searching && <p role="status">Searching the official catalogue...</p>}
    {hasQuery && !searching && filtered.length === 0 && <p>No matching catalogue entries to display. Check the search status below.</p>}
    {filtered.map((item) => {
      const saved = datasets.find((d) => d.id === item.id);
      return <div key={item.id} className="csdi-source">
        <strong>{item.title}</strong>
        {item.catalog_stale && <small>Cached catalogue · Live refresh unavailable. Download still validates the WFS service.</small>}
        {saved ? <small>WFS validated · Session snapshot available</small>
          : item.discovered && <small>Discovered source · WFS not yet validated</small>}
        {saved && <small>{saved.row_count} records · WGS 84<br />Downloaded: {new Date(saved.downloaded_at).toLocaleString()}</small>}
        <div className="csdi-actions">
          <button disabled={busy} onClick={() => download(item.id, !!saved)}>{saved ? 'Refresh snapshot' : 'Download'}</button>
          <button disabled={busy} onClick={() => onPrompt(`Use CSDI ${item.id} and show its facilities on the map.`)}>Map this source</button>
        </div>
      </div>;
    })}
    <p role="status" className="upload-help">{message}</p>
    <small>{datasets.length} temporary datasets. Clear session or restart the backend to remove them.</small>
  </section>;
}
