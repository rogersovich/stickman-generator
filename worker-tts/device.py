"""Pick the best torch device on this machine: NVIDIA CUDA, then Apple MPS, then CPU."""

import os
import platform

# must be set before torch is imported
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch  # noqa: E402


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda:0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def describe_device() -> str:
    device = pick_device()
    if device.startswith("cuda"):
        return f"CUDA · {torch.cuda.get_device_name(0)}"
    if device == "mps":
        return f"MPS · Apple {platform.machine()}"
    return "CPU"


def free_memory(device: str) -> None:
    import gc

    gc.collect()
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    elif device == "mps":
        torch.mps.empty_cache()
