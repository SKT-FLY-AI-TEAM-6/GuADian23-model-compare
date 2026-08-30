"""score_gold.py 검증 — 손으로 만든 작은 입력으로 순수 함수를 확인한다

    python test_score_gold.py

pytest 를 쓰지 않는 이유는 이 저장소가 provider SDK 말고는 의존성을 두지 않기
때문이다 (requirements.txt 주석). test_assembly.py 와 같은 모양으로, 각 검사는
(실패수, 전체수) 를 돌려주고 main 이 합산해 exit code 를 낸다.
"""

from __future__ import annotations

import score_gold as G


def _check(label: str, got, want) -> int:
    """같으면 0, 다르면 1 을 돌려주고 무엇이 어긋났는지 찍는다"""
    if got == want:
        return 0
    print(f"  FAIL {label}\n    want: {want!r}\n    got : {got!r}")
    return 1


def test_buckets() -> tuple[int, int]:
    """auto_agree+human_type 은 등급과 유형의 구간이 갈린다 — 이 계획의 핵심"""
    cases = [
        ("auto_agree",            "consensus", "consensus"),
        ("human_review",          "human",     "human"),
        # 등급은 3사 합의, 유형은 사람. 하나의 분류를 둘에 같이 쓰면
        # 사람이 정한 유형이 순환 구간에 섞인다
        ("auto_agree+human_type", "consensus", "human"),
    ]
    fails = 0
    for source, want_risk, want_type in cases:
        fails += _check(f"risk_bucket({source})", G.risk_bucket(source), want_risk)
        fails += _check(f"type_bucket({source})", G.type_bucket(source), want_type)
    return fails, len(cases) * 2


def test_join() -> tuple[int, int]:
    """gold 에만 있는 case 는 채점 대상에서 빼고 따로 센다"""
    gold = {"c1": {}, "c2": {}, "c3": {}}
    compare = {"c1": {}, "c3": {}, "c9": {}}
    both, gold_only = G.join(gold, compare)
    fails = _check("both", both, ["c1", "c3"])
    fails += _check("gold_only", gold_only, ["c2"])
    return fails, 2


def main() -> int:
    total_f = total_n = 0
    for name, fn in [("구간 분류", test_buckets), ("조인", test_join)]:
        f, n = fn()
        print(f"{name}: {n - f}/{n} 통과")
        total_f += f
        total_n += n
    print(f"\n합계 {total_n - total_f}/{total_n} 통과")
    return 1 if total_f else 0


if __name__ == "__main__":
    raise SystemExit(main())
