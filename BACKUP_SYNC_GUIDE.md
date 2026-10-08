# Timesfm Git 同步备份指南

> **路径口径**：本文用 `<FM_ROOT>` 表示仓库根（本机为 WSL 活仓；换机器/换用户后由脚本按自身位置推导，不要写死绝对路径）。

## 架构

```
本机 WSL Ubuntu-22.04          目标机 Windows (100.96.19.116)
<FM_ROOT>              ┌─ SSH Server (OpenSSH, chong 用户)
git remote "backup" ──────────► │  └─ WSL Ubuntu-24.04
                                 │     /root/timesfm (root 用户)
                                 └─ administrators_authorized_keys 认证
```

## 快速命令

```bash
cd <FM_ROOT>

# 检查同步状态
git fetch backup && git log --oneline HEAD..backup/master

# 推送到备份
git push backup master

# 从备份拉取
git pull backup master
```

## 配置细节

| 项目 | 值 |
|------|-----|
| 目标机 IP | 100.96.19.116 |
| SSH 用户 | chong |
| 认证方式 | ed25519 密钥（`~/.ssh/id_ed25519`） |
| 密钥位置（Windows） | `C:\ProgramData\ssh\administrators_authorized_keys` |
| 远程 WSL 发行版 | Ubuntu-24.04 |
| 远程 timesfm 路径 | `/root/timesfm`（root 用户） |
| Git remote 名称 | backup |
| uploadpack | `wsl -d Ubuntu-24.04 -- git-upload-pack` |
| receivepack | `wsl -d Ubuntu-24.04 -- git-receive-pack` |

## 故障排查

```bash
# 测试 SSH 连接
ssh chong@100.96.19.116 "echo OK"

# 测试 WSL 命令
ssh chong@100.96.19.116 "wsl -d Ubuntu-24.04 -- ls /root/timesfm"

# 检查 remote 配置
git remote -v
git config --get remote.backup.uploadpack
```

## 注意事项

- 目标机 WSL 以 **root** 运行，路径是 `/root/timesfm`（非 `/home/...`）
- 目标机 WSL 发行版是 **Ubuntu-24.04**（本机是 22.04）
- Windows SSH 对管理员用户使用 `administrators_authorized_keys` 而非用户目录下的 `authorized_keys`
- 推送前先 commit 本地更改

## 拉取+比对命令

当需要检查远程更新并与本地比对时：

```bash
cd <FM_ROOT> && ./pull_and_compare.sh
```

该脚本会：
1. 从 backup remote 拉取最新
2. 显示同步状态（是否一致）
3. 列出远程有但本地没有的提交
4. 列出本地有但远程没有的提交
5. 显示文件差异统计
6. 给出操作建议（merge/pull/push）

**触发短语**：当用户说"拉取目标机仓库"时，执行此脚本。
