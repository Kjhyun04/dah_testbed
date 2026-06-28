# 페이로드 채널 (C) — 카메라/짐벌 + KLV + 영상

UAV 페이로드 다운링크(드론→지상)를 모델링하는 무선 채널. 세 요소:

| 요소 | 구현 | 컨테이너 |
|---|---|---|
| **C.0** 카메라/짐벌 (MAVLink) | comp=100 컴포넌트, HEARTBEAT·GIMBAL 상태·명령 ACK | `dah-payload` (`payload/payload.py`) |
| **C.1** KLV 메타데이터 | MISB ST0601 (센서 위경도·방위·타임스탬프) → dahnet 브로드캐스트 14580 | `dah-payload` |
| **C.2** 영상 | Gazebo 카메라(iris_with_gimbal) H.264 RTP → 호스트 UDP 5600 | `dah-air` (Gazebo GstCameraPlugin) |

## 동작 (브로드캐스트 전환)

- 페이로드 컴포넌트가 다운링크(14550)에서 FC 위치(GLOBAL_POSITION_INT)를 읽어 **ST0601 KLV의
  센서 위치**에 실어 송신.
- 카메라 HEARTBEAT/짐벌 상태는 **다운링크 브로드캐스트(14550)로 방사**(누구나 도청), 카메라 명령은
  **업링크(14555)에서 수신**해 ACK. KLV도 dahnet 브로드캐스트(14580), 영상은 호스트 5600.
- **영상원(C.2)**: 이제 air 컨테이너의 **Gazebo 카메라**(iris_with_gimbal의 GstCameraPlugin,
  P-25)가 H.264 RTP를 호스트 5600으로 송출한다. 옛 테스트패턴(`dah-video`)은 폴백 전용
  (`docker compose --profile testvid up -d video`).

## 검증 (tools 컨테이너)

```bash
docker compose exec tools python scripts/check_payload.py   # [OK] 카메라 comp=100 + KLV 디코드
python scripts/check_video.py                               # [OK] RTP 영상(호스트 5600)
```

## 사용자 공격면

- **KLV 센서위치 스푸핑**: KLV의 sensor lat/lon을 위조 → GPS 스푸핑과 교차연계해 상관 기반 탐지 회피.
- **영상 가로채기/재밍**: RTP 스트림(5600) 가로채기·차단.
- **카메라/짐벌 탈취**: comp=100에 명령 주입(LOI 3 수준).

## 한계
- 영상은 Gazebo 카메라 센서(P-25). GPU 미통과 환경에선 소프트웨어 렌더링이라 프레임 부하가
  있을 수 있다(폴백: `--profile testvid`의 테스트패턴). KLV-in-MPEG-TS 멀티플렉싱(완전 STANAG
  4609)은 미구현 — KLV는 별도 UDP로 송신(영상과 동기 메타데이터의 근사).
