# score_gold.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `gold/gold_251.jsonl` 을 정답으로 claude · gemini · openai 를 채점하되, Gold 의 220건이 3사 합의로 만들어진 데서 오는 순환을 구간 분리로 드러낸다.

**Architecture:** 단일 스크립트 `score_gold.py`. compare 파일(예측)과 gold 파일(정답)을 case_id 로 조인하고, Gold 행의 `source` 로 구간을 나눈 뒤 등급·유형을 따로 채점한다. 등급과 유형은 **구간 분류가 다르다** — `auto_agree+human_type` 행은 등급이 3사 합의, 유형이 사람 확정이기 때문. 순수 함수로 계산하고 출력은 맨 마지막에만 한다.

**Tech Stack:** Python 3.12 표준 라이브러리만 (`argparse` · `json` · `csv` · `collections`). 새 의존성 없음.

## Global Constraints

- **pytest 를 쓰지 않는다.** 이 저장소의 테스트는 `test_assembly.py` 처럼 `python test_xxx.py` 로 도는 독립 스크립트다. `requirements.txt` 에는 provider SDK 3개만 있고 "맡은 provider의 것만 설치하면 된다"는 방침이므로 팀원에게 새 의존성을 강요하지 않는다.
- 테스트 함수는 `(fail_count, total)` 을 반환하고, `main()` 이 합산해 exit code 를 낸다 — `test_assembly.py:104` 의 모양.
- 주석과 docstring 은 한국어. **무엇을 하는지가 아니라 왜 그렇게 했는지**를 적는다 — 이 저장소의 기존 파일들이 그렇게 되어 있다.
- 예측은 `run_eval.py` 결과를 직접 읽지 않고 compare 파일의 provider 셀에서만 읽는다. run 선택 규칙은 `merge_results.py:58` 에 이미 있고 두 벌로 두면 어긋난다.
- 등급 순서: `LOW < MEDIUM < HIGH`. `merge_results.py:37` 의 `RISK_ORDER` 와 같은 값을 쓴다.
- provider 이름은 `providers.base.PROVIDER_NAMES` = `("claude", "gemini", "openai")` 에서 가져온다. 하드코딩하지 않는다 — fine-tuned model 이 붙을 자리다.
- 산출 CSV 는 `results/scored/` 에 쓴다. `.gitignore` 의 `results/*/*.csv` 규칙에 이미 걸려 커밋되지 않는다(판정 문장이 들어간다). **`.gitignore` 를 고치지 않는다.**

## File Structure

| 파일 | 책임 |
| :-- | :-- |
| `score_gold.py` (생성) | 로딩·조인 · 구간 분류 · 등급 채점 · 유형 채점 · 검산 · 출력. 약 260줄 |
| `test_score_gold.py` (생성) | 손으로 만든 작은 입력으로 위 순수 함수들을 검증. 네트워크·실제 데이터 없음 |

`score_gold.py` 안의 함수는 **모두 순수 함수**로 두고 파일 읽기와 출력만 `main()` 이 한다. 테스트가 파일을 만들 필요 없이 dict 를 직접 넣을 수 있게 하려는 것이다.

---

### Task 1: 로딩 · 조인 · 구간 분류

**Files:**
- Create: `score_gold.py`
- Create: `test_score_gold.py`

**Interfaces:**
- Consumes: `providers.base.PROVIDER_NAMES`
- Produces:
  - `RISK_ORDER: dict[str, int]`
  - `risk_bucket(source: str) -> str` — `"consensus"` 또는 `"human"`
  - `type_bucket(source: str) -> str` — 같은 두 값
  - `load_jsonl(path: str) -> dict[str, dict]` — case_id → 행
  - `join(gold: dict[str, dict], compare: dict[str, dict]) -> tuple[list[str], list[str]]` — (양쪽에 다 있는 case_id 정렬 목록, gold 에만 있는 case_id 목록)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_score_gold.py` 를 새로 만든다:

```python
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
```

- [ ] **Step 2: 실패하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'score_gold'`

- [ ] **Step 3: 최소 구현을 쓴다**

`score_gold.py` 를 새로 만든다:

```python
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
```

- [ ] **Step 4: 통과하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: PASS — `합계 8/8 통과`

- [ ] **Step 5: 커밋한다**

```bash
git add score_gold.py test_score_gold.py
git commit -m "feat: 채점 구간 분류 — 등급과 유형을 따로 나눈다

auto_agree+human_type 행은 등급이 3사 합의, 유형이 사람 확정이다. 하나의 구간
분류를 둘에 같이 쓰면 사람이 정한 유형이 순환 구간에 섞여 100% 판정을 받는다."
```

---

### Task 2: 등급 채점 — 정확도 · 방향 · 혼동행렬

