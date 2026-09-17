# 快环→慢环→快环 屏障握手 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 把监督环从「时间窗内并排试快/慢环」改成文件完成信号驱动的相位屏障：快环筛选结束并 harvest 后立刻开慢环；慢环抽干队列后才允许下一轮快环。

**Architecture:** 不引入 asyncio / 消息队列。快环、慢环仍是独立子进程。监督环在 `supervisor_state.json` 增加 `phase ∈ {fast, slow, wait_quota}`。`slow_loop_window` 不再是硬门。`cycles_done` 改到 harvest_empty 或慢环抽干之后。

**Spec:** docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md

See session plan for full TDD steps. This file is the repo-canonical pointer.

**Tasks:** (1) phase state machine + supervisor tick + tests (2) goal.yaml + runbook + spec wording.
