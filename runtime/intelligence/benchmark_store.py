"""BenchmarkStore: persistent scorecard storage (MISSION-032 Phase 7)."""
import json
import logging
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional

from runtime.intelligence.models import BenchmarkScorecard, CertificationStatus

logger = logging.getLogger(__name__)
DEFAULT_STORE_DIR = os.path.expanduser("~/.anny/intelligence/scorecards")


class BenchmarkStore:
    """Thread-safe JSON file store for BenchmarkScorecards."""

    def __init__(self, store_dir: str = DEFAULT_STORE_DIR):
        self.store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)
        self._lock = threading.Lock()

    def save_scorecard(self, scorecard: BenchmarkScorecard) -> str:
        filename = self._filename(scorecard.scorecard_id)
        data = self._to_dict(scorecard)
        with self._lock:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        logger.info(f"Saved scorecard {scorecard.scorecard_id}")
        return filename

    def mark_stale(self, capability_id: str, implementation_id: str, reason: str = "") -> int:
        count = 0
        for sc in self.list_scorecards():
            if sc.capability_id == capability_id and sc.implementation_id == implementation_id:
                sc.certification_status = CertificationStatus.STALE
                self.save_scorecard(sc)
                count += 1
        if count:
            logger.warning(f"Marked {count} scorecards STALE for {capability_id}/{implementation_id}: {reason}")
        return count

    def revoke(self, capability_id: str, implementation_id: str) -> int:
        count = 0
        for sc in self.list_scorecards():
            if sc.capability_id == capability_id and sc.implementation_id == implementation_id:
                sc.certification_status = CertificationStatus.REVOKED
                self.save_scorecard(sc)
                count += 1
        if count:
            logger.warning(f"Revoked {count} scorecards for {capability_id}/{implementation_id}")
        return count

    def load_scorecard(self, scorecard_id: str) -> Optional[BenchmarkScorecard]:
        filename = self._filename(scorecard_id)
        if not os.path.exists(filename):
            return None
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return self._from_dict(json.load(f))
        except Exception as e:
            logger.error(f"Failed to load scorecard {scorecard_id}: {e}")
            return None

    def list_scorecards(self) -> List[BenchmarkScorecard]:
        results = []
        with self._lock:
            for fname in os.listdir(self.store_dir):
                if not fname.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(self.store_dir, fname), "r", encoding="utf-8") as f:
                        results.append(self._from_dict(json.load(f)))
                except Exception as e:
                    logger.warning(f"Skipping corrupt scorecard {fname}: {e}")
        return results

    def best_scorecard(self, capability_id: str) -> Optional[BenchmarkScorecard]:
        candidates = [
            sc for sc in self.list_scorecards()
            if sc.capability_id == capability_id
            and sc.certification_status == CertificationStatus.CERTIFIED
        ]
        return max(candidates, key=lambda sc: sc.score) if candidates else None

    def summary(self) -> List[Dict]:
        return sorted([{
            "capability_id": sc.capability_id,
            "implementation_id": sc.implementation_id,
            "score": sc.score,
            "confidence": sc.confidence,
            "latency_p50": sc.latency_p50,
            "latency_p95": sc.latency_p95,
            "certification_status": sc.certification_status.value,
            "created_at": str(sc.created_at) if sc.created_at else None,
        } for sc in self.list_scorecards()], key=lambda x: x["capability_id"])

    def _filename(self, scorecard_id: str) -> str:
        safe = scorecard_id.replace("/", "_").replace(".", "_")
        return os.path.join(self.store_dir, f"{safe}.json")

    def _to_dict(self, sc: BenchmarkScorecard) -> Dict:
        return {
            "scorecard_id": sc.scorecard_id, "capability_id": sc.capability_id,
            "implementation_id": sc.implementation_id,
            "implementation_revision": sc.implementation_revision,
            "benchmark_version": sc.benchmark_version, "dataset_version": sc.dataset_version,
            "score": sc.score, "confidence": sc.confidence,
            "latency_p50": sc.latency_p50, "latency_p95": sc.latency_p95,
            "latency_p99": sc.latency_p99, "resource_usage": sc.resource_usage,
            "certification_status": sc.certification_status.value,
            "hardware_profile": sc.hardware_profile, "adapter_revision": sc.adapter_revision,
            "created_at": str(sc.created_at) if sc.created_at else None,
        }

    def _from_dict(self, d: Dict) -> BenchmarkScorecard:
        created_at = None
        if d.get("created_at"):
            try:
                created_at = datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))
            except Exception:
                pass
        return BenchmarkScorecard(
            scorecard_id=d["scorecard_id"], capability_id=d["capability_id"],
            implementation_id=d["implementation_id"],
            implementation_revision=d["implementation_revision"],
            benchmark_version=d["benchmark_version"], dataset_version=d["dataset_version"],
            score=float(d["score"]), confidence=float(d["confidence"]),
            latency_p50=float(d["latency_p50"]), latency_p95=float(d["latency_p95"]),
            latency_p99=float(d.get("latency_p99", 0.0)),
            resource_usage=d.get("resource_usage", {}),
            certification_status=CertificationStatus(d["certification_status"]),
            hardware_profile=d.get("hardware_profile"), adapter_revision=d.get("adapter_revision"),
            created_at=created_at,
        )