**Files:**
- Modify: `score_gold.py` (Task 1 의 끝에 이어 쓴다)
- Modify: `test_score_gold.py` (`test_buckets` 아래에 이어 쓴다)

**Interfaces:**
- Consumes: `RISK_ORDER` · `risk_bucket` (Task 1)
- Produces:
  - `direction(gold_risk: str, pred_risk: str) -> str | None` — 맞으면 `None`, 낮게 봤으면 `"under"`, 높게 봤으면 `"over"`
  - `score_risk(gold, compare, cids, providers, raw=False) -> dict[str, dict]` — provider → `{"n", "hit", "under", "over", "skipped", "confusion"}`. `confusion` 은 `dict[tuple[str, str], int]` 로 `(gold_risk, pred_risk) → 건수`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_score_gold.py` 의 `test_join` 아래에 넣는다:

```python
def test_direction() -> tuple[int, int]:
    """미탐과 과탐은 서비스에서 의미가 전혀 다르다 — 방향을 등급 순서로 판정한다"""
    cases = [
        ("LOW", "LOW", None),
        ("HIGH", "LOW", "under"),      # 위험한데 안전하다고 봤다 — 미탐
        ("MEDIUM", "LOW", "under"),
        ("LOW", "HIGH", "over"),       # 안전한데 위험하다고 봤다 — 과탐
        ("LOW", "MEDIUM", "over"),
    ]
    fails = 0
    for g, p, want in cases:
        fails += _check(f"direction({g},{p})", G.direction(g, p), want)
    return fails, len(cases)


def _gold(cid, risk, type_, source):
    return {"case_id": cid, "risk": risk, "type": type_, "source": source}


def _cmp(cid, **cells):
    """compare 한 행. cells 는 provider 이름 → (risk, type) 또는 None(실패)"""
    row = {"case_id": cid, "url": f"https://x/{cid}"}
    for p, v in cells.items():
        row[p] = {"ok": False} if v is None else {"ok": True, "risk": v[0], "type": v[1]}
    return row


def test_score_risk() -> tuple[int, int]:
    """실패한 provider 는 오답이 아니라 skipped 로 센다"""
    gold = {
        "c1": _gold("c1", "LOW", "none", "auto_agree"),
        "c2": _gold("c2", "HIGH", "impersonation", "human_review"),
        "c3": _gold("c3", "MEDIUM", "unverifiable", "human_review"),
    }
    compare = {
        "c1": _cmp("c1", claude=("LOW", "none")),
        "c2": _cmp("c2", claude=("LOW", "none")),        # 미탐
        "c3": _cmp("c3", claude=None),                   # API 실패
    }
    s = G.score_risk(gold, compare, ["c1", "c2", "c3"], ["claude"])["claude"]
    fails = _check("n", s["n"], 2)                       # 실패 1건은 채점 대상에서 빠진다
    fails += _check("hit", s["hit"], 1)
    fails += _check("under", s["under"], 1)
    fails += _check("over", s["over"], 0)
    fails += _check("skipped", s["skipped"], 1)
    fails += _check("confusion[HIGH,LOW]", s["confusion"].get(("HIGH", "LOW")), 1)
    return fails, 6
```

`main()` 의 목록에 두 줄을 더한다:

```python
    for name, fn in [("구간 분류", test_buckets), ("조인", test_join),
                     ("방향 판정", test_direction), ("등급 채점", test_score_risk)]:
```

- [ ] **Step 2: 실패하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: FAIL — `AttributeError: module 'score_gold' has no attribute 'direction'`

- [ ] **Step 3: 최소 구현을 쓴다**

`score_gold.py` 의 `join` 아래에 이어 쓴다:

```python
def direction(gold_risk: str, pred_risk: str) -> str | None:
    """틀린 방향. 맞으면 None

    등급은 순서가 있어 단순 정답/오답보다 방향이 중요하다. Gold 가 HIGH 인데 LOW 로
    본 것(미탐)과 Gold 가 LOW 인데 HIGH 로 본 것(과탐)은 서비스에서 의미가 다르다
    """
    if gold_risk == pred_risk:
        return None
    return "under" if RISK_ORDER[pred_risk] < RISK_ORDER[gold_risk] else "over"


def _pred(compare_row: dict, provider: str, raw: bool) -> dict | None:
    """provider 셀에서 예측을 꺼낸다. 실패했으면 None — 오답이 아니라 '채점 불가'다"""
    cell = compare_row.get(provider) or {}
    if not cell.get("ok"):
        return None
    return {"risk": cell.get("risk_raw" if raw else "risk"),
            "type": cell.get("type_raw" if raw else "type")}


