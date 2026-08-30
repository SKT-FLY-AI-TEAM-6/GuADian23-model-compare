"""Gold 기준 3사 채점

    python score_gold.py results/merged/compare_0830.jsonl

`gold/gold_251.jsonl` 을 정답으로 놓고 provider 별 정확도를 낸다. 예측은 compare
파일의 provider 셀에서 읽는다 — 어느 run 을 쓸지 고르는 규칙(최신 우선·성공 우선)이
`merge_results.py:58` 에 이미 있고, 두 군데 두면 언젠가 어긋난다.

## 왜 구간을 나누는가

Gold 251건 중 220건은 3사 합의로 자동 확정된 것이다. 그 구간을 정답으로 놓고 채점하면
세 모델 모두 **정의상** 100% 가 나온다. 전체 정확도만 내면 이 순환이 숫자에 가려지므로
전체 / 3사 합의 / 사람 확정 세 구간으로 나누어 낸다. 실제 변별력은 사람 확정 구간에서만
나온다.

## 등급과 유형은 구간이 다르다

`auto_agree+human_type` (case_131 · case_204) 은 등급이 3사 합의, 유형이 사람 확정이다.
하나의 구간 분류를 둘에 같이 쓰면 사람이 정한 유형이 순환 구간에 섞여 100% 판정을 받는다.
그래서 `risk_bucket` 과 `type_bucket` 을 따로 둔다.

| | consensus | human |
| :-- | --: | --: |
| 등급 | auto_agree + auto_agree+human_type | human_review |
| 유형 | auto_agree | human_review + auto_agree+human_type |
"""

from __future__ import annotations

import json

from providers.base import PROVIDER_NAMES

# merge_results.py:37 과 같은 값. 등급은 순서가 있어 "틀린 방향"을 판정할 수 있다
RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

CONSENSUS = "consensus"
HUMAN = "human"


def risk_bucket(source: str) -> str:
    """등급의 출처. auto_agree+human_type 은 **등급만은** 3사 합의로 정해졌다"""
    return HUMAN if source == "human_review" else CONSENSUS


def type_bucket(source: str) -> str:
    """유형의 출처. auto_agree+human_type 은 유형을 사람이 채웠다 — 순환이 아니다"""
    return CONSENSUS if source == "auto_agree" else HUMAN


def load_jsonl(path: str) -> dict[str, dict]:
    """jsonl 을 case_id → 행 으로. 같은 case_id 가 두 번 나오면 뒤엣것이 이긴다"""
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                out[r["case_id"]] = r
    return out


def join(gold: dict[str, dict], compare: dict[str, dict]) -> tuple[list[str], list[str]]:
    """(양쪽에 다 있는 case_id, gold 에만 있는 case_id)

    gold 에만 있는 case 를 오답으로 세면 "예측이 없다"와 "틀렸다"가 한 숫자에 섞인다.
    빼고 건수만 따로 보고한다
    """
    both = sorted(cid for cid in gold if cid in compare)
    gold_only = sorted(cid for cid in gold if cid not in compare)
    return both, gold_only
