# Claude Code 双系统 PATH 关系图与排查记录

> **日期**:2026-09-17
> **范围**:Windows(Claude Code 主机)+ WSL Ubuntu-22.04(FM_a 项目宿主)
> **用途**:新 hook / MCP / CLI 工具接入时的权威参考;PATH 类报错排查手册
> **触发**:codegraph hook 报 `command not found`,顺藤排查出 WSL 侧两个潜伏 bug

---

## 0. 结论速览

| 问题 | 根因 | 修复 |
|------|------|------|
| UserPromptSubmit hook 报 `codegraph.cmd: command not found` | `~/.claude/settings.json` 的 `env.PATH` 整体替换会话 PATH,不含 npm 全局目录 | `env.PATH` 追加 `C:/Users/Puchon~1/AppData/Roaming/npm` |
| codegraph MCP 同受 PATH 影响 | `~/.claude.json` 里是裸命令 `codegraph` | 改为 `cmd /c <绝对路径>/codegraph.cmd serve --mcp` |
| WSL `bash -lc` 找不到 codegraph | PATH 写在 `~/.bashrc`,但非交互 shell 在 `.bashrc` 开头 guard 处提前 return | PATH 移至 `~/.profile`(幂等写法) |
| WSL login shell 每次报 5 个 `export: not a valid identifier` | Git Bash→wsl.exe 传参时 `$PATH` 被当场展开,带空格的完整值被写死进文件 | 脚本文件方式重写(见 §5 陷阱 ③) |

---

## 1. 总体架构

```
Claude Code 只在 Windows 侧运行(用户决策,2026-09-17 确认)。
WSL 无 Claude Code、无 MCP server;仅被 wsl.exe 按需调用。
```

```
┌─ Windows(Claude Code 唯一运行地)──────────────────────────┐
│                                                            │
│  ~/.claude/settings.json 的 env.PATH ←── 整体替换,非追加!  │
│  = System32 · PowerShell · Git cmd/bin ×2 · tmux ·         │
│    nodejs · npm(2026-09-17 加)                             │
│         │                                                  │
│         └─ 全部子进程继承此 PATH:                           │
│             hooks(Git Bash 执行,MSYS 转 POSIX)             │
│             MCP stdio 进程 · statusLine · Bash/PS 工具      │
└────────────────────────────────────────────────────────────┘
                    │ wsl -d Ubuntu-22.04 -- bash -lc "<cmd>"
                    ▼
┌─ WSL Ubuntu-22.04(仅被调用)───────────────────────────────┐
│  初始化链:/etc/profile → ~/.profile(必读)                │
│            → ~/.bashrc(非交互时提前 return!)               │
│  调用模式 bash -lc = 非交互登录 → 只有 .profile 生效         │
│  interop 把 Windows 目录追加到 WSL PATH 尾(/mnt/c/...带空格)│
└────────────────────────────────────────────────────────────┘
```

---

## 2. Windows 侧:组件清单与 PATH 依赖

`env.PATH` 当前值(settings.json,顺序即查找顺序):

```
C:/Windows/System32
C:/Windows/System32/WindowsPowerShell/v1.0
C:/Program Files/Git/cmd
C:/Program Files/Git/bin
D:/Program Files/Git/cmd
D:/Program Files/Git/bin
C:/Users/Puchon~1/AppData/Local/Microsoft/WinGet/Packages/marlocarlo.psmux_...   (tmux)
D:/Program Files/nodejs
C:/Users/Puchon~1/AppData/Roaming/npm          ← 2026-09-17 追加
```

| 组件 | 配置位置 | 命令 | PATH 依赖 | 状态 |
|------|---------|------|----------|------|
| UserPromptSubmit hook | `~/.claude/settings.json` | `codegraph.cmd prompt-hook` | 靠 PATH 找 .cmd | ✓ |
| AQE quality-gate hook | `D:\FlyBuddy\.claude\settings.json` | `node D:\FlyBuddy\.claude\hooks\quality-gate.cjs` | 裸 node 靠 PATH(nodejs 在列) | ✓ |
| MCP codegraph | `~/.claude.json` | `cmd /c C:/Users/Puchon~1/AppData/Roaming/npm/codegraph.cmd serve --mcp` | 无(绝对路径) | ✓ |
| MCP optiontrader | `~/.claude/settings.json` | `C:\Users\Puchon~1\python-sdk\python3.10.16\python.exe -m mcp_server`,cwd `D:\FlyBuddy\optiontrader` | 无 | ✓ |
| MCP jin10 | `~/.claude/settings.json` | streamable_http | 无 | ✓ |
| statusLine(hud) | `~/.claude/settings.json` | 绝对路径 node.exe(omc-hud.mjs) | 无 | ✓ |

验证方式(2026-09-17):用 settings.json 真实完整 PATH + Git Bash(`/d/Program Files/Git/usr/bin/bash.exe`)精确模拟 hook 执行,`command -v codegraph.cmd` 解析成功、`prompt-hook` exit 0;`cmd /c <正斜杠路径> version` → 1.6.0。

**注意**:`codegraph upgrade` 或重装若重写 `~/.claude.json` / `settings.json` 的 hook/MCP 配置,需复查 PATH 与绝对路径是否被还原。

---

## 3. WSL 侧:shell 初始化链与 PATH

三种启动方式的行为差异(**这是本次排查的核心发现**):

