# Gold 기준 3사 채점 — 설계

`gold/gold_251.jsonl` 을 정답으로 놓고 claude · gemini · openai 의 판정을 채점하는
스크립트 `score_gold.py` 의 설계.

## 왜 필요한가

지금까지는 "세 모델이 서로 얼마나 일치하는가"만 있었다 (`merge_results.py`). 일치율은
누가 더 맞는지를 말해 주지 않는다 — 셋이 함께 틀려도 일치율은 100% 다. Gold 가 확정된
지금, 처음으로 "누가 더 맞는가"를 물을 수 있다.

## 채점 범위 — 순환을 숨기지 않는다

Gold 251건 중 220건은 **3사 합의로 자동 확정된 것**이다. 그 구간을 정답으로 놓고 채점하면
세 모델 모두 정의상 100% 가 나온다. 전체 정확도만 내면 이 순환이 숫자에 가려진다.

그래서 세 구간을 나누어 낸다.

| 구간 | 성격 |
| :-- | :-- |
| 전체 251건 | 대외 보고용. **순환 포함이라고 출력에 명시한다** |
| 3사 합의 구간 | 정의상 전원 100%. 검산용 |
| 사람 확정 구간 | 순환이 없는 유일한 구간. **실제 변별력은 여기서만 나온다** |

### 등급과 유형은 구간이 다르다

`auto_agree+human_type` 2건(case_131 · case_204)은 **등급은 3사 합의, 유형은 사람**이
정했다. 하나의 구간 분류를 등급·유형에 같이 쓰면 이 2건이 한쪽에서 잘못된 구간에 들어간다
— 사람이 정한 유형이 "3사 합의 구간"에 섞여 순환 판정을 받게 된다.

| | 3사 합의 구간 | 사람 확정 구간 |
| :-- | --: | --: |
| **등급 (risk)** | 222건 (`auto_agree` 220 + `auto_agree+human_type` 2) | 29건 |
| **유형 (type)** | 220건 (`auto_agree`) | 31건 (`human_review` 29 + `auto_agree+human_type` 2) |

구간은 Gold 행의 `source` 로 정한다. 등급용·유형용 두 벌을 따로 계산한다.

## 입력과 조인

```
gold/gold_251.jsonl                  정답 (risk · type · source · why)
results/merged/compare_{tag}.jsonl   예측 (provider 셀)
        └─ case_id 로 조인
```

예측은 `run_eval.py` 결과를 직접 읽지 않고 **compare 파일의 provider 셀에서 읽는다**.
어느 run 을 쓸지 고르는 규칙(최신 우선 · 성공 우선)이 이미 `merge_results.py:58` 에 있고,
그것을 두 군데 두면 언젠가 어긋난다. compare 파일이 이미 그 규칙을 적용한 결과다.

`--raw` 는 다른 스크립트와 같은 의미로 단다 (후처리 전 `risk_raw` · `type_raw` 기준).
Gold 는 후처리 후 값으로 만들어졌으므로 `--raw` 로 채점하면 기준이 어긋난다 — 그 사실을
출력에 경고로 남긴다.

Gold 에는 있는데 compare 에 없는 case, 또는 해당 provider 가 실패한 case 는 **정답으로도
오답으로도 세지 않고** 별도로 건수만 보고한다. 실패를 오답으로 세면 모델의 판단력과
API 실패가 한 숫자에 섞인다.

## 지표

등급은 순서가 있다 (LOW < MEDIUM < HIGH). 단순 정답/오답보다 **틀린 방향**이 중요하다 —
Gold 가 HIGH 인데 LOW 로 본 것(미탐)과 Gold 가 LOW 인데 HIGH 로 본 것(과탐)은 서비스에서
의미가 전혀 다르다.

provider 마다:

- 정확도 (맞힌 수 / 채점된 수)
- **미탐(under)** · **과탐(over)** 건수 — 등급 순서로 방향을 판정
- 3×3 혼동행렬 (gold × pred)

