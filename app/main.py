"""IIS Web Monitor API.

엔드포인트:
- GET  /health                 헬스체크
- GET  /api/iis/summary        상태별 건수 + 고유 방문자 수
- GET  /api/iis/timeseries     시간대별 요청 추이 (interval, since_minutes)
- GET  /api/iis/preview        로그 조회 (필터 + 페이지네이션)
- GET  /api/sim/status         시뮬레이터 상태/설정 조회
- POST /api/sim/config         시뮬레이터 설정 조작(요청량/오류율/이용자수 등)

"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import es_client, simulator
from .iis_parser import parse_iis_log

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CWD가 아니라 이 파일 위치 기준 절대 경로 -> Docker/uvicorn 어디서 띄워도 안 깨짐
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = Path(os.environ.get("IIS_LOG_PATH", BASE_DIR / "logs" / "sample_iis.log"))

app = FastAPI(
    title="IIS Web Monitor",
    description="IIS 요청 로그 기반 장애/응답지연 모니터링",
    version="1.0.0",
)

# 데모 편의를 위해 전체 허용. 실배포 시엔 프론트 도메인만 화이트리스트.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    try:
        es_client.ensure_index()
        if LOG_PATH.exists():
            records = parse_iis_log(LOG_PATH)
            es_client.index_records(records)
        else:
            logger.warning("초기 로그 파일 없음, 적재 생략: %s", LOG_PATH)
    except Exception:
        logger.exception("시작 시 초기 적재 실패 (ES 준비 전일 수 있음)")
    # 랜덤 트래픽 시뮬레이터 기동. SIM_ENABLED=false면 생성은 멈춘 상태로 스레드만 대기.
    simulator.start()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/iis/summary")
def summary():
    try:
        by_status, unique_visitors = es_client.summary_by_status()
        return {"by_status": by_status, "unique_visitors": unique_visitors}
    except Exception:
        logger.exception("요약 조회 실패")
        raise HTTPException(status_code=503, detail="검색 엔진에 연결할 수 없습니다.")


@app.get("/api/iis/timeseries")
def get_timeseries(
    interval: str = Query(default="1h", description="예: 1m, 30m, 1h, 1d"),
    since_minutes: int | None = Query(default=None, description="최근 N분만(실시간 뷰용)"),
):
    try:
        return {
            "interval": interval,
            "series": es_client.timeseries(interval, since_minutes),
        }
    except Exception:
        logger.exception("시계열 조회 실패")
        raise HTTPException(status_code=503, detail="검색 엔진에 연결할 수 없습니다.")


@app.get("/api/iis/preview")
def preview(
    health_status: str | None = Query(default=None, description="normal|slow|warning|error"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    try:
        total, records = es_client.search_records(health_status, limit, offset)
    except Exception:
        logger.exception("조회 실패")
        raise HTTPException(status_code=503, detail="검색 엔진에 연결할 수 없습니다.")
    return {
        "total": total,
        "count": len(records),
        "offset": offset,
        "limit": limit,
        "records": records,
    }


class SimConfig(BaseModel):
    # 모두 선택. 준 값만 갱신된다.
    enabled: bool | None = None
    interval_seconds: float | None = None
    requests_per_tick: int | None = None
    error_rate: float | None = None
    slow_rate: float | None = None
    user_pool: int | None = None


@app.get("/api/sim/status")
def sim_status():
    return simulator.status()


@app.post("/api/sim/config")
def sim_config(cfg: SimConfig):
    # 방어적 클램프: 데모가 폭주하지 않게 상한을 둔다.
    patch = cfg.model_dump(exclude_none=True)
    if "requests_per_tick" in patch:
        patch["requests_per_tick"] = max(0, min(200, patch["requests_per_tick"]))
    if "user_pool" in patch:
        patch["user_pool"] = max(1, min(100000, patch["user_pool"]))
    if "error_rate" in patch:
        patch["error_rate"] = max(0.0, min(1.0, patch["error_rate"]))
    if "slow_rate" in patch:
        patch["slow_rate"] = max(0.0, min(1.0, patch["slow_rate"]))
    if "interval_seconds" in patch:
        patch["interval_seconds"] = max(0.5, min(60.0, patch["interval_seconds"]))
    updated = simulator.update_config(patch)
    return {"config": updated}
