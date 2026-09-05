import React, { useState, useRef, useCallback } from "react";
import PdfViewer from "./PdfViewer.jsx";
import "./app.css";

const API_BASE = "";

export default function App() {
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | queued | running | done | failed
  const [result, setResult] = useState(null);
  const [pdfUrl, setPdfUrl] = useState(null);
  const [selected, setSelected] = useState(null);
  const pollRef = useRef(null);

  const pollJob = useCallback((id) => {
    pollRef.current = setInterval(async () => {
      const res = await fetch(`${API_BASE}/jobs/${id}`);
      const data = await res.json();
      setStatus(data.status);
      if (data.status === "done") {
        clearInterval(pollRef.current);
        setResult(data.result);
        setPdfUrl(`${API_BASE}/jobs/${id}/pdf`);
      } else if (data.status === "failed") {
        clearInterval(pollRef.current);
        console.error("Analysis failed:", data.error);
      }
    }, 3000);
  }, []);

  const onUpload = useCallback(
    async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const form = new FormData();
      form.append("file", file);
      setStatus("queued");
      setResult(null);
      setPdfUrl(null);
      const res = await fetch(`${API_BASE}/jobs`, { method: "POST", body: form });
      const data = await res.json();
      setJobId(data.job_id);
      pollJob(data.job_id);
    },
    [pollJob]
  );

  return (
    <div className="app">
      <header className="app-header">
        <h1>PDF Contract Analyzer</h1>
        <label className="upload-btn">
          Upload contract
          <input type="file" accept=".pdf,.docx,.doc,.rtf,.html,.htm" onChange={onUpload} hidden />
        </label>
        {jobId && <span className="status-pill">{status}</span>}
      </header>

      <div className="app-body">
        <aside className="sidebar">
          {!result && <p className="hint">Upload a contract to see extracted CUAD fields here.</p>}
          {result && <ExtractionList extractions={result.cuad_extractions} onSelect={setSelected} selected={selected} />}
        </aside>
        <main className="viewer-pane">
          <PdfViewer pdfUrl={pdfUrl} selectedExtraction={selected} />
        </main>
      </div>
    </div>
  );
}

function ExtractionList({ extractions, onSelect, selected }) {
  const populatedClasses = Object.entries(extractions).filter(([, items]) => items.length > 0);

  if (populatedClasses.length === 0) {
    return <p className="hint">No CUAD categories were extracted from this document.</p>;
  }

  return (
    <div className="extraction-list">
      {populatedClasses.map(([cuadClass, items]) => (
        <div key={cuadClass} className="extraction-group">
          <h3>{cuadClass.replaceAll("_", " ")}</h3>
          {items.map((item, i) => (
            <button
              key={i}
              className={`extraction-item ${item.is_verified ? "verified" : "unverified"} ${
                selected === item ? "selected" : ""
              }`}
              onClick={() => onSelect(item)}
              title={item.review_flag.reason}
            >
              <span className="extraction-text">{item.vlm_text}</span>
              <span className="extraction-meta">
                p.{item.source.page} · {Math.round(item.confidence * 100)}%
                {!item.is_verified && " · needs review"}
              </span>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
