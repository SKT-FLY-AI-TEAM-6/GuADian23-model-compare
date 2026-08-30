# GuADian23-model-compare

같은 입력·같은 판정 기준으로 Claude / Gemini / OpenAI를 비교하는 독립 실험 저장소.
이후 fine-tuned classifier도 같은 자리에 끼워 비교한다.

```
dataset/cases.jsonl       (별도 공유 — raw tool_outputs가 든 최종 선별본)
dataset/prompt_spec.json  (GuADian 서버에서 1회 추출해 봉인한 판정 기준)
        │
        ├─ build_prompt.py: raw tool_outputs → 서비스와 동일한 규칙으로 user 프롬프트 조립
        │
        ├─ python run_eval.py --provider claude  →  results/claude/{run_id}.jsonl
        ├─ python run_eval.py --provider gemini  →  results/gemini/{run_id}.jsonl
        └─ python run_eval.py --provider openai  →  results/openai/{run_id}.jsonl
                                                          │
                        python merge_results.py  →  results/merged/compare_{tag}.jsonl + .csv
                                                          │
                        python extract_disagreements.py  →  dataset/to_label_{tag}.json
                                                          │  (사람이 expect 를 채운다)
                        python build_gold.py             →  gold/gold_251.jsonl
                                                          │
                        python score_gold.py             →  results/scored/errors_{tag}.csv
                                                          │
                        python build_trainset.py --tag 0831  →  dataset/trainset_0831.jsonl
```

## 저장소 구분

| 저장소 | 하는 일 |
| :-- | :-- |
| **GuADian23-judge-research** | 실제 GuADian 판정 로직. 판정하며 `tool_outputs` · `prompt_text` · `page_text` 등 판정 원본을 **수집**한다 |
| **GuADian23-model-compare** (이 저장소) | 수집된 **고정 입력**으로 Claude / Gemini / OpenAI 및 이후 fine-tuned model을 **비교**하는 독립 실험 저장소 |

수집과 비교를 분리한 이유는, 비교 단계가 페이지를 다시 열지도 광고를 다시 누르지도 않기
때문이다. 저장된 snapshot만 읽으므로 몇 번을 돌려도 같은 입력이고, 서버 코드와 무관하게 굴러간다.

## 채점 — 누가 더 맞는가

`merge_results.py` 의 일치율은 "셋이 서로 얼마나 같은가"이지 "누가 더 맞는가"가 아니다.
셋이 함께 틀려도 일치율은 100% 다. Gold 가 확정된 뒤에야 정확도를 물을 수 있다.

```bash
python score_gold.py results/merged/compare_0830.jsonl
python test_score_gold.py                          # 채점 로직 검증 (네트워크 없음)
```

Gold 251건 중 220건은 3사 합의로 자동 확정된 것이라, 그 구간을 정답으로 놓으면 세 모델
모두 **정의상** 100% 가 나온다. 그래서 전체 / 3사 합의 / 사람 확정 세 구간으로 나누어
찍는다 — **실제 변별력은 사람 확정 구간에서만 나온다**. 3사 합의 구간에서 100% 가 안
나오면 채점이 틀린 것이므로 중단한다.

등급은 순서가 있어(LOW < MEDIUM < HIGH) 정확도와 함께 미탐·과탐을 나누어 낸다.
한 provider 라도 틀린 case 는 `results/scored/errors_{tag}.csv` 로 나간다 (커밋되지 않는다).

## 학습셋 — fine-tuned classifier 용

```bash
python build_trainset.py --tag 0831
python test_build_trainset.py              # 추출 로직 검증 (네트워크 없음)
```

Gold 의 등급을 2클래스(LOW=0 · MEDIUM·HIGH=1)로 묶어 라벨로, `build_prompt.py` 가 조립한
user 프롬프트를 입력으로 낸다. HIGH 가 1건뿐이라 3클래스로는 학습도 평가도 되지 않는다.
원본 `risk` · `type` · `source` 를 각 행에 실어 두므로, 데이터가 늘면 **다시 조립하지 않고**
라벨만 바꿔 재산출할 수 있다.

