# HomeNAS 本地产物

本仓库把代码与本机运行状态分开保存。忽略的实体文件存放在 `D:\Repos\Artifacts\nas-home`，相对路径按仓库路径镜像；这个目录不是 Git 仓库，不能对它执行 `git init`、`git add` 或提交。

## 路径映射

| 仓库路径 | Artifacts 路径 | 内容 | 是否可重建 |
| --- | --- | --- | --- |
| `.venv/` | `.venv/` | Python 本地开发依赖 | 是，重新创建 venv 并安装依赖 |
| `frontend/node_modules/` | `frontend/node_modules/` | 前端构建依赖 | 是，运行 `npm install --prefix frontend` |
| `runtime/` | `runtime/` | SQLite 数据库、临时脚本和本地运行记录 | 数据库需单独备份 |
| `.oil-ui/` | `.oil-ui/` | UI 设计工作资产和预览素材 | 部分可重建 |
| `backend/**/__pycache__/`、`deploy/**/__pycache__/` | `_ephemeral/pycache/<原相对路径>/` | Python `.pyc` 缓存 | 是，Python 会自动重建；不挂 junction |
| `docs/*-nas.md`、`docs/environment-report*.md` | `docs/` 下的同名文件 | 真实 NAS 环境、网络和服务审计 | 否，应随本机备份保护，不能提交公开仓库 |

## 当前 junction

以下仓库路径是 NTFS junction，目标均在同卷产物库中：

- `.venv` → `D:\Repos\Artifacts\nas-home\.venv`
- `frontend\node_modules` → `D:\Repos\Artifacts\nas-home\frontend\node_modules`
- `runtime` → `D:\Repos\Artifacts\nas-home\runtime`
- `.oil-ui` → `D:\Repos\Artifacts\nas-home\.oil-ui`

映射明细和文件数记录在产物库的 `MANIFEST.csv`；每次增删映射时同步更新。

产物库中还保留了未挂接到仓库路径的本地 UI 工作材料：`flow-ui-architect/`、`ui-flow-preview-runtime/` 和 `ui-preview-runtime/`。前者包含浏览器 profile、cookie 和截图，后两者含预览数据库/状态；它们只用于本机视觉迭代，不要复制到 Git 或公共共享位置。

## 新克隆或恢复

新电脑没有这份本地产物库时，克隆后的仓库可以直接重新创建 `.venv` 和 `frontend/node_modules`，HomeNAS 会在 `runtime/` 保存运行时状态。私有 NAS 审计报告和仍需保留的数据库应从受控备份恢复到本机 Artifacts；不要把这些内容推到 GitHub。

如果在原电脑恢复已备份的 Artifacts，先确保仓库对应路径不存在，再用管理员 PowerShell 创建 junction：

```powershell
New-Item -ItemType Junction -Path .venv -Target D:\Repos\Artifacts\nas-home\.venv
New-Item -ItemType Junction -Path frontend\node_modules -Target D:\Repos\Artifacts\nas-home\frontend\node_modules
New-Item -ItemType Junction -Path runtime -Target D:\Repos\Artifacts\nas-home\runtime
New-Item -ItemType Junction -Path .oil-ui -Target D:\Repos\Artifacts\nas-home\.oil-ui
```

不要对 junction 使用递归删除、移动或备份工具；不要运行 `git clean -xfd`。需要拆除链接时用 `cmd /c rmdir <junction>`，它只移除链接本身。
