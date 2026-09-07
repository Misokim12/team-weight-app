# 선수 체중관리 PWA v2

학생선수가 휴대폰에서 앱처럼 설치해서 아침/저녁 체중을 기록하고,
지도자가 웹/PC에서 선수별 기록, 완성도, 평균, 그래프, CSV를 관리하는 PWA MVP입니다.

## 포함 기능

### 선수
- 휴대폰 앱처럼 설치 가능한 PWA
- 아침/저녁 체중 입력
- 오늘 2회 기록 현황
- 최근 기록 확인
- Web Push 알림 권한 신청

### 지도자
- 전체 선수 대시보드
- 기간별 기록 조회
- 선수별 기록 완성도
- 선수별 아침/저녁/전체 평균
- 기간별 체중 변화 그래프
- CSV 다운로드
- 선수 추가
- 선수 이름/팀/종목/비밀번호 수정
- 계정 활성/비활성

### 자동 미기록 알림
`send-reminders` 명령을 cron 등으로 실행하면 해당 시각에 기록하지 않은 선수에게
Web Push 알림을 보낼 수 있습니다.

기본 시각:
- 아침 08:00
- 저녁 20:00

환경변수로 변경할 수 있습니다.

---

## 1. 로컬 실행

Python 3.11+ 권장.

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

환경변수 설정:

```powershell
$env:SECRET_KEY="매우-긴-랜덤-문자열"
$env:ADMIN_USERNAME="coach"
$env:ADMIN_PASSWORD="강한-관리자-비밀번호"
```

DB 초기화:

```bash
flask --app app init-db
```

실행:

```bash
flask --app app run
```

브라우저:
http://127.0.0.1:5000

---

## 2. PWA 설치

PWA는 `localhost` 또는 HTTPS에서 설치할 수 있습니다.

운영 서버에서는 반드시 HTTPS를 사용하세요.

휴대폰에서 웹사이트에 접속한 후:
- Android/Chrome: 브라우저의 설치/홈 화면 추가 메뉴
- iPhone/Safari: 공유 메뉴 → 홈 화면에 추가

---

## 3. Web Push 알림 설정

먼저 VAPID 키를 생성합니다.

```bash
flask --app app generate-vapid
```

출력된 두 값을 환경변수에 넣습니다.

```text
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_CLAIMS_EMAIL=mailto:your-email@example.com
```

서버를 재시작합니다.

선수 휴대폰에서 로그인 → `🔔 알림 켜기`를 눌러 권한을 허용합니다.

### 미기록 알림

현재 시각을 검사해서 미기록 선수에게 알림을 보내는 명령:

```bash
flask --app app send-reminders
```

예를 들어 Linux 서버의 cron에서 1분마다 실행:

```cron
* * * * * cd /path/to/student_weight_app_v2 && /path/to/venv/bin/flask --app app send-reminders >> /var/log/weight-reminder.log 2>&1
```

그러면 08:00과 20:00에만 실제 알림이 발송됩니다.

Windows 서버라면 작업 스케줄러에서 1분 주기로 실행하면 됩니다.

---

## 4. 운영 배포 권장 구조

```text
학생 휴대폰 PWA
       ↓ HTTPS
Nginx / HTTPS
       ↓
Gunicorn + Flask
       ↓
PostgreSQL
       ↓
Web Push
       ↓
학생 휴대폰 알림
```

예:

```bash
gunicorn -w 2 -b 127.0.0.1:8000 app:app
```

실제 인터넷에 공개할 때는 Nginx/Cloudflare 등의 HTTPS 구성을 추가하세요.

---

## 5. 개인정보/학생선수 데이터 주의

체중은 개인 신체 데이터이므로 실제 학교/팀 운영에서는 다음을 적용하는 것을 권장합니다.

- HTTPS 필수
- 강한 관리자 비밀번호
- 관리자 계정 공유 금지
- 학생은 자기 데이터만 접근
- DB 백업 및 접근권한 관리
- CSV 파일 외부 공유 주의
- 공개 순위표/체중 공개 기능을 기본값으로 만들지 않기
- 학교/팀의 개인정보 처리방침과 동의 절차 확인
- 운영 전 CSRF 보호, 로그인 시도 제한, 보안 헤더, 감사 로그 추가 권장

---

## 6. 다음 단계로 확장하기 좋은 기능

- 종목/팀/학년/코치별 그룹
- 선수별 목표 체중 범위
- 체중 급격한 변화 자동 경고
- 지도자에게만 보이는 미기록 선수 목록
- 코치 여러 명의 권한 분리
- 체중계 BLE 자동 입력
- 선수별 주간/월간 리포트
- Excel(xlsx) 다운로드
- 선수 사진/프로필
- QR코드로 빠른 로그인
- 학교 계정/Google/Microsoft 로그인
- 관리자 감사 로그
- PostgreSQL + 클라우드 배포
