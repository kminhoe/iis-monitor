"""Elasticsearch 연동.

"""

import logging
import os

from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)

ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
INDEX_NAME = "iis-logs"

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "logged_at": {"type": "date", "format": "strict_date_time||strict_date_optional_time"},
            "method": {"type": "keyword"},
            "path": {"type": "keyword"},
            "status_code": {"type": "integer"},
            "response_time_ms": {"type": "integer"},
            "health_status": {"type": "keyword"},
            "visitor_id": {"type": "keyword"},
        }
    }
}

_client = None


def get_es():
    global _client
    if _client is None:
        _client = Elasticsearch(ES_URL, request_timeout=10)
    return _client


def ensure_index():
    es = get_es()
    if not es.indices.exists(index=INDEX_NAME):
        es.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)
        logger.info("인덱스 생성: %s", INDEX_NAME)


def index_records(records):
    """결정적 doc_id를 _id로 사용해 upsert. 재실행해도 중복 안 쌓임."""
    es = get_es()
    actions = []
    for r in records:
        doc = {k: v for k, v in r.items() if k != "doc_id"}
        actions.append({"_index": INDEX_NAME, "_id": r["doc_id"], "_source": doc})
    if not actions:
        return 0
    success, _ = helpers.bulk(es, actions)
    es.indices.refresh(index=INDEX_NAME)  # 적재 직후 조회 가능하도록
    logger.info("ES 적재 완료: %d건", success)
    return success


def index_live(records):
    """실시간 시뮬레이션용. 매번 새 이벤트이므로 ES 자동 ID 사용(중복 제거 안 함)."""
    es = get_es()
    actions = [
        {"_index": INDEX_NAME, "_source": {k: v for k, v in r.items() if k != "doc_id"}}
        for r in records
    ]
    if not actions:
        return 0
    success, _ = helpers.bulk(es, actions)
    es.indices.refresh(index=INDEX_NAME)
    return success


def search_records(health_status=None, limit=100, offset=0):
    es = get_es()
    query = {"match_all": {}} if not health_status else {"term": {"health_status": health_status}}
    resp = es.search(
        index=INDEX_NAME,
        query=query,
        sort=[{"logged_at": {"order": "asc"}}],
        from_=offset,
        size=limit,
    )
    total = resp["hits"]["total"]["value"]
    records = [hit["_source"] for hit in resp["hits"]["hits"]]
    return total, records


def summary_by_status():
    """상태별 건수 + 고유 방문자 수를 한 번의 집계로."""
    es = get_es()
    resp = es.search(
        index=INDEX_NAME,
        size=0,
        aggs={
            "by_status": {"terms": {"field": "health_status"}},
            # cardinality = 중복 제거 개수(근사). visitor_id 기준 고유 방문자.
            "unique_visitors": {"cardinality": {"field": "visitor_id"}},
        },
    )
    by_status = {
        b["key"]: b["doc_count"] for b in resp["aggregations"]["by_status"]["buckets"]
    }
    unique_visitors = resp["aggregations"]["unique_visitors"]["value"]
    return by_status, unique_visitors


def timeseries(interval="1h", since_minutes=None):
    """시간대별 요청 추이. since_minutes를 주면 최근 N분만(실시간 뷰용)."""
    es = get_es()
    if since_minutes:
        query = {"range": {"logged_at": {"gte": f"now-{int(since_minutes)}m"}}}
    else:
        query = {"match_all": {}}
    resp = es.search(
        index=INDEX_NAME,
        size=0,
        query=query,
        aggs={
            "over_time": {
                "date_histogram": {
                    "field": "logged_at",
                    "fixed_interval": interval,
                    "min_doc_count": 0,  # 데이터 없는 구간도 0으로 채워 라인이 끊기지 않게
                },
                "aggs": {"by_status": {"terms": {"field": "health_status"}}},
            }
        },
    )
    result = []
    for bucket in resp["aggregations"]["over_time"]["buckets"]:
        row = {
            "time": bucket["key_as_string"],
            "total": bucket["doc_count"],
            "normal": 0,
            "slow": 0,
            "warning": 0,
            "error": 0,
        }
        for s in bucket["by_status"]["buckets"]:
            row[s["key"]] = s["doc_count"]
        result.append(row)
    return result
