#!/usr/bin/env python3
# ============================================================================
# mav_aria_proxy — MAVLink C2 스트림을 KCMVP 국산암호(ARIA-256)로 감싸는 UDP 프록시.
#
#   목적(응용계층 PoC): 검증된 셀룰러 C2 경로(UAV-UE ↔ GCS-UE, UDP 14550)를 건드리지 않고,
#     그 사이에 암·복호 프록시 한 쌍을 끼워 셀룰러 링크 위로는 **ARIA 암호문만** 흐르게 한다.
#     → 기존 MAVLink v2 서명(무결성·인증)과 상보: 서명=위조방지, ARIA=기밀성(도청방지).
#
#   구성(대칭 양방향 릴레이 — 같은 스크립트, 역할만 다름):
#       [SITL] --평문--> (UAV프록시) --ARIA암호문(셀룰러)--> (GCS프록시) --평문--> [GCS]
#              <--평문--            <--ARIA암호문(셀룰러)--             <--평문--
#
#   암호 스킴(Encrypt-then-MAC, AEAD 등가):
#       datagram = VER(1=0x01) || IV(16) || CT(ARIA-256-CBC, PKCS7) || HMAC-SHA256(32)
#       enc_key = SHA256("DAH-ARIA-ENC"||master),  mac_key = SHA256("DAH-ARIA-MAC"||master)
#       HMAC 검증 실패 시 조용히 폐기(위·변조 차단).
#
#   ARIA 는 OpenSSL libcrypto(EVP_aria_256_cbc)를 ctypes 로 호출(air 이미지=Ubuntu, libcrypto.so.3).
#   ★KCMVP 검증모듈 지향: 실제 검증모듈로 교체 시 아래 `AriaCbc` 클래스 1개만 갈아끼우면 된다.
#
#   사용:
#     자가검증(먼저!):  python3 mav_aria_proxy.py --selftest
#     UAV 측:  python3 mav_aria_proxy.py --plain-listen 127.0.0.1:14550 \
#                  --cipher-listen 0.0.0.0:14555 --cipher-peer <GCS_IP>:14555 --key-hex <64hex>
#     GCS 측:  python3 mav_aria_proxy.py --plain-listen 127.0.0.1:14556 --plain-peer 127.0.0.1:14550 \
#                  --cipher-listen 0.0.0.0:14555 --key-hex <64hex>
#   ※ 공격/복호시도(무단)는 사용자 몫. 본 스크립트는 방어 배선(인프라)만 세운다.
# ============================================================================
import sys, os, socket, select, argparse, hashlib, hmac, ctypes, ctypes.util