def score_risk(gold: dict[str, dict], compare: dict[str, dict], cids: list[str],
               providers: list[str], raw: bool = False) -> dict[str, dict]:
    """provider → 등급 채점 결과

    실패한 provider 는 skipped 로 따로 센다. 오답으로 세면 모델의 판단력과 API 실패가
    한 숫자에 섞인다
    """
    out: dict[str, dict] = {}
    for p in providers:
        s = {"n": 0, "hit": 0, "under": 0, "over": 0, "skipped": 0, "confusion": {}}
        for cid in cids:
            pred = _pred(compare[cid], p, raw)
            if pred is None or not pred["risk"]:
                s["skipped"] += 1
                continue
            g = gold[cid]["risk"]
            s["n"] += 1
            key = (g, pred["risk"])
            s["confusion"][key] = s["confusion"].get(key, 0) + 1
            d = direction(g, pred["risk"])
            if d is None:
                s["hit"] += 1
            else:
                s[d] += 1
        out[p] = s
    return out
```

- [ ] **Step 4: 통과하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: PASS — `합계 19/19 통과`

- [ ] **Step 5: 커밋한다**

```bash
git add score_gold.py test_score_gold.py
git commit -m "feat: 등급 채점 — 정확도·미탐/과탐·혼동행렬

실패한 provider 는 오답이 아니라 skipped 로 센다. 오답으로 세면 모델의 판단력과
API 실패가 한 숫자에 섞인다."
```

---

### Task 3: 유형 채점

**Files:**
- Modify: `score_gold.py`
- Modify: `test_score_gold.py`

**Interfaces:**
- Consumes: `_pred` · `type_bucket` (Task 1·2)
- Produces: `score_type(gold, compare, cids, providers, raw=False) -> dict[str, dict]` — provider → `{"n", "hit", "skipped", "pairs"}`. `pairs` 는 `dict[tuple[str, str], int]` 로 `(gold_type, pred_type) → 건수`, 틀린 것만 담는다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_score_gold.py` 의 `test_score_risk` 아래에 넣는다:

```python
def test_score_type() -> tuple[int, int]:
    """gold type 이 빈 행은 채점하지 않는다 — 정답이 없는 것을 틀렸다고 할 수 없다"""
    gold = {
        "c1": _gold("c1", "LOW", "none", "auto_agree"),
        "c2": _gold("c2", "MEDIUM", "contentfarm", "human_review"),
        "c3": _gold("c3", "MEDIUM", "", "auto_agree"),      # 유형 미확정
    }
    compare = {
        "c1": _cmp("c1", claude=("LOW", "none")),
        "c2": _cmp("c2", claude=("MEDIUM", "unverifiable")),
        "c3": _cmp("c3", claude=("MEDIUM", "unverifiable")),
    }
    s = G.score_type(gold, compare, ["c1", "c2", "c3"], ["claude"])["claude"]
    fails = _check("n", s["n"], 2)
    fails += _check("hit", s["hit"], 1)
    fails += _check("skipped", s["skipped"], 1)
    fails += _check("pairs", s["pairs"], {("contentfarm", "unverifiable"): 1})
    return fails, 4
```

`main()` 의 목록에 한 줄을 더한다:

```python
                     ("방향 판정", test_direction), ("등급 채점", test_score_risk),
                     ("유형 채점", test_score_type)]:
```

- [ ] **Step 2: 실패하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: FAIL — `AttributeError: module 'score_gold' has no attribute 'score_type'`

- [ ] **Step 3: 최소 구현을 쓴다**

`score_gold.py` 의 `score_risk` 아래에 이어 쓴다:

```python
def score_type(gold: dict[str, dict], compare: dict[str, dict], cids: list[str],
               providers: list[str], raw: bool = False) -> dict[str, dict]:
    """provider → 유형 채점 결과. 틀린 (정답, 예측) 쌍을 세어 어디서 갈리는지 본다

    Gold 의 type 이 비어 있는 행은 채점하지 않는다 — 정답이 없는 것을 틀렸다고 할 수
    없다. 지금 251건에는 빈 type 이 없지만, 확정 규칙이 바뀌면 다시 생길 수 있다
    """
    out: dict[str, dict] = {}
    for p in providers:
        s = {"n": 0, "hit": 0, "skipped": 0, "pairs": {}}
        for cid in cids:
            g = gold[cid].get("type") or ""
            pred = _pred(compare[cid], p, raw)
            if not g or pred is None or not pred["type"]:
                s["skipped"] += 1
                continue
            s["n"] += 1
            if pred["type"] == g:
                s["hit"] += 1
            else:
                key = (g, pred["type"])
                s["pairs"][key] = s["pairs"].get(key, 0) + 1
        out[p] = s
    return out
```

- [ ] **Step 4: 통과하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: PASS — `합계 23/23 통과`