유형은 별도 블록에서 정확도와 상위 오답 쌍(gold_type → pred_type 빈도)을 낸다.

**넣지 않는 것**: macro F1 · 신뢰구간. Gold 의 HIGH 가 1건이라 클래스별 지표가 의미를
갖기 어렵고, 사람 확정 구간 29~31건은 표본이 작아 소수점이 오해를 부른다. 필요해지면
그때 붙인다.

## 검산 — 어긋나면 멈춘다

정의상 성립해야 하는 것이 있다: **3사 합의 구간에서 세 provider 모두 100%**.

여기서 100% 가 안 나오면 조인이 어긋났거나, `--raw` 기준이 Gold 와 다르거나, compare
파일이 Gold 를 만든 것과 다른 것이다. 어느 쪽이든 나머지 숫자를 믿을 수 없다. 조용히
이상한 값을 내놓는 것보다 **중단하고 무엇이 어긋났는지 말하는 쪽**이 낫다.

단, `--raw` 를 준 때는 기준이 다른 것이 의도된 것이므로 중단하지 않고 경고만 낸다.

## 출력

콘솔에 세 덩어리 — 전체 / 3사 합의 / 사람 확정. 각 구간마다 provider 별 정확도 ·
미탐 · 과탐 · 혼동행렬. 이어서 유형 블록.

`results/scored/errors_{tag}.csv` — **틀린 case 만**. 숫자를 보고 바로 "그래서 어떤
case 에서 틀렸는데"로 넘어갈 수 있어야 한다.

| 열 | 내용 |
| :-- | :-- |
| `case_id` · `url` | 어느 case 인가 |
| `gold_risk` · `gold_type` · `gold_source` | 정답과 그 출처 |
| `{provider}_risk` · `{provider}_type` | 세 모델의 판정 (틀린 모델뿐 아니라 셋 다 — 나란히 봐야 왜 갈렸는지 보인다) |
| `direction` | under / over / type_only |
| `why` | 사람이 라벨링 때 적은 근거 (`human_review` 행에만 있다) |

`results/scored/` 는 `results/*/*.csv` 규칙에 이미 걸려 gitignore 된다 — 판정 문장이
들어가므로 커밋하지 않는다.

## 인터페이스

```bash
python score_gold.py results/merged/compare_0830.jsonl \
    --gold gold/gold_251.jsonl \
    --tag 0830
```

| 인자 | 기본값 |
| :-- | :-- |
| `compare_jsonl` (위치인자) | 필수 |
| `--gold` | `gold/gold_251.jsonl` |
| `--tag` | compare 파일 이름에서 따온다 (`compare_0830.jsonl` → `0830`) |
| `--providers` | `PROVIDER_NAMES` |
| `--raw` | 꺼짐 |

`build_gold.py` · `extract_disagreements.py` 와 같은 모양이다 — compare 파일을 위치인자로
받고 나머지는 옵션.

## 테스트

`test_assembly.py` 가 이미 있는 검증 스크립트지만 그것은 프롬프트 조립 검증용이라
성격이 다르다. 채점 로직은 다음을 손으로 만든 작은 입력으로 확인한다.

1. 3사 합의 구간에서 전원 100% 가 나온다 (검산이 통과한다)
2. 검산이 깨지는 입력을 주면 **중단한다**
3. `auto_agree+human_type` 행이 등급은 합의 구간, 유형은 사람 구간으로 간다
4. 미탐/과탐 방향이 등급 순서대로 판정된다 (HIGH→LOW 는 under, LOW→HIGH 는 over)
5. provider 실패 행이 오답으로 세지지 않는다

## 다음

fine-tuned classifier 가 `providers/` 에 붙으면 `--providers` 에 이름 하나를 더해
같은 표에서 비교한다. 그때 이 스크립트를 고칠 일이 없어야 한다.
