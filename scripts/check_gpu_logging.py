"""
Example demonstrating GPU selection logging in LLM usage logs.

This script shows how to verify GPU selection was logged correctly.
"""

import json
from pathlib import Path


def parse_llm_usage_log(log_file_path: str):
    """
    Parse LLM usage log and extract GPU selection information.

    Args:
        log_file_path: Path to the LLM usage log file

    Returns:
        Dictionary with GPU selection info, or None if not found
    """
    log_path = Path(log_file_path)

    if not log_path.exists():
        print(f"❌ Log file not found: {log_file_path}")
        return None

    print(f"📄 Reading log file: {log_file_path}")
    print()

    gpu_selection_entries = []
    llm_call_count = 0

    with open(log_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            try:
                entry = json.loads(line.strip())

                # Check for GPU selection event
                if entry.get("event") == "gpu_selection":
                    gpu_selection_entries.append(entry)
                    print(f"✅ Found GPU selection entry at line {line_num}")
                    print(f"   Physical GPU: {entry.get('physical_gpu_id')}")
                    print(f"   Assignment: {entry.get('assignment_method')}")
                    print(f"   Model: {entry.get('model', 'unknown')}")
                    print()
                elif "method" in entry:  # Regular LLM call
                    llm_call_count += 1

            except json.JSONDecodeError:
                print(f"⚠️  Line {line_num}: Invalid JSON")
            except Exception as e:
                print(f"⚠️  Line {line_num}: Error parsing - {e}")

    print(f"📊 Summary:")
    print(f"   GPU selection entries: {len(gpu_selection_entries)}")
    print(f"   LLM call entries: {llm_call_count}")
    print()

    return gpu_selection_entries[0] if gpu_selection_entries else None


def display_gpu_selection_info(gpu_info: dict):
    """Display GPU selection information in a readable format."""
    print("=" * 60)
    print("GPU Selection Information")
    print("=" * 60)

    if not gpu_info:
        print("❌ No GPU selection information found")
        return

    print(f"Physical GPU ID:       {gpu_info.get('physical_gpu_id', 'unknown')}")
    print(f"Logical GPU ID:        {gpu_info.get('logical_gpu_id', 'unknown')}")
    print(f"Assignment Method:     {gpu_info.get('assignment_method', 'unknown')}")
    print(f"CUDA_VISIBLE_DEVICES:  {gpu_info.get('cuda_visible_devices', 'not set')}")
    print(f"Backend:               {gpu_info.get('backend', 'unknown')}")
    print(f"Model:                 {gpu_info.get('model', 'unknown')}")
    print(f"Timestamp:             {gpu_info.get('timestamp', 'unknown')}")

    # Explain the assignment method
    print()
    print("Assignment Method Explanation:")
    method = gpu_info.get("assignment_method", "unknown")

    if method == "ray_assigned":
        print("  ✓ Ray assigned a specific GPU via CUDA_VISIBLE_DEVICES")
    elif method == "dynamic_selection":
        print("  ✓ YSimulator dynamically selected GPU based on available memory")
    elif method == "default":
        print("  ⚠ Using default GPU (no dynamic selection)")
    else:
        print(f"  ? Unknown method: {method}")

    print("=" * 60)


if __name__ == "__main__":
    import sys

    # Example usage
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        # Default to common location
        log_file = "example/llm_population_100_vllm/logs/client_0_llm_usage.log"

        print("💡 Usage: python check_gpu_logging.py <path_to_llm_usage_log>")
        print(f"💡 Using default: {log_file}")
        print()

    gpu_info = parse_llm_usage_log(log_file)
    print()
    display_gpu_selection_info(gpu_info)
