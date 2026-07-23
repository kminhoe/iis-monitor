"use client";

import { useEffect, useRef, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const REFRESH_MS = 3000;      // 실시간 폴링 주기
const WINDOW_MIN = 10;        // 실시간 라인 차트 표시 구간(최근 N분)

const C = {
  tile: "#111c2e",
  tileBorder: "#25344a",
  accent: "#3aa0ff",
  text: "#e6edf3",
  muted: "#8b97a5",
  grid: "#1e2a3d",
};

const STATUS_META = {
   normal: { label: "정상", color: "#3fb950" },
   slow: { label: "지연", color: "#d29922" },
   warning: { label: "경고(4XX)", color: "#f0883e" },
   error: { label: "오류(5XX)", color: "#f85149" },
   timeout: { label: "타임아웃", color: "#c026d3" },
   }

export default function Dashboard() {
  const [summary, setSummary] = useState({});
  const [uniqueVisitors, setUniqueVisitors] = useState(0);
  const [series, setSeries] = useState([]);
  const [records, setRecords] = useState([]);
  const [sim, setSim] = useState(null);
  const [filter, setFilter] = useState(null);
  const [live, setLive] = useState(true);
  const [error, setError] = useState(null);
  const filterRef = useRef(filter);
  filterRef.current = filter;

  async function load() {
    try {
      const previewUrl = new URL(`${API_BASE}/api/iis/preview`);
      previewUrl.searchParams.set("limit", "100");
      if (filterRef.current) previewUrl.searchParams.set("health_status", filterRef.current);

      const [sumRes, tsRes, pvRes, simRes] = await Promise.all([
        fetch(`${API_BASE}/api/iis/summary`),
        fetch(`${API_BASE}/api/iis/timeseries?interval=1m&since_minutes=${WINDOW_MIN}`),
        fetch(previewUrl),
        fetch(`${API_BASE}/api/sim/status`),
      ]);
      if (!sumRes.ok || !tsRes.ok || !pvRes.ok) throw new Error("API 응답 오류");

      const sumData = await sumRes.json();
      const tsData = await tsRes.json();
      const pvData = await pvRes.json();
      const simData = simRes.ok ? await simRes.json() : null;

      setSummary(sumData.by_status || {});
      setUniqueVisitors(sumData.unique_visitors || 0);
      setSeries(
        (tsData.series || []).map((r) => ({ ...r, label: r.time.slice(11, 16) }))
      );
      setRecords(pvData.records || []);
      if (simData) setSim(simData);
      setError(null);
    } catch (e) {
      setError("API에 연결할 수 없습니다. 백엔드/ES가 떠 있는지 확인하세요.");
    }
  }

  // 최초 1회 + live일 때 주기적 폴링. filter 변경 시 즉시 재조회.
  useEffect(() => {
    load();
    if (!live) return;
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [live, filter]);

  const totalCount = Object.values(summary).reduce((a, b) => a + b, 0);
  const pieData = Object.keys(STATUS_META)
    .map((k) => ({ key: k, name: STATUS_META[k].label, value: summary[k] || 0 }))
    .filter((d) => d.value > 0);

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 22px 60px" }}>
      <header
        style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 22 }}
      >
        <div>
          <div style={{ fontSize: 13, color: C.accent, letterSpacing: 0.5 }}>MONITORING</div>
          <h1 style={{ fontSize: 26, margin: "2px 0 4px" }}>IIS Web Monitor</h1>
          <p style={{ color: C.muted, margin: 0, fontSize: 14 }}>
            실시간 요청 · 장애 · 응답지연 대시보드
          </p>
        </div>
        <button
          onClick={() => setLive((v) => !v)}
          style={{
            display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
            padding: "8px 14px", borderRadius: 20, background: C.tile,
            border: `1px solid ${live ? "#3fb95066" : C.tileBorder}`, color: C.text,
          }}
        >
          <span
            style={{
              width: 9, height: 9, borderRadius: "50%",
              background: live ? "#3fb950" : C.muted,
              boxShadow: live ? "0 0 8px #3fb950" : "none",
            }}
          />
          {live ? "실시간 ON" : "실시간 OFF"}
        </button>
      </header>

      {error && (
        <div style={{ color: "#fca5a5", padding: 14, background: "#7f1d1d33",
          border: "1px solid #b91c1c55", borderRadius: 10, marginBottom: 18 }}>
          {error}
        </div>
      )}

      {/* KPI 타일 */}
      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
        gap: 14, marginBottom: 18 }}>
        <Kpi label="전체 요청" value={totalCount} color={C.accent} big
             active={filter === null} onClick={() => setFilter(null)} />
        <Kpi label="고유 방문자" value={uniqueVisitors} color="#a371f7" />
        {Object.keys(STATUS_META).map((k) => (
          <Kpi key={k} label={STATUS_META[k].label} value={summary[k] || 0}
               color={STATUS_META[k].color} active={filter === k}
               onClick={() => setFilter(filter === k ? null : k)} />
        ))}
      </section>

      {/* 시뮬레이터 조작 패널 */}
      {sim && <SimPanel sim={sim} onApply={load} />}

      {/* 차트 2단 */}
      <section style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 14, marginBottom: 18 }}>
        <Panel title={`요청 추이 (최근 ${WINDOW_MIN}분, 분 단위)`}>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="label" stroke={C.muted} fontSize={12} tickLine={false} />
              <YAxis stroke={C.muted} fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={{ background: C.tile, border: `1px solid ${C.tileBorder}`,
                borderRadius: 8, color: C.text }} />
              <Line type="monotone" dataKey="total" name="전체" stroke={C.accent} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="error" name="오류" stroke="#f85149" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="상태 비율">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2} isAnimationActive={false}>
                {pieData.map((d) => (<Cell key={d.key} fill={STATUS_META[d.key].color} stroke="none" />))}
              </Pie>
              <Tooltip contentStyle={{ background: C.tile, border: `1px solid ${C.tileBorder}`,
                borderRadius: 8, color: C.text }} />
              <Legend wrapperStyle={{ fontSize: 12, color: C.muted }} />
            </PieChart>
          </ResponsiveContainer>
        </Panel>
      </section>

      {/* 로그 테이블 */}
      <Panel title={`최근 요청 로그${filter ? ` · ${STATUS_META[filter].label} 필터` : ""}`}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", color: C.muted, fontSize: 12 }}>
                <th style={th}>시각</th><th style={th}>메서드</th><th style={th}>경로</th>
                <th style={th}>상태</th><th style={th}>응답(ms)</th><th style={th}>판정</th>
                <th style={th}>쿼리</th>
              </tr>
            </thead>
            <tbody>
              {records.slice().reverse().slice(0, 60).map((r, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${C.grid}` }}>
                  <td style={td}>{r.logged_at}</td>
                  <td style={td}>{r.method}</td>
                  <td style={{ ...td, color: C.text }}>{r.path}</td>
                  <td style={td}>{r.status_code}</td>
                  <td style={td}>{r.response_time_ms}</td>
                  <td style={{ ...td, color: STATUS_META[r.health_status]?.color, fontWeight: 600 }}>
                    {STATUS_META[r.health_status]?.label || r.health_status}
                  </td>
                  <td style={td}>{r.query || "-"}</td> 
                </tr>

              ))}
              {records.length === 0 && (
                <tr><td style={td} colSpan={7}>표시할 로그가 없습니다.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </main>
  );
}

function SimPanel({ sim, onApply }) {
  const [form, setForm] = useState({
    requests_per_tick: sim.config.requests_per_tick,
    error_rate: sim.config.error_rate,
    user_pool: sim.config.user_pool,
    enabled: sim.config.enabled,
  });
  const [busy, setBusy] = useState(false);

  async function apply(patch) {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/sim/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      await onApply();
    } finally {
      setBusy(false);
    }
  }

  const field = { display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: C.muted };
  const input = {
    background: "#0b1220", border: `1px solid ${C.tileBorder}`, borderRadius: 6,
    color: C.text, padding: "6px 8px", width: 110,
  };

  return (
    <div style={{ background: C.tile, border: `1px dashed ${C.tileBorder}`, borderRadius: 12,
      padding: 16, marginBottom: 18 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: C.text }}>
        트래픽 시뮬레이터 <span style={{ color: C.muted, fontWeight: 400 }}>(데모 전용 · 실 운영에선 끔)</span>
      </div>
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={field}>
          요청량 / tick
          <input type="number" style={input} value={form.requests_per_tick}
            onChange={(e) => setForm({ ...form, requests_per_tick: Number(e.target.value) })} />
        </label>
        <label style={field}>
          이용자 수(풀)
          <input type="number" style={input} value={form.user_pool}
            onChange={(e) => setForm({ ...form, user_pool: Number(e.target.value) })} />
        </label>
        <label style={field}>
          오류율 (0~1)
          <input type="number" step="0.01" style={input} value={form.error_rate}
            onChange={(e) => setForm({ ...form, error_rate: Number(e.target.value) })} />
        </label>
        <button disabled={busy} onClick={() => apply(form)}
          style={{ cursor: "pointer", padding: "8px 16px", borderRadius: 6, border: "none",
            background: C.accent, color: "#03203f", fontWeight: 700 }}>
          {busy ? "적용 중..." : "적용"}
        </button>
        <button disabled={busy}
          onClick={() => { const next = !form.enabled; setForm({ ...form, enabled: next }); apply({ enabled: next }); }}
          style={{ cursor: "pointer", padding: "8px 16px", borderRadius: 6,
            border: `1px solid ${C.tileBorder}`, background: "transparent",
            color: form.enabled ? "#f85149" : "#3fb950" }}>
          {form.enabled ? "생성 정지" : "생성 시작"}
        </button>
        <span style={{ fontSize: 12, color: C.muted }}>
          상태: {sim.running ? (sim.config.enabled ? "생성 중" : "대기") : "정지"}
        </span>
      </div>
    </div>
  );
}

function Kpi({ label, value, color, big, active, onClick }) {
  const clickable = typeof onClick === "function";
  return (
    <div onClick={onClick} style={{ cursor: clickable ? "pointer" : "default",
      padding: "16px 18px", borderRadius: 12, background: C.tile,
      border: active ? `2px solid ${color}` : `1px solid ${C.tileBorder}` }}>
      <div style={{ fontSize: 12, color: C.muted, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: big ? 30 : 26, fontWeight: 700, color }}>
        {Number(value).toLocaleString()}
      </div>
    </div>
  );
}

function Panel({ title, children }) {
  return (
    <div style={{ background: C.tile, border: `1px solid ${C.tileBorder}`, borderRadius: 12, padding: 18 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: C.text }}>{title}</div>
      {children}
    </div>
  );
}

const th = { padding: "8px 10px", fontWeight: 600 };
const td = { padding: "8px 10px", fontSize: 13, color: C.muted };
