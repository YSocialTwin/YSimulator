# VLLMService Error Handling Guide

## Overview
VLLMService now provides clear, actionable error messages when initialization fails. This guide explains common errors and how to resolve them.

## Common Errors and Solutions

### Error: Actor Died During Creation

**Symptom:**
```
(VLLMService pid=795) Exception raised in creation task: The actor died because of 
an error raised in its creation task, ray::VLLMService.__init__()
```

**What This Means:**
VLLMService failed to initialize. The specific error will be printed to stderr (visible in Ray logs). Look for error messages starting with ❌.

---

### Error: PyTorch Not Installed

**Error Message:**
```
❌ PyTorch is not installed.
vLLM requires PyTorch with CUDA support.
Install with: pip install torch
See: https://pytorch.org/get-started/locally/
```

**Solution:**
```bash
# Install PyTorch with CUDA support
pip install torch

# Verify installation
python -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
```

**Note:** Make sure to install PyTorch with CUDA support, not CPU-only version.

---

### Error: CUDA Not Available

**Error Message:**
```
❌ CUDA is not available.
vLLM requires CUDA-enabled GPU(s).
Check:
  - GPU drivers are installed
  - CUDA toolkit is installed
  - PyTorch was installed with CUDA support
Run: python -c 'import torch; print(torch.cuda.is_available())'
```

**Solutions:**

1. **Check GPU drivers:**
   ```bash
   nvidia-smi
   ```
   If this fails, install NVIDIA drivers.

2. **Verify CUDA toolkit:**
   ```bash
   nvcc --version
   ```

3. **Check PyTorch CUDA support:**
   ```bash
   python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
   python -c "import torch; print(f'CUDA version: {torch.version.cuda}')"
   ```

4. **Reinstall PyTorch with CUDA:**
   ```bash
   pip uninstall torch
   pip install torch --index-url https://download.pytorch.org/whl/cu118
   ```

---

### Error: vLLM Not Installed

**Error Message:**
```
❌ vLLM is not installed.
Install with: pip install vllm
Note: vLLM requires Linux and is not supported on macOS.
```

**Solution:**
```bash
# Install vLLM
pip install vllm

# Verify installation
python -c "import vllm; print(f'vLLM version: {vllm.__version__}')"
```

**Note:** vLLM only works on Linux. For macOS, use the Ollama backend instead.

---

### Error: vLLM Model Initialization Failed

**Error Message:**
```
======================================================================
❌ vLLM Text Model Initialization Failed
======================================================================
Error: ValueError: Free memory on device cuda:0 is less than desired
Model: meta-llama/Llama-3.2-3B
GPU Memory Utilization: 0.9
Max Model Length: 40000
======================================================================
```

**Solutions:**

1. **Reduce GPU memory utilization:**
   ```json
   {
     "llm": {
       "backend": "vllm",
       "gpu_memory_utilization": 0.7  // Reduce from 0.9 to 0.7
     }
   }
   ```

2. **Use a smaller model:**
   ```json
   {
     "llm": {
       "model": "meta-llama/Llama-3.2-1B"  // Smaller model
     }
   }
   ```

3. **Reduce max sequence length:**
   ```json
   {
     "llm": {
       "max_model_len": 20000  // Reduce from 40000
     }
   }
   ```

4. **Close other GPU-using processes:**
   ```bash
   # Check GPU memory usage
   nvidia-smi
   
   # Kill processes if needed
   kill <pid>
   ```

5. **Use a different GPU (multi-GPU systems):**
   ```bash
   CUDA_VISIBLE_DEVICES=1 python run_client.py --config example/llm_population_100_vllm
   ```

---

## How to Find Detailed Error Messages

### Method 1: Check Ray Logs
Ray captures stderr output. Look for lines starting with ❌ in the Ray worker logs.

```bash
# View Ray logs
ray logs

# Or check specific worker logs in /tmp/ray/session_*/logs/
```

### Method 2: Check Application Logs
If running with logging enabled, check the simulation logs:

```bash
tail -f logs/client_0.log
```

### Method 3: Run with Ray in Local Mode
For debugging, run Ray in local mode to see errors directly:

```python
import ray
ray.init(local_mode=True)  # Errors printed directly to console
```

---

## Error Message Structure

All error messages from VLLMService follow this structure:

```
======================================================================
❌ <What Failed>
======================================================================
Error: <Error Type>: <Error Message>

<Actionable Guidance>
- What to check
- What to install
- Commands to run
======================================================================
```

This makes errors:
- **Visible**: Printed to stderr (captured by Ray)
- **Clear**: Emojis and formatting make errors easy to spot
- **Actionable**: Includes specific commands to fix the issue
- **Comprehensive**: Includes full traceback for debugging

---

## Debugging Tips

### Enable Debug Logging
Set logging level to DEBUG to see more details:

```json
{
  "logging": {
    "level": "DEBUG"
  }
}
```

### Test Dependencies Separately
Before running the full simulation, verify dependencies:

```python
# test_vllm_setup.py
import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA devices: {torch.cuda.device_count()}")

import vllm
print(f"vLLM: {vllm.__version__}")

# Try initializing vLLM with a small model
from vllm import LLM
llm = LLM(model="facebook/opt-125m")
print("✓ vLLM initialization successful")
```

### Check GPU Memory
Monitor GPU memory usage:

```bash
# Continuous monitoring
watch -n 1 nvidia-smi

# Or use Python
python -c "import torch; print(torch.cuda.mem_get_info())"
```

---

## Prevention

To avoid initialization errors:

1. **Pre-flight checks:** Test dependencies before running simulations
2. **Start small:** Test with small models first
3. **Monitor resources:** Watch GPU memory usage
4. **Use appropriate configs:** Match configuration to available resources
5. **Check compatibility:** Ensure PyTorch, CUDA, and vLLM versions are compatible

---

## Getting Help

If errors persist:

1. Check the error message for specific guidance
2. Verify all dependencies are installed correctly
3. Test with a minimal configuration
4. Check Ray logs for additional details
5. Report issues with:
   - Full error message (including ❌ sections)
   - System information (GPU, CUDA version, Python version)
   - Configuration used
   - Output of diagnostic commands

---

**Last Updated:** February 10, 2026
**Status:** Active maintenance