**조립 결과는 3사에게 실제로 보낸 것과 전건 대조한다.** `results/*/*.jsonl` 에 기록된
`prompt_sha256` 과 하나라도 다르면 중단한다 — 입력이 다르면 `score_gold.py` 의 같은 표에서
비교해도 공정하지 않다. 조립 파라미터도 하드코딩하지 않고 참조 run 에서 읽는다.

산출물은 커밋되지 않는다 (`text` 가 페이지 본문이다).

**한계**: Gold 251건 중 220건이 3사 합의로 만들어졌으므로, 이것으로 학습한 분류기는 상당
부분 3사를 모방하도록 배운다. 평가할 때 `source` 로 갈라 구간별 점수를 따로 내라.

## 이 저장소는 단독으로 실행된다

GuADian 원본 저장소가 로컬에 없어도 아래가 모두 동작한다.

```bash
python run_eval.py --dry-run
python run_eval.py --provider claude --limit 3
python run_eval.py --provider claude
python merge_results.py
```

판정 기준은 `dataset/prompt_spec.json`에 봉인된 채로 저장소에 들어 있고, `run_eval.py`는
그 파일만 읽는다. GuADian 저장소가 필요한 것은 **보조 기능 둘뿐**이며, 없으면 명확한
메시지와 함께 건너뛰거나 종료한다 — 판정 실행에는 영향을 주지 않는다.

| 보조 기능 | 필요한 환경변수 |
| :-- | :-- |
| 판정 기준 재생성 `build_prompt.py --from-server` | `GUARDIAN_SERVER` |
| 조립이 서버 코드와 같은지 검증 `test_assembly.py` (검사 A·B) | `GUARDIAN_ROOT` |

```bash
export GUARDIAN_SERVER=~/GuADian23-judge-research/server
python build_prompt.py --from-server --force      # 서버의 판정 기준이 바뀌었을 때만

export GUARDIAN_ROOT=~/GuADian23-judge-research
python test_assembly.py                           # 조립이 서비스와 같은지 검증
```

## 모델 API 말고는 바깥으로 나가지 않는다

페이지를 다시 열지 않고, 광고를 다시 누르지 않고, 차단 목록·RDAP도 조회하지 않는다.
case에 저장된 도구 결과를 읽어 문자열로 조립할 뿐이다. `run_eval.py`는 실행 중
provider API 호스트 외의 연결을 차단하며(`--no-guard`로 끌 수 있으나 권장하지 않는다),
`--dry-run`은 **어떤** 연결도 막는다.

## 준비

```bash
pip install -r requirements.txt        # 맡은 provider 것만 깔아도 된다
```

키는 **환경변수로만** 받는다. 코드·결과 파일·저장소 어디에도 남기지 않는다.

| provider | 환경변수 | 기본 모델 (`--model`로 변경) |
| :-- | :-- | :-- |
| `claude` | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` — 운영과 동일 |
| `gemini` | `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY` | `gemini-2.5-pro` |
| `openai` | `OPENAI_API_KEY` | `gpt-5` |

## 먼저 dry-run — API 키·SDK 없이

```bash
python run_eval.py --dry-run
python run_eval.py --dry-run --input-mode raw
```

provider API를 부르지 않으므로 **키도 SDK도 필요 없고 비용도 들지 않는다.**
돈을 쓰기 전에 이것부터 보라. 확인해 주는 것:

case 로드 성공/실패 · 프롬프트 생성 성공/실패 · fetch_page 3000자 trim 건수 ·
그 밖 도구 1200자 trim 건수 · 프롬프트 길이 분포(min/median/p90/max와 히스토그램) ·
`tool_outputs` 파싱 실패 · 슬롯 복원 문제(핵심 슬롯 누락 · 같은 자리 중복으로 버려짐 ·
모르는 도구 이름). 문제가 하나라도 있으면 종료 코드 1.

case별 프롬프트 **전문**과 진단이 `results/dryrun/{시각}-{모드}.jsonl`에 남으므로,
실제로 모델이 무엇을 받게 되는지 눈으로 확인할 수 있다.

## 실행

```bash
export GEMINI_API_KEY=...
python run_eval.py --provider gemini                       # guardian-trim (서비스와 동일)
python run_eval.py --provider openai --model gpt-5 --sleep 0.5
python run_eval.py --provider claude --resume              # 끊긴 지점부터