- [ ] **Step 5: 커밋한다**

```bash
git add score_gold.py test_score_gold.py
git commit -m "feat: 유형 채점 — 틀린 (정답,예측) 쌍까지

Gold 의 type 이 빈 행은 채점하지 않는다. 정답이 없는 것을 틀렸다고 할 수 없다."
```

---

### Task 4: 검산 — 3사 합의 구간이 100% 가 아니면 멈춘다

**Files:**
- Modify: `score_gold.py`
- Modify: `test_score_gold.py`

**Interfaces:**
- Consumes: `score_risk` (Task 2)
- Produces: `verify_consensus(risk_scores: dict[str, dict], raw: bool) -> list[str]` — 어긋난 provider 설명 목록. `raw` 가 참이면 항상 빈 목록(경고는 호출자가)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_score_gold.py` 의 `test_score_type` 아래에 넣는다:

```python
def test_verify_consensus() -> tuple[int, int]:
    """3사 합의 구간에서 100% 가 안 나오면 조인이나 기준이 어긋난 것이다 — 멈춘다"""
    clean = {"claude": {"n": 10, "hit": 10}, "gemini": {"n": 10, "hit": 10}}
    broken = {"claude": {"n": 10, "hit": 9}, "gemini": {"n": 10, "hit": 10}}
    fails = _check("정상", G.verify_consensus(clean, raw=False), [])
    got = G.verify_consensus(broken, raw=False)
    fails += _check("어긋남 건수", len(got), 1)
    fails += _check("어긋난 provider 이름이 들어간다", "claude" in got[0], True)
    # --raw 는 기준이 다른 것이 의도된 것이라 중단시키지 않는다
    fails += _check("raw 는 통과", G.verify_consensus(broken, raw=True), [])
    return fails, 4
```

`main()` 의 목록에 한 줄을 더한다:

```python
                     ("유형 채점", test_score_type), ("검산", test_verify_consensus)]:
```

- [ ] **Step 2: 실패하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: FAIL — `AttributeError: module 'score_gold' has no attribute 'verify_consensus'`

- [ ] **Step 3: 최소 구현을 쓴다**

`score_gold.py` 의 `score_type` 아래에 이어 쓴다:

```python
def verify_consensus(risk_scores: dict[str, dict], raw: bool) -> list[str]:
    """3사 합의 구간에서 전원 100% 인지 본다. 어긋난 provider 설명 목록을 돌려준다

    이 구간의 정답은 세 모델이 합의한 값 그 자체다. 100% 가 아니라면 모델이 틀린 게
    아니라 **채점이 틀린** 것이다 — 조인이 어긋났거나, compare 파일이 Gold 를 만든 것과
    다르거나, 후처리 기준이 다르다. 어느 쪽이든 나머지 숫자를 믿을 수 없으므로
    조용히 이상한 값을 내놓는 것보다 멈추는 쪽이 낫다.

    `--raw` 를 준 때는 기준이 다른 것이 의도된 것이므로 검사하지 않는다. Gold 는
    후처리 후 값으로 만들어졌기 때문에 raw 기준에서는 어긋나는 게 정상이다
    """
    if raw:
        return []
    bad = []
    for p, s in risk_scores.items():
        if s["n"] and s["hit"] != s["n"]:
            bad.append(f"{p}: 3사 합의 구간 {s['hit']}/{s['n']} — 100% 여야 한다")
    return bad
```

- [ ] **Step 4: 통과하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: PASS — `합계 27/27 통과`

- [ ] **Step 5: 커밋한다**

```bash
git add score_gold.py test_score_gold.py
git commit -m "feat: 검산 — 3사 합의 구간이 100% 가 아니면 멈춘다

이 구간의 정답은 세 모델이 합의한 값 그 자체다. 100% 가 아니면 모델이 아니라
채점이 틀린 것이라 나머지 숫자를 믿을 수 없다. --raw 는 기준이 다른 것이
의도된 것이라 검사하지 않는다."
```

---

### Task 5: 오답 행 만들기

**Files:**
- Modify: `score_gold.py`
- Modify: `test_score_gold.py`

**Interfaces:**
- Consumes: `_pred` · `direction` (Task 1·2)
- Produces: `error_rows(gold, compare, cids, providers, raw=False) -> list[dict]` — 한 provider 라도 등급이나 유형이 틀린 case 만. 각 행은 `case_id · url · gold_risk · gold_type · gold_source · why · {p}_risk · {p}_type · {p}_direction` (provider 마다 3열)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_score_gold.py` 의 `test_verify_consensus` 아래에 넣는다:

```python
def test_error_rows() -> tuple[int, int]:
    """맞힌 case 는 빠지고, 남은 행에는 세 provider 판정이 나란히 들어간다"""
    gold = {
        "c1": _gold("c1", "LOW", "none", "auto_agree"),
        "c2": _gold("c2", "HIGH", "impersonation", "human_review"),
    }
    gold["c2"]["why"] = "공식 도메인 사칭"
    compare = {
        "c1": _cmp("c1", claude=("LOW", "none"), gemini=("LOW", "none")),
        "c2": _cmp("c2", claude=("HIGH", "impersonation"), gemini=("LOW", "none")),
    }
    rows = G.error_rows(gold, compare, ["c1", "c2"], ["claude", "gemini"])
    fails = _check("맞힌 case 는 빠진다", [r["case_id"] for r in rows], ["c2"])
    r = rows[0]
    fails += _check("gold_source", r["gold_source"], "human_review")
    fails += _check("why", r["why"], "공식 도메인 사칭")
    # 틀린 모델뿐 아니라 셋 다 실어야 왜 갈렸는지 나란히 보인다
    fails += _check("맞힌 provider 도 실린다", r["claude_risk"], "HIGH")
    fails += _check("claude_direction", r["claude_direction"], "")
    fails += _check("gemini_direction", r["gemini_direction"], "under")
    return fails, 6
```

`main()` 의 목록에 한 줄을 더한다:

```python
                     ("검산", test_verify_consensus), ("오답 행", test_error_rows)]:
```

- [ ] **Step 2: 실패하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: FAIL — `AttributeError: module 'score_gold' has no attribute 'error_rows'`

- [ ] **Step 3: 최소 구현을 쓴다**

`score_gold.py` 의 `verify_consensus` 아래에 이어 쓴다:

```python
def error_rows(gold: dict[str, dict], compare: dict[str, dict], cids: list[str],
               providers: list[str], raw: bool = False) -> list[dict]:
    """한 provider 라도 틀린 case 만. 숫자에서 바로 "어떤 case 에서 틀렸는데"로 넘어가려는 것

    틀린 모델만 싣지 않고 **세 provider 를 다** 싣는다 — 나란히 놓고 봐야 왜 갈렸는지
    보인다. `why` 는 사람이 라벨링 때 적은 근거로, human_review 행에만 있다
    """
    rows = []
    for cid in cids:
        g = gold[cid]
        cells, wrong = {}, False
        for p in providers:
            pred = _pred(compare[cid], p, raw)
            if pred is None:
                cells[f"{p}_risk"] = cells[f"{p}_type"] = ""
                cells[f"{p}_direction"] = "실패"
                continue
            d = direction(g["risk"], pred["risk"]) if pred["risk"] else None
            cells[f"{p}_risk"] = pred["risk"] or ""
            cells[f"{p}_type"] = pred["type"] or ""
            cells[f"{p}_direction"] = d or ""
            if d or (g.get("type") and pred["type"] and pred["type"] != g["type"]):
                wrong = True
        if not wrong:
            continue
        rows.append({"case_id": cid, "url": compare[cid].get("url") or g.get("url") or "",
                     "gold_risk": g["risk"], "gold_type": g.get("type", ""),
                     "gold_source": g.get("source", ""), "why": g.get("why", ""),
                     **cells})
    return rows
```

- [ ] **Step 4: 통과하는 것을 확인한다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: PASS — `합계 33/33 통과`

- [ ] **Step 5: 커밋한다**

```bash
git add score_gold.py test_score_gold.py
git commit -m "feat: 오답 행 — 세 provider 를 나란히 싣는다

틀린 모델만 싣지 않는다. 나란히 놓고 봐야 왜 갈렸는지 보인다."
```

---

### Task 6: CLI 조립 · 콘솔 출력 · CSV

**Files:**
- Modify: `score_gold.py`

**Interfaces:**
- Consumes: Task 1~5 의 모든 함수
- Produces: `main() -> int`. CLI 는 `score_gold.py <compare_jsonl> [--gold] [--tag] [--providers] [--raw]`

- [ ] **Step 1: 구현을 쓴다**

이 태스크는 앞선 순수 함수들을 엮어 찍는 것뿐이라 단위 테스트를 새로 쓰지 않는다.
검증은 Step 3 의 실제 데이터 실행으로 한다 — 251건이 이미 있고, 검산이 통과하는지가
곧 조립이 맞는지의 증거다.

`score_gold.py` 의 `error_rows` 아래에 이어 쓴다:

```python
def _tag_from(compare_path: str) -> str:
    """`compare_0830.jsonl` → `0830`. 채점 결과가 어느 병합본에서 나왔는지 이름에 남긴다"""
    stem = os.path.basename(compare_path)
    for cut in (".jsonl", ".json"):
        stem = stem[: -len(cut)] if stem.endswith(cut) else stem
    return stem[len("compare_"):] if stem.startswith("compare_") else stem or "latest"


def _pct(hit: int, n: int) -> str:
    return f"{hit}/{n} ({hit / n * 100:5.1f}%)" if n else f"{hit}/0 (  —  )"


def _print_risk(title: str, note: str, scores: dict[str, dict], providers: list[str]) -> None:
    print(f"\n── {title} " + "─" * max(0, 60 - len(title)))
    if note:
        print(f"   {note}")
    for p in providers:
        s = scores[p]
        line = f"  {p:8s} 정확도 {_pct(s['hit'], s['n'])}"
        if s["n"]:
            line += f" · 미탐 {s['under']} · 과탐 {s['over']}"
        if s["skipped"]:
            line += f" · 채점제외 {s['skipped']}"
        print(line)
        if not s["n"]:
            continue
        order = [r for r in RISK_ORDER if any(k[0] == r for k in s["confusion"])]
        if order:
            print("             gold\\pred " + "".join(f"{r:>8s}" for r in RISK_ORDER))
            for gr in order:
                cells = "".join(f"{s['confusion'].get((gr, pr), 0):8d}" for pr in RISK_ORDER)
                print(f"             {gr:9s}" + cells)


def main() -> int:
    ap = argparse.ArgumentParser(description="Gold 기준 3사 채점")
    ap.add_argument("compare_jsonl", help="merge_results.py 가 만든 compare_{tag}.jsonl")
    ap.add_argument("--gold", default=os.path.join(HERE, "gold", "gold_251.jsonl"))
    ap.add_argument("--tag", default=None, help="기본은 compare 파일 이름에서 따온다")
    ap.add_argument("--providers", nargs="+", default=list(PROVIDER_NAMES))
    ap.add_argument("--raw", action="store_true",
                    help="후처리 전(risk_raw) 기준. Gold 는 후처리 후 값으로 만들어졌으므로 "
                         "기준이 어긋난다 — 검산을 끄고 경고만 낸다")
    args = ap.parse_args()

    gold = load_jsonl(args.gold)
    compare = load_jsonl(args.compare_jsonl)
    cids, gold_only = join(gold, compare)
    if not cids:
        raise SystemExit(f"조인된 case 가 없다 — {args.gold} 와 {args.compare_jsonl} 의 "
                         "case_id 가 서로 다른 dataset 에서 나온 것 같다")
    tag = args.tag or _tag_from(args.compare_jsonl)

    risk_c = [c for c in cids if risk_bucket(gold[c].get("source", "")) == CONSENSUS]
    risk_h = [c for c in cids if risk_bucket(gold[c].get("source", "")) == HUMAN]
    type_c = [c for c in cids if type_bucket(gold[c].get("source", "")) == CONSENSUS]
    type_h = [c for c in cids if type_bucket(gold[c].get("source", "")) == HUMAN]

    print(f"gold {args.gold} — {len(gold)}건")
    print(f"예측 {args.compare_jsonl} — 조인 {len(cids)}건"
          + (f" (gold 에만 있는 case {len(gold_only)}건은 채점에서 제외)" if gold_only else ""))
    print(f"기준: {'후처리 전(raw)' if args.raw else '후처리 후'} · 이름표 {tag}")
    if args.raw:
        print("  ! --raw 는 Gold(후처리 후)와 기준이 다르다 — 검산을 끄고 낸다")

    s_all = score_risk(gold, compare, cids, args.providers, args.raw)
    s_con = score_risk(gold, compare, risk_c, args.providers, args.raw)
    s_hum = score_risk(gold, compare, risk_h, args.providers, args.raw)

    bad = verify_consensus(s_con, args.raw)
    if bad:
        raise SystemExit(
            "검산 실패 — 3사 합의 구간은 정의상 전원 100% 여야 한다.\n  "
            + "\n  ".join(bad)
            + "\n  조인이 어긋났거나, 이 compare 파일이 Gold 를 만든 것과 다르다.\n"
              "  build_gold.py 에 넣었던 compare 파일과 같은 것을 주고 있는지 확인하라.")

    print("\n" + "=" * 62)
    print(f"등급 (risk) — 3사 합의 {len(risk_c)}건 · 사람 확정 {len(risk_h)}건")
    print("=" * 62)
    _print_risk(f"전체 {len(cids)}건", "순환 포함 — Gold 의 대부분이 3사 합의라 참고용이다",
                s_all, args.providers)
    _print_risk(f"3사 합의 {len(risk_c)}건", "정의상 전원 100% (검산 통과)",
                s_con, args.providers)
    _print_risk(f"사람 확정 {len(risk_h)}건", "★ 순환이 없는 유일한 구간 — 실제 변별력",
                s_hum, args.providers)

    t_con = score_type(gold, compare, type_c, args.providers, args.raw)
    t_hum = score_type(gold, compare, type_h, args.providers, args.raw)
    print("\n" + "=" * 62)
    print(f"유형 (type) — 3사 합의 {len(type_c)}건 · 사람 확정 {len(type_h)}건")
    print("  등급과 구간이 다르다 — auto_agree+human_type 행은 유형을 사람이 채웠다")
    print("=" * 62)
    for label, sc in (("3사 합의", t_con), ("사람 확정", t_hum)):
        print(f"\n── {label} " + "─" * 50)
        for p in args.providers:
            s = sc[p]
            print(f"  {p:8s} 정확도 {_pct(s['hit'], s['n'])}"
                  + (f" · 채점제외 {s['skipped']}" if s["skipped"] else ""))
            top = sorted(s["pairs"].items(), key=lambda kv: -kv[1])[:3]
            for (gt, pt), c in top:
                print(f"             {gt} → {pt}  {c}건")

    rows = error_rows(gold, compare, cids, args.providers, args.raw)
    out_dir = os.path.join(HERE, "results", "scored")
    os.makedirs(out_dir, exist_ok=True)
    cpath = os.path.join(out_dir, f"errors_{tag}.csv")
    cols = (["case_id", "url", "gold_risk", "gold_type", "gold_source", "why"]
            + [f"{p}_{k}" for p in args.providers for k in ("risk", "type", "direction")])
    with open(cpath, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\n한 provider 라도 틀린 case {len(rows)}건 → {cpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

파일 맨 위 import 를 다음으로 바꾼다 (`argparse` · `csv` · `os` 가 늘어난다):

```python
import argparse
import csv
import json
import os

