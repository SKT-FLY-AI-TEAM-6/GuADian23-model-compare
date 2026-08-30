# fine-tuned classifier 학습셋 추출 — 설계

`gold/gold_251.jsonl` 을 라벨로, `build_prompt.py` 가 조립한 프롬프트를 입력으로 하는
학습셋 `dataset/trainset_{tag}.jsonl` 을 만드는 스크립트 `build_trainset.py` 의 설계.

## 범위

**학습셋 하나까지다.** 학습 코드·모델 선택·하이퍼파라미터는 넣지 않는다 — 모델이 아직
없고 프레임워크도 정해지지 않았다. `providers/` 에 붙일 어댑터는 모델이 생긴 뒤에 만든다.

## 라벨 — 2클래스로 간다

Gold 251건의 분포가 이 결정을 강제한다.

```
등급   LOW 129 · MEDIUM 121 · HIGH 1
유형   none 129 · unverifiable 66 · personal_info 45 · contentfarm 8 · urgency 2 · impersonation 1
```

**HIGH 가 1건, `impersonation` 1건, `urgency` 2건이다.** 이 클래스들은 학습도 평가도
불가능하다 — train/test 로 나누면 한쪽에만 들어가거나 아예 빠진다. 유형 6클래스도
251건에는 무리이고 하위 3개 클래스가 합쳐서 11건이다.

그래서 등급을 2클래스로 묶는다.

| label | 원본 risk | 건수 |
| --: | :-- | --: |
| `0` | LOW | 129 |
| `1` | MEDIUM · HIGH | 122 |

129 대 122 로 균형이 좋고, 서비스에서도 "경고를 띄울지 말지"가 가장 큰 결정이다.

원본 `risk` · `type` · `source` 는 각 행에 그대로 실어 둔다. 나중에 데이터가 늘어
3클래스나 유형 분류로 갈 때 **251건을 다시 조립하지 않고 라벨만 바꿔 재산출**할 수
있어야 하기 때문이다.

## 입력 — 3사가 본 것과 문자 단위로 같게

`build_prompt.py` 가 만드는 user 프롬프트를 그대로 `text` 로 쓴다. 길이는 중앙 3,019자
(p10 1,094 · p90 4,683 · 최대 5,399).

`run_eval.py` 가 세 provider 에게 보낸 것과 **같은 함수·같은 파라미터로 조립**하므로,
분류기가 붙었을 때 `score_gold.py` 의 같은 표에서 비교해도 공정하다. 입력이 다르면
"누가 더 맞는가"가 아니라 "누가 더 좋은 입력을 받았는가"를 재게 된다.

### `lookup_cache` 를 반드시 제외한다

`run_eval.py` 의 `DEFAULT_EXCLUDE` 와 같은 값을 쓴다. 그 도구 출력의 `previous` 에는
**과거 Claude 판정이 들어 있어** 입력에 남기면 라벨 누출이다. 팀 가이드라인 §3 이
금지하는 것이기도 하고, 3사가 보지 않은 것을 분류기만 보면 비교가 깨진다.

다만 이 값을 스크립트에 **하드코딩하지 않는다** — 아래 검증 단계에서 참조 run 의
기록을 읽어 쓴다.

## 검증 — sha 가 하나라도 어긋나면 중단한다

`prompt_sha256` 을 계산해 행에 남기는 것만으로는 부족하다. 기록해 두고 아무도 안 보면
조립 규칙이 바뀌어도 모른 채 다른 입력으로 학습하게 된다. **계산이 아니라 검증 단계로
넣는다.**

### 참조원

`results/*/*.jsonl` 전체에서 `case_id → prompt_sha256` 을 모은다. 조사 결과:

- run 파일 12개, 세 provider, 두 spec(`oneshot-20260828` · `oneshot-20260828-impers1`),
  여러 재실행에 걸쳐 **case 별 sha 가 단 하나씩** — 충돌 0건
- 251건 전부 sha 를 가지고 있고 빈 값 0건
- spec 이 달라도 user 프롬프트는 같다 (spec 은 system 만 바꾼다)

그래서 참조원을 특정 run 으로 못 박을 필요가 없다. 있는 run 을 다 모아 교차 확인한다.

### 절차

```
1. 참조 sha 수집   results/*/*.jsonl 전체 → case_id → sha
                   같은 case 에 다른 sha 가 있으면 그 자체가 이상 → 중단
2. 조립 파라미터   참조 run 행의 input_mode · excluded_tools 를 읽어 그대로 쓴다
3. 조립 + 해시     build_prompt.py 로 조립하고 sha256 계산
4. 전건 대조       하나라도 다르면 중단
```

**2번이 핵심이다.** 설계 중 실제로 밟은 실수가 여기 있다 — 프롬프트 길이를 재면서
`input_mode='oneshot'` 을 썼는데 모든 run 은 `guardian-trim` 이었다. 이 데이터에서는
두 모드가 같은 결과를 내 숫자가 틀리지 않았지만, 하드코딩했다면 조용히 다른 조립을
쓸 수 있었다. 조립 파라미터는 결과 행에 이미 기록돼 있으므로 그것을 정본으로 삼는다.

### 중단 메시지

어긋난 `case_id`, 기록된 sha, 지금 계산된 sha, 그리고 원인 후보 세 가지를 낸다.

| 원인 후보 | 확인할 곳 |
| :-- | :-- |
| 조립 규칙이 바뀌었다 | `build_prompt.py` |
| 판정 기준의 assembly 가 바뀌었다 | `dataset/prompt_spec.json` 의 `assembly` |
| 다른 cases 파일을 주고 있다 | `--cases` 인자 |

이 셋 말고는 어긋날 이유가 없다.

