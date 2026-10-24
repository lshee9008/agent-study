---
name: velog-devlog
description: GitHub 커밋/PR과 Notion 기록을 모아 한국어 개발일지 마크다운을 쓰고 Velog에 비공개로 발행한다. 개발일지, 벨로그 정리, 주간 회고 요청 시 사용.
---

# Velog 개발일지 작성 절차

## 0. 설정 읽기
- `/opt/workspace/sources.yaml` 을 읽어 대상 레포, 노션 페이지, `lookback_days`, `publish_private` 를 확인한다.
- 대상이 비어 있으면 작업을 멈추고 "sources.yaml 에 대상이 없습니다"라고 보고한다.

## 1. 수집 (읽기 전용)
- GitHub MCP: 각 레포의 최근 `lookback_days` 일 커밋, 머지된 PR, 닫힌 이슈를 가져온다.
- Notion MCP: 지정 페이지의 최근 수정 내용(회의록, 기획, 트러블슈팅)을 가져온다.
- 수집한 원문은 `/opt/workspace/drafts/_raw-YYYY-MM-DD.md` 에 메모로 저장한다.

## 2. 레포별로 글 1편씩 작성
파일: `/opt/workspace/drafts/YYYY-MM-DD-<repo>.md`

```markdown
---
title: "[<series 또는 repo>] <이번 기간 핵심을 한 줄로>"
tags: [<기술스택 3~5개>]
is_private: true
---
## 이번 주 한 일
## 문제와 해결   (트러블슈팅이 있을 때만)
## 배운 점
## 다음 할 일
```

규칙:
- 커밋/PR/노션에 **실제로 있는 내용만** 쓴다. 없는 수치, 성능 개선, 기능을 지어내지 않는다.
- 근거가 된 커밋은 짧은 SHA나 PR 번호로 본문에 표기한다.
- 토큰, 키, 내부 URL, 개인정보가 보이면 제거한다.
- 말투는 담백한 1인칭 기술 블로그체("~했다").
- 활동이 거의 없는 레포는 글을 만들지 않는다.

## 3. 발행
- Velog MCP의 로컬 마크다운 발행 도구로 각 초안을 올린다.
- `publish_private: true` 이면 반드시 비공개로 올린다. 공개 발행은 사용자가 직접 한다.
- 글 삭제/수정 도구는 사용하지 않는다.

## 4. 보고
발행한 글 제목, 비공개 여부, 근거 커밋 수를 짧게 요약한다. 실패한 단계가 있으면 이유를 적는다.
(Velog 인증 오류면 "토큰 만료 — .env 갱신 후 render-config.sh 재실행" 안내)
