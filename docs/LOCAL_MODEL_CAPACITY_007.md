# Local Model Capacity 007

## Method

The explicit read-only inventory is available through:

```bash
PYTHONPATH=. python cli/main.py local-planner-capacity
```

It reads operating-system CPU, memory and filesystem counters; checks already
installed runtime executables with bounded version commands; examines only
fixed local cache locations; and probes GPU utilities only if they already
exist. It does not start containers or services, load a model, query a model
provider, download content, read environment variables, or persist absolute
paths. The durable sanitized report is written to
`native-executions/planning/local-model-capacity.json` in the Runtime data
directory.

## Measured capacity on this machine

The 2026-10-27 explicit inventory observed:

- x86_64 Intel Core i7-6820HQ with 8 logical CPUs;
- 25.1 GB RAM total, 16.4 GB available at collection, and 16.4 GB free swap;
- 83.3 GB free on the filesystem containing the workspace and model cache;
- Intel HD Graphics 530 observed by PCI inspection, but no NVIDIA/ROCm tooling
  or accessible compute accelerator; inference should therefore be planned as
  CPU-bound;
- Podman 5.4.2 rootless with seccomp enabled;
- Ollama client 0.32.5 installed but no running loopback service;
- no Ollama, llama.cpp or LM Studio cache; and a 491 MB Hugging Face cache for
  `Qwen/Qwen2.5-0.5B-Instruct-GGUF`.

The cached GGUF is an artifact observation only. It was not loaded, validated
as complete, or used for inference. Consequently the planner remains
`LOCAL_RUNTIME_WITHOUT_MODEL`, never `LOCAL_MODEL_READY`.

## Candidate options (estimates, not execution results)

| Candidate | Published artifact size | Fit assessment | Use for Runtime planning |
| --- | ---: | --- | --- |
| Qwen2.5-Coder 1.5B | 986 MB | Comfortably fits disk/RAM; CPU-only latency expected | Lowest-risk code/JSON-plan experiment |
| Qwen2.5-Coder 3B | 1.9 GB | Fits disk/RAM; CPU-only latency and long contexts require conservative timeouts | Better candidate for simple code changes after evaluation |
| Qwen2.5-Coder 7B | 4.7 GB | Fits measured free RAM/disk in principle, but likely slow CPU inference and context KV-cache growth | Evaluate only after smaller model proves the planner contract |
| Llama 3.2 1B/3B | 1B / 3B parameter family | Fits host memory class; general instruction following rather than code-specialist positioning | Alternative for structured planning evaluation |

Ollama lists the cited Qwen2.5-Coder artifacts and their 32K context windows;
it describes the series as code-specific. The same official catalog lists
Llama 3.2 as 1B and 3B instruction-tuned text models, positioned for tasks
such as instruction following and tool use. These sizes are artifact sizes,
not a promise of runtime RAM, throughput, or plan quality: CPU inference and
KV cache consume additional memory and this machine has no verified inference
accelerator. Quantization reduces artifact/model-memory pressure at a possible
quality and accuracy cost; selection must be tested with the actual plan
validation corpus before enabling any capability.

Sources: [Ollama Qwen2.5-Coder catalog](https://ollama.com/library/qwen2.5-coder),
[Ollama Qwen2.5-Coder tags](https://ollama.com/library/qwen2.5-coder/tags),
and [Ollama Llama 3.2 catalog](https://ollama.com/library/llama3.2).

## Next action

A separate authorized task must select a local model and explicitly permit its
download or use, then start only the local provider, run the bounded inference
probe, and evaluate JSON-plan validity. Until then, no cache observation or
capacity metric authorizes `local-plan` to execute work.