### 참조 run 이 없는 case 도 중단이다

지금은 251건 전부 있다. cases 파일이 바뀌어 새 case 가 들어오면 그 case 는 3사가
판정한 적이 없다는 뜻이고, 그러면 "3사와 같은 입력"이라는 전제 자체가 깨진다.
조용히 넘어가면 학습셋 일부만 검증되지 않은 조립으로 들어간다.

**`--allow-unverified` 같은 우회 옵션은 두지 않는다.** 이 검증을 통과하지 못하는
학습셋은 만들 이유가 없다.

## 분할

`label × source` 로 계층화한다. `source` 를 층에 넣는 이유는 아래 "한계" 절과 같다 —
auto_agree 와 human_review 는 성격이 다른 데이터라 한쪽에 몰리면 안 된다.

- `split` — `train` / `test`, 기본 8:2, seed 고정
- `fold` — 같은 계층 기준으로 5-fold 배정 (0~4)

**`split` 과 `fold` 는 서로 독립이다.** `fold` 는 `split` 과 무관하게 **251건 전체에**
배정한다 — test 행도 fold 를 가진다. 둘은 서로 다른 평가 방식이라 섞으면 안 된다.

| 쓰는 방식 | 보는 컬럼 |
| :-- | :-- |
| 한 번 학습해 held-out 으로 평가 | `split` 만 (`train` 으로 학습, `test` 로 평가) |
| 5-fold 교차검증 | `fold` 만 (`fold != k` 로 학습, `fold == k` 로 평가, k=0~4) |

두 컬럼을 동시에 쓰지 않는다. 예컨대 "train 중에서 fold 나누기"는 하지 않는다 — 그러면
CV 가 251건이 아니라 201건만 덮게 되어 human_review 29건 전부를 평가한다는 목적이 깨진다.

파일을 셋으로 쪼개지 않고 **한 파일에 컬럼으로** 둔다. 분할이 맞게 됐는지 한 파일만
보면 검증되고, 재현이 쉽고, fold 를 바꿔 가며 돌리기도 편하다.

251건은 held-out test 가 50건뿐이라 추정치가 불안정하다. 그중 human_review 는 6건에
불과하다. 그래서 **5-fold 를 같이 배정해 29건 전부가 한 번씩 평가되게** 한다.

평가할 때는 `source` 로 갈라 auto_agree 구간과 human_review 구간 점수를 **따로** 낸다.
`score_gold.py` 가 이미 쓰는 방식과 같다.

## 정직하게 적어둘 한계

**Gold 251건 중 220건이 3사 합의로 만들어졌다.** 이것으로 학습한 분류기는 상당 부분
**3사를 모방하도록** 배운다 — 지식 증류에 가깝지 사람이 정한 정답을 배우는 것이 아니다.
순환이 없는 신호는 사람 확정 29건뿐이고, 그중 test 로 가는 것은 6건이다.

데이터가 늘기 전까지 해결되지 않는 구조적 한계다. **설계 문서와 스크립트 콘솔 출력
양쪽에 명시한다** — "정확도 92%" 같은 숫자가 혼자 돌아다니면 오해를 부른다.

## 산출물은 커밋하지 않는다

`text` 가 조립된 프롬프트 전문, 즉 페이지 본문이다. `results/*.jsonl` 과 같은 취급이라
`.gitignore` 에 `dataset/trainset_*.jsonl` 을 추가한다.

커밋되는 것은 스크립트와 이 문서뿐이다.

## 인터페이스

```bash
python build_trainset.py --tag 0831
```

| 인자 | 기본값 |
| :-- | :-- |
| `--gold` | `gold/gold_251.jsonl` |
| `--cases` | `dataset/cases_251_20260829.jsonl` |
| `--spec` | `dataset/prompt_spec.json` |
| `--results` | `results` — 참조 sha 를 모을 곳 |
| `--tag` | 필수 — 산출 파일 이름표 |
| `--test-ratio` | `0.2` |
| `--folds` | `5` |
| `--seed` | `42` |

`build_gold.py` · `score_gold.py` 와 같은 결이다.

## 출력 행

```json
{"case_id": "case_001", "text": "[도착 주소] …", "label": 0,
 "risk": "LOW", "type": "none", "source": "auto_agree",
 "split": "train", "fold": 2, "prompt_sha256": "a3f…"}
```

## 콘솔 출력

- 참조 sha 수집 결과 (run 파일 수 · 검증된 case 수)
- 검증 통과 여부
- label × source 교차표, split · fold 별 건수
- **"3사 모방" 한계 경고** — 매 실행 출력한다

## 테스트

`test_score_gold.py` 와 같은 모양의 독립 스크립트 `test_build_trainset.py`.
pytest 를 쓰지 않는다 (`requirements.txt` 가 provider SDK 만 두는 방침).

손으로 만든 작은 입력으로 확인한다.

1. 라벨 매핑 — LOW→0, MEDIUM→1, HIGH→1
2. sha 검증이 통과한다 (참조와 같은 조립)
3. sha 가 어긋나면 **중단한다**
4. 같은 case 에 참조 sha 가 둘이면 **중단한다**
5. 참조 run 이 없는 case 가 있으면 **중단한다**
6. 계층 분할이 label × source 비율을 유지한다
7. fold 가 0~4 로 고르게 배정되고 모든 case 가 정확히 한 fold 에 속한다
   (test 행 포함 — fold 는 split 과 독립이다)
8. seed 가 같으면 분할이 재현된다

## 다음

모델이 생기면 `providers/` 에 어댑터를 만들고 `score_gold.py --providers` 에 이름을
더해 같은 표에서 비교한다. 그때 이 스크립트를 고칠 일이 없어야 한다.
