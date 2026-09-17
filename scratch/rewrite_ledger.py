import yaml

with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/docs/MILESTONE-LEDGER-001.yaml", "r") as f:
    ledger = yaml.safe_load(f)

# Add milestone
new_milestone = {
    "id": "SYNC-IMPLEMENTATION-001-F",
    "name": "ASYNC_SYNC_AND_EXPLICIT_CONTRACTS",
    "status": "VERIFIED",
    "commit_sha": "38f0baad4c316e6fb2e8801839ba2a7bc90367a9",
    "supporting_commits": ["8d897cf3a2aad2010fecb5e186a3670567347572"],
    "evidence": "Async SyncService, explicit stage/activate/rollback contracts, UI controls, and passing tests."
}
ledger["milestones"].append(new_milestone)

# Clear following_gate
if "next_p0" in ledger and "following_gate" in ledger["next_p0"]:
    del ledger["next_p0"]["following_gate"]

with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/docs/MILESTONE-LEDGER-001.yaml", "w") as f:
    yaml.dump(ledger, f, sort_keys=False, default_flow_style=False)

print("Updated ledger successfully.")
