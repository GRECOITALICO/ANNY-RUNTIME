"""Real benchmark dataset for ANNY Capability Benchmark System (MISSION-032 Phases 4-5).

RULE: BLIND_TEST cases must never be used for training or adaptation.
"""
from typing import List
from runtime.intelligence.models import BenchmarkCase

DATASET_VERSION = "v1.0.0"

SUMMARIZATION_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        benchmark_id="sum_train_001", capability_id="text.summarization",
        difficulty="easy", dataset_partition="TRAIN", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"text": "The Python programming language was created by Guido van Rossum and first released in 1991. It emphasizes code readability and simplicity. Python supports multiple programming paradigms including procedural, object-oriented, and functional programming."},
        expected_output="Python is a programming language created by Guido van Rossum in 1991, known for code readability and supporting multiple paradigms.",
    ),
    BenchmarkCase(
        benchmark_id="sum_val_001", capability_id="text.summarization",
        difficulty="medium", dataset_partition="VALIDATION", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"text": "Machine learning is a subfield of artificial intelligence that enables systems to learn from data without being explicitly programmed. It includes supervised learning, where models are trained on labeled examples, unsupervised learning, which discovers patterns in unlabeled data, and reinforcement learning, which learns through reward signals."},
        expected_output="Machine learning enables systems to learn from data without explicit programming, encompassing supervised, unsupervised, and reinforcement learning.",
    ),
    BenchmarkCase(
        benchmark_id="sum_blind_001", capability_id="text.summarization",
        difficulty="hard", dataset_partition="BLIND_TEST", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"text": "Distributed computing involves multiple computers working together over a network to solve problems that a single machine cannot handle efficiently. Challenges include network latency, partial failures, data consistency across nodes, and coordination overhead. Systems like Apache Kafka, Hadoop, and Spark have emerged to address these challenges."},
        expected_output="Distributed computing uses multiple networked computers to solve large problems, facing challenges of latency, failures, and consistency, addressed by systems like Kafka, Hadoop, and Spark.",
    ),
]

CLASSIFICATION_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        benchmark_id="cls_train_001", capability_id="text.classification",
        difficulty="easy", dataset_partition="TRAIN", version=DATASET_VERSION,
        grading_method="structured_match",
        input={"text": "This product is absolutely amazing! Best purchase I have ever made.", "labels": ["positive", "negative", "neutral"]},
        expected_output={"label": "positive", "confidence": 0.95},
    ),
    BenchmarkCase(
        benchmark_id="cls_val_001", capability_id="text.classification",
        difficulty="medium", dataset_partition="VALIDATION", version=DATASET_VERSION,
        grading_method="structured_match",
        input={"text": "The delivery was on time but the packaging was damaged.", "labels": ["positive", "negative", "neutral"]},
        expected_output={"label": "neutral", "confidence": 0.70},
    ),
    BenchmarkCase(
        benchmark_id="cls_blind_001", capability_id="text.classification",
        difficulty="hard", dataset_partition="BLIND_TEST", version=DATASET_VERSION,
        grading_method="structured_match",
        input={"text": "While the interface is technically functional, I find myself missing the elegance of the previous version despite acknowledging the new performance gains.", "labels": ["positive", "negative", "neutral"]},
        expected_output={"label": "neutral", "confidence": 0.60},
    ),
]

EXTRACTION_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        benchmark_id="ext_train_001", capability_id="data.extraction",
        difficulty="easy", dataset_partition="TRAIN", version=DATASET_VERSION,
        grading_method="structured_match",
        input={"text": "Contact John Smith at john.smith@example.com or call +1-555-0123.", "fields": ["name", "email", "phone"]},
        expected_output={"name": "John Smith", "email": "john.smith@example.com", "phone": "+1-555-0123"},
    ),
    BenchmarkCase(
        benchmark_id="ext_val_001", capability_id="data.extraction",
        difficulty="medium", dataset_partition="VALIDATION", version=DATASET_VERSION,
        grading_method="structured_match",
        input={"text": "The meeting is scheduled for Thursday, October 15, 2026 at 3:30 PM EST in Conference Room B.", "fields": ["date", "time", "timezone", "location"]},
        expected_output={"date": "October 15, 2026", "time": "3:30 PM", "timezone": "EST", "location": "Conference Room B"},
    ),
    BenchmarkCase(
        benchmark_id="ext_blind_001", capability_id="data.extraction",
        difficulty="hard", dataset_partition="BLIND_TEST", version=DATASET_VERSION,
        grading_method="structured_match",
        input={"text": "Invoice #INV-2026-004421 issued by Acme Corp (VAT: GB123456789) to Beta Ltd. Total: EUR 14,500.00 net, EUR 17,400.00 incl. VAT (20%).", "fields": ["invoice_number", "issuer", "vat_number", "recipient", "total_net", "total_gross", "vat_rate"]},
        expected_output={"invoice_number": "INV-2026-004421", "issuer": "Acme Corp", "vat_number": "GB123456789", "recipient": "Beta Ltd", "total_net": "EUR 14,500.00", "total_gross": "EUR 17,400.00", "vat_rate": "20%"},
    ),
]

