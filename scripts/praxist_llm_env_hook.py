#!/usr/bin/env python3
"""Patch praxist so anthropic_messages honors process ANTHROPIC_BASE_URL.

Praxist's freeze_provider_env / _scoped_legacy_provider_env for
model_provider:anthropic_messages only pass ANTHROPIC_API_KEY. Custom
gateways (Volcengine Ark, DashScope coding) therefore relied on a hardcoded
task.yaml runtime_environment.env.ANTHROPIC_BASE_URL — which blocks 429
failover overlays from the supervisor.

This hook (installed via zz_fm_llm_env.pth) makes process-env BASE_URL win
so supervisor can switch Ark ↔ DashScope without mutating task.yaml.
"""
from __future__ import annotations

import os
import threading

_PATCHED = False
_LOCK = threading.Lock()


def _patch_freeze(mod) -> bool:
    orig = getattr(mod, "freeze_provider_env", None)
    if not callable(orig) or getattr(orig, "_fm_llm_env_patched", False):
        return bool(orig and getattr(orig, "_fm_llm_env_patched", False))

    def freeze_provider_env(model_provider_ref, env):  # type: ignore[no-untyped-def]
        out = orig(model_provider_ref, env)
        if model_provider_ref == "model_provider:anthropic_messages":
            base = (env.get("ANTHROPIC_BASE_URL") or "").strip()
            if base:
                out = dict(out)
                out["ANTHROPIC_BASE_URL"] = base
            auth = (env.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
            if auth and not (out.get("ANTHROPIC_AUTH_TOKEN") or "").strip():
                out = dict(out)
                out["ANTHROPIC_AUTH_TOKEN"] = auth
        return out

    freeze_provider_env._fm_llm_env_patched = True  # type: ignore[attr-defined]
    freeze_provider_env._fm_llm_env_orig = orig  # type: ignore[attr-defined]
    mod.freeze_provider_env = freeze_provider_env
    return True


def _patch_scoped(mod) -> bool:
    orig = getattr(mod, "_scoped_legacy_provider_env", None)
    if not callable(orig) or getattr(orig, "_fm_llm_env_patched", False):
        return bool(orig and getattr(orig, "_fm_llm_env_patched", False))

    def _scoped_legacy_provider_env():  # type: ignore[no-untyped-def]
        env = orig()
        provider_ref = os.environ.get("PRAXIST_MODEL_PROVIDER_REF", "")
        if provider_ref == "model_provider:anthropic_messages":
            base = (os.environ.get("ANTHROPIC_BASE_URL") or "").strip()
            if base:
                env = dict(env)
                env["ANTHROPIC_BASE_URL"] = base
            auth = (os.environ.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
            if auth and not env.get("ANTHROPIC_AUTH_TOKEN"):
                env = dict(env)
                env["ANTHROPIC_AUTH_TOKEN"] = auth
        return env

    _scoped_legacy_provider_env._fm_llm_env_patched = True  # type: ignore[attr-defined]
    _scoped_legacy_provider_env._fm_llm_env_orig = orig  # type: ignore[attr-defined]
    mod._scoped_legacy_provider_env = _scoped_legacy_provider_env
    return True


def install() -> None:
    global _PATCHED
    with _LOCK:
        if _PATCHED:
            return
        try:
            from praxist.plugins.workflow_stages.research_loop import provider_env as pe
            _patch_freeze(pe)
        except Exception:
            pass
        try:
            from praxist.plugins.workflow_stages.research_loop.backend import agent as ag
            _patch_scoped(ag)
        except Exception:
            pass
        # stage.py has a local _provider_env fallback; patch if present
        try:
            from praxist.plugins.workflow_stages.research_loop import stage as st
            if hasattr(st, "freeze_provider_env"):
                _patch_freeze(st)
            # stage imports freeze_provider_env from provider_env — already patched
        except Exception:
            pass
        _PATCHED = True


install()
