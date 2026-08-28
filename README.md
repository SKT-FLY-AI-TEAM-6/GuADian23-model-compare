# GuADian23-model-compare

같은 입력·같은 판정 기준으로 Claude / Gemini / OpenAI를 비교하는 독립 실험 저장소.
이후 fine-tuned classifier도 같은 자리에 끼워 비교한다.

## 저장소 구분

| 저장소 | 하는 일 |
| :-- | :-- |
| **GuADian23-judge-research** | 실제 GuADian 판정 로직. 판정하며 `tool_outputs` · `prompt_text` · `page_text` 등 판정 원본을 **수집**한다 |
| **GuADian23-model-compare** (이 저장소) | 수집된 **고정 입력**으로 여러 모델을 **비교**한다 |

수집과 비교를 분리한 이유는, 비교 단계가 페이지를 다시 열지도 광고를 다시 누르지도 않기
때문이다. 저장된 snapshot만 읽으므로 몇 번을 돌려도 같은 입력이고, 서버 코드와 무관하게
굴러간다. 이 저장소는 GuADian 원본 저장소 없이 단독으로 실행된다.

파이프라인은 다음 PR에서 추가된다.
