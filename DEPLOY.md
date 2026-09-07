# 팀 전용으로 실제 운영하는 방법

이 앱은 PWA이므로 APK 파일을 직접 설치하는 방식이 아니라 **팀 전용 HTTPS 주소**를 휴대폰에서 열고 "홈 화면에 추가/앱 설치"하는 방식입니다.

## 가장 쉬운 운영 방식

1. 인터넷에 공개된 서버(VPS/클라우드)에 이 폴더를 올립니다.
2. Docker Compose로 실행합니다.
3. 도메인을 연결합니다.
4. HTTPS를 설정합니다.
5. 지도자가 선수 계정을 생성합니다.
6. 선수에게 개인 아이디/비밀번호를 전달합니다.
7. 선수는 주소로 접속 → 홈 화면에 추가합니다.

PWA는 HTTPS(또는 개발 환경의 localhost)에서 설치할 수 있습니다.

## 팀원만 사용하게 하는 방법

현재 앱은 **관리자가 직접 만든 선수 계정만 로그인할 수 있는 구조**입니다.
따라서 공개 회원가입이 없습니다.

권장 운영:
- 관리자 계정 1~2개만 생성
- 선수마다 개인 계정 생성
- 선수는 자기 데이터만 조회
- 퇴단/휴식 선수는 계정 비활성화
- URL을 알고 있어도 계정이 없으면 로그인할 수 없음

더 강한 제한이 필요하면 회사/학교 이메일 도메인 제한 또는 초대코드 기능을 추가할 수 있습니다.

## HTTPS

PWA 설치를 위해 운영 주소는 HTTPS가 필요합니다.

예:
https://weight.your-team.com

Nginx + Let's Encrypt, Cloudflare, 또는 HTTPS를 제공하는 클라우드 플랫폼을 사용하세요.

## Docker 실행

```bash
docker compose up -d --build
```

초기 관리자 계정은 `.env`의 다음 값으로 설정합니다.

```env
SECRET_KEY=아주-긴-랜덤-문자열
ADMIN_USERNAME=coach
ADMIN_PASSWORD=강한-비밀번호
```

실제 운영에서는 반드시 값을 변경하세요.

## VAPID 푸시 알림

```bash
docker compose exec app flask --app app generate-vapid
```

출력된 값을 `.env`에 넣고:

```env
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_CLAIMS_EMAIL=mailto:관리자이메일
```

그 다음:

```bash
docker compose up -d --build
```

## 미기록 알림

기본:
- 08:00 아침
- 20:00 저녁

서버의 cron/작업 스케줄러에서 다음 명령을 주기적으로 실행합니다.

```bash
docker compose exec app flask --app app send-reminders
```

예를 들어 Linux cron에서 매분:

```cron
* * * * * cd /your/path/team_weight_app_final && docker compose exec -T app flask --app app send-reminders >/dev/null 2>&1
```

## 휴대폰에 설치

### Android
Chrome으로 팀 URL 접속 → 브라우저 메뉴 → "앱 설치" 또는 "홈 화면에 추가".

### iPhone
Safari로 팀 URL 접속 → 공유 버튼 → "홈 화면에 추가".

설치 후에는 일반 앱처럼 홈 화면 아이콘으로 실행할 수 있습니다.

## 중요

이 프로젝트 ZIP을 만든 것만으로 인터넷 주소가 자동으로 생기지는 않습니다.
실제 팀원들이 동시에 사용하려면 서버와 HTTPS 도메인이 필요합니다.

또한 체중 데이터는 민감할 수 있으므로 운영 전:
- HTTPS
- 강한 관리자 비밀번호
- DB 백업
- 접근권한 최소화
- 관리자 계정 공유 금지
- 학교/팀 개인정보 처리 절차 확인
을 적용하세요.
