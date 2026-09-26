# cpatools-toolbox (public mirror)

Claude Skills · 회계 실무 자동화 · 일상 도구

> ⚠️ 이 repo는 자동 동기화된 **공개 미러**입니다. 작업 원본은 비공개 저장소에 있으며, `config/publishing.yml`에 등록된 skill만 여기에 노출됩니다.

자매 사이트: [cpatools.co.kr](https://www.cpatools.co.kr)


## `work/` (4 skills)

| Skill | 설명 |
| --- | --- |
| [`skill-land-price-query`](work/skill-land-price-query/) 공시지가 조회 | 부동산공시가격알리미(realtyprice.kr)에서 개별공시지가를 조회하고 감사 워크페이퍼(엑셀)를 생성하며, 필요하면 실제 조회 화면 스크린샷(PNG)을 첨부하는 스킬. |
| [`skill-ocr-google-layout`](work/skill-ocr-google-layout/) 표·레이아웃 보존 PDF OCR | GCP Document AI Layout Parser 기반 PDF OCR. inbox 폴더의 PDF를 배치 처리해 레이아웃·표 구조를 보존한 HTML·Markdown으로 변환한다. PDF OCR·문서 레이아웃 인식·표 인식·스캔 문서 텍스트 추출이 필요할 때 사용한다. 등기부 OCR은 이미지에서 취소선 존재 여부를 먼저 확인하고, 존재하거나 불확실하면 상세 범위 판독을, 없다고 확인되면 텍스트 분석을 진행한다. 근저당 합계·공동담보 분석 자체는 이 스킬의 범위가 아니다. |
| [`skill-registry-mortgage-analysis`](work/skill-registry-mortgage-analysis/) 부동산등기부등본 분석 | 부동산등기부등본 PDF의 모든 페이지를 이미지로 확인하고, 취소 범위를 반영한 현행 소유자·근저당·압류와 공동담보 중복 제거 금액을 엑셀 감사 조서로 만든다. |
| [`skill-revenue-tod`](work/skill-revenue-tod/) 매출테스트 자동화 | 매출 Test of Details (TOD) 감사 절차를 수행하는 스킬. |

## 기여
버그·제안은 **이 repo에 직접 issue/PR을 받지 않습니다.** 운영자 연락처는 [cpatools.co.kr/about](https://www.cpatools.co.kr/about) 참조. 내용은 비공개 원본 저장소에서 검토 후 다음 자동 동기화 사이클에 반영됩니다.

## 라이선스

MIT — [LICENSE](LICENSE) 참조.
