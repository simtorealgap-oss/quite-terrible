# Quite Terrible — 끔찍한 램 사용자 모임 (RAM Users Club)

PC용 DDR4·DDR5 램과 NVIDIA GeForce RTX 가격만 추적하는 한·영 시세 사이트.
사이트 이름·문구는 `config/i18n.json` 한 곳에 있습니다(`brand`, `brandTagline`, `footerJoke`).

## 실행

Python 3.11 이상. 외부 패키지·빌드가 필요 없습니다.

```sh
cd /Users/user/Documents/ramprice
python3 server.py
```

- http://127.0.0.1:8765/ → 언어 자동 선택 후 `/ko/` 또는 `/en/`으로 이동
- 시세: `/ko/`, `/en/` · 뉴스: `/ko/news/`, `/en/news/`
- 예시 데이터로 화면 확인: 주소 끝에 `?demo=1` (가상 가격, DB에 저장하지 않음)

## 화면 구성

- **시세(첫 화면)**: 소개 문구 없이 주요 부품 6개 가격 차트가 바로 나옵니다.
  순서는 `config/products.json`의 `featured` (DDR5 16GB → DDR5 32GB 키트 → RTX 5080 → 5070 Ti → 5070 → 5060 Ti).
  7/30/90일 전환, 차트에 마우스를 올리면 그날 가격 표시. 아래에 전체 10개 모델 표(24시간·7일 변동, 30일 범위, 정렬).
  제품을 누르면 상세(긴 차트, 판매처별 가격·구매 링크).
- **뉴스(별도 탭)**: 언어별 관련 기사 제목을 날짜별로 정리. 하루 한 번 갱신.

## 언어·판매 지역 자동 선택

화면에 언어·지역 선택 버튼은 없습니다.

1. 언어: 브라우저 `Accept-Language`에서 가장 선호하는 ko/en. 둘 다 없으면 접속 국가(KR이면 한국어).
2. 판매 지역: 접속 국가(KR → 한국·KRW, 그 외 → 미국·USD). 국가를 모르면 언어 기준. 미국 가격이 아직 없으면 한국 가격을 보여 줍니다.

접속 국가는 Cloudflare(`CF-IPCountry`)·CloudFront·Vercel 등 CDN이 넣어 주는 헤더를 씁니다. 로컬에서는 국가 정보가 없어 언어 기준으로만 동작합니다.
`/ko/`, `/en/`처럼 언어가 들어간 주소로 직접 들어오면 강제로 바꾸지 않습니다.

## 가격 출처

### 한국: 다나와 (키 불필요)

매일 오전 9시(KST)에 제품마다 다나와 검색 페이지 1번씩, 요청 사이 10초 간격으로 읽습니다(robots.txt의 Crawl-delay 준수, 금지 경로인 `/api/`·`/info/ajax/`는 쓰지 않음). 전체 약 2분.

- 다나와 분류 번호로 거릅니다: 그래픽카드 972, DDR5 데스크톱 221725, DDR4 데스크톱 56243. 중고·노트북·서버용·외장 GPU 박스는 제외됩니다.
- 판매처 3곳 이상인 새 상품만 씁니다(판매처 1~2곳짜리는 가격이 튀는 경우가 있음).
- 제품별로 가장 싼 모델 10개를 저장하고, 상세 화면에서 다나와 상품 페이지로 연결합니다.
- 검색어와 매칭 조건은 `config/products.json`의 `danawa` 항목에 있습니다.
- 다나와 화면 구조가 바뀌면 수집이 `error`로 기록되고 화면에 "가격 수집 오류"가 뜹니다.
- 다나와 데이터를 가져와 공개 사이트에 쓰는 것은 다나와 약관·부정경쟁방지법·DB 제작자 권리 측면의 위험이 남아 있습니다. 출처 표시와 원문 링크로 줄이지만 없애지는 못합니다. 쿠팡 파트너스 API가 열리면 그쪽으로 옮기는 것을 권합니다.

```sh
python3 server.py --update prices   # 지금 바로 한 번 수집 (예약 시간과 무관)
```

출력의 `matched`가 제품별로 찾은 모델 수입니다. 0이면 `config/products.json`의 `danawa` 검색어·조건을 조정합니다.

### 미국: eBay Browse API (키 필요)

`.env`에 `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`(Production 키)를 넣으면 매일 같은 시간에 함께 수집합니다.

- 새 상품(conditionId 1000)과 즉시구매, 미국 발송 상품만 조회하고 가격순으로 정렬합니다. 분류는 그래픽카드 27386, 메모리 170083입니다.
- 평가 100건 미만이거나 긍정률 98% 미만인 판매자, 박스만 파는 상품, 부품용, 쿨러 같은 부속품, 제품별 최저 금액(`products.json`의 `ebay.min`)보다 싼 매물은 뺍니다.
- 판매자 아이디는 저장하지 않습니다. 키를 만들 때 eBay가 요구하는 Marketplace Account Deletion 항목은 "사용자 데이터를 저장하지 않음" 예외로 신청할 수 있습니다.
- `EBAY_CAMPAIGN_ID`(eBay Partner Network)를 넣으면 구매 링크가 제휴 링크가 됩니다.
- **샘플 응답으로만 테스트했고, 실제 키로는 아직 검증하지 않았습니다.** eBay API 약관의 데이터 보관 조건도 운영 전에 확인하세요.

### 미국: Best Buy Products API (키 필요)

