# AWS_SETUP — 공유 EC2 로 testbed-4g 운영하기

> **왜 AWS 인가:** srsRAN+Open5GS 는 **SCTP 커널모듈 + TUN + Docker host networking** 을 요구한다.
> 애플 실리콘 Mac 은 Docker 가 경량 VM 안에서 돌아 이 셋이 막혀 사실상 구동 불가.
> EC2 Ubuntu 는 `modprobe sctp` 되고 host networking 이 네이티브라 **로컬 WSL2 와 동일 구성**을 그대로 재현한다.
> RF 는 SDR 하드웨어 없이 **ZMQ 소프트웨어 RF** → 클라우드에 그대로 올라간다.
>
> **운영 정책(합의):** 팀 공용 **단일 EC2** · **CPU 인스턴스** · **필요할 때만 기동** · 웹 UI 는 **SSH 터널 전용**.
> 역할경계: 이 문서/스크립트는 **인프라·환경만**. 공격(TM1/2/3)·방어·비행 실행은 사용자.

---

## 0. 구성 요약

| 항목 | 권장값 | 비고 |
|------|--------|------|
| OS(AMI) | **Ubuntu 22.04 LTS** | `00-ec2-prep.sh` 가 apt 기준 |
| 인스턴스 | **c6i.4xlarge** (16 vCPU/32GB) 시작 | 가볍게: c6i.2xlarge(8vCPU). **타입은 나중에 자유 변경**(§7) |
| 스토리지 | **gp3 60GB** | open5gs/srsRAN 컴파일 이미지가 큼 |
| 리전 | **ap-northeast-2 (서울)** | 팀 지연 최소 |
| 보안그룹 | **SSH(22) 만, 팀 IP 로 제한** | 웹 UI 는 포트 개방 대신 SSH 터널(§3) |
| 비용 | c6i.4xlarge 서울 온디맨드 ≈ **$0.7/시간** | 필요시만 stop → 컴퓨트 0, EBS 월 ~$5 |

---

## 1. 프로비저닝 (계정 준비자 1회)

> 콘솔로 만들어도 되고, 아래 CLI 스니펫을 **복붙**해도 된다(값만 채워서). 자동 실행 스크립트는 두지 않는다 — 계정·리전 종속이라 문서로 관리.

```bash
# 사전: aws configure 로 자격증명/리전(ap-northeast-2) 설정 완료 가정
REGION=ap-northeast-2
KEY=dah-testbed            # 키페어 이름
MYIP=$(curl -s https://checkip.amazonaws.com)/32   # 본인 공인 IP (팀원별로 뒤에서 추가)

# (a) 키페어 — 최초 1회. pem 은 팀에 안전히 공유하거나 팀원별 공개키 방식(§4) 권장
aws ec2 create-key-pair --region $REGION --key-name $KEY \
  --query 'KeyMaterial' --output text > ~/.ssh/$KEY.pem && chmod 400 ~/.ssh/$KEY.pem

# (b) 보안그룹 — SSH(22) 만, 우선 본인 IP. 팀원 IP 는 아래 authorize 를 반복
SG=$(aws ec2 create-security-group --region $REGION \
  --group-name dah-testbed-sg --description "dah testbed: SSH only" \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG \
  --protocol tcp --port 22 --cidr $MYIP
#  팀원 추가:  aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 22 --cidr <팀원IP>/32

# (c) 인스턴스 기동 (Ubuntu 22.04 AMI 는 SSM 파라미터로 최신 조회)
AMI=$(aws ec2 describe-images --region $REGION --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
            "Name=state,Values=available" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)

aws ec2 run-instances --region $REGION --image-id $AMI \
  --instance-type c6i.4xlarge --key-name $KEY --security-group-ids $SG \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":60,"VolumeType":"gp3"}}]' \
  --instance-initiated-shutdown-behavior stop \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=dah-testbed-4g}]' \
  --query 'Instances[0].InstanceId' --output text
```

> `--instance-initiated-shutdown-behavior stop` 를 반드시 지정 → §6 유휴 자동종료가 **terminate 가 아닌 stop** 으로 동작(디스크 보존).
> (선택) 고정 접속 주소가 필요하면 Elastic IP 를 할당·연결한다. stop/start 시 퍼블릭 IP 가 바뀌므로 팀 공유엔 EIP 편함.

---

## 2. 최초 셋업 (인스턴스에서 1회)

```bash
ssh -i ~/.ssh/dah-testbed.pem ubuntu@<PUBLIC_IP_or_EIP>

git clone https://github.com/Kjhyun04/dah_testbed
cd dah_testbed/testbed-4g
FORCE_EC2=1 bash bootstrap.sh      # 00-ec2-prep(docker/sctp/tun) → EPC → provision → G0
```

최초 1회 이미지 빌드(open5gs/srsRAN 컴파일)로 수~십분. 이후 재기동은 §5 `aws-resume.sh` 로 몇 분.

---

## 3. 웹 UI 접근 — SSH 터널 전용 (Mac 사용자 포함)

웹 UI 포트는 **루프백(127.0.0.1)에만 바인딩**되어 있어(보안그룹에 뚫려도 외부 미노출) SSH 터널로만 접근한다.
Mac 사용자도 **터미널 한 줄 + 브라우저**면 끝 — 아무것도 설치하지 않는다.

