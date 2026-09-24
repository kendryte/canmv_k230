import gc
import nncase_runtime as nn
from libs.AIBase import AIBase


def deinit_model(model, pipelines=(), tensor_lists=()):
    """Release extra resources after the interpreter drops its tensor refs."""
    error = None
    try:
        AIBase.deinit(model)
    except Exception as exc:
        error = exc
    for name in tensor_lists:
        tensors = getattr(model, name, None)
        if tensors is None:
            continue
        for i, tensor in enumerate(tensors):
            if tensor is not None:
                try:
                    tensor.release()
                    tensors[i] = None
                except Exception as exc:
                    if error is None:
                        error = exc
        if all(tensor is None for tensor in tensors):
            tensors.clear()
    for name in pipelines:
        pipeline = getattr(model, name, None)
        if pipeline is not None:
            try:
                pipeline.deinit()
                setattr(model, name, None)
            except Exception as exc:
                if error is None:
                    error = exc
    gc.collect()
    nn.shrink_memory_pool()
    if error is not None:
        raise error


def deinit_with_retry(model):
    """Retry a model's idempotent cleanup once, only after a release failure."""
    if model is None:
        return
    try:
        model.deinit()
    except Exception:
        gc.collect()
        model.deinit()
