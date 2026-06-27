# 페이로드 채널 (C) — 카메라/짐벌 + KLV + 영상

UAV 페이로드 다운링크(드론→지상)를 모델링하는 무선 채널. 세 요소:

| 요소 | 구현 | 컨테이너 |
|---|---|---|
| **C.0** 카메라/짐벌 (MAVLink) | comp=100 컴포넌트, HEARTBEAT·GIMBAL 상태·명령 ACK | `dah-payload` (`payload/payload.py`) |
| **C.1** KLV 메타데이터 | MISB ST0601 (센서 위경도·방위·타임스탬프) → UDP 14580 | `dah-payload` |
| **C.2** 영상 | GStreamer H.264 RTP → 지상 UDP 5600(QGC) | `dah-video` (`../video/`) |

## 동작

- 페이로드 컴포넌트가 FC 위치(GLOBAL_POSITION_INT)를 읽어 **ST0601 KLV의 센서 위치**에 실어 송신.
- 라우터 전용 엔드포인트 14553 경유로 MAVLink, KLV는 호스트 14580, 영상은 호스트 5600.

## 검증 (2026-06-27)

```bash
python ../scripts/check_payload.py   # [OK] 카메라 comp=100 + KLV 센서위치 디코드
python ../scripts/check_video.py     # [OK] RTP 영상 패킷 수신
```

## 사용자 공격면

- **KLV 센서위치 스푸핑**: KLV의 sensor lat/lon을 위조 → GPS 스푸핑과 교차연계해 상관 기반 탐지 회피.
- **영상 가로채기/재밍**: RTP 스트림(5600) 가로채기·차단.
- **카메라/짐벌 탈취**: comp=100에 명령 주입(LOI 3 수준).

## 한계
- 영상은 테스트 패턴(videotestsrc). KLV-in-MPEG-TS 멀티플렉싱(완전 STANAG 4609)은 미구현 —
  KLV는 별도 UDP로 송신(영상과 동기 메타데이터의 근사).