from providers.base import PROVIDER_NAMES

HERE = os.path.dirname(os.path.abspath(__file__))
```

- [ ] **Step 2: 단위 테스트가 여전히 통과하는지 본다**

Run: `.venv/Scripts/python.exe test_score_gold.py`
Expected: PASS — `합계 33/33 통과`

- [ ] **Step 3: 실제 데이터로 돌린다**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe score_gold.py results/merged/compare_0830.jsonl
```

Expected:
- 검산 통과 (3사 합의 222건에서 세 provider 모두 100%). **여기서 멈추면 조립이 잘못된 것이다** — 오류 메시지가 시키는 대로 compare 파일이 `build_gold.py` 에 넣었던 것과 같은지부터 확인한다.
- 등급 블록 세 개 · 유형 블록 두 개가 찍힌다
- `results/scored/errors_0830.csv` 가 생긴다

- [ ] **Step 4: CSV 가 gitignore 되는지 확인한다**

Run: `git check-ignore -v results/scored/errors_0830.csv`
Expected: `.gitignore:9:results/*/*.csv	results/scored/errors_0830.csv`

판정 문장이 든 파일이므로 커밋되면 안 된다. 규칙에 안 걸리면 **`.gitignore` 를 고치지 말고 멈추고 보고한다** — 커밋 정책은 팀이 정한 것이다.

- [ ] **Step 5: `--raw` 가 중단되지 않는지 확인한다**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe score_gold.py results/merged/compare_0830.jsonl --raw
```
Expected: `! --raw 는 Gold(후처리 후)와 기준이 다르다` 경고가 찍히고 **끝까지 돈다** (검산으로 중단되지 않는다)

- [ ] **Step 6: 커밋한다**

```bash
git add score_gold.py
git commit -m "feat: 채점 CLI · 콘솔 출력 · 오답 CSV

전체/3사 합의/사람 확정 세 구간을 나누어 찍고, 전체 숫자에는 순환 포함이라고
명시한다. 오답은 results/scored/errors_{tag}.csv 로 — gitignore 대상이다."
```

---

### Task 7: README 갱신

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: 없음
- Produces: 없음

- [ ] **Step 1: README 의 파이프라인 그림에 채점 단계를 더한다**

`README.md` 상단 코드블록의 `merge_results.py` 줄 아래에 이어 붙인다:

```
                        python merge_results.py  →  results/merged/compare_{tag}.jsonl + .csv
                                                          │
                        python extract_disagreements.py  →  dataset/to_label_{tag}.json
                                                          │  (사람이 expect 를 채운다)
                        python build_gold.py             →  gold/gold_251.jsonl
                                                          │
                        python score_gold.py             →  results/scored/errors_{tag}.csv
```

- [ ] **Step 2: 채점 절 을 더한다**

README 의 "이 저장소는 단독으로 실행된다" 절 아래에 넣는다:

```markdown
## 채점 — 누가 더 맞는가

