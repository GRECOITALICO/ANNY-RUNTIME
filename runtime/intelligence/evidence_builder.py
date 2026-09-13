"""EvidenceBuilder for ANNY Capability Benchmark System (MISSION-032).

Phases 32, 39, 40: Compiles all certified benchmarks and taxonomy into 
tamper-evident JSON evidence files, and computes SHA256SUMS.
"""
import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any

from runtime.intelligence.taxonomy import ALL_CAPABILITIES, CAPABILITY_FAMILIES
from runtime.intelligence.models import CertificationStatus
from runtime.intelligence.benchmark_store import BenchmarkStore

def _compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

class EvidenceBuilder:
    """Builds cryptographic evidence of capability certification."""

    def __init__(self, output_dir: str = "/home/anny/anny-runtime-certification"):
        self.output_dir = output_dir
        self.store = BenchmarkStore()
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_all(self) -> Dict[str, Any]:
        """Generate all evidence files and SHA256SUMS."""
        manifest = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "capabilities_certified": 0,
            "capabilities_failed": 0,
            "evidence_files": []
        }
        
        # 1. Export taxonomy map
        tax_path = os.path.join(self.output_dir, "taxonomy.json")
        with open(tax_path, "w", encoding="utf-8") as f:
            json.dump({
                "families": CAPABILITY_FAMILIES,
                "all_capabilities": sorted(list(ALL_CAPABILITIES))
            }, f, indent=2)
        manifest["evidence_files"].append(tax_path)
        
        # 2. Export each certified capability
        scorecards = self.store.list_scorecards()
        for cap_id in ALL_CAPABILITIES:
            # Find best certified scorecard for this capability
            best = self.store.best_scorecard(cap_id)
            if not best:
                manifest["capabilities_failed"] += 1
                continue
                
            manifest["capabilities_certified"] += 1
            safe_id = cap_id.replace(".", "_")
            out_path = os.path.join(self.output_dir, f"cert_{safe_id}.json")
            
            # Re-serialize for evidence
            data = {
                "capability_id": best.capability_id,
                "implementation_id": best.implementation_id,
                "score": best.score,
                "confidence": best.confidence,
                "latency_p50": best.latency_p50,
                "dataset_version": best.dataset_version,
                "certified_at": best.created_at.isoformat() if best.created_at else None,
                "hardware": best.hardware_profile
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            manifest["evidence_files"].append(out_path)
            
        # 3. Generate SHA256SUMS
        sums_path = os.path.join(self.output_dir, "SHA256SUMS")
        with open(sums_path, "w", encoding="utf-8") as f:
            for filepath in manifest["evidence_files"]:
                filename = os.path.basename(filepath)
                h = _compute_sha256(filepath)
                f.write(f"{h}  {filename}\n")
                
        # 4. Write manifest
        man_path = os.path.join(self.output_dir, "manifest.json")
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            
        return manifest

if __name__ == "__main__":
    builder = EvidenceBuilder()
    res = builder.generate_all()
    print(f"Generated evidence for {res['capabilities_certified']} capabilities.")
