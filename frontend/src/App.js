import React, { useState, useRef } from 'react';
import './App.css';

function App() {

  const [segments, setSegments] = useState({
    cold_open: 10,
    topic: 50,
    banter: 15,
    ad: 10,
    outro: 15
  });

  const [lockedSegments, setLockedSegments] = useState(new Set());
  const dragInfo = useRef({
    isDragging: false,
    startX: 0,
    segmentType: null,
    initialWidth: 0
  });
  const containerRef = useRef(null);

  const [formData, setFormData] = useState({
    topics: 'AI ethics\nIndie film picks',
    hosts: 'Maya|sarcastic film geek\nRowan|calm tech nerd',
    stationStyle: 'chill night radio'
  });
  const [isGenerating, setIsGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [error, setError] = useState(null);

  const handleDoubleClick = (type) => {
    setLockedSegments(prev => {
      const newLocked = new Set(prev);
      if (newLocked.has(type)) newLocked.delete(type);
      else newLocked.add(type);
      return newLocked;
    });
  };

  const handleMouseDown = (e, segmentType) => {
    if (lockedSegments.has(segmentType)) return;

    const rect = containerRef.current.getBoundingClientRect();
    dragInfo.current = {
      isDragging: true,
      startX: e.clientX,
      segmentType,
      initialWidth: segments[segmentType],
      containerWidth: rect.width
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  const handleMouseMove = (e) => {
    if (!dragInfo.current.isDragging) return;
    const deltaX = e.clientX - dragInfo.current.startX;
    const deltaPercentage = (deltaX / dragInfo.current.containerWidth) * 100;
    const newWidth = Math.max(5, Math.min(70, dragInfo.current.initialWidth + deltaPercentage));

    const newSegments = { ...segments };
    const oldWidth = segments[dragInfo.current.segmentType];
    const difference = newWidth - oldWidth;

    const adjustableSegments = Object.keys(segments).filter(
      key => key !== dragInfo.current.segmentType && !lockedSegments.has(key)
    );

    if (adjustableSegments.length === 0) return;
    const adjustment = -difference / adjustableSegments.length;

    adjustableSegments.forEach(key => {
      newSegments[key] = Math.max(5, segments[key] + adjustment);
    });

    newSegments[dragInfo.current.segmentType] = newWidth;

    const total = Object.values(newSegments).reduce((a, b) => a + b, 0);
    if (Math.abs(total - 100) < 0.1) setSegments(newSegments);
  };

  const handleMouseUp = () => {
    dragInfo.current.isDragging = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
  };

  //12 minutes in seconds
  const totalTime = 12 * 60;

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleGenerate = async () => {
    try {
      setIsGenerating(true);
      setError(null);
      setAudioUrl(null);

      const topics = formData.topics.split('\n').filter(t => t.trim());
      const hosts = formData.hosts.split('\n')
        .filter(h => h.trim())
        .map(h => {
          const [name, persona] = h.split('|');
          return { name: name.trim(), persona: persona?.trim() || '' };
        });

      const response = await fetch('http://localhost:8000/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topics,
          hosts,
          style: formData.stationStyle,
          segments
        }),
      });

      if (!response.ok) throw new Error('Failed to generate audio');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="App">
      <header className="app-header">
        <h1>AI Radio Station</h1>
      </header>

      <main className="app-main">
        {/* --- Config Form --- */}
        <section className="form-section">
          <h2>Episode Configuration</h2>

          <div className="input-group">
            <label htmlFor="topics">Topics</label>
            <textarea
              id="topics"
              name="topics"
              value={formData.topics}
              onChange={handleInputChange}
              placeholder="One topic per line"
              rows={4}
              className="form-textarea"
            />
          </div>

          <div className="input-group">
            <label htmlFor="hosts">Hosts</label>
            <textarea
              id="hosts"
              name="hosts"
              value={formData.hosts}
              onChange={handleInputChange}
              placeholder="One host per line in format: Name|Persona"
              rows={4}
              className="form-textarea"
            />
          </div>

          <div className="input-group">
            <label htmlFor="stationStyle">Station Style</label>
            <input
              type="text"
              id="stationStyle"
              name="stationStyle"
              value={formData.stationStyle}
              onChange={handleInputChange}
              className="form-input"
            />
          </div>
        </section>

        {/* --- Segment Mixer --- */}
        <section className="segment-section">
          <h2>Segment Mix</h2>
          <p className="instructions">Double-click a segment to lock/unlock its duration</p>

          <div className="segment-mixer">
            <div className="segment-bar" ref={containerRef}>
              {Object.entries(segments).map(([type, percentage]) => (
                <div
                  key={type}
                  className={`segment-section ${type} ${lockedSegments.has(type) ? 'locked' : ''}`}
                  style={{ width: `${percentage}%` }}
                  onMouseDown={(e) => handleMouseDown(e, type)}
                  onDoubleClick={() => handleDoubleClick(type)}
                >
                  <div className="segment-label">
                    {type.replace('_', ' ')}<br />
                    {percentage.toFixed(1)}%<br />
                    {Math.round((percentage / 100) * totalTime)}s
                    {lockedSegments.has(type) && <span className="lock-indicator">🔒</span>}
                  </div>
                  <div className="drag-handle"></div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* --- Controls --- */}
        <div className="controls">
          <button 
            className="generate-button"
            onClick={handleGenerate}
            disabled={isGenerating}
          >
            {isGenerating ? 'Generating Episode...' : 'Generate Episode'}
          </button>
        </div>

        {/* --- Error Message --- */}
        {error && <div className="error-message">{error}</div>}

        {/* --- Audio Output --- */}
        {audioUrl && (
          <div className="audio-player">
            <h3>Generated Episode</h3>
            <audio controls src={audioUrl} className="audio-element">
              Your browser does not support the audio element.
            </audio>
            <button
              className="download-button"
              onClick={() => {
                const a = document.createElement('a');
                a.href = audioUrl;
                a.download = 'radio-episode.mp3';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
              }}
            >
              Download Episode
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;