# ── ARIA-256-CBC via OpenSSL libcrypto (ctypes) ─────────────────────────────
class AriaCbc:
    """OpenSSL EVP 를 통한 ARIA-256-CBC 블록연산. (KCMVP 검증모듈 교체 지점)"""
    def __init__(self):
        self.lib = self._load()
        L = self.lib
        L.EVP_CIPHER_CTX_new.restype = ctypes.c_void_p
        L.EVP_CIPHER_CTX_free.argtypes = [ctypes.c_void_p]
        L.EVP_aria_256_cbc.restype = ctypes.c_void_p
        L.EVP_CipherInit_ex.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        L.EVP_CipherInit_ex.restype = ctypes.c_int
        L.EVP_CipherUpdate.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int),
                                       ctypes.c_char_p, ctypes.c_int]
        L.EVP_CipherUpdate.restype = ctypes.c_int
        L.EVP_CipherFinal_ex.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        L.EVP_CipherFinal_ex.restype = ctypes.c_int
        L.EVP_CIPHER_CTX_set_padding.argtypes = [ctypes.c_void_p, ctypes.c_int]
        L.EVP_CIPHER_CTX_set_padding.restype = ctypes.c_int

    @staticmethod
    def _load():
        names = ["libcrypto.so.3", "libcrypto.so.1.1", "libcrypto.so",
                 ctypes.util.find_library("crypto")]
        for n in names:
            if not n:
                continue
            try:
                return ctypes.CDLL(n)
            except OSError:
                continue
        raise RuntimeError("libcrypto 로드 실패 — OpenSSL(ARIA 포함) 필요")

    def crypt(self, key, iv, data, enc, pad=True):
        assert len(key) == 32 and len(iv) == 16
        L = self.lib
        ctx = L.EVP_CIPHER_CTX_new()
        if not ctx:
            raise RuntimeError("EVP_CIPHER_CTX_new 실패")
        try:
            if L.EVP_CipherInit_ex(ctx, L.EVP_aria_256_cbc(), None, key, iv, 1 if enc else 0) != 1:
                raise RuntimeError("EVP_CipherInit_ex 실패")
            L.EVP_CIPHER_CTX_set_padding(ctx, 1 if pad else 0)
            out = ctypes.create_string_buffer(len(data) + 32)
            olen = ctypes.c_int(0)
            if L.EVP_CipherUpdate(ctx, out, ctypes.byref(olen), data, len(data)) != 1:
                raise RuntimeError("EVP_CipherUpdate 실패")
            fin = ctypes.create_string_buffer(32)
            flen = ctypes.c_int(0)
            if L.EVP_CipherFinal_ex(ctx, fin, ctypes.byref(flen)) != 1:
                raise RuntimeError("EVP_CipherFinal_ex 실패(복호 시 패딩/키 불일치)")
            return out.raw[:olen.value] + fin.raw[:flen.value]
        finally:
            L.EVP_CIPHER_CTX_free(ctx)


# ── AEAD 래퍼 (ARIA-256-CBC + HMAC-SHA256, Encrypt-then-MAC) ─────────────────
VER = b"\x01"

class C2Cipher:
    def __init__(self, master_key: bytes, aria: AriaCbc):
        self.enc_key = hashlib.sha256(b"DAH-ARIA-ENC" + master_key).digest()   # 32B
        self.mac_key = hashlib.sha256(b"DAH-ARIA-MAC" + master_key).digest()   # 32B
        self.aria = aria

    def encrypt(self, pt: bytes) -> bytes:
        iv = os.urandom(16)
        ct = self.aria.crypt(self.enc_key, iv, pt, enc=True, pad=True)
        hdr = VER + iv + ct
        mac = hmac.new(self.mac_key, hdr, hashlib.sha256).digest()
        return hdr + mac

    def decrypt(self, blob: bytes):
        if len(blob) < 1 + 16 + 16 + 32:            # VER+IV+최소1블록+MAC
            return None
        hdr, mac = blob[:-32], blob[-32:]
        exp = hmac.new(self.mac_key, hdr, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, exp):        # 위·변조/오키 → 폐기
            return None
        if hdr[0:1] != VER:
            return None
        iv, ct = hdr[1:17], hdr[17:]
        if len(ct) == 0 or len(ct) % 16 != 0:
            return None
        try:
            return self.aria.crypt(self.enc_key, iv, ct, enc=False, pad=True)
        except Exception:
            return None


# ── 자가검증 (KAT: openssl 로 교차검증된 벡터 + 라운드트립 + 변조탐지) ─────────
def selftest() -> int:
    print("[selftest] ARIA-256-CBC KAT (openssl 교차검증 벡터)...")
    aria = AriaCbc()
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
    iv  = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    pt  = b"MAVLINK_ARIA_KAT"                         # 정확히 16B
    exp = bytes.fromhex("839063fd5e0ce79f9c2f64c303200ed6")
    got = aria.crypt(key, iv, pt, enc=True, pad=False)
    assert got == exp, "KAT 불일치! got=%s" % got.hex()
    back = aria.crypt(key, iv, got, enc=False, pad=False)
    assert back == pt, "KAT 복호 불일치"
    print("           ✓ ARIA-256-CBC 정답 일치 (%s)" % exp.hex())

    print("[selftest] AEAD 라운드트립 + 변조탐지...")
    c = C2Cipher(os.urandom(32), aria)
    msg = b"\xfe\x09..HEARTBEAT..MAVLINK C2 payload " * 3
    blob = c.encrypt(msg)
    assert c.decrypt(blob) == msg, "라운드트립 실패"
    tampered = bytearray(blob); tampered[20] ^= 0x01
    assert c.decrypt(bytes(tampered)) is None, "변조 미탐지!"
    wrong = C2Cipher(os.urandom(32), aria)
    assert wrong.decrypt(blob) is None, "타키 복호 허용됨!"
    print("           ✓ 라운드트립 OK · 1비트 변조/타키 → 폐기 OK")
    print("[selftest] ✅ 전체 통과 — ARIA C2 프록시 사용 가능")
    return 0


