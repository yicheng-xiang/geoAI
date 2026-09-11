import { useEffect, useMemo, useRef } from 'react';
import { chatMessages } from './chatMessages.js';
import './ChatPanel.css';

export default function ChatPanel({ logs, prompt, setPrompt, loading, busy, onSend, onClear }) {
  const messages = useMemo(() => chatMessages(logs), [logs]);
  const scroller = useRef(null);
  const follow = useRef(true);
  useEffect(() => {
    if (follow.current && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [messages, loading]);
  return <section className="chat-panel" aria-label="GeoAI conversation">
    <header className="chat-heading"><strong>GeoAI chat</strong><span>Ask · Analyse · Refine</span></header>
    <div className="chat-messages" ref={scroller} role="log" aria-label="Conversation messages"
      onScroll={(e) => { const el = e.currentTarget; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 64; }}>
      {!messages.length && <div className="chat-welcome"><strong>What would you like to explore?</strong>
        <p>Ask about facilities in Hong Kong, then refine the map with a follow-up message.</p>
        <p className="chat-example">Try: Show ambulance depots in Hong Kong.</p></div>}
      {messages.map((message, i) => message.role === 'activity'
        ? <details className="chat-activity" key={i}><summary>Operation details · {message.lines.length}</summary>
          {message.lines.map((line, j) => <pre key={j}>{line}</pre>)}</details>
        : <article className={`chat-message is-${message.role}`} key={i}>
          <span className="chat-author">{message.role === 'user' ? 'You' : message.role === 'error' ? 'GeoAI · Request failed' : 'GeoAI'}</span>
          <div>{message.text}</div></article>)}
      {loading && <p className="chat-working" role="status">GeoAI is working on your request…</p>}
    </div>
    <form className="chat-composer" onSubmit={(e) => { e.preventDefault(); follow.current = true; onSend(); }}>
      <label htmlFor="geo-prompt">Message GeoAI</label>
      <textarea id="geo-prompt" aria-label="Natural-language GIS request" rows={3}
        placeholder="Ask a question or refine the current map…" value={prompt} disabled={busy}
        onChange={(e) => setPrompt(e.target.value)} onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
            e.preventDefault(); follow.current = true; onSend();
          }
        }} />
      <div className="chat-actions"><button type="button" onClick={onClear} disabled={busy}>Clear session</button>
        <button type="submit" className="chat-send" disabled={busy || !prompt.trim()}>{loading ? 'Working…' : 'Send ↑'}</button></div>
      <small>Enter to send · Shift+Enter for a new line</small>
    </form>
  </section>;
}
