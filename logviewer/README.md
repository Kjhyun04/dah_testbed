# 웹 로그뷰어 (#9)

세 채널(GPS·C2·페이로드)의 상태와 공격 효과를 한 화면에서 실시간 관측하는 대시보드.
v0 방향(환경→채널→로그뷰어)의 마지막 산출물.

## 구성
- `server.py` — MAVLink(다운링크 브로드캐스트 14550 수동 수신)·채널 상태(`/ctrl`) 수집 → `/state`(JSON), `/`(페이지).
- `index.html` — 패널(기체/GPS/C2/페이로드) + 궤적 캔버스 + 이벤트 로그. 1초 폴링.
- 컨테이너 `dah-logviewer` (172.28.0.80), 호스트 **http://localhost:8080**.

## 보는 것
| 패널 | 내용 |
|---|---|
| 기체 | 모드·무장·고도·하트비트율 |
| GPS 채널 | fix·위성·위경도 |
| C2 채널 | active 링크·primary/secondary 재밍률(바) |
| 페이로드 | 카메라 활성·센서 위치·영상 |
| 궤적 | 기체 위치 플롯 |
| 이벤트 | 모드변경·ARM·GPS fix변화·재밍·**failover** 타임라인 |

## 검증 (2026-06-27)
- 정적: `/state`가 세 채널 데이터 제공(drone/gps/c2/payload + events).
- 동적: `echo 0.9 > rf/channel/ctrl/jam_primary` → 대시보드가 `active→secondary` 전환과
  "primary 재밍=0.90 / C2 active→secondary" 이벤트를 실시간 포착. 해제 시 failback.

## 사용
```bash
docker compose up -d logviewer
# 브라우저: http://localhost:8080
# 공격을 가하면(재밍/스푸핑) 대시보드·이벤트에 즉시 반영
```