| 启动方式 | `/etc/profile` | `~/.profile` | `~/.bashrc` | 典型场景 |
|---------|---------------|--------------|-------------|---------|
| WSL 终端交互 | ✓ | ✓ | ✓ | 人坐在 WSL 里敲命令 |
| `wsl -- bash -lc "<cmd>"` | ✓ | ✓ | **✗**(开头 `case $- in *i*) ;; *) return;;` 提前退出) | **Windows Claude Code 调用 FM_a 的主要模式** |
| `wsl -- bash -c "<cmd>"` | ✗ | ✗ | ✗ | PATH 全靠进程继承,几乎不用 |

**规则:给 WSL 装的 CLI 工具,PATH 写进 `~/.profile`,不是 `.bashrc`。**

`~/.profile` 尾部当前写法(幂等,防重复追加):

```bash
# CodeGraph CLI (added 2026-09-17)
case ":$PATH:" in *":$HOME/.npm-global/bin:"*) ;; *) export PATH="$HOME/.npm-global/bin:$PATH";; esac
```

WSL 侧已装工具:`/home/abug/.npm-global/bin/codegraph`(npm 用户级前缀,因系统 npm 目录无写权限且无免密 sudo)。

interop 说明:WSL PATH 尾部自动追加 Windows 目录(`/mnt/c/...`),其中含带空格路径(`Pu Chong`)——排在查找顺序末尾,对 Linux 工具解析无实际影响;但**任何未加引号的 `export PATH=$PATH:...` 拼接都会被这些空格拆坏**,这是 §5 陷阱 ③ 的温床。

---

## 4. 已验证的跨系统调用方式

### Windows hook(模拟验证可复现)

```bash
# 用 settings.json 的真实 PATH 模拟 hook 执行环境
GS_BASH="/d/Program Files/Git/usr/bin/bash.exe"
POSIXPATH=$(cygpath -p "<env.PATH 的值>")
env PATH="$POSIXPATH" "$GS_BASH" -c 'echo "{}" | codegraph.cmd prompt-hook; echo $?'
```

### WSL 工具调用(稳妥写法)

```bash
# ✓ 命令字符串以 cd 开头(不以 / 开头,防 MSYS 转换)
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && codegraph status ."

# ✓ 或直接全路径(不依赖任何 shell 初始化)
wsl -d Ubuntu-22.04 -- bash -c "/home/abug/.npm-global/bin/codegraph version"
```

---

## 5. 陷阱清单(全部实操踩中,含规避方法)

| # | 陷阱 | 现象 | 规避 |
|---|------|------|------|
| ① | MSYS 路径转换 | Git Bash 里传给 wsl.exe 的命令字符串**以 `/` 开头**时,被转成 `D:/Program Files/Git/...`(`bash -c` 包裹也拦不住) | 命令字符串一律以 `cd ... &&` 或其他命令开头 |
| ② | Git Bash→wsl.exe 变量展开 | `$PATH`/`$HOME` 被中间 shell 当场展开,把展开值(含空格)写进目标文件 | 复杂文件写入用脚本文件方式(见 ③) |
| ③ | wsl.exe 内联脚本转义地狱 | 多层引号拼接的 heredoc/echo 产生不可预期的展开 | Write 脚本到 `D:\FlyBuddy\.omc\tmp_*.py` → WSL 侧 `python3 /mnt/d/FlyBuddy/.omc/xxx.py` → 删除。已验证可靠 |
| ④ | `.bashrc` 非交互 guard | 非交互 shell 永远执行不到 `.bashrc` 尾部的自定义行 | PATH 类配置写 `~/.profile` |
| ⑤ | `env.PATH` 是替换不是追加 | 新工具目录不在列 → hook/MCP/工具全挂 | 新工具:绝对短路径(`puchon~1`)或显式加目录进 `env.PATH` |
| ⑥ | Windows 侧执行 `.cmd` 的前提 | `.cmd` shim 内部调 `node`,需要 nodejs 在 PATH;路径含空格需引号 | 短路径 + 确认 nodejs 在 `env.PATH` |

---

## 6. 新组件接入 Checklist

- [ ] Windows hook/MCP:命令用绝对短路径(`puchon~1`),或其目录已进 `env.PATH`?
- [ ] 若改 `env.PATH`:意识到这影响**所有** hooks/MCP/工具子进程?
- [ ] WSL CLI 工具:PATH 写 `~/.profile`(幂等写法)而非 `.bashrc`?
- [ ] Git Bash→WSL 传参:命令字符串不以 `/` 开头?无内联变量写入?
- [ ] 改完后:用 §4 的模拟方式验证,并跑一次真实调用?

---

## 7. 修复时间线

| 时间 | 动作 |
|------|------|
| 2026-09-16 | CodeGraph 接入(Windows npm 全局 + Claude Code MCP;trader/ThinkMesh/OptionTrader/FM_a 建索引);WSL 侧 PATH 误写入 `.bashrc`(被展开,潜伏) |
| 2026-09-17 | 修 hook:`env.PATH` + npm 目录、MCP 绝对路径化;发现并修复 WSL `.bashrc`/`.profile` 潜伏 bug(脚本文件方式重写,幂等);本图成文 |

## 关联记忆

- Agent 记忆:`~/.claude/projects/D--FlyBuddy/memory/windows-wsl-path-map.md`(本档的精简版)
- `codegraph-setup.md` — CodeGraph 安装与索引全景
- `env-management-lessons.md` — 教训 #4(MSYS 精确触发条件)、#11(WSL npm 用户级前缀)
- `wsl-wsl-windows.md` — 9P 协议缓存问题(Windows 挂载路径读 WSL 文件不可靠)
