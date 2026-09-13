import re
import json
import math
import difflib
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class GradingResult:
    score: float
    confidence: float
    grading_method: str
    details: Dict[str, Any]
    passed: bool


class GradingEngine:
    """Grades inference outputs for capability benchmarks (MISSION-032 Phase 6)."""

    PASSING_THRESHOLD = 0.5

    def grade(self, method: str, output: Any, expected: Any, details: Optional[Dict] = None) -> GradingResult:
        handlers = {
            "exact_match": self.exact_match,
            "structured_match": self.structured_match,
            "semantic_grading": self.semantic_grading,
            "reference_comparison": self.reference_comparison,
            "task_success": self.task_success,
            "human_adjudication": self.human_adjudication,
        }
        handler = handlers.get(method)
        if not handler:
            raise ValueError(f"Unknown grading method: {method}")
        return handler(output, expected, **(details or {}))

    def exact_match(self, output: Any, expected: Any, **kwargs) -> GradingResult:
        norm_out = self._normalize_str(str(output))
        norm_exp = self._normalize_str(str(expected))
        match = norm_out == norm_exp
        return GradingResult(
            score=1.0 if match else 0.0, confidence=1.0,
            grading_method="exact_match",
            details={"normalized_output": norm_out, "normalized_expected": norm_exp},
            passed=match
        )

    def structured_match(self, output: Any, expected: Any, tolerance: float = 0.0, **kwargs) -> GradingResult:
        try:
            out_dict = json.loads(output) if isinstance(output, str) else output
            exp_dict = json.loads(expected) if isinstance(expected, str) else expected
        except (json.JSONDecodeError, TypeError) as e:
            return GradingResult(score=0.0, confidence=0.9, grading_method="structured_match",
                                 details={"error": f"JSON parse failed: {e}"}, passed=False)
        matched, total, mismatches = 0, 0, []
        for key, exp_val in exp_dict.items():
            total += 1
            out_val = out_dict.get(key)
            if self._values_match(out_val, exp_val, tolerance):
                matched += 1
            else:
                mismatches.append({"key": key, "expected": exp_val, "got": out_val})
        score = matched / total if total > 0 else 0.0
        return GradingResult(score=score, confidence=0.95 if total > 0 else 0.5,
                             grading_method="structured_match",
                             details={"matched": matched, "total": total, "mismatches": mismatches},
                             passed=score >= self.PASSING_THRESHOLD)

    def semantic_grading(self, output: Any, expected: Any, **kwargs) -> GradingResult:
        out_tokens = set(self._tokenize(str(output)))
        exp_tokens = set(self._tokenize(str(expected)))
        if not exp_tokens:
            return GradingResult(score=0.0, confidence=0.5, grading_method="semantic_grading",
                                 details={"reason": "empty_expected"}, passed=False)
        intersection = out_tokens & exp_tokens
        union = out_tokens | exp_tokens
        jaccard = len(intersection) / len(union) if union else 0.0
        recall = len(intersection) / len(exp_tokens) if exp_tokens else 0.0
        score = 0.6 * jaccard + 0.4 * recall
        confidence = min(0.95, 0.5 + 0.05 * len(exp_tokens))
        return GradingResult(score=round(score, 4), confidence=round(confidence, 4),
                             grading_method="semantic_grading",
                             details={"jaccard": round(jaccard, 4), "recall": round(recall, 4),
                                      "out_tokens": len(out_tokens), "exp_tokens": len(exp_tokens)},
                             passed=score >= self.PASSING_THRESHOLD)

    def reference_comparison(self, output: Any, expected: Any, **kwargs) -> GradingResult:
        out_lines = str(output).splitlines(keepends=True)
        exp_lines = str(expected).splitlines(keepends=True)
        ratio = difflib.SequenceMatcher(None, exp_lines, out_lines).ratio()
        return GradingResult(score=round(ratio, 4), confidence=0.85, grading_method="reference_comparison",
                             details={"similarity_ratio": round(ratio, 4)}, passed=ratio >= self.PASSING_THRESHOLD)

    def task_success(self, output: Any, expected: Any, required_keys: Optional[List[str]] = None, **kwargs) -> GradingResult:
        try:
            out_dict = json.loads(output) if isinstance(output, str) else output
            if not isinstance(out_dict, dict):
                raise ValueError("Output is not a dict")
        except Exception as e:
            return GradingResult(score=0.0, confidence=0.95, grading_method="task_success",
                                 details={"error": str(e)}, passed=False)
        keys = required_keys or (list(expected.keys()) if isinstance(expected, dict) else [])
        missing = [k for k in keys if k not in out_dict]
        passed = len(missing) == 0
        score = 1.0 if passed else ((len(keys) - len(missing)) / len(keys) if keys else 0.0)
        return GradingResult(score=round(score, 4), confidence=0.95, grading_method="task_success",
                             details={"required_keys": keys, "missing_keys": missing}, passed=passed)

    def human_adjudication(self, output: Any, expected: Any, **kwargs) -> GradingResult:
        return GradingResult(score=0.5, confidence=0.0, grading_method="human_adjudication",
                             details={"status": "PENDING_HUMAN_REVIEW", "output_preview": str(output)[:200]},
                             passed=False)

    def _normalize_str(self, s: str) -> str:
        return re.sub(r'\s+', ' ', s.strip().lower())

    def _tokenize(self, s: str) -> List[str]:
        s = re.sub(r'[^\w\s]', '', s.lower())
        stopwords = {'the', 'a', 'an', 'is', 'in', 'of', 'to', 'and', 'or', 'for', 'it', 'this', 'that', 'with', 'as', 'be', 'are', 'was', 'were', 'by', 'at', 'from', 'on'}
        return [t for t in s.split() if len(t) > 1 and t not in stopwords]

    def _values_match(self, a: Any, b: Any, tolerance: float) -> bool:
        if a is None:
            return False
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            return abs(float(a) - float(b)) <= tolerance + abs(float(b)) * 0.01
        return str(a).strip().lower() == str(b).strip().lower()