`merge_results.py` 의 일치율은 "셋이 서로 얼마나 같은가"이지 "누가 더 맞는가"가 아니다.
셋이 함께 틀려도 일치율은 100% 다. Gold 가 확정된 뒤에야 정확도를 물을 수 있다.

    python score_gold.py results/merged/compare_0830.jsonl

Gold 251건 중 220건은 3사 합의로 자동 확정된 것이라, 그 구간을 정답으로 놓으면 세 모델
모두 **정의상** 100% 가 나온다. 그래서 전체 / 3사 합의 / 사람 확정 세 구간으로 나누어
찍는다 — **실제 변별력은 사람 확정 구간에서만 나온다**.

등급은 순서가 있어(LOW < MEDIUM < HIGH) 정확도와 함께 미탐·과탐을 나누어 낸다.
한 provider 라도 틀린 case 는 `results/scored/errors_{tag}.csv` 로 나간다 (커밋되지 않는다).
```

- [ ] **Step 3: 커밋한다**

```bash
git add README.md
git commit -m "docs: README 에 채점 단계 추가

일치율과 정확도는 다른 것이라는 점, 구간을 나누는 이유를 적었다."
```

---

## Self-Review

**1. 스펙 커버리지** — 설계 문서의 각 절을 태스크에 대응시켰다.

| 스펙 절 | 태스크 |
| :-- | :-- |
| 채점 범위 · 구간 분리 | Task 1 (`risk_bucket`·`type_bucket`), Task 6 (세 구간 출력) |
| 등급과 유형의 구간이 다름 | Task 1 (`test_buckets` 가 이것만 검사한다) |
| 입력과 조인 | Task 1 (`load_jsonl`·`join`) |
| 예측을 compare 셀에서 읽음 | Task 2 (`_pred`) |
| gold 에만 있는 case 제외 | Task 1 (`join` 이 나눠 돌려줌), Task 6 (건수 보고) |
| provider 실패를 오답으로 세지 않음 | Task 2 (`skipped`), `test_score_risk` 가 검사 |
| 정확도 · 미탐/과탐 · 혼동행렬 | Task 2 |
| 유형 정확도 · 상위 오답 쌍 | Task 3 |
| 검산 · `--raw` 는 경고만 | Task 4 |
| 콘솔 세 덩어리 | Task 6 |
| errors CSV · 열 구성 | Task 5 (행), Task 6 (쓰기) |
| CSV 가 gitignore 됨 | Task 6 Step 4 가 확인 |
| 인터페이스(인자 표) | Task 6 |
| 테스트 5가지 | Task 1~5 의 테스트가 각각 대응 (1·2·3·4·5 ↔ 검산통과·검산중단·구간분리·방향·실패제외) |
| macro F1 을 넣지 않음 | 어느 태스크에도 없음 — 의도된 것 |
| fine-tuned model 확장 | `--providers` 로 열어 둠 (Task 6) |

빠진 요구사항 없음.

**2. 플레이스홀더 검사** — "TBD" · "적절히 처리" · "위의 것에 대한 테스트를 쓴다" 같은 표현 없음. 모든 코드 단계에 실제 코드가 들어 있다.

**3. 타입 일관성** — 태스크 간에 쓰는 이름을 대조했다.

- `_pred(compare_row, provider, raw) -> dict | None` — Task 2 에서 정의, Task 3·5 에서 같은 이름·같은 인자로 사용
- `direction(gold_risk, pred_risk) -> str | None` — Task 2 정의, Task 5 사용
- `s["confusion"]` 은 `dict[tuple[str,str], int]` — Task 2 가 만들고 Task 6 `_print_risk` 가 `.get((gr, pr), 0)` 로 읽는다. 키 순서 `(gold, pred)` 일치
- `s["pairs"]` 도 `(gold_type, pred_type)` — Task 3 이 만들고 Task 6 이 `for (gt, pt), c in top` 으로 읽는다. 일치
- `risk_bucket`/`type_bucket` 반환값 `CONSENSUS`·`HUMAN` 상수 — Task 1 정의, Task 6 비교에 사용
- `error_rows` 의 열 이름 `{p}_risk`·`{p}_type`·`{p}_direction` — Task 5 가 만들고 Task 6 의 `cols` 가 같은 규칙으로 생성

어긋난 곳 없음.

**한 가지 남는 위험**: Task 6 Step 3 의 검산이 실제 데이터에서 통과할지는 돌려 봐야 안다. `build_gold.py` 가 `compare_0830.jsonl` 에서 Gold 를 만들었고 같은 파일을 채점에 주므로 통과해야 하지만, 만약 실패하면 그 자체가 유용한 발견이다 — 검산이 제 역할을 한 것이므로 원인을 찾아 보고하고 넘어가지 않는다.