python run_eval.py --provider claude --input-mode raw \
    --out-dir results/claude-raw                           # 자르기 영향 실험
python run_eval.py --provider claude --temperature 0 \
    --out-dir results/claude-t0                            # 재현성 실험

python merge_results.py --tag 0829                         # 세 결과 병합
python merge_results.py --tag 0829 --raw                   # 후처리 전(모델 원본) 기준
```

**`--input-mode`나 `--temperature`를 바꿔 돌릴 때는 `--out-dir`을 나눠라.** 같은 폴더에
섞이면 서로 다른 입력으로 잰 결과가 한 병합에 들어간다. 결과 행의 `input_mode` ·
`temperature` · `prompt_sha256`으로 사후 확인도 된다.

## 실제 데이터셋은 저장소에 없다

`dataset/cases.jsonl`(최종 선별 100건)은 저장소에 포함하지 않는다. 페이지 본문에 개인
이메일과 제3자 저작물이 들어 있기 때문이다 — `.gitignore`로 제외돼 있다.
**팀 내부에서 별도로 공유**하며, 받은 파일이 같은 것인지 아래 값으로 확인한다.

| 항목 | 값 |
| :-- | :-- |
| SHA256 | `2e6aea4b491f33c758d7254628c292aee67f2bb5c5b468482bfd8a6d64963392` |
| 줄 수 | 100 |
| 크기 | 711,954 bytes |

```bash
shasum -a 256 dataset/cases.jsonl
```

세 사람이 **같은 파일**로 돌려야 비교가 성립한다. 해시가 다르면 돌리지 말고 먼저 맞춰라.
형식은 `dataset/cases.example.jsonl`(합성 3건)을 참고한다.

판정 결과(`results/*/*.jsonl` · `.csv`)도 같은 이유로 저장소에 두지 않는다 —
프롬프트 전문과 판정 문장이 들어간다.

## 입력 형식

### `dataset/cases.jsonl` — 한 줄 = 한 case

**raw를 그대로 넣는다.** trim된 값이나 완성된 프롬프트를 저장하지 않는다 — 자르기가
판정을 얼마나 바꾸는지 `--input-mode raw`로 바로 비교해 보려면 원본이 있어야 한다.

| 필드 | 필수 | 무엇 |
| :-- | :-: | :-- |
| `case_id` | ✅ | 병합 키. 중복이면 로드 단계에서 중단 |
| `input.url` | ✅ | 광고를 눌러 도착한 주소. 프롬프트 첫 줄에 들어간다 |
| `input.tool_outputs` | ✅ | 판정 당시 도구가 돌려준 **원본**. `[{"tool","args","output"}, …]` |
| `input.click_url` | 선택 | 누른 광고의 링크. `url`과 다를 때만 프롬프트에 줄이 추가된다 |
| `reference` | 선택 | 기존 판정. **정답이 아니라 비교 기준선** |

`output`은 JSON 문자열이어도, 이미 dict로 풀려 있어도 받는다.
`tool_outputs`의 **순서는 상관없다** — 서비스도 스레드 셋에서 동시에 쌓기 때문에 순서가
매번 다르고, 조립기는 (도구 이름, 인자)로 자리를 가른다. 그래서 `domain_age`의
`args.host`와 `official_domain_of`의 `args.brand`는 채워져 있어야 한다.

### 조립 규칙 — `input_mode`

| 모드 | 무엇 | 쓰임 |
| :-- | :-- | :-- |
| `guardian-trim` (기본) | 현재 서비스와 **동일**. fetch 3000자·나머지 1200자 trim + 조건부 지시문 | 서비스 baseline |
| `raw` | 같은 조립, **trim 없음** | 잘린 본문이 판정을 바꾸는지 |
| `stored` | `input.prompt_text`를 그대로 사용 | 판정 당시 프롬프트가 통째로 있을 때 |

조립되는 것: 도착 주소 → (click_url이 다르면) 광고 링크 → `## 미리 모아 둔 것` 섹션
(fetch_page · page_signals · official_domain_of(도착 도메인) · official_domain_of(언급된 브랜드) ·
check_blocklist · lookup_cache · domain_age · domain_age(도착지) 순, 없는 슬롯은
`(시간 안에 못 받음)`) → js_only / 4xx / 공식도메인 확인 여부에 따른 조건부 지시문 →
`이것으로 final_verdict를 내라.`

`lookup_cache`는 **기본으로 뺀다** — 과거 모델의 판정이 새 모델 입력으로 흘러드는 유일한
통로이기 때문이다. 서비스와 byte 단위로 같은지 확인할 때만 `--include-lookup-cache`로 켠다.
프롬프트에서 뺀 도구는 근거 검증(`_ground`)의 대조 원문에서도 빠진다 — 모델에게 보여 주지
않은 문장을 근거로 인정하면 안 되기 때문이다.

### 판정 기준 — `dataset/prompt_spec.json`

GuADian 서버의 `main.py::CRITERIA` + `judge_agent.py::ONESHOT_RULES`,
출력 스키마는 `judge_agent.py::TOOLS[final_verdict].input_schema`.

**한 번 만들고 고정한다.** 세 사람이 각자 다른 시점에 돌리는데 그 사이 기준이 바뀌면
모델 차이가 아니라 기준 차이를 재게 된다. `system_sha256`으로 봉인하고, `run_eval.py`는
실행마다 해시를 재계산해 어긋나면 중단한다.

| 항목 | 값 |
| :-- | :-- |
| `spec_id` | `oneshot-20260828` |
| `system_sha256` | `50dcb7dcef47475353d87837a0a6ab2f42c017b9bf043bd02f032732dec3cc6e` |
| 파일 SHA256 | `af5c136ed645603f52bd08d2ceb6c92bcf328d11b016baceceb9d2c087234033` |

`temperature`는 **지정하지 않는다.** GuADian 서버 어디에도 그 파라미터가 없어 운영은 API
기본값으로 돌기 때문이다 — 임의로 0을 박으면 baseline이 서비스와 다른 설정으로 잰 것이 된다.
표집 난수를 없애고 싶은 실험만 `--temperature 0`으로 그때 덮어쓰고, 그 값은 결과 행에 남는다.

## 결과 형식

**저장은 JSONL 파일뿐이다.** SQLite도, 다른 DB도, 서버도 쓰지 않는다 — 세 사람이 각자
자기 파일만 만들고 마지막에 합치면 되므로 공유 저장소가 필요 없고, 사람이 열어 볼 수 있는
편이 낫다.

| 무엇 | 어디 |
| :-- | :-- |
| provider별 판정 | `results/{provider}/{run_id}.jsonl` — case 한 건당 한 줄, 한 건 끝날 때마다 flush |
| 병합·비교 | `results/merged/compare_{tag}.jsonl` + `.csv` |
| dry-run 진단 | `results/dryrun/{시각}-{모드}.jsonl` |

`{run_id}` = `{UTC 시각}-{provider}-{기준 해시 앞 6자}` — 다시 돌려도 덮어쓰지 않는다.

```json
{"case_id":"case_001","run_id":"20260829T1000Z-gemini-50dcb7",
 "provider":"gemini","model":"gemini-2.5-pro",
 "spec_id":"oneshot-20260828","system_sha256":"50dcb7…",
 "input_mode":"guardian-trim","excluded_tools":["lookup_cache"],"temperature":null,
 "prompt_sha256":"a1b2…","ok":true,
 "verdict_raw":{"risk":"HIGH","type":"impersonation","reason":"…","advice":"…","evidence":"…"},
 "verdict":    {"risk":"MEDIUM","type":"impersonation","reason":"…","advice":"…","evidence":"…"},
 "postprocess":{"fill_type_applied":false,"ground_downgraded":true},
 "latency_ms":1840,"usage":{"input_tokens":5120,"output_tokens":172},
 "attempts":1,"error":null}
```

`verdict_raw`는 모델 원본, `verdict`는 서비스 후처리(`_fill_type` → `_ground`)를 거친 것이다.
"모델 그대로" 비교할지 "서비스에 넣었을 때"로 비교할지 나중에 고를 수 있게 둘 다 남긴다.
`ground_downgraded`가 `null`이면 대조할 `tool_outputs`가 없어 강등 판단을 **보류**한 것이다 —
데이터가 없어서 내려간 것을 근거가 없어서 내려간 것으로 읽지 않게 구분한다.

**실패도 남긴다.** 빼먹으면 스키마를 못 지킨 건이 파일에서 사라지고, 남은 것만으로 계산한
일치율이 공정해 보인다. 세 모델의 스키마 준수 실패율 자체가 비교 항목이다.

## 조립이 서비스와 같은지 검증

```bash
export GUARDIAN_ROOT=~/GuADian23-judge-research
python test_assembly.py
```

세 갈래로 본다. 어느 쪽도 네트워크를 쓰지 않는다.

| 검사 | 정답의 출처 | GuADian 저장소 |
| :-- | :-- | :--: |
| A | 실제 페이지에서 나온 수집본의 `prompt_text` | 필요 |
| B | `server/judge_agent.py::_prefetch` 를 가짜 `run_tool`로 **직접 실행**한 결과 | 필요 |
| C | `input_mode` 동작과 `lookup_cache` 제외 | 불필요 |

`_prefetch`가 `run_tool`을 인자로 받는 함수라서 B가 가능하다 — 정답을 손으로 적지 않고
원본 코드에서 뽑으므로, 서버의 조립이 바뀌면 이 검사가 먼저 깨진다.
`GUARDIAN_ROOT`가 없으면 A·B를 건너뛰고 C만 돈다.

## 파일

| 파일 | 무엇 |
| :-- | :-- |
| `build_prompt.py` | 판정 기준 추출·봉인 확인 · raw tool_outputs → user 프롬프트 조립 |
| `schema.py` | case·result 스키마와 검증 (단일 출처) |
| `postprocess.py` | `_fill_type` · `_ground` 재현 (GuADian 서버 원본의 복사본, 출처 줄번호 주석) |
| `domains.py` | `host_of` · `site_of` · `looks_like_domain` (조립의 슬롯 판별용, 복사본) |
| `providers/base.py` | 공통 계약 · 스키마 변환 3종 · registry |
| `providers/{claude,gemini,openai}.py` | SDK 호출만 |
| `run_eval.py` | provider 하나로 전 case 판정 · `--dry-run` |
| `merge_results.py` | `case_id` 병합 · 일치율 · 쌍별 불일치 |
| `test_assembly.py` | 조립이 서비스와 같은지 검증 |

세 모델은 같은 출력 스키마를 각자 네이티브 방식으로 강제한다. 변환은 `providers/base.py`
한 곳에 모아 각자 다르게 구현하는 사고를 막는다.

| provider | 강제 방식 |
| :-- | :-- |
| claude | `tools=[final_verdict]` + `tool_choice` 강제 (운영과 동일) |
| gemini | `response_schema` + JSON mime type |
| openai | `response_format: json_schema` (strict) |

`postprocess.py` · `domains.py` · `build_prompt.py`의 조립부는 GuADian 서버의 복사·재현이라
원본이 바뀌면 **손으로 맞춰야 한다.** 주석의 출처 줄번호가 대조표이고,
`test_assembly.py`의 B 검사가 어긋남을 자동으로 잡는다.
