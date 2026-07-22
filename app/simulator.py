"""랜덤 IIS 트래픽 시뮬레이터 (데모 전용).

⚠️ 실제 운영 사이트에는 절대 켜지 말 것.
   운영에서는 이 생성기 대신 실제 IIS 로그를 tail 해서 적재해야 한다.
   (SIM_ENABLED=false 로 끄고, 실 로그 인제스터를 붙이는 게 운영 구조)
"""

import logging
import os
import random
import threading
from datetime import datetime, timezone

from . import es_client
from .iis_parser import _classify, _visitor_id

logger = logging.getLogger(__name__)

_PATHS_OK = ["/home", "/api/products", "/api/search", "/api/report", "/favicon.ico",
             "/api/user/profile", "/dashboard", "/api/notices", "/static/main.css"]
_PATHS_SLOW = ["/api/report", "/api/search", "/api/export"]
_PATHS_ERR = ["/api/checkout", "/api/payment", "/api/report"]
_PATHS_BAD = ["/old-page", "/wp-admin", "/admin/secret.aspx", "/.env"]
_UAS = ["Mozilla/5.0+(Windows+NT+10.0;+Win64)", "Mozilla/5.0+(Macintosh)",
        "Mozilla/5.0+(iPhone)", "Mozilla/5.0+(Android)", "Mozilla/5.0+(X11;+Linux)"]

# 런타임에 API로 조작되는 설정. 매 tick마다 이 값을 다시 읽는다.
config = {
    "enabled": os.environ.get("SIM_ENABLED", "true").lower() == "true",
    "interval_seconds": 2,      # 몇 초마다 생성할지
    "requests_per_tick": 8,     # 한 번에 만들 요청 수 (= 트래픽 세기)
    "error_rate": 0.08,         # 5xx 비율
    "slow_rate": 0.10,          # 3초 이상 지연 비율
    "user_pool": 40,            # 서로 다른 방문자 수 (고유 방문자가 이 값으로 수렴)
}

_stop = threading.Event()
_thread = None


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_one():
    pool = max(1, int(config["user_pool"]))
    n = random.randint(0, pool - 1)
    ip = f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"
    ua = _UAS[n % len(_UAS)]  # 방문자별 UA 고정 -> (IP,UA) 조합 수 = user_pool

    roll = random.random()
    if roll < config["error_rate"]:
        path = random.choice(_PATHS_ERR)
        status = random.choice([500, 503])
        rt = random.randint(200, 1500)
        method = "POST"
    elif roll < config["error_rate"] + config["slow_rate"]:
        path = random.choice(_PATHS_SLOW)
        status = 200
        rt = random.randint(3000, 8000)
        method = "GET"
    elif roll < config["error_rate"] + config["slow_rate"] + 0.05:
        path = random.choice(_PATHS_BAD)
        status = random.choice([404, 401, 400])
        rt = random.randint(3, 40)
        method = random.choice(["GET", "POST"])
    else:
        path = random.choice(_PATHS_OK)
        status = 200
        rt = random.randint(15, 400)
        method = random.choice(["GET", "GET", "POST"])

    return {
        "logged_at": _now_iso(),
        "method": method,
        "path": path,
        "status_code": status,
        "response_time_ms": rt,
        "health_status": _classify(status, rt),
        "visitor_id": _visitor_id(ip, ua),
    }


def _loop():
    logger.info("시뮬레이터 스레드 시작 (enabled=%s)", config["enabled"])
    while not _stop.is_set():
        if config["enabled"]:
            try:
                records = [_gen_one() for _ in range(int(config["requests_per_tick"]))]
                es_client.index_live(records)
            except Exception:
                logger.exception("시뮬레이션 적재 실패 (ES 준비 전일 수 있음)")
        # 설정이 바뀌면 다음 tick부터 반영. 종료 신호도 여기서 체크.
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
