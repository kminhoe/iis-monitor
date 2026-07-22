"""Elasticsearch 연동.

설계 메모(면접 talking point):
- 로그 모니터링에서 ES를 쓰는 이유: 상태/경로/시간 기반 검색·집계가 표준이고 빠르다.
- 적재 시 파서가 만든 결정적 doc_id를 _id로 사용 -> 같은 로그를 다시 적재해도 중복이 아니라 덮어쓰기(idempotent).
- 매핑을 명시(keyword/integer/date)해 status_code 정렬·health_status 집계가 정확히 되도록 한다.
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
    es = get_es()
    resp = es.search(
        index=INDEX_NAME,
        size=0,
        aggs={"by_status": {"terms": {"field": "health_status"}}},
    )
    buckets = resp["aggregations"]["by_status"]["buckets"]
    return {b["key"]: b["doc_count"] for b in buckets}