ANALYSIS_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        benchmark_id="ana_train_001", capability_id="data.analysis",
        difficulty="easy", dataset_partition="TRAIN", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"data": {"sales": [100, 150, 130, 170, 200]}, "question": "What is the overall trend?"},
        expected_output="Sales show a consistent upward trend over 5 periods with a generally increasing trajectory.",
    ),
    BenchmarkCase(
        benchmark_id="ana_val_001", capability_id="data.analysis",
        difficulty="medium", dataset_partition="VALIDATION", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"data": {"response_times_ms": [45, 52, 48, 210, 47, 51, 49, 890, 46]}, "question": "Identify outliers and assess system health."},
        expected_output="Two significant outliers detected at 210ms and 890ms. System is mostly healthy with occasional spikes.",
    ),
    BenchmarkCase(
        benchmark_id="ana_blind_001", capability_id="data.analysis",
        difficulty="hard", dataset_partition="BLIND_TEST", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"data": {"conversions": {"control": {"visitors": 10000, "conversions": 520}, "variant": {"visitors": 9800, "conversions": 588}}}, "question": "Evaluate A/B test and recommend action."},
        expected_output="Control rate 5.2%, variant rate 6.0%, lift 15.4%. Variant shows meaningful improvement; recommend deploying with monitoring.",
    ),
]

REWRITING_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        benchmark_id="rew_train_001", capability_id="text.rewriting",
        difficulty="easy", dataset_partition="TRAIN", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"text": "The utilization of the aforementioned methodological framework necessitates comprehensive pre-implementation evaluation.", "target_style": "plain"},
        expected_output="Using this method requires a thorough evaluation before implementation.",
    ),
    BenchmarkCase(
        benchmark_id="rew_val_001", capability_id="text.rewriting",
        difficulty="medium", dataset_partition="VALIDATION", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"text": "Our Q3 revenue declined 8% YoY.", "target_style": "executive_summary"},
        expected_output="Third-quarter revenue fell 8% compared to the same period last year, requiring strategic review.",
    ),
    BenchmarkCase(
        benchmark_id="rew_blind_001", capability_id="text.rewriting",
        difficulty="hard", dataset_partition="BLIND_TEST", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"text": "sys.exit() terminates the Python interpreter.", "target_style": "user_documentation"},
        expected_output="The sys.exit() function stops your Python program immediately. Use it when you need to end execution at a specific point, such as after detecting a critical error.",
    ),
]

CODE_UNDERSTANDING_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        benchmark_id="cund_train_001", capability_id="code.understanding",
        difficulty="easy", dataset_partition="TRAIN", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"code": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)", "question": "What does this function do?"},
        expected_output="Computes the factorial of n using recursion. Base case returns 1 when n is 1 or less.",
    ),
    BenchmarkCase(
        benchmark_id="cund_val_001", capability_id="code.understanding",
        difficulty="medium", dataset_partition="VALIDATION", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"code": "result = {k: v for k, v in data.items() if v is not None and k not in excluded}", "question": "Explain the expression."},
        expected_output="A dict comprehension that filters data keeping only entries where the value is not None and the key is not in the excluded set.",
    ),
    BenchmarkCase(
        benchmark_id="cund_blind_001", capability_id="code.understanding",
        difficulty="hard", dataset_partition="BLIND_TEST", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"code": "def memoize(fn):\n    cache = {}\n    def wrapper(*args):\n        if args not in cache:\n            cache[args] = fn(*args)\n        return cache[args]\n    return wrapper", "question": "Explain what this decorator does and identify limitations."},
        expected_output="A memoization decorator that caches function results by argument tuple. Limitations: only works with hashable arguments and has unbounded cache growth.",
    ),
]

CODE_GENERATION_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        benchmark_id="cgen_train_001", capability_id="code.generation",
        difficulty="easy", dataset_partition="TRAIN", version=DATASET_VERSION,
        grading_method="task_success",
        input={"task": "Write a Python function that returns the sum of all even numbers in a list."},
        expected_output={"code": "def sum_even(lst):\n    return sum(x for x in lst if x % 2 == 0)"},
    ),
    BenchmarkCase(
        benchmark_id="cgen_val_001", capability_id="code.generation",
        difficulty="medium", dataset_partition="VALIDATION", version=DATASET_VERSION,
        grading_method="task_success",
        input={"task": "Write a Python context manager that measures and prints execution time of a code block."},
        expected_output={"code": "import time\nfrom contextlib import contextmanager\n\n@contextmanager\ndef timer(label='block'):\n    start = time.perf_counter()\n    yield\n    elapsed = time.perf_counter() - start\n    print(f'{label}: {elapsed:.4f}s')"},
    ),
    BenchmarkCase(
        benchmark_id="cgen_blind_001", capability_id="code.generation",
        difficulty="hard", dataset_partition="BLIND_TEST", version=DATASET_VERSION,
        grading_method="task_success",
        input={"task": "Write a thread-safe singleton implementation in Python using a metaclass."},
        expected_output={"code": "import threading\n\nclass SingletonMeta(type):\n    _instances = {}\n    _lock = threading.Lock()\n\n    def __call__(cls, *args, **kwargs):\n        with cls._lock:\n            if cls not in cls._instances:\n                cls._instances[cls] = super().__call__(*args, **kwargs)\n        return cls._instances[cls]"},
    ),
]

