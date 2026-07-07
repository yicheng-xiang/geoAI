import React, { useState, useRef, useEffect } from 'react';
import './App.css';

function App() {
  const [prompt, setPrompt] = useState('');
  const [thought, setThought] = useState('Awaiting user instructions...');
  const [logs, setLogs] = useState([]);
  const [mapImage, setMapImage] = useState(null);
  const [loading, setLoading] = useState(false);
  const logEndRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // One-click Session Reset Handler
  const handleClearBoard = async () => {
    if (loading) return;
    if (window.confirm("Are you sure you want to completely clear the map layer stack and conversation logs?")) {
      try {
        await fetch("http://127.0.0.1:5000/api/clear_session", { method: "POST" });
        setLogs([]);
        setMapImage(null);
        setPrompt('');
        setThought('The geographic spatial sandbox has been reset. Ready for new mapping assignments.');
      } catch (err) {
        alert("Failed to communicate with the spatial server grid.");
      }
    }
  };

  const handleSendPrompt = async () => {
    if (!prompt.trim() || loading) return;

    setLoading(true);
    setLogs(prev => [...prev, `❯ User: ${prompt}`, `----------------------------------------`]);
    setThought('Agent is reviewing spatial history buffers and drafting cartographic topologies...');

    try {
      const response = await fetch("http://127.0.0.1:5000/api/chat_and_map_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt })
      });

      if (!response.ok) throw new Error(`Server gateway error: ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const rawData = line.replace("data: ", "").trim();
            if (!rawData) continue;

            try {
              const stepResult = JSON.parse(rawData);

              if (stepResult.error) {
                setLogs(prev => [...prev, `🛑 [Error Check]: ${stepResult.error}`]);
                setLoading(false);
                return;
              }

              if (stepResult.thought) {
                setThought(stepResult.thought);
              }
              if (stepResult.log) {
                setLogs(prev => [...prev, stepResult.log]);
              }
              if (stepResult.image) {
                setMapImage(stepResult.image); 
              }
              if (stepResult.status === "completed") {
                setLoading(false);
                setPrompt(''); 
              }
            } catch (e) {
              console.error(e);
            }
          }
        }
      }
    } catch (err) {
      setLogs(prev => [...prev, `❌ Critical Fault: ${err.message}`]);
      setLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Left Wing: Agent Analytical Workbench */}
      <div className="control-panel">
        <h2 className="title">OpenGIS Agent Workbench 🗺️</h2>
        
        <div className="status-box">
          <div className="section-title">💡 Agent Cognitive Thought State:</div>
          <p className="thought-text">{thought}</p>
        </div>

        <div className="log-box">
          <div className="section-title">📜 ReAct Spatial Operator Transaction History:</div>
          <div className="control-log-content" style={{ maxHeight: '350px', overflowY: 'auto' }}>
            {logs.map((log, index) => (
              <div key={index} className="log-line">{log}</div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>

        <div className="input-area">
          <textarea
            className="prompt-input"
            rows="2"
            placeholder="Type your geographic spatial scripting commands here..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={loading}
          />
          <div className="btn-group" style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
            <button 
              className="clear-btn"
              onClick={handleClearBoard}
              disabled={loading}
              style={{ background: '#ef4444', color: 'white', border: 'none', padding: '10px 15px', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}
            >
              Clear Sandbox
            </button>
            <button 
              className={`send-btn ${loading ? 'disabled' : ''}`}
              onClick={handleSendPrompt}
              disabled={loading}
              style={{ flexGrow: 1, padding: '10px', borderRadius: '6px', fontWeight: 'bold' }}
            >
              {loading ? 'Processing Layers...' : 'Execute Command'}
            </button>
          </div>
        </div>
      </div>

      {/* Right Wing: High-Fidelity Spatial Canvas viewport */}
      <div className="map-gallery">
        {mapImage ? (
          <div className="image-wrapper">
            <img src={mapImage} alt="Autonomous GIS Canvas Render" className="map-img-fluid" />
          </div>
        ) : (
          <div className="empty-map-placeholder">
            <div className="placeholder-icon">🛰️</div>
            <p>Awaiting geographic task deployment to compile spatial visualizations...</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;