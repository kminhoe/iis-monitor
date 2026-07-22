"""IIS Web Monitor API.

엔드포인트:
- GET /health              헬스체크
- GET /api/iis/summary     health_status별 건수 집계
- GET /api/iis/preview     로그 조회 (health_status 필터 + 페이지네이션)

설계 메모(면접 talking point):
- 앞선 버전은 매 요청마다 파일 전체를 파싱하고 전 레코드를 그대로 반환했다.
  대용량 로그에서 메모리/직렬화가 터진다 -> 적재는 시작 시 1회, 조회는 ES 페이지네이션으로 분리.
- 조회는 ES가 담당하므로 API 프로세스 메모리는 페이지 크기(<=1000)만큼만 쓴다.
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import es_client
from .iis_parser import parse_iis_log

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CWD가 아니라 이 파일 위치 기준 절대 경로 -> Docker/uvicorn 어디서 띄워도 안 깨짐
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = Path(os.environ.get("IIS_LOG_PATH", BASE_DIR / "logs" / "sample_iis.log"))

app = FastAPI(
    title="IIS Web Monitor",
    description="IIS 요청 로그 기반 장애/응답지연 모니터링 API",
    version="1.0.0",
)

# 데모 편의를 위해 전체 허용. 실배포 시엔 프론트 도메인만 화이트리스트.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.on_event("startup")
def ingest_on_startup():
    try:
        es_client.ensure_index()
        if not LOG_PATH.exists():
            logger.warning("로그 파일 없음, 적재 생략: %s", LOG_PATH)
            return
        records = parse_iis_log(LOG_PATH)
        es_client.index_records(records)
    except Exception:
        # ES가 아직 안 떠서 실패해도 앱은 뜨게 둔다(헬스체크/재시도 여지).
        logger.exception("시작 시 적재 실패 (ES 준비 전일 수 있음)")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/iis/summary")
def summary():
    try:
        return {"by_status": es_client.summary_by_status()}
    except Exception:
        logger.exception("요약 조회 실패")
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
