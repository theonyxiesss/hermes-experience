# Dependency Compatibility Notes

## Problem: faiss-cpu fails with numpy 2.x

**Error seen:**
```
File ".../faiss/swigfaiss.py", line 10, in <module>
    from . import _swigfaiss
AttributeError: _ARRAY_API not found

A module that was compiled using NumPy 1.x cannot be run in NumPy 2.x
```

**Root cause:** The installed `faiss-cpu==1.7.4` wheel was compiled against numpy 1.x. The Hermes venv had numpy 2.4.3 pre-installed (from other dependencies like opencv-python). The FAISS C extension's numpy ABI is incompatible.

**Fix:** Pin numpy to `<2` for the Hermes venv:
```bash
"$HERMES_PYTHON" -m pip install "numpy<2"
```

## Problem: huggingface_hub version conflicts with sentence-transformers

**Error seen (with huggingface_hub==1.28.0):**
```
cannot import name 'cached_download' from 'huggingface_hub'
```

**Error seen (with huggingface_hub==0.30.0):**
```
huggingface-hub>=0.34.0,<1.0 is required for a normal functioning of this module
```

**Root cause:** sentence-transformers and transformers pin specific huggingface_hub ranges. Installing packages one-at-a-time lets pip resolve them to incompatible versions.

**Fix:** Install all ML packages in ONE pip command so the dependency resolver sees the full graph:
```bash
"$HERMES_PYTHON" -m pip install "numpy<2" sentence-transformers faiss-cpu loguru huggingface_hub transformers
```

## Problem: Using the wrong Python binary

**Error seen:** Global python (uv-managed) can't find hermés packages installed in the Hermes venv.

**Root cause:** Hermes uses its own venv at `$HERMES_HOME/../hermes-agent/venv/`. Installing packages globally (via `pip install` without specifying the venv binary) puts them in a different Python environment.

**Fix:** Always use the Hermes venv Python explicitly:
- Windows: `$HERMES_HOME/../hermes-agent/venv/Scripts/python.exe`
- Linux/macOS: `$HERMES_HOME/../hermes-agent/venv/bin/python`

## Recommended Install for Knowledge System

```bash
HERMES_HOME=~/.hermes/profiles/data-mnd
VENV="$HERMES_HOME/../hermes-agent/venv/Scripts/python.exe"  # Windows
# OR
VENV="$HERMES_HOME/../hermes-agent/venv/bin/python"  # Linux/macOS

"$VENV" -m pip install "numpy<2" loguru sentence-transformers faiss-cpu huggingface_hub transformers
```

This single command resolves all numpy compatibility, huggingface_hub range constraints, and dependency version conflicts in one pass.