```bash
# 로컬(각자 PC)에서:
ssh -i ~/.ssh/dah-testbed.pem \
    -L 6080:localhost:6080 \   # Gazebo noVNC  → 브라우저 http://localhost:6080/vnc.html
    -L 8080:localhost:8080 \   # 로그뷰어      → http://localhost:8080
    -L 9999:localhost:9999 \   # Open5GS WebUI → http://localhost:9999 (admin/1423)
    ubuntu@<PUBLIC_IP_or_EIP>
```

터널 유지 중에는 로컬 브라우저에서 위 주소로 접속. 세션 닫으면 터널도 닫힌다.

---

## 4. 팀 다중 사용자

- **접속 키:** (권장) 팀원별 공개키를 인스턴스 `~/.ssh/authorized_keys` 에 추가 → 추적성↑, pem 공유 불필요.
  ```bash
  # 인스턴스에서, 팀원 공개키를 붙여넣기
  echo "ssh-ed25519 AAAA... teammate" >> ~/.ssh/authorized_keys
  ```
  각 팀원 IP 를 보안그룹 22 에 authorize(§1-b) 하는 것도 잊지 말 것.
- **동시 실험 규칙:** 같은 EPC/포트를 공유하므로 **"동시 1실험 + 나머지는 관찰"** 을 기본으로.
  기동한 사람이 tmux 로 띄우고 나머지는 붙어서 본다:
  ```bash
  기동자:  tmux new -s dah
  관찰자:  tmux attach -t dah      # 같은 화면 공유(읽기만 하려면 tmux attach -r)
  ```

---

## 5. Stop / Resume (필요할 때만 기동)

```bash
# 안 쓸 때 — 로컬/콘솔에서 인스턴스 정지 (컴퓨트 요금 0, EBS 만 과금)
aws ec2 stop-instances  --region ap-northeast-2 --instance-ids <ID>
# 다시 쓸 때
aws ec2 start-instances --region ap-northeast-2 --instance-ids <ID>
```

start 후 인스턴스에 SSH 접속해서 **재기동 원스텝**:
```bash
cd dah_testbed/testbed-4g
bash scripts/aws-resume.sh          # sctp/tun/docker 재확인 → EPC 되살림 → G0 재수립
```
- 이미지/가입자DB 는 EBS 에 보존되어 **rebuild/재-provision 불필요**.
- srsRAN 라디오 attach 는 stop 후 사라지므로 `aws-resume.sh` 가 20-ran-up 으로 재수립한다.
- ⚠️ **terminate 금지**(디스크·이미지 소멸). 항상 **stop** 만.

---

## 6. 비용 가드 — 유휴 자동종료 (옵트인)

켜두고 깜빡해도 아무도 안 쓰면 알아서 stop 되도록:
```bash
# 5분 주기 cron 등록 (root)
sudo crontab -e
#   아래 한 줄 추가(경로는 실제 클론 위치로):
#   */5 * * * * /home/ubuntu/dah_testbed/testbed-4g/scripts/aws-idle-autostop.sh >> /var/log/dah-autostop.log 2>&1
```
- 판정: **로그인 세션 0 && 15분 loadavg < 0.4** 가 연속 3회(≈15분) → `shutdown -h now`(= stop, §1 설정 전제).
- 임계 조정: `IDLE_LOAD_MAX`, `CHECKS_REQUIRED` 환경변수. 점검만:  `DRY_RUN=1 bash scripts/aws-idle-autostop.sh`.

---

## 7. 인스턴스 타입 변경 (CPU ↔ GPU)

락인 없음. Gazebo 3D 를 부드럽게 봐야 할 데모 직전엔 GPU 로, 끝나면 CPU 로 되돌린다:
```bash
aws ec2 stop-instances --instance-ids <ID> && aws ec2 wait instance-stopped --instance-ids <ID>
aws ec2 modify-instance-attribute --instance-id <ID> --instance-type g4dn.xlarge   # 되돌릴 땐 c6i.4xlarge
aws ec2 start-instances --instance-ids <ID>
```
EBS(디스크·이미지·DB)는 그대로 유지된다. GPU 인스턴스에선 NVIDIA 드라이버 추가 설치가 필요할 수 있다(별도).

---

## 8. 트러블슈팅

| 증상 | 원인 / 해결 |
|------|-------------|
| `modprobe sctp` 실패 | `sudo apt-get install -y linux-modules-extra-$(uname -r) && sudo modprobe sctp` |
| `.sh` 실행 시 `no such file or directory` | CRLF 오염 — 루트 `.gitattributes`(`*.sh eol=lf`)로 예방됨. 이미 깨졌다면 재클론 또는 `sed -i 's/\r$//' <file>` |
| `docker: permission denied` | docker 그룹 미반영 — `newgrp docker` 후 재시도(또는 재로그인) |
| EPC 컨테이너 없음 | 최초 구축 필요 — `bash bootstrap.sh` |
| noVNC/로그뷰어 접속 안 됨 | 포트는 루프백 전용 — 반드시 SSH 터널(§3)로 접근 |
