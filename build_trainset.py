"""Gold 라벨 + 조립 프롬프트 → fine-tuned classifier 학습셋

    python build_trainset.py --tag 0831

`gold/gold_251.jsonl` 의 등급을 2클래스로 묶어 라벨로 삼고, `build_prompt.py` 가
조립한 user 프롬프트를 입력 텍스트로 쓴다. 3사에게 실제로 보낸 것과 **문자 단위로 같은
입력**이라야 `score_gold.py` 의 같은 표에서 비교해도 공정하다.

## 왜 2클래스인가

Gold 251건의 분포가 이 결정을 강제한다 — HIGH 1건, impersonation 1건, urgency 2건.
train/test 로 나누면 한쪽에만 들어가거나 아예 빠져서 학습도 평가도 안 된다. 등급을
LOW(0) 대 MEDIUM·HIGH(1) 로 묶으면 129 대 122 로 균형이 맞는다. 원본 risk·type·source 는
각 행에 그대로 실어, 데이터가 늘어 3클래스로 갈 때 **다시 조립하지 않고 라벨만 바꿔**
재산출할 수 있게 한다.

## 왜 sha 를 검증하는가

계산해서 남기기만 하면 아무도 안 본다. 조립 규칙이 바뀌어도 모른 채 다른 입력으로
학습하게 되므로, `results/*/*.jsonl` 의 기록과 **전건 대조해 하나라도 어긋나면 중단**한다.
조립 파라미터(input_mode·excluded_tools)도 하드코딩하지 않고 참조 run 에서 읽는다 —
설계 중 input_mode 를 'oneshot' 으로 잘못 쓴 실수를 실제로 밟았고, 이 데이터에서는
우연히 같은 결과가 나왔지만 하드코딩했다면 조용히 다른 조립을 썼을 것이다.
"""

from __future__ import annotations

import hashlib
import json
import os

import build_prompt as B

# 등급 2클래스. HIGH 가 1건뿐이라 MEDIUM 과 묶는다 — 자세한 이유는 위 docstring
RISK_TO_LABEL = {"LOW": 0, "MEDIUM": 1, "HIGH": 1}


def label_of(risk: str) -> int:
    """등급 → 2클래스 라벨. 모르는 등급은 조용히 넘기지 않는다"""
    if risk not in RISK_TO_LABEL:
        raise SystemExit(f"모르는 등급: {risk!r} (가능: {', '.join(RISK_TO_LABEL)})")
    return RISK_TO_LABEL[risk]


def collect_reference(results_dir: str) -> tuple[dict[str, dict], list[str]]:
    """`results/*/*.jsonl` 에서 case_id → {"sha", "input_mode", "exclude"} 와 충돌 목록

    **세 필드를 다 가진 행만 참조가 된다.** dryrun 행은 prompt_sha256 은 있어도
    input_mode·excluded_tools 를 기록하지 않아 조립 파라미터를 줄 수 없고, merged 의
    compare 행은 prompt_sha256 자체가 없다. 참조는 "어떤 조립으로 무엇이 나왔는지"를
    둘 다 말해 줄 수 있어야 한다
    """
    ref: dict[str, dict] = {}
    conflicts: list[str] = []
    if not os.path.isdir(results_dir):
        return ref, conflicts
    for sub in sorted(os.listdir(results_dir)):
        d = os.path.join(results_dir, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".jsonl"):
                continue
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    r = json.loads(line)
                    sha = r.get("prompt_sha256")
                    mode = r.get("input_mode")
                    exc = r.get("excluded_tools")
                    if not (sha and mode and exc is not None):
                        continue
                    entry = {"sha": sha, "input_mode": mode, "exclude": tuple(exc)}
                    cid = r["case_id"]
                    prev = ref.get(cid)
                    if prev is None:
                        ref[cid] = entry
                    elif prev != entry:
                        conflicts.append(
                            f"{cid}: 참조가 서로 다르다 — {prev} vs {entry} ({sub}/{fn})")
    return ref, conflicts


def assembly_params(reference: dict[str, dict]) -> tuple[str, tuple[str, ...]]:
    """참조에서 (input_mode, exclude) 를 도출한다. 하나로 정해지지 않으면 중단

    이 값을 스크립트에 박아 두지 않는 이유는, 박아 두면 실제 실행과 다른 조립을 써도
    아무도 모르기 때문이다. 결과 행에 이미 기록돼 있으므로 그것이 정본이다
    """
    if not reference:
        raise SystemExit(
            "참조할 run 결과가 없다 — results/<provider>/*.jsonl 이 있어야 한다.\n"
            "  학습셋 입력이 3사에게 보낸 것과 같은지 확인할 방법이 없으므로 만들지 않는다.")
    combos = {(e["input_mode"], e["exclude"]) for e in reference.values()}
    if len(combos) > 1:
        raise SystemExit(
            "참조 run 들의 조립 파라미터가 서로 다르다 — 어느 쪽으로 조립할지 정할 수 없다.\n  "
            + "\n  ".join(str(c) for c in sorted(combos, key=str))
            + "\n  같은 조립으로 돈 run 만 남기고 다시 실행하라.")
    return combos.pop()


def assemble(cases: list[dict], spec: dict, input_mode: str,
             exclude: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    """case_id → (조립된 user 프롬프트, 그 sha256)

    `run_eval.py` 와 같은 함수를 같은 파라미터로 부른다. 조립이 실패하는 case 는
    조용히 빠뜨리지 않고 중단한다 — 251건 중 몇 건이 사라지면 학습셋 건수가 어긋난다
    """
    out: dict[str, tuple[str, str]] = {}
    for case in cases:
        cid = case["case_id"]
        try:
            _system, user = B.build_messages(case, spec, input_mode=input_mode,
                                             exclude=exclude)
        except Exception as e:
            raise SystemExit(f"{cid} 조립 실패: {type(e).__name__}: {e}")
        out[cid] = (user, hashlib.sha256(user.encode("utf-8")).hexdigest())
    return out


def verify(assembled: dict[str, tuple[str, str]],
           reference: dict[str, dict]) -> list[str]:
    """조립 결과가 3사에게 보낸 것과 같은지 전건 대조. 어긋남 설명 목록을 돌려준다

    참조에 없는 case 도 어긋남으로 센다. 그 case 는 3사가 판정한 적이 없다는 뜻이고,
    그러면 "3사와 같은 입력"이라는 전제 자체가 깨진다 — 조용히 넘어가면 학습셋 일부만
    검증되지 않은 조립으로 들어간다
    """
    bad = []
    for cid in sorted(assembled):
        _text, sha = assembled[cid]
        entry = reference.get(cid)
        if entry is None:
            bad.append(f"{cid}: 참조 run 이 없다 (3사가 판정한 적이 없는 case)")
        elif entry["sha"] != sha:
            bad.append(f"{cid}: sha 불일치 — 기록 {entry['sha'][:16]}… vs 지금 {sha[:16]}…")
    return bad
