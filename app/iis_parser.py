"""IIS W3C 확장 로그 파서.

설계 메모(면접 talking point):
- IIS는 UA 등 값 안의 공백을 '+'로 인코딩하므로 line.split()으로 안전하게 토큰 분리가 된다.
- date/time은 W3C 스펙상 선택 필드라 없을 수 있다 -> 없으면 'NoneTNoneZ' 같은 쓰레기 대신 진짜 None을 넣는다.
- 필드 수가 안 맞는 줄(공격 시도/깨진 줄)은 조용히 버리지 않고 개수를 세어 로그로 남긴다.
- 방문자 식별은 IP+UA를 salt와 함께 해시. salt 없는 해시는 IPv4(32bit) 전수대입으로 역산되므로 salt 필수.
"""

import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# 실배포 시 반드시 환경변수로 주입. 하드코딩된 기본값은 데모 전용.
VISITOR_SALT = os.environ.get("VISITOR_SALT", "demo-salt-change-me")

SLOW_THRESHOLD_MS = 3000


def to_int(value, default=0):
    if value is None:
        return default
    value = value.strip()
    if value.isdigit():
        return int(value)
    return default


def _build_timestamp(date_str, time_str):
    if not date_str or not time_str:
        return None
    # IIS W3C 로그의 시각은 기본 UTC 기준
    return f"{date_str}T{time_str}Z"


def _classify(status_code, response_time_ms):
    # 우선순위 정책: 상태코드 이상 > 응답지연.
    # (400대이면서 느린 요청은 warning으로 잡히고 slow는 놓친다 - 의도된 단순화)
    if status_code >= 500:
        return "error"
    if status_code >= 400:
        return "warning"
    if response_time_ms >= SLOW_THRESHOLD_MS:
        return "slow"
    return "normal"


def _visitor_id(client_ip, user_agent):
    source = f"{VISITOR_SALT}|{client_ip}|{user_agent}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _doc_id(record):
    # 재적재 시 중복 방지용 결정적 ID. 같은 줄이면 같은 ID -> Elasticsearch upsert.
    key = f"{record['logged_at']}|{record['path']}|{record['status_code']}|{record['visitor_id']}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def parse_iis_log(file_path):
    fields = []
    records = []
    skipped = 0

    with open(file_path, "r", encoding="utf-8", errors="replace") as log_file:
        for line_no, line in enumerate(log_file, start=1):
            line = line.strip()
            if not line:
                continue
            if line.startswith("#Fields:"):
                fields = line.replace("#Fields:", "", 1).strip().split()
                continue
            if line.startswith("#") or not fields:
                continue

            values = line.split()
            if len(values) != len(fields):
                skipped += 1
                logger.warning("필드 수 불일치로 스킵 (line %d): %s", line_no, line[:200])
                continue

            raw = dict(zip(fields, values))
            status_code = to_int(raw.get("sc-status"))
            response_time_ms = to_int(raw.get("time-taken"))

            record = {
                "logged_at": _build_timestamp(raw.get("date"), raw.get("time")),
                "method": raw.get("cs-method"),
                "path": raw.get("cs-uri-stem"),
                "status_code": status_code,
                "response_time_ms": response_time_ms,
                "health_status": _classify(status_code, response_time_ms),
                "visitor_id": _visitor_id(
                    raw.get("c-ip", "-"), raw.get("cs(User-Agent)", "-")
                ),
            }
            record["doc_id"] = _doc_id(record)
            records.append(record)

    if skipped:
        logger.warning("총 %d개 라인 스킵됨", skipped)
    return records
