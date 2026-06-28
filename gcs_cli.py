#!/usr/bin/env python3
"""gcs_cli — QGroundControl 대체 제어 CLI (P-26).

router/QGC 제거(브로드캐스트 전환) 후, 기체 제어(ARM/이륙/모드/RTL 등)를
업링크 브로드캐스트로 발행하는 최소 지상통제 도구. dahnet 상의 컨테이너(tools)
에서 실행한다.

사용 (tools 컨테이너 내부):
    python gcs_cli.py status
    python gcs_cli.py arm
    python gcs_cli.py mode GUIDED
    python gcs_cli.py takeoff 10
    python gcs_cli.py rtl
    python gcs_cli.py disarm

흐름: gcs_cli ─업링크 bcast(UP_PORT)→ c2channel ─TCP→ air(FC)
      air ─다운링크 bcast(DOWN_PORT)→ gcs_cli (ACK/상태 수신)
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import bcastlink  # noqa: E402
from pymavlink import mavutil  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1].lower()

    m = bcastlink.connect(255, 190)   # QGC 자리(255/190)
    m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                         mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    print("[gcs] 다운링크 하트비트 대기 ...")
    if m.wait_heartbeat(timeout=20) is None:
        print("[!] 하트비트 없음 — air/c2channel 기동 확인"); sys.exit(1)
    sysid, comp = m.target_system, m.target_component
    print(f"[gcs] 연결됨 sys={sysid}")

    def cmd_long(command, *params):
        p = list(params) + [0] * (7 - len(params))
        m.mav.command_long_send(sysid, comp, command, 0, *p)

    def wait_ack(command, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            msg = m.recv_match(type="COMMAND_ACK", blocking=True, timeout=2)
            if msg and msg.command == command:
                ok = msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED
                print(f"[gcs] ACK cmd={command} result={msg.result} "
                      f"({'OK' if ok else '거부/지연'})")
                return ok
        print(f"[gcs] cmd={command} ACK 미수신(timeout)")
        return False

    if cmd == "status":
        print("[gcs] 5초간 상태 관측 ...")
        end = time.time() + 5
        while time.time() < end:
            msg = m.recv_match(blocking=True, timeout=2)
            if not msg:
                continue
            t = msg.get_type()
            if t == "HEARTBEAT" and msg.get_srcComponent() == 1:
                armed = bool(msg.base_mode
                             & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                print(f"   mode={mavutil.mode_string_v10(msg)} "
                      f"armed={armed}")
            elif t == "GLOBAL_POSITION_INT":
                print(f"   pos=({msg.lat/1e7:.6f},{msg.lon/1e7:.6f}) "
                      f"relalt={msg.relative_alt/1000:.1f}m")
            elif t == "GPS_RAW_INT":
                print(f"   gps fix={msg.fix_type} sats={msg.satellites_visible}")

    elif cmd == "arm":
        cmd_long(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        wait_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)

    elif cmd == "disarm":
        cmd_long(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)
        wait_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)

    elif cmd == "takeoff":
        alt = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
        cmd_long(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, alt)
        wait_ack(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF)

    elif cmd == "mode":
        if len(sys.argv) < 3:
            print("[!] 사용: gcs_cli.py mode <MODE>  (예: GUIDED/STABILIZE/RTL/LAND)")
            return
        mode = sys.argv[2].upper()
        mapping = m.rx.mode_mapping() if hasattr(m.rx, "mode_mapping") else None
        if mapping and mode in mapping:
            cmd_long(mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                     mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                     mapping[mode])
            wait_ack(mavutil.mavlink.MAV_CMD_DO_SET_MODE)
        else:
            print(f"[!] 모드 매핑 실패: {mode} (가능: "
                  f"{sorted(mapping) if mapping else '미상'})")

    elif cmd == "rtl":
        cmd_long(mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH)
        wait_ack(mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH)

    elif cmd == "land":
        cmd_long(mavutil.mavlink.MAV_CMD_NAV_LAND)
        wait_ack(mavutil.mavlink.MAV_CMD_NAV_LAND)

    else:
        print(f"[!] 알 수 없는 명령: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