# ── UDP 양방향 암호 릴레이 ──────────────────────────────────────────────────
def hostport(s: str):
    h, p = s.rsplit(":", 1)
    return (h, int(p))

def run_proxy(a) -> int:
    key = bytes.fromhex(a.key_hex.strip())
    if len(key) != 32:
        print("[proxy] ✗ --key-hex 는 32바이트(64 hex) 여야 함", file=sys.stderr); return 2
    cipher = C2Cipher(key, AriaCbc())

    plain = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    plain.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    plain.bind(hostport(a.plain_listen))
    ciph = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ciph.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ciph.bind(hostport(a.cipher_listen))

    plain_peer  = hostport(a.plain_peer)  if a.plain_peer  else None   # 없으면 학습
    cipher_peer = hostport(a.cipher_peer) if a.cipher_peer else None
    print("[proxy] plain=%s(peer=%s)  cipher=%s(peer=%s)  ARIA-256-CBC+HMAC" % (
        a.plain_listen, plain_peer, a.cipher_listen, cipher_peer), flush=True)

    n_up = n_dn = n_drop = 0
    while True:
        r, _, _ = select.select([plain, ciph], [], [])
        for s in r:
            if s is plain:                              # 평문 수신 → 암호화 → 셀룰러
                data, addr = plain.recvfrom(65535)
                if a.plain_peer is None:
                    plain_peer = addr
                if cipher_peer is None:
                    continue                            # 상대 아직 미학습 → 폐기
                ciph.sendto(cipher.encrypt(data), cipher_peer)
                n_up += 1
            else:                                       # 암호문 수신 → 복호 → 평문측
                blob, addr = ciph.recvfrom(65535)
                if a.cipher_peer is None:
                    cipher_peer = addr
                pt = cipher.decrypt(blob)
                if pt is None:
                    n_drop += 1
                    if a.verbose:
                        print("[proxy] ✗ HMAC 실패/폐기 (누적 %d)" % n_drop, flush=True)
                    continue
                if plain_peer is None:
                    continue
                plain.sendto(pt, plain_peer)
                n_dn += 1
            if a.verbose and (n_up + n_dn) % 50 == 0:
                print("[proxy] up=%d dn=%d drop=%d" % (n_up, n_dn, n_drop), flush=True)


def main():
    ap = argparse.ArgumentParser(description="MAVLink C2 ARIA-256 암호 프록시 (KCMVP PoC)")
    ap.add_argument("--selftest", action="store_true", help="ARIA KAT+라운드트립 자가검증 후 종료")
    ap.add_argument("--plain-listen",  help="평문측 bind host:port")
    ap.add_argument("--plain-peer",    default=None, help="평문측 고정 목적지(생략=학습)")
    ap.add_argument("--cipher-listen", help="암호문측 bind host:port")
    ap.add_argument("--cipher-peer",   default=None, help="암호문측 고정 목적지(생략=학습)")
    ap.add_argument("--key-hex",       help="공유 마스터키 64 hex(32B)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not (a.plain_listen and a.cipher_listen and a.key_hex):
        ap.error("--plain-listen, --cipher-listen, --key-hex 필요 (또는 --selftest)")
    sys.exit(run_proxy(a))


if __name__ == "__main__":
    main()