`.env`에 `BESTBUY_API_KEY`를 넣으면 같은 시간에 함께 수집합니다. 키는 https://developer.bestbuy.com 에서 회사 이메일로 신청합니다(무료 메일 주소는 받지 않음). **코드는 있지만 실제 키로는 아직 검증하지 않았습니다.** Best Buy 약관의 데이터 저장 제한도 운영 전에 확인하세요.
미국 데이터가 없으면 영어권 방문자에게도 한국 가격을 기본으로 보여 줍니다.

### 네이버 쇼핑 API는 쓰지 않습니다

네이버 쇼핑 검색 API는 2026년 7월 31일 종료됐고, 네이버 API HUB에도 쇼핑 검색은 없습니다.

### 그 밖의 피드

`PRICE_FEED_URL`에 사용 권한이 있는 HTTPS JSON 피드를 연결할 수 있습니다(형식: `config/feed.example.json`). 파일로 가져오기: `python3 server.py --import-feed /absolute/path/to/observations.json`

## 자동 갱신

`python3 server.py`는 웹 서버와 수집 스레드를 함께 띄웁니다. 수집 스레드는 10분마다 확인해서

- 가격: 그날(KST) 아직 수집하지 않았고 오전 9시가 지났으면 실행. 한 번도 수집한 적이 없으면 바로 실행. 실패하면 1시간 뒤 재시도.
- 뉴스: 언어·분류별 피드를 성공 후 24시간에 한 번.

서버가 꺼져 있거나 컴퓨터가 잠들면 수집도 멈춥니다. 매일 빠짐없이 쌓으려면 상시 켜 둔 서버가 필요합니다.

## 데이터 기준

- 현재 최저가: 36시간 안에 확인한 유효 가격(하루 한 번 수집이므로 24시간이 아닌 36시간). 시장 전체 최저가를 보장하지 않음.
- 배송비·세금·개인 쿠폰은 기본 최저가에 합산하지 않으며 배송비는 상세에 별도 표시.
- 품절과 만료 가격을 현재 최저가에서 제외.
- 24시간 변동은 24~36시간 전의 관측값이 있을 때만 계산.
- 일별 차트는 그날 마지막 관측값. 관측 간격이 긴 경우 선을 끊고 가격을 채워 넣지 않음.
- SQLite는 `data/ramprice.sqlite3`. 백업은 실행 중 단순 파일 복사 대신 SQLite backup API 사용.

## 수익화

우선순위는 **구매 제휴 링크 → 뉴스 지면의 명시적 스폰서 → 트래픽 확보 후 일반 광고**입니다. 로그인과 유료 구독은 초기에 추가하지 않습니다. `affiliate_url`이 설정된 판매처는 화면에 제휴 표시와 `rel="sponsored"`가 붙고, 정렬은 가격 기준으로 유지됩니다. 계정 가입·제휴 승인·광고 삽입은 아직 하지 않았습니다.

2026-10-31 확인한 Amazon US 표준 수수료표에서 PC/PC Components는 2.5%입니다. 실제 지급은 적격 구매·상품 분류·반품·프로그램 조건에 따릅니다.
공식 표: https://affiliate-program.amazon.com/help/node/topic/GRXPHT8U84RAYDXZ

사업성 계산 예시(예측이 아닌 가정): 월 방문 10,000 × 구매링크 클릭 20% × 구매 전환 3% × 평균 구매 $300 × 수수료 2.5% = 월 $450. 여기서 데이터·호스팅 비용, 반품 등을 차감해야 합니다. 국내 제휴율은 선택한 프로그램에서 별도로 확인합니다. 가격 데이터 이용권과 API 비용을 먼저 확정하는 것이 핵심입니다.

## 무료 배포 (GitHub Pages + GitHub Actions)

`.github/workflows/daily.yml`이 매일 00:00 UTC(09:00 KST)에 실행됩니다.

1. 테스트 → 다나와·뉴스(키가 있으면 eBay·Best Buy) 수집
2. `data/ramprice.sqlite3`를 저장소에 커밋(가격 이력이 여기에 쌓임)
3. `build.py`로 정적 사이트(`dist/`)를 만들어 GitHub Pages에 배포

- 정적 호스팅은 방문자 정보를 서버에서 볼 수 없으므로 언어는 브라우저 언어(없으면 시간대), 판매 지역은 시간대(Asia/Seoul이면 한국)와 페이지 언어로 브라우저가 정합니다.
- API 키는 저장소 Settings → Secrets → Actions에 `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_CAMPAIGN_ID`, `BESTBUY_API_KEY`로 넣습니다.
- 무료 Pages는 공개 저장소가 필요합니다. 코드와 수집 데이터가 공개됩니다.
- 로컬에서 정적 결과 확인: `python3 build.py --base /quite-terrible --out /tmp/site/quite-terrible` 후 `/tmp/site`를 정적 서버로 엽니다.

## 검증 및 배포 경계

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js  # 선택: JS 구문 확인
```

SQLite·수집 로직 테스트는 품절/만료/통화 분리/0원/잘못된 SKU/중복/원자적 가져오기/뉴스 갱신 제한을 다룹니다.

현재 서버는 로컬 MVP용 Python 표준 라이브러리 HTTP 서버입니다. 공개 운영 전에는 TLS 리버스 프록시와 프로세스 관리, SQLite 영구 볼륨, 백업, 외부 데이터 공급 계약을 구성하세요. 여러 웹 프로세스를 띄울 때는 수집기를 한 개만 두고 나머지는 `--no-worker`로 실행해야 합니다. 공개 배포는 아직 하지 않았습니다.
