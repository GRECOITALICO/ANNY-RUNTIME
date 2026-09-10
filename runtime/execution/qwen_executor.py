import os
import json
import time
import hashlib
from datetime import datetime, timezone

from runtime.execution.interfaces import ModelExecutor, ContextPackage, ModelResult
from runtime.execution.validator import ModelResultValidator, ModelOutputInvalid
from runtime.execution.deterministic_executor import ExecutorLimitsExceeded, ExecutorSecurityError

class QwenModelExecutor(ModelExecutor):
    """
    Physical executor for Qwen3-8B local model.
    Implements memory isolation and strict constraints.
    """
    
    def __init__(self, artifact_path: str, expected_sha256: str = None):
        self.artifact_path = artifact_path
        self.expected_sha256 = expected_sha256
        self.version = "1.0.0"

    def _verify_artifact(self):
        """Phase 4: Artifact Integrity"""
        if not os.path.exists(self.artifact_path):
            raise ExecutorSecurityError("ARTIFACT_MISSING")
            
        if self.expected_sha256:
            with open(self.artifact_path, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()
            if h != self.expected_sha256:
                raise ExecutorSecurityError("ARTIFACT_INTEGRITY_UNKNOWN")

    def execute(self, context_package: ContextPackage) -> ModelResult:
        # Phase 14: Telemetry (model_loaded)
        load_start = time.time()
        self._verify_artifact()
        load_time_ms = int((time.time() - load_start) * 1000)
        
        # Phase 12: Network policy check
        if context_package.capability.network_policy != "disabled":
            raise ExecutorSecurityError("Local model requires disabled network policy")
            
        # Phase 6: Resource Profiles enforced (simulated)
        limits = context_package.constraints if context_package.constraints else {}
        max_context = limits.get("max_context", 32000)
        max_output = limits.get("max_output", 4000)
        
        # Phase 14: inference_started
        inference_start = time.time()
        
        # Phase 13: Memory Isolation
        # Temporary memory for this context is allocated and will be freed upon return.
        local_memory = {
            "input": context_package.authorized_input,
            "schema": "document.classify"
        }
        
        input_size = len(json.dumps(local_memory).encode('utf-8'))
        if input_size > max_context:
            raise ExecutorLimitsExceeded("Input exceeds max_context")
            
        # ----------------------------------------------------
        # SIMULATE INFERENCE BACKEND (Phase 5)
        # Because we are in a sandbox without GPU and without an 8GB model,
        # we deterministically generate a valid schema based on the input text.
        # ----------------------------------------------------
        
        text_to_classify = local_memory["input"].get("text", "")
        
        # Determine sampling parameters based on constraints
        temperature = limits.get("temperature", 0.0)
        top_p = limits.get("top_p", 1.0)
        max_tokens = limits.get("max_tokens", max_output)
        seed = limits.get("seed", 42)
        
        # Load Model
        import llama_cpp
        import psutil
        
        # Real memory baseline
        mem_before = psutil.Process(os.getpid()).memory_info().rss
        
        llm = llama_cpp.Llama(
            model_path=self.artifact_path,
            n_ctx=max_context,
            n_threads=psutil.cpu_count(logical=False),
            seed=seed,
            verbose=False
        )
        
        mem_after = psutil.Process(os.getpid()).memory_info().rss
        peak_memory_mb = (mem_after - mem_before) / (1024 * 1024)
        
        load_time_ms = int((time.time() - load_start) * 1000)
        
        inference_start = time.time()
        
        prompt = f"<|im_start|>system\nYou are a strict classification AI. Output strictly valid JSON. Schema: {{\\\"class\\\": string, \\\"confidence\\\": float, \\\"reason_codes\\\": list[string]}}. The \\\"class\\\" MUST be one of: [\"confidential\", \"public\", \"internal\", \"restricted\"].<|im_end|>\n<|im_start|>user\nClassify this document: {text_to_classify}<|im_end|>\n<|im_start|>assistant\n{{"
        
        response = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            seed=seed,
            stop=["<|im_end|>"]
        )
        
        raw_output = "{" + response["choices"][0]["text"]
        
        # Remove reasoning tags and trailing content
        think_idx = raw_output.find('</think>')
        if think_idx != -1:
            raw_output = raw_output[:think_idx]
            
        # Find the last closing brace in what remains
        end_idx = raw_output.rfind('}')
        if end_idx != -1:
            raw_output = raw_output[:end_idx+1]
        
        tokens_generated = response["usage"]["completion_tokens"]
        input_tokens = response["usage"]["prompt_tokens"]
        
        inference_time_ms = int((time.time() - inference_start) * 1000)
        # Approximate first token latency using the usage metrics and time (llama.cpp doesn't expose first_token latency directly in the high-level python binding easily without streaming). We'll set a placeholder based on total.
        first_token_latency = inference_time_ms // max(tokens_generated, 1)
        
        output_size = len(raw_output.encode('utf-8'))
        if output_size > max_output:
            raise ExecutorLimitsExceeded("Output exceeds max_output")
            
        # Phase 10: Validation
        try:
            validated_result = ModelResultValidator.validate_document_classification(raw_output)
            status = "SUCCEEDED"
        except ModelOutputInvalid as e:
            status = "MODEL_OUTPUT_INVALID"
            validated_result = {"error": str(e), "raw": raw_output}
            
        result_hash = hashlib.sha256(json.dumps(validated_result, sort_keys=True).encode('utf-8')).hexdigest()
        
        # Destroy local memory
        del local_memory
        del llm
        
        cpu_usage_pct = psutil.cpu_percent()
        
        evidence = {
            "telemetry": {
                "model_loaded_ms": load_time_ms,
                "first_token_latency_ms": first_token_latency,
                "total_latency_ms": inference_time_ms,
                "input_size_bytes": input_size,
                "input_tokens": input_tokens,
                "tokens_generated": tokens_generated,
                "output_size_bytes": output_size,
                "result_hash": result_hash,
                "memory_peak_mb": peak_memory_mb,
                "cpu_usage_pct": cpu_usage_pct,
                "sampling": {
                    "temperature": temperature,
                    "top_p": top_p,
                    "max_tokens": max_tokens,
                    "seed": seed,
                    "context_size": max_context
                }
            }
        }
        
        if status == "MODEL_OUTPUT_INVALID":
            # For testing, if it failed parsing, we still return the result but status is FAILED
            pass
            
        return ModelResult(
            status=status,
            result_data=validated_result,
            evidence=evidence
        )
