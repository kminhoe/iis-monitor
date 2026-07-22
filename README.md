# IIS Web Monitor

IIS 요청 로그를 파싱해 오류(4xx/5xx)와 응답 지연을 자동 분류하고, 검색·집계·시각화하는 개인 학습 프로젝트.


## 스택

| 구분 | 기술 |
| --- | --- |
| 백엔드 | Python 3.11, FastAPI |
| 데이터스토어 | Elasticsearch 8 |
| 프론트엔드 | Next.js 14 (App Router), React |
| 실행 환경 | Docker Compose (Linux 컨테이너) |

## 아키텍처

```
IIS access log ──▶ 파서(Python) ──▶ Elasticsearch ──▶ FastAPI ──▶ Next.js 대시보드
                   상태 분류/익명화       검색·집계        조회 API      요약·필터·테이블
```

- 파서: W3C 로그를 파싱, 상태코드/응답시간으로 `normal / slow / warning / error` 분류
- ES: 상태·경로·시각 기반 검색과 집계 담당
- API: ES를 조회하는 얇은 계층, 페이지네이션 제공
- 프론트: 상태별 건수 요약 + 필터 + 로그 테이블

## 실행

```bash
docker compose up --build
```

- 대시보드: http://localhost:3000
- API 문서(Swagger): http://localhost:8001/docs
- Elasticsearch: http://localhost:9200


## API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/health` | 헬스체크 |
| GET | `/api/iis/summary` | health_status별 건수 집계 |
| GET | `/api/iis/preview?health_status=&limit=&offset=` | 로그 조회(필터 + 페이지네이션) |


