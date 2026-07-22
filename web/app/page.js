"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const STATUS_META = {
  normal: { label: "정상", color: "#22c55e" },
  slow: { label: "지연", color: "#eab308" },
  warning: { label: "경고(4xx)", color: "#f97316" },
  error: { label: "오류(5xx)", color: "#ef4444" },
};

export default function Dashboard() {
  const [summary, setSummary] = useState({});
  const [records, setRecords] = useState([]);
  const [filter, setFilter] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  // filter가 바뀔 때마다 요약 + 목록을 다시 불러온다.
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const previewUrl = new URL(`${API_BASE}/api/iis/preview`);
        previewUrl.searchParams.set("limit", "200");
        if (filter) previewUrl.searchParams.set("health_status", filter);

        const [summaryRes, previewRes] = await Promise.all([
          fetch(`${API_BASE}/api/iis/summary`),
          fetch(previewUrl),
        ]);
        if (!summaryRes.ok || !previewRes.ok) throw new Error("API 응답 오류");

        const summaryData = await summaryRes.json();
        const previewData = await previewRes.json();
        if (cancelled) return;
        setSummary(summaryData.by_status || {});
        setRecords(previewData.records || []);
      } catch (e) {
        if (!cancelled) setError("API에 연결할 수 없습니다. 백엔드/ES가 떠 있는지 확인하세요.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true; // 언마운트/재요청 시 이전 응답이 상태를 덮어쓰지 않게
    };
  }, [filter]);

  return (
    <main style={{ maxWidth: 1000, margin: "0 auto", padding: "32px 20px" }}>
      <h1 style={{ fontSize: 24, marginBottom: 4 }}>IIS Web Monitor</h1>
      <p style={{ color: "#94a3b8", marginTop: 0 }}>
        요청 로그 기반 장애 / 응답지연 모니터링
      </p>

      {/* 상태별 요약 카드 (클릭 시 필터) */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "20px 0" }}>
        <Card
          active={filter === null}
          onClick={() => setFilter(null)}
          label="전체"
          count={Object.values(summary).reduce((a, b) => a + b, 0)}
          color="#38bdf8"
        />
        {Object.keys(STATUS_META).map((key) => (
          <Card
            key={key}
            active={filter === key}
            onClick={() => setFilter(key)}
            label={STATUS_META[key].label}
            count={summary[key] || 0}
            color={STATUS_META[key].color}
          />
        ))}
      </div>

      {error && (
        <div style={{ color: "#fca5a5", padding: 12, background: "#7f1d1d33", borderRadius: 8 }}>
          {error}
        </div>
      )}

      {loading ? (
        <p style={{ color: "#94a3b8" }}>불러오는 중...</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "#94a3b8", fontSize: 13 }}>
              <th style={th}>시각</th>
              <th style={th}>메서드</th>
              <th style={th}>경로</th>
              <th style={th}>상태</th>
              <th style={th}>응답(ms)</th>
              <th style={th}>판정</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r, i) => (
              <tr key={i} style={{ borderTop: "1px solid #1e293b" }}>
                <td style={td}>{r.logged_at}</td>
                <td style={td}>{r.method}</td>
                <td style={td}>{r.path}</td>
                <td style={td}>{r.status_code}</td>
                <td style={td}>{r.response_time_ms}</td>
                <td style={{ ...td, color: STATUS_META[r.health_status]?.color }}>
                  {STATUS_META[r.health_status]?.label || r.health_status}
                </td>
              </tr>
            ))}
            {records.length === 0 && (
              <tr>
                <td style={td} colSpan={6}>
                  표시할 로그가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </main>
  );
}

function Card({ label, count, color, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        cursor: "pointer",
        minWidth: 110,
        padding: "14px 16px",
        borderRadius: 10,
        border: active ? `2px solid ${color}` : "1px solid #1e293b",
        background: "#111827",
        color: "#e2e8f0",
        textAlign: "left",
      }}
    >
      <div style={{ fontSize: 12, color: "#94a3b8" }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{count}</div>
    </button>
  );
}

const th = { padding: "8px 10px", fontWeight: 600 };
const td = { padding: "8px 10px", fontSize: 14 };
