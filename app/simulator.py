"""랜덤 IIS 트래픽 시뮬레이터 (데모 전용).
"""


import logging
import os
import random
import threading
from datetime import datetime, timezone
 
from . import es_client
from .iis_parser import IIS_FIELDS, parse_lines
 
logger = logging.getLogger(__name__)
 
_PATHS_OK = ["/home", "/api/products", "/api/search", "/api/report", "/favicon.ico",
             "/api/user/profile", "/dashboard", "/api/notices", "/static/main.css"]
_PATHS_SLOW = ["/api/report", "/api/search", "/api/export"]
_PATHS_ERR = ["/api/checkout", "/api/payment", "/api/report"]
_PATHS_BAD = ["/old-page", "/wp-admin", "/admin/secret.aspx", "/.env"]
_UAS = ["Mozilla/5.0+(Windows+NT+10.0;+Win64)", "Mozilla/5.0+(Macintosh)",
        "Mozilla/5.0+(iPhone)", "Mozilla/5.0+(Android)", "Mozilla/5.0+(X11;+Linux)"]
# GET 조회 계열 경로에 붙일 쿼리스트링 후보. None이면 쿼리 없음("-").
_QUERIES = ["q=apple&page=1", "q=banana&page=2", "q=laptop", "type=full",
            "type=summary", "category=book&page=3", None, None]
# 조회 계열 경로에만 쿼리를 붙인다.
_QUERY_PATHS = {"/api/search", "/api/report", "/api/products"}
 
# 런타임에 API로 조작되는 설정. 매 tick마다 이 값을 다시 읽는다.
config = {
    "enabled": os.environ.get("SIM_ENABLED", "true").lower() == "true",
    "interval_seconds": 2,
    "requests_per_tick": 8,
    "error_rate": 0.08,
    "slow_rate": 0.10,
    "timeout_rate": 0.02,    # 30초 이상 timeout 비율
    "user_pool": 40,
}
 
_stop = threading.Event()
_thread = None
 
 
def _gen_line():
    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    time_ = now.strftime("%H:%M:%S")
 
    pool = max(1, int(config["user_pool"]))
    n = random.randint(0, pool - 1)
    c_ip = f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"
    ua = _UAS[n % len(_UAS)]
 
    roll = random.random()
    if roll < config["timeout_rate"]:
        path = random.choice(_PATHS_SLOW)
        status, rt, method = 500, random.randint(30000, 60000), "GET"
    elif roll < config["timeout_rate"] + config["error_rate"]:
        path = random.choice(_PATHS_ERR)
        status, rt, method = random.choice([500, 503]), random.randint(200, 1500), "POST"
    elif roll < config["timeout_rate"] + config["error_rate"] + config["slow_rate"]:
        path = random.choice(_PATHS_SLOW)
        status, rt, method = 200, random.randint(3000, 20000), "GET"
    elif roll < config["timeout_rate"] + config["error_rate"] + config["slow_rate"] + 0.05:
        path = random.choice(_PATHS_BAD)
        status, rt, method = random.choice([404, 401, 400]), random.randint(3, 40), random.choice(["GET", "POST"])
    else:
        path = random.choice(_PATHS_OK)
        status, rt, method = 200, random.randint(15, 400), random.choice(["GET", "GET", "POST"])
 
    # 조회 계열 GET 경로면 쿼리스트링, 아니면 "-"
    if method == "GET" and path in _QUERY_PATHS:
        q = random.choice(_QUERIES)
        query = q if q else "-"
    else:
        query = "-"
 
    return (
        f"{date} {time_} 10.0.0.5 {method} {path} {query} 443 - "
        f"{c_ip} {ua} {status} 0 0 {rt}"
    )
 
 
def _loop():
    logger.info("시뮬레이터 스레드 시작 (enabled=%s)", config["enabled"])
    while not _stop.is_set():
        if config["enabled"]:
            try:
                lines = [_gen_line() for _ in range(int(config["requests_per_tick"]))]
                records = parse_lines(lines)          # 진짜 로그와 동일한 파싱 경로
                es_client.index_live(records)
            except Exception:
                logger.exception("시뮬레이션 적재 실패 (ES 준비 전일 수 있음)")
        _stop.wait(max(0.5, float(config["interval_seconds"])))
 
 
def start():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="iis-simulator", daemon=True)
    _thread.start()
 
 
def stop():
    _stop.set()
 
 
def update_config(patch: dict):
    for k, v in patch.items():
        if k in config and v is not None:
            config[k] = v
    return dict(config)
 
 
def status():
    return {"running": bool(_thread and _thread.is_alive()), "config": dict(config)}