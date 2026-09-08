import { useEffect, useRef, useState } from 'react';
import MapView from './MapView.jsx';
import CsdiPanel from './CsdiPanel.jsx';
import { createPngObjectUrl, pngFilename } from './mapExport.js';
import './App.css';

const API_BASE_URL = 'http://127.0.0.1:5000';
const EXCEL_FILE_PATTERN = /\.xlsx$/i;

const initialUploadState = {
  phase: 'idle',
  message: 'Choose an Excel workbook containing names and coordinates.',
};

function App() {
  const [sessionId] = useState(() => {
    const stored = window.sessionStorage.getItem('geoai_session_id');
    if (stored) return stored;
    const created = window.crypto.randomUUID();
    window.sessionStorage.setItem('geoai_session_id', created);
    return created;
  });
  const [prompt, setPrompt] = useState('');
  const [thought, setThought] = useState('Awaiting a GIS analysis request...');
  const [logs, setLogs] = useState([]);
  const [geojson, setGeojson] = useState(null);
  const [mapLayers, setMapLayers] = useState([]);
  const [mapPresentation, setMapPresentation] = useState({});
  const [resultVersion, setResultVersion] = useState(0);
  const [analysis, setAnalysis] = useState(null);
  const [statistics, setStatistics] = useState([]);
  const [quality, setQuality] = useState(null);
  const [viewMode, setViewMode] = useState('interactive');
  const [exportPreview, setExportPreview] = useState(null);
  const [exportTitle, setExportTitle] = useState('Hong Kong Spatial Analysis');
  const [exportDownloadUrl, setExportDownloadUrl] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [csdiBusy, setCsdiBusy] = useState(false);
  const [csdiRevision, setCsdiRevision] = useState(0);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadState, setUploadState] = useState(initialUploadState);
  const [uploadedDataset, setUploadedDataset] = useState(null);
  const logEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const mapViewRef = useRef(null);

  const uploading = uploadState.phase === 'uploading';
  const busy = loading || uploading || exporting || csdiBusy;

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  useEffect(() => {
    let cancelled = false;
    const restoreSessionDataset = async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/session_state?session_id=${encodeURIComponent(sessionId)}`,
        );
        if (!response.ok) return;
        const payload = await response.json();
        if (cancelled || payload.status !== 'success' || !payload.uploaded_dataset) return;
        const restored = payload.uploaded_dataset;
        setUploadedDataset(restored);
        setUploadState({
          phase: 'success',
          message: `${restored.filename} remains active in this browser session.`,
        });
      } catch {
        // The normal health/error flow will report backend connectivity if a task is run.
      }
    };
    restoreSessionDataset();
    return () => { cancelled = true; };
  }, [sessionId]);

  useEffect(() => () => {
    if (exportDownloadUrl) URL.revokeObjectURL(exportDownloadUrl);
  }, [exportDownloadUrl]);

  const resetClientResults = () => {
    setLogs([]);
    setGeojson(null);
    setMapLayers([]);
    setMapPresentation({});
    setResultVersion((current) => current + 1);
    setAnalysis(null);
    setStatistics([]);
    setQuality(null);
    setViewMode('interactive');
    setExportPreview(null);
    setExportDownloadUrl(null);
    setExportTitle('Hong Kong Spatial Analysis');
    setPrompt('');
    setSelectedFile(null);
    setUploadState(initialUploadState);
    setUploadedDataset(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleClearBoard = async () => {
    if (busy) return;
    if (!window.confirm('Clear all map layers and conversation logs in this session?')) return;

    try {
      const response = await fetch(`${API_BASE_URL}/api/clear_session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      resetClientResults();
      setCsdiRevision((value) => value + 1);
      setThought('The spatial analysis session has been reset. Ready for a new task.');
    } catch (error) {
      window.alert(`Failed to clear the session: ${error.message}`);
    }
  };

  const handleFileChange = (event) => {
    const file = event.target.files?.[0] || null;
    if (!file) {
      setSelectedFile(null);
      setUploadState(initialUploadState);
      return;
    }

    if (!EXCEL_FILE_PATTERN.test(file.name)) {
      setSelectedFile(null);
      setUploadState({
        phase: 'error',
        message: 'Unsupported file type. Select an .xlsx workbook.',
      });
      event.target.value = '';
      return;
    }

    setSelectedFile(file);
    setUploadState({
      phase: 'selected',
      message: `Ready to upload: ${file.name}`,
    });
  };

  const handleUpload = async () => {
    if (!selectedFile || busy) return;

    const file = selectedFile;
    const replacingDataset = Boolean(uploadedDataset);
    setUploadState({
      phase: 'uploading',
      message: `Uploading and validating ${file.name}...`,
    });

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('session_id', sessionId);

      const response = await fetch(`${API_BASE_URL}/api/upload_dataset`, {
        method: 'POST',
        body: formData,
      });

      let payload = null;
      try {
        payload = await response.json();
      } catch {
        // The HTTP status below still provides a useful fallback message.
      }

      if (!response.ok || payload?.status !== 'success') {
        throw new Error(payload?.message || payload?.error || `Server returned ${response.status}`);
      }

      const rowCount = payload.quality?.valid_records ?? payload.row_count ?? 0;
      setUploadState({
        phase: 'success',
        message: replacingDataset
          ? `${payload.filename || file.name} replaced the previous session dataset.`
          : `${payload.filename || file.name} is ready for spatial analysis.`,
      });
      setUploadedDataset(payload);
      setGeojson(null);
      setMapLayers([]);
      setMapPresentation({});
      setResultVersion((current) => current + 1);
      setAnalysis(null);
      setStatistics([]);
      setQuality(null);
      setViewMode('interactive');
      setExportPreview(null);
      setExportDownloadUrl(null);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      setThought(`The uploaded dataset is ready. You can now request mapping or spatial analysis for its ${rowCount} valid records.`);
      setLogs((current) => [
        ...current,
        `Dataset uploaded: ${payload.filename || file.name}`,
        `Registered as ${payload.dataset_id || 'session_upload'} with ${rowCount} valid records.`,
      ]);
    } catch (error) {
      setUploadState({
        phase: 'error',
        message: `Upload failed: ${error.message}`,
      });
    }
  };

  const applyStreamResult = (stepResult) => {
    if (stepResult.thought) setThought(stepResult.thought);
    if (stepResult.log) setLogs((current) => [...current, stepResult.log]);
    if (stepResult.warning) {
      setLogs((current) => [...current, `[Warning] ${stepResult.warning}`]);
    }
    if (Array.isArray(stepResult.map_layers)) {
      setMapLayers(stepResult.map_layers);
      setExportPreview(null);
      setExportDownloadUrl(null);
      setViewMode('interactive');
    }
    if (stepResult.map_presentation) {
      setMapPresentation(stepResult.map_presentation);
      setExportPreview(null);
      setExportDownloadUrl(null);
      setViewMode('interactive');
    }
    if (stepResult.geojson) {
      setGeojson(stepResult.geojson);
      setResultVersion((current) => current + 1);
      setViewMode('interactive');
      setExportPreview(null);
      setExportDownloadUrl(null);
    }
    if (stepResult.analysis) setAnalysis(stepResult.analysis);
    if (stepResult.statistics) setStatistics(stepResult.statistics);
    if (stepResult.quality) setQuality(stepResult.quality);

    if (stepResult.error) {
      if (!stepResult.log) setLogs((current) => [...current, `Task failed: ${stepResult.error}`]);
      return false;
    }
    return stepResult.status !== 'failed';
  };

  const handleSendPrompt = async () => {
    const submittedPrompt = prompt.trim();
    if (!submittedPrompt || busy) return;

    setLoading(true);
    setLogs((current) => [...current, `User: ${submittedPrompt}`, '----------------------------------------']);
    setThought('The agent is interpreting the spatial task and selecting GIS tools...');

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat_and_map_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: submittedPrompt, session_id: sessionId }),
      });
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      if (!response.body) throw new Error('No streaming response was received');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let shouldContinue = true;

      while (shouldContinue) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const event of events) {
          const dataLine = event.split('\n').find((line) => line.startsWith('data: '));
          if (!dataLine) continue;
          const rawData = dataLine.slice(6).trim();
          if (!rawData) continue;

          try {
            const stepResult = JSON.parse(rawData);
            shouldContinue = applyStreamResult(stepResult);
            if (stepResult.status === 'completed') setPrompt('');
            if (['completed', 'failed'].includes(stepResult.status)) setCsdiRevision((value) => value + 1);
          } catch {
            setLogs((current) => [...current, 'Received an invalid server event.']);
          }
        }

        if (done) break;
      }
    } catch (error) {
      setLogs((current) => [...current, `Connection failed: ${error.message}`]);
      setThought('The task could not be completed. Check the backend service and network connection.');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendPrompt();
    }
  };

  const handleExportPreview = async () => {
    if (viewMode === 'export' && exportPreview) return;
    if (!mapViewRef.current || exporting) return;

    setExporting(true);
    try {
      const title = mapViewRef.current.getTitle();
      const image = await mapViewRef.current.exportPng();
      // Decode before revealing the preview so the previous view is never
      // replaced by a temporarily empty image panel.
      const previewImage = new Image();
      previewImage.src = image;
      await previewImage.decode();
      setExportTitle(title);
      setExportPreview(image);
      setExportDownloadUrl(createPngObjectUrl(image));
      setViewMode('export');
      setLogs((current) => [...current, '[Export Success] Interactive map preview generated as a high-resolution PNG.']);
    } catch (error) {
      setLogs((current) => [...current, `[Export Failed] ${error.message}`]);
      window.alert(`Failed to export the interactive map: ${error.message}`);
    } finally {
      setExporting(false);
    }
  };

  const resultSummary = analysis
    ? `${analysis.method || 'Spatial analysis'} · ${statistics.length} statistical records${quality ? ' · Quality report available' : ''}`
    : 'No structured analysis result yet';

  const uploadedQuality = uploadedDataset?.quality;

  return (
    <main className="app-container">
      <aside className="control-panel">
        <header className="panel-header">
          <h1 className="title">GeoAI Spatial Analysis Workbench</h1>
          <span className={`connection-badge ${busy ? 'is-running' : ''}`}>
            {uploading ? 'Uploading' : loading ? 'Running' : 'Ready'}
          </span>
        </header>

        <section className="status-box" aria-live="polite">
          <h2 className="section-title">Agent status</h2>
          <p className="thought-text">{thought}</p>
        </section>

        <section className="log-box">
          <h2 className="section-title">Spatial operation log</h2>
          <div className="control-log-content">
            {logs.length === 0 && <p className="empty-log">Execution details will appear here.</p>}
            {logs.map((log, index) => <div key={`${index}-${log}`} className="log-line">{log}</div>)}
            <div ref={logEndRef} />
          </div>
        </section>

        <CsdiPanel sessionId={sessionId} revision={csdiRevision} busy={busy}
          onBusy={setCsdiBusy} onPrompt={setPrompt} />
        <section className="upload-box" aria-labelledby="upload-title">
          <h2 id="upload-title" className="section-title">Session dataset</h2>
          <p className="upload-help">
            Required: Name, Latitude, Longitude; optional: FacilityType. CRS: WGS84 (EPSG:4326).
          </p>
          <div className="upload-controls">
            <input
              ref={fileInputRef}
              id="dataset-file"
              className="file-input"
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={handleFileChange}
              disabled={busy}
              aria-describedby="upload-message"
            />
            <button
              className="upload-btn"
              type="button"
              onClick={handleUpload}
              disabled={!selectedFile || busy}
            >
              {uploading ? 'Uploading...' : 'Upload Excel'}
            </button>
          </div>
          <p
            id="upload-message"
            className={`upload-message is-${uploadState.phase}`}
            role={uploadState.phase === 'error' ? 'alert' : 'status'}
          >
            {uploadState.message}
          </p>
          {uploadedDataset && (
            <dl className="upload-summary" aria-label="Uploaded dataset summary">
              <div>
                <dt>Valid</dt>
                <dd>{uploadedQuality?.valid_records ?? uploadedDataset.row_count ?? 0}</dd>
              </div>
              <div>
                <dt>Excluded</dt>
                <dd>{uploadedQuality?.excluded_records ?? 0}</dd>
              </div>
              <div>
                <dt>CRS</dt>
                <dd>EPSG:4326</dd>
              </div>
            </dl>
          )}
          {(uploadedQuality?.excluded_records ?? 0) > 0 && (
            <p className="upload-warning">
              Excluded rows failed the name, coordinate, or Hong Kong extent checks.
            </p>
          )}
          {uploadedDataset && (
            <div className="upload-examples" aria-label="Example requests for uploaded data">
              <span>Try:</span>
              <button type="button" onClick={() => setPrompt('Display the uploaded data.')} disabled={busy}>
                Display the uploaded data
              </button>
              <button type="button" onClick={() => setPrompt('Count the uploaded points by district.')} disabled={busy}>
                Count the uploaded points by district
              </button>
            </div>
          )}
        </section>

        <div className="input-area">
          <label className="input-label" htmlFor="geo-prompt">Natural-language GIS request</label>
          <textarea
            id="geo-prompt"
            className="prompt-input"
            rows="3"
            placeholder="Example: Find primary schools within 2 km of Hong Kong Polytechnic University Block Z."
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={busy}
          />
          <div className="btn-group">
            <button className="clear-btn" onClick={handleClearBoard} disabled={busy}>Clear session</button>
            <button className="send-btn" onClick={handleSendPrompt} disabled={busy || !prompt.trim()}>
              {loading ? 'Processing...' : 'Run request'}
            </button>
          </div>
        </div>
      </aside>

      <section className="map-workspace" aria-label="Map workspace">
        <header className="map-toolbar">
          <div>
            <h2>Hong Kong WebGIS</h2>
            <p>{resultSummary}</p>
          </div>
          <div className="view-switch" aria-label="Map view selection">
            <button
              className={viewMode === 'interactive' ? 'active' : ''}
              aria-pressed={viewMode === 'interactive'}
              onClick={() => setViewMode('interactive')}
            >Interactive map</button>
            <button
              className={viewMode === 'export' ? 'active' : ''}
              aria-pressed={viewMode === 'export'}
              onClick={handleExportPreview}
              disabled={exporting}
            >{exporting ? 'Generating...' : 'Export preview'}</button>
            <a
              className={`download-map-btn ${!exportDownloadUrl || exporting ? 'is-disabled' : ''}`}
              href={exportDownloadUrl || undefined}
              download={pngFilename(exportTitle)}
              aria-disabled={!exportDownloadUrl || exporting}
              onClick={(event) => {
                if (!exportDownloadUrl || exporting) event.preventDefault();
              }}
            >Download PNG</a>
          </div>
        </header>

        <div className="map-gallery">
          <div
            className={`map-view-panel${viewMode !== 'interactive' ? ' is-inactive' : ''}`}
            aria-hidden={viewMode !== 'interactive'}
            inert={viewMode !== 'interactive'}
          >
            <MapView
              ref={mapViewRef}
              mapLayers={mapLayers}
              geojson={geojson}
              analysis={analysis}
              mapPresentation={mapPresentation}
              resultVersion={resultVersion}
            />
          </div>
          {exportPreview && (
            <div
              className={`map-view-panel${viewMode !== 'export' ? ' is-inactive' : ''}`}
              aria-hidden={viewMode !== 'export'}
              inert={viewMode !== 'export'}
            >
              <div className="image-wrapper export-preview-wrapper">
                <img src={exportPreview} alt="PNG preview exported from the interactive map" className="map-img-fluid" />
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

export default App;
