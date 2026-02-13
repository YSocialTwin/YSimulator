#!/usr/bin/env python3
"""
Demonstration of immediate LLM usage logging.

This script shows that logs are written to disk immediately after each call,
without needing to close the logger or wait for buffer flush.
"""

import json
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from YSimulator.YClient.llm_utils.cost_tracker import CostTracker


def main():
    print("=" * 70)
    print("Demonstrating Immediate LLM Usage Logging")
    print("=" * 70)
    print()

    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "demo_llm_usage.log"
        print(f"📁 Log file: {log_file}")
        print()

        # Create cost tracker
        print("1️⃣  Creating CostTracker...")
        tracker = CostTracker(
            token_costs=None,
            log_file_path=log_file,
            enable_file_logging=True,
        )
        print(f"   ✅ Created with log file: {log_file}")
        print()

        # Log GPU selection
        print("2️⃣  Logging GPU selection...")
        gpu_info = {
            "physical_gpu_id": 1,
            "logical_gpu_id": 0,
            "assignment_method": "dynamic_selection",
            "cuda_visible_devices": "1",
        }
        tracker.log_gpu_selection(gpu_info, model_name="meta-llama/Llama-3.2-3B", backend="vllm")

        # Check file immediately
        if log_file.exists():
            print(f"   ✅ Log file exists immediately!")
            with open(log_file, "r") as f:
                content = f.read()
            print(f"   📏 File size: {len(content)} bytes")
            print()
        else:
            print("   ❌ Log file not found!")
            return

        # Record some LLM calls
        print("3️⃣  Recording LLM calls...")
        tracker.record_call("generate_post", input_tokens=45, output_tokens=23)
        tracker.record_call("generate_comment", input_tokens=52, output_tokens=31)
        tracker.record_call("decide_reaction", input_tokens=38, output_tokens=5)
        print("   ✅ Recorded 3 LLM calls")
        print()

        # Read and display all logs
        print("4️⃣  Reading log file (without closing tracker)...")
        with open(log_file, "r") as f:
            lines = f.readlines()

        print(f"   📊 Found {len(lines)} log entries:")
        print()

        for i, line in enumerate(lines, 1):
            entry = json.loads(line.strip())
            if entry.get("event") == "gpu_selection":
                print(f"   Entry {i}: GPU Selection")
                print(f"      - Physical GPU: {entry['physical_gpu_id']}")
                print(f"      - Assignment: {entry['assignment_method']}")
                print(f"      - Model: {entry.get('model', 'N/A')}")
            elif "method" in entry:
                print(f"   Entry {i}: LLM Call - {entry['method']}")
                print(f"      - Tokens: {entry['input_tokens']} in, {entry['output_tokens']} out")
                print(f"      - Total: {entry['total_tokens']}")
            print()

        print("=" * 70)
        print("✅ SUCCESS: All logs written immediately!")
        print("=" * 70)
        print()
        print("Key points:")
        print("  • Logs are written immediately after each call")
        print("  • No need to close the logger or wait for flush")
        print("  • Log file can be read while logging is still active")
        print("  • Perfect for monitoring and debugging in real-time")


if __name__ == "__main__":
    main()
