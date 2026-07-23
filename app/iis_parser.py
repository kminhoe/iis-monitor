"""IIS W3C 확장 로그 파서.

"""

import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# 실배포 시 반드시 환경변수로 주입. 하드코딩된 기본값은 데모 전용.
VISITOR_SALT = os.environ.get("VISITOR_SALT", "demo-salt-change-me")

IIS_FIELDS = [
    "date", "time", "s-ip", "cs-method", "cs-uri-stem", "cs-uri-query",
    "s-port", "cs-username", "c-ip", "cs(User-Agent)",
    "sc-status", "sc-substatus", "sc-win32-status", "time-taken",
]

SLOW_THRESHOLD_MS = 3000
TIMEOUT_THRESHOLD_MS = 30000

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
    if response_time_ms >= TIMEOUT_THRESHOLD_MS:
       return "timeout"
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
   key = f"{record['logged_at']}|{record['path']}|{record['status_code']}|{record['visitor_id']}|{record['query']}"
   return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _parse_line(line, fields):

    values = line.split()
    if len(values) != len(fields):
        return None  # 필드 수 불일치(깨진 줄/공격 시도)
 
    raw = dict(zip(fields, values))
    status_code = to_int(raw.get("sc-status"))
    response_time_ms = to_int(raw.get("time-taken"))
 
    query_raw = raw.get("cs-uri-query")
    query = None if query_raw in (None, "-") else query_raw
 
    record = {
        "logged_at": _build_timestamp(raw.get("date"), raw.get("time")),
        "method": raw.get("cs-method"),
        "path": raw.get("cs-uri-stem"),
        "query": query,
        "status_code": status_code,
        "response_time_ms": response_time_ms,
        "health_status": _classify(status_code, response_time_ms),
        "visitor_id": _visitor_id(
            raw.get("c-ip", "-"), raw.get("cs(User-Agent)", "-")
        ),
    }
    record["doc_id"] = _doc_id(record)
    return record
 
 
def parse_lines(lines, fields=IIS_FIELDS):
    records = []
    skipped = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rec = _parse_line(line, fields)
        if rec is None:
            skipped += 1
        else:
            records.append(rec)
    if skipped:
        logger.warning("parse_lines: %d개 라인 스킵됨", skipped)
    return records
 
 
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
 
            rec = _parse_line(line, fields)
            if rec is None:
                skipped += 1
                logger.warning("필드 수 불일치로 스킵 (line %d): %s", line_no, line[:200])
            else:
                records.append(rec)
 
    if skipped:
        logger.warning("총 %d개 라인 스킵됨", skipped)
    return records
