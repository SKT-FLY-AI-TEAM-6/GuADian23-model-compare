"""build_trainset.py 검증 — 손으로 만든 작은 입력으로 순수 함수를 확인한다

    python test_build_trainset.py

pytest 를 쓰지 않는 이유는 이 저장소가 provider SDK 말고는 의존성을 두지 않기
때문이다 (requirements.txt 주석). test_score_gold.py 와 같은 모양으로, 각 검사는
(실패수, 전체수) 를 돌려주고 main 이 합산해 exit code 를 낸다.
"""

from __future__ import annotations

import json
import os
import tempfile

import build_trainset as T


def _check(label: str, got, want) -> int:
    """같으면 0, 다르면 1 을 돌려주고 무엇이 어긋났는지 찍는다"""
    if got == want:
        return 0
    print(f"  FAIL {label}\n    want: {want!r}\n    got : {got!r}")
    return 1


def _results_dir(tmp: str, layout: dict[str, list[dict]]) -> str:
    """results/<하위디렉터리>/run.jsonl 을 만들어 준다. layout 은 디렉터리 → 행 목록"""
    root = os.path.join(tmp, "results")
    for sub, rows in layout.items():
        d = os.path.join(root, sub)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "run.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return root


def _row(cid, sha, mode="guardian-trim", exc=("lookup_cache",)):
    return {"case_id": cid, "prompt_sha256": sha, "input_mode": mode,
            "excluded_tools": list(exc)}


def test_label_of() -> tuple[int, int]:
    """등급 3단계를 2클래스로. HIGH 가 1건뿐이라 MEDIUM 과 묶는다"""
    cases = [("LOW", 0), ("MEDIUM", 1), ("HIGH", 1)]
    fails = 0
    for risk, want in cases:
        fails += _check(f"label_of({risk})", T.label_of(risk), want)
    return fails, len(cases)


def test_collect_reference() -> tuple[int, int]:
    """세 필드를 다 가진 행만 참조가 된다 — 조립 파라미터를 못 주는 행은 쓸 수 없다"""
    with tempfile.TemporaryDirectory() as tmp:
        root = _results_dir(tmp, {
            "claude": [_row("c1", "aaa"), _row("c2", "bbb")],
            "gemini": [_row("c1", "aaa")],                       # 같은 sha — 충돌 아님
            # dryrun 은 prompt_sha256 은 있지만 input_mode·excluded_tools 가 없다
            "dryrun": [{"case_id": "c3", "prompt_sha256": "ccc"}],
            # merged 의 compare 행은 prompt_sha256 자체가 없다
            "merged": [{"case_id": "c1", "url": "https://x"}],
        })
        ref, conflicts = T.collect_reference(root)
    fails = _check("참조 case", sorted(ref), ["c1", "c2"])
    fails += _check("sha", ref["c1"]["sha"], "aaa")
    fails += _check("input_mode", ref["c1"]["input_mode"], "guardian-trim")
    fails += _check("exclude", ref["c1"]["exclude"], ("lookup_cache",))
    fails += _check("충돌 없음", conflicts, [])
    return fails, 5


def test_collect_reference_conflict() -> tuple[int, int]:
    """같은 case 에 다른 sha 가 있으면 그 자체가 이상 신호다 — 설명을 돌려준다"""
    with tempfile.TemporaryDirectory() as tmp:
        root = _results_dir(tmp, {
            "claude": [_row("c1", "aaa")],
            "gemini": [_row("c1", "zzz")],       # 같은 case, 다른 sha
        })
        _ref, conflicts = T.collect_reference(root)
    fails = _check("충돌 건수", len(conflicts), 1)
    fails += _check("case_id 가 설명에 들어간다", "c1" in conflicts[0], True)
    return fails, 2


def test_assembly_params() -> tuple[int, int]:
    """조립 파라미터는 참조에서 읽는다 — 하드코딩하면 조용히 다른 조립을 쓰게 된다"""
    ref = {
        "c1": {"sha": "aaa", "input_mode": "guardian-trim", "exclude": ("lookup_cache",)},
        "c2": {"sha": "bbb", "input_mode": "guardian-trim", "exclude": ("lookup_cache",)},
    }
    fails = _check("도출", T.assembly_params(ref), ("guardian-trim", ("lookup_cache",)))

    # 조합이 둘이면 어느 쪽으로 조립할지 정할 수 없다 → 중단
    mixed = dict(ref)
    mixed["c3"] = {"sha": "ccc", "input_mode": "raw", "exclude": ()}
    try:
        T.assembly_params(mixed)
        fails += _check("조합이 둘이면 중단", "중단 안 함", "SystemExit")
    except SystemExit:
        pass

    # 참조가 비면 검증 자체를 할 수 없다 → 중단
    try:
        T.assembly_params({})
        fails += _check("참조가 비면 중단", "중단 안 함", "SystemExit")
    except SystemExit:
        pass
    return fails, 3


def main() -> int:
    total_f = total_n = 0
    for name, fn in [("라벨 매핑", test_label_of),
                     ("참조 수집", test_collect_reference),
                     ("참조 충돌", test_collect_reference_conflict),
                     ("조립 파라미터", test_assembly_params)]:
        f, n = fn()
        print(f"{name}: {n - f}/{n} 통과")
        total_f += f
        total_n += n
    print(f"\n합계 {total_n - total_f}/{total_n} 통과")
    return 1 if total_f else 0


if __name__ == "__main__":
    raise SystemExit(main())
