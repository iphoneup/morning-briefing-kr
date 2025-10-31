# KR Morning Briefing (뉴스 + 증시 요약)

이 리포는 매일 아침(한국 시간) 다음 내용을 담은 `briefing.json`을 자동 생성합니다.
- 뉴스: 경제 → 정치 → 연예 → 증시 카테고리별 상위 기사 3~5개 (Google News RSS, 키 없음)
- 상한가: 전일 기준 “상한가 관련 기사 제목”에서 추출한 종목 최대 10개 + 간단 이유(제목 기반, 베스트에포트)
- 섹터 추천: 이차전지/방산/화학 섹터별 고정 5종목(편집 가능, `data/sectors.json`)

주의/한계
- 상한가 10개는 뉴스 제목 기반 추출이라 100% 정확하진 않습니다. 정확도를 높이고 싶으면 이후에 증권사 Open API를 백엔드에만 붙일 수 있어요(아이폰엔 키 노출 X).
- 주말엔 “금요일 장 기준 브리핑”으로 표시합니다. 한국 공휴일은 기본 반영 안 됨(추가 가능).

## 어떻게 쓰나
1) 이 리포를 본인 깃허브에 생성
2) 아래 파일들을 동일 구조로 추가(push)
3) GitHub Actions가 매일 자동으로 `briefing.json`을 갱신
4) 아이폰 단축어에서 아래 RAW URL을 읽기
   - https://raw.githubusercontent.com/본인계정/본인리포/main/briefing.json?ts=123

Shortcuts(단축어) 아이디어
- “URL 내용 가져오기” → 위 raw URL
- “사전 가져오기”로 JSON 파싱
- 카테고리별 텍스트 조합 후 “말하기(Speak Text)”
- limit_up과 sectors도 순서대로 읽기

## 로컬 테스트(선택)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/make_briefing.py
cat briefing.json
