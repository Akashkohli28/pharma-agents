import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import {
  Thermometer, Users, AlertTriangle, TrendingUp, Send,
  Settings, History, BarChart3, Pill, MessageSquare,
  LayoutDashboard, Loader2, Play, CheckCircle
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8088';

// ── Skeleton loader ──
function Skeleton({ width = '100%', height = '1rem', style = {} }) {
  return (
    <div style={{
      width, height, borderRadius: '6px',
      background: 'linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%)',
      backgroundSize: '200% 100%',
      animation: 'shimmer 1.5s infinite',
      ...style
    }} />
  );
}

function App() {
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard' | 'chat'
  const [chatInput, setChatInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runStatus, setRunStatus] = useState(null); // 'success' | 'error' | null
  const [messages, setMessages] = useState([
    { id: 'init', role: 'bot', text: 'Welcome to PharmaIQ. How can I assist with your supply chain today?' }
  ]);
  const chatEndRef = useRef(null);

  const [isLoading, setIsLoading] = useState(true);
  const [dashData, setDashData] = useState({
    coldChain: null, demand: null, staffing: null, expiry: null, reports: []
  });

  // Auto-scroll chat to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [cc, dd, st, ex, re] = await Promise.all([
        axios.get(`${API_BASE}/dashboard/cold-chain`),
        axios.get(`${API_BASE}/dashboard/demand`),
        axios.get(`${API_BASE}/dashboard/staffing`),
        axios.get(`${API_BASE}/dashboard/expiry`),
        axios.get(`${API_BASE}/reports`),
      ]);
      setDashData({
        coldChain: cc.data, demand: dd.data,
        staffing: st.data, expiry: ex.data, reports: re.data
      });
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleRunPipeline = async () => {
    setIsRunning(true);
    setRunStatus(null);
    try {
      await axios.post(`${API_BASE}/run`, {
        trigger_type: 'manual',
        store_ids: ['STR-001', 'STR-042', 'STR-080'],
        priority: 'med',
      });
      setRunStatus('success');
      await fetchDashboardData();
    } catch (err) {
      console.error('Pipeline run failed:', err);
      setRunStatus('error');
    } finally {
      setIsRunning(false);
      setTimeout(() => setRunStatus(null), 4000);
    }
  };

  const handleSend = async () => {
    if (!chatInput.trim() || isSending) return;
    const userMsg = chatInput.trim();
    const msgId = Date.now().toString();
    setMessages(prev => [...prev, { id: msgId, role: 'user', text: userMsg }]);
    setChatInput('');
    setIsSending(true);

    try {
      const res = await axios.post(`${API_BASE}/chat`, { message: userMsg });
      const fullText = res.data.answer;
      const botMsgId = `${msgId}-bot`;

      // Start with an empty message for typing effect
      setMessages(prev => [...prev, { id: botMsgId, role: 'bot', text: '' }]);

      let currentText = '';
      let index = 0;

      const typingInterval = setInterval(() => {
        if (index < fullText.length) {
          currentText += fullText[index];
          setMessages(prev =>
            prev.map(m => m.id === botMsgId ? { ...m, text: currentText } : m)
          );
          index++;
        } else {
          clearInterval(typingInterval);
        }
      }, 15); // 15ms per character for a smooth effect

    } catch (err) {
      setMessages(prev => [...prev, {
        id: `${msgId}-err`, role: 'bot',
        text: 'Could not reach the server. Please check the backend is running.'
      }]);
    } finally {
      setIsSending(false);
    }
  };

  const revenueAtRisk = (dashData.demand?.revenue_at_risk ?? 0) / 100000;

  return (
    <>
      {/* Sidebar */}
      <div className="sidebar glass">
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '28px' }}>
          <Settings color="#4f46e5" size={24} />
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700 }}>PharmaIQ</h2>
        </div>

        {/* Tab Nav */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '24px' }}>
          <button
            onClick={() => setActiveTab('dashboard')}
            style={{
              display: 'flex', alignItems: 'center', gap: '10px',
              background: activeTab === 'dashboard' ? 'rgba(79,70,229,0.2)' : 'transparent',
              border: activeTab === 'dashboard' ? '1px solid rgba(79,70,229,0.5)' : '1px solid transparent',
              color: activeTab === 'dashboard' ? '#a5b4fc' : 'var(--text-muted)',
              padding: '10px 14px', borderRadius: '8px', fontWeight: 500,
              cursor: 'pointer', textAlign: 'left', width: '100%', fontSize: '0.9rem',
            }}
          >
            <LayoutDashboard size={16} /> Dashboard
          </button>
          <button
            onClick={() => setActiveTab('chat')}
            style={{
              display: 'flex', alignItems: 'center', gap: '10px',
              background: activeTab === 'chat' ? 'rgba(79,70,229,0.2)' : 'transparent',
              border: activeTab === 'chat' ? '1px solid rgba(79,70,229,0.5)' : '1px solid transparent',
              color: activeTab === 'chat' ? '#a5b4fc' : 'var(--text-muted)',
              padding: '10px 14px', borderRadius: '8px', fontWeight: 500,
              cursor: 'pointer', textAlign: 'left', width: '100%', fontSize: '0.9rem',
            }}
          >
            <MessageSquare size={16} /> AI Assistant
          </button>
        </nav>

        {/* Run Pipeline Button */}
        <div style={{ marginBottom: '24px' }}>
          <button
            onClick={handleRunPipeline}
            disabled={isRunning}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
              width: '100%', padding: '11px',
              background: isRunning ? 'rgba(79,70,229,0.4)' : 'var(--primary)',
              opacity: isRunning ? 0.8 : 1,
              cursor: isRunning ? 'not-allowed' : 'pointer',
              fontSize: '0.9rem',
            }}
          >
            {isRunning
              ? <><Loader2 size={15} className="spin" /> Running Pipeline…</>
              : runStatus === 'success'
                ? <><CheckCircle size={15} /> Pipeline Complete</>
                : <><Play size={15} /> Run Pipeline</>
            }
          </button>
          {runStatus === 'error' && (
            <p style={{ color: 'var(--error)', fontSize: '0.78rem', marginTop: '6px', textAlign: 'center' }}>
              Run failed — check backend logs.
            </p>
          )}
          {runStatus === 'success' && (
            <p style={{ color: 'var(--secondary)', fontSize: '0.78rem', marginTop: '6px', textAlign: 'center' }}>
              Dashboard updated with live data.
            </p>
          )}
        </div>

        {/* Chat panel — always visible in sidebar */}
        <div className="chat-container" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div className="chat-header" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <MessageSquare size={16} color="#9ca3af" />
            <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>Quick Ask</span>
          </div>
          <div className="chat-history" style={{ flex: 1, overflowY: 'auto' }}>
            {messages.map((m) => (
              <div key={m.id} className={`message ${m.role}`}>{m.text}</div>
            ))}
            {isSending && (
              <div className="message bot" style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                <Loader2 size={14} className="spin" />
                <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Thinking…</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
          <div className="chat-input-area" style={{ paddingTop: '12px' }}>
            <input
              type="text"
              placeholder="Ask anything…"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              disabled={isSending}
              style={{ opacity: isSending ? 0.6 : 1 }}
            />
            <button onClick={handleSend} disabled={isSending || !chatInput.trim()}
              style={{ opacity: isSending || !chatInput.trim() ? 0.5 : 1, cursor: isSending ? 'not-allowed' : 'pointer' }}>
              {isSending ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
            </button>
          </div>
        </div>
      </div>

      {activeTab === 'dashboard' ? (
        <main className="dashboard">
          {/* Cold Chain Card */}
          <div className="card glass">
            <div className="card-header">
              <Thermometer color="#ef4444" size={24} />
              <span className="card-title">Cold Chain Status</span>
              {dashData.coldChain?.run_timestamp && (
                <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text-muted)' }}>Live</span>
              )}
            </div>
            {isLoading ? <Skeleton height="2.5rem" /> : (
              <div className="card-value">{dashData.coldChain?.breach_rate || '--'}</div>
            )}
            <div className="card-sub">Stock Compromised (Breach Rate)</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {isLoading
                ? [1, 2, 3].map(i => <Skeleton key={i} height="38px" style={{ borderRadius: '8px' }} />)
                : dashData.coldChain?.sensors.map((s, i) => (
                  <div key={i} className="op-item">
                    <span>{s.store} — {s.id}</span>
                    <span className={`status-tag ${s.status === 'ok' ? 'status-ok' : 'status-err'}`}>
                      {s.temp}°C
                    </span>
                  </div>
                ))}
            </div>
          </div>

          {/* Demand Card */}
          <div className="card glass">
            <div className="card-header">
              <TrendingUp color="#10b981" size={24} />
              <span className="card-title">Epidemic & Demand</span>
              {dashData.demand?.run_timestamp && (
                <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text-muted)' }}>Live</span>
              )}
            </div>
            {isLoading ? <Skeleton height="2.5rem" /> : (
              <div className="card-value">₹{revenueAtRisk.toFixed(1)}L</div>
            )}
            <div className="card-sub">Revenue at Risk (Forecasting)</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {isLoading
                ? [1, 2].map(i => <Skeleton key={i} height="38px" style={{ borderRadius: '8px' }} />)
                : dashData.demand?.alerts.map((a, i) => (
                  <div key={i} className="op-item">
                    <span>{a.disease} Surge ({a.zone})</span>
                    <span className={`status-tag ${a.severity === 'High' || a.severity === 'HIGH' ? 'status-err' : 'status-warn'}`}>
                      {a.severity}
                    </span>
                  </div>
                ))}
            </div>
          </div>

          {/* Staffing Card */}
          <div className="card glass">
            <div className="card-header">
              <Users color="#4f46e5" size={24} />
              <span className="card-title">Workforce Optimized</span>
              {dashData.staffing?.run_timestamp && (
                <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text-muted)' }}>Live</span>
              )}
            </div>
            {isLoading ? <Skeleton height="2.5rem" /> : (
              <div className="card-value">{dashData.staffing?.coverage || '--'}</div>
            )}
            <div className="card-sub">Schedule H Compliance Coverage</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {isLoading
                ? [1].map(i => <Skeleton key={i} height="38px" style={{ borderRadius: '8px' }} />)
                : <>
                  {dashData.staffing?.gaps.map((g, i) => (
                    <div key={i} className="op-item">
                      <span style={{ color: '#ef4444' }}>Gap: {g.store}</span>
                      <span>{g.date}</span>
                    </div>
                  ))}
                  <div className="op-item">
                    <span>Optimized Shifts</span>
                    <span>{dashData.staffing?.optimized_shifts} active</span>
                  </div>
                </>
              }
            </div>
          </div>

          {/* Expiry Card */}
          <div className="card glass">
            <div className="card-header">
              <Pill color="#f59e0b" size={24} />
              <span className="card-title">Inventory Expiry</span>
              {dashData.expiry?.run_timestamp && (
                <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text-muted)' }}>Live</span>
              )}
            </div>
            {isLoading ? <Skeleton height="2.5rem" /> : (
              <div className="card-value">{dashData.expiry?.nearing_expiry_count ?? '--'}</div>
            )}
            <div className="card-sub">SKUs Nearing Expiry (90-day window)</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {isLoading
                ? [1, 2].map(i => <Skeleton key={i} height="38px" style={{ borderRadius: '8px' }} />)
                : dashData.expiry?.items.map((item, i) => (
                  <div key={i} className="op-item">
                    <span>{item.sku} ({item.store})</span>
                    <span style={{ color: item.days < 0 ? '#ef4444' : '#f59e0b' }}>
                      {item.days < 0 ? `${Math.abs(item.days)}d expired` : `${item.days}d left`}
                    </span>
                  </div>
                ))}
            </div>
          </div>

          {/* Ops Reports */}
          <div className="card glass" style={{ gridColumn: '1 / -1' }}>
            <div className="card-header">
              <History color="#9ca3af" size={24} />
              <span className="card-title">Ops Reports & Audit Log</span>
            </div>
            <div style={{ overflowX: 'auto', marginTop: '10px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                <thead>
                  <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--glass-border)' }}>
                    {['Run ID', 'Timestamp', 'Risk Score', 'Actions', 'Status'].map(h => (
                      <th key={h} style={{ padding: '12px' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {isLoading
                    ? [1, 2].map(i => (
                      <tr key={i}><td colSpan={5} style={{ padding: '12px' }}>
                        <Skeleton height="24px" />
                      </td></tr>
                    ))
                    : dashData.reports.map((r, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                        <td style={{ padding: '12px', fontFamily: 'monospace', color: '#a5b4fc' }}>{r.run_id}</td>
                        <td style={{ padding: '12px', color: 'var(--text-muted)' }}>{new Date(r.timestamp).toLocaleString()}</td>
                        <td style={{ padding: '12px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{ width: '80px', height: '6px', background: '#1f2937', borderRadius: '3px' }}>
                              <div style={{
                                width: `${Math.min(r.score, 100)}%`, height: '100%', borderRadius: '3px',
                                background: r.score > 70 ? '#ef4444' : r.score > 40 ? '#f59e0b' : '#10b981',
                                transition: 'width 0.6s ease',
                              }} />
                            </div>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{r.score}</span>
                          </div>
                        </td>
                        <td style={{ padding: '12px' }}>{r.actions} automated</td>
                        <td style={{ padding: '12px' }}>
                          <span className="status-tag status-ok">Verified</span>
                        </td>
                      </tr>
                    ))
                  }
                </tbody>
              </table>
            </div>
          </div>
        </main>
      ) : (
        <main style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '32px', overflow: 'hidden' }}>
          <h2 style={{ marginBottom: '24px', fontSize: '1.4rem', fontWeight: 700 }}>
            <MessageSquare size={20} style={{ verticalAlign: 'middle', marginRight: '10px' }} />
            AI Knowledge Assistant
          </h2>
          <div className="glass" style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '24px', overflow: 'hidden' }}>
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '14px', paddingRight: '8px' }}>
              {messages.map((m) => (
                <div key={m.id} className={`message ${m.role}`} style={{ maxWidth: '75%' }}>{m.text}</div>
              ))}
              {isSending && (
                <div className="message bot" style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                  <Loader2 size={14} className="spin" />
                  <span style={{ color: 'var(--text-muted)' }}>Thinking…</span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            <div className="chat-input-area" style={{ paddingTop: '16px', borderTop: '1px solid var(--glass-border)', marginTop: '16px' }}>
              <input
                type="text"
                placeholder="Ask about inventory, cold chain, demand signals…"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                disabled={isSending}
                style={{ fontSize: '1rem', opacity: isSending ? 0.6 : 1 }}
              />
              <button onClick={handleSend} disabled={isSending || !chatInput.trim()}
                style={{ opacity: isSending || !chatInput.trim() ? 0.5 : 1, cursor: isSending ? 'not-allowed' : 'pointer', padding: '10px 20px' }}>
                {isSending ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
              </button>
            </div>
          </div>
        </main>
      )}
    </>
  );
}

export default App;
