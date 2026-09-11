// Adapt existing execution events without changing the backend/session protocol.
export function chatMessages(logs) {
  const messages = [];
  for (const text of logs) {
    if (/^-{3,}$/.test(text.trim())) continue;
    if (text.startsWith('User: ')) messages.push({ role: 'user', text: text.slice(6) });
    else if (text.startsWith('[Task Success]')) messages.push({ role: 'assistant', text: text.replace(/^\[Task Success\]\s*/, '') });
    else if (/^(\[Task Failed\]|Task failed:|Connection failed:)/i.test(text)) messages.push({ role: 'error', text });
    else {
      const last = messages.at(-1);
      if (last?.role === 'activity') last.lines.push(text);
      else messages.push({ role: 'activity', lines: [text] });
    }
  }
  return messages;
}