BUG_DIAGNOSIS_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        benchmark_id="bug_train_001", capability_id="bug.diagnosis",
        difficulty="easy", dataset_partition="TRAIN", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"code": "def divide(a, b):\n    return a / b\n\nresult = divide(10, 0)", "error": "ZeroDivisionError: division by zero"},
        expected_output="Root cause: division by zero because b is 0. Fix: add a guard checking if b is zero before dividing.",
    ),
    BenchmarkCase(
        benchmark_id="bug_val_001", capability_id="bug.diagnosis",
        difficulty="medium", dataset_partition="VALIDATION", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"code": "items = [1, 2, 3]\nfor i in range(len(items)):\n    items.append(i * 10)", "symptom": "Program never terminates"},
        expected_output="Root cause: mutating the list while iterating it causes the loop to run indefinitely. Fix: iterate over a copy of the original list.",
    ),
    BenchmarkCase(
        benchmark_id="bug_blind_001", capability_id="bug.diagnosis",
        difficulty="hard", dataset_partition="BLIND_TEST", version=DATASET_VERSION,
        grading_method="semantic_grading",
        input={"code": "import threading\nshared = []\ndef worker():\n    local = shared\n    local.append(threading.current_thread().name)\nthreads = [threading.Thread(target=worker) for _ in range(10)]\n[t.start() for t in threads]\n[t.join() for t in threads]\nprint(len(shared))", "symptom": "Output is sometimes less than 10"},
        expected_output="Race condition: list.append is not guaranteed atomic under all GIL conditions. Multiple threads may interleave during list resize. Fix: use threading.Lock() around append.",
    ),
]

TOOL_USE_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        benchmark_id="tool_train_001", capability_id="tool.use",
        difficulty="easy", dataset_partition="TRAIN", version=DATASET_VERSION,
        grading_method="task_success",
        input={"task": "Read the contents of /etc/hostname and report the hostname.", "available_tools": ["filesystem.read"]},
        expected_output={"tool_calls": [{"tool": "filesystem.read", "args": {"path": "/etc/hostname"}}]},
    ),
    BenchmarkCase(
        benchmark_id="tool_val_001", capability_id="tool.use",
        difficulty="medium", dataset_partition="VALIDATION", version=DATASET_VERSION,
        grading_method="task_success",
        input={"task": "Search for Python files containing 'deprecated' in /opt/anny-runtime/runtime/.", "available_tools": ["search.query"]},
        expected_output={"tool_calls": [{"tool": "search.query", "args": {"path": "/opt/anny-runtime/runtime/", "pattern": "deprecated", "file_type": "py"}}]},
    ),
    BenchmarkCase(
        benchmark_id="tool_blind_001", capability_id="tool.use",
        difficulty="hard", dataset_partition="BLIND_TEST", version=DATASET_VERSION,
        grading_method="task_success",
        input={"task": "Find commits in last 30 days modifying runtime/intelligence/ and show diff of the most recent.", "available_tools": ["git.log", "git.diff"]},
        expected_output={"tool_calls": [{"tool": "git.log", "args": {"since": "30 days ago", "path": "runtime/intelligence/"}}, {"tool": "git.diff", "args": {"commit": "HEAD", "path": "runtime/intelligence/"}}]},
    ),
]

INITIAL_BATTERY: List[BenchmarkCase] = (
    SUMMARIZATION_CASES + CLASSIFICATION_CASES + EXTRACTION_CASES +
    ANALYSIS_CASES + REWRITING_CASES + CODE_UNDERSTANDING_CASES +
    CODE_GENERATION_CASES + BUG_DIAGNOSIS_CASES + TOOL_USE_CASES
)

def get_partition(partition: str) -> List[BenchmarkCase]:
    assert partition in ("TRAIN", "VALIDATION", "BLIND_TEST")
    return [c for c in INITIAL_BATTERY if c.dataset_partition == partition]

def get_by_capability(capability_id: str) -> List[BenchmarkCase]:
    return [c for c in INITIAL_BATTERY if c.capability_id == capability_id]

def get_blind_test_cases() -> List[BenchmarkCase]:
    return get_partition("BLIND_TEST")
