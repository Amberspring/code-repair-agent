# CodeRepair Agent

Python 函数修复：模型生成代码 → AST/入口校验 → Docker 公开测试 → 反馈重试 → 独立隐藏测试 → 原子 checkpoint 与运行记录。支持 OpenAI-compatible API；使用通用代码模型，不默认使用电商适配器。

```sh
python -m pip install -e . pytest
git clone https://github.com/jkoppel/QuixBugs ../QuixBugs
git -C ../QuixBugs checkout 4257f44b0ff1181dedaedee6a447e133219fcebf
python scripts/build_quixbugs.py --source ../QuixBugs
docker pull python:3.12-slim
python -m pytest -q
python -m repair.cli --url http://127.0.0.1:8000/v1 --model Qwen3-8B --iterations 1 --output results/single
python -m repair.cli --url http://127.0.0.1:8000/v1 --model Qwen3-8B --iterations 3 --output results/multi
```

API 密钥通过 REPAIR_API_KEY 环境变量提供。失败恢复显式使用 --resume；相同任务与总轮数预算继续执行，不额外获得重试次数。修复任务只发送题目、错误代码与公开测试；隐藏测试仅在最终评估执行，期望输出保留在宿主进程。

本机或 AutoDL 容器没有 Docker 时，可以追加 `--github-worker Amberspring/code-repair-agent`，通过本机已授权的 `gh` 将公开基准候选代码交给专用 GitHub Actions worker。工作流将输入作为 base64 数据解码，再交给相同的 Docker 隔离器；GitHub 凭证不传给模型或容器，每次执行返回可追溯的 worker URL。该方式会上传候选代码及测试到指定 GitHub 仓库的工作流，不应用于未经授权的私有代码；API 推理仍在配置的模型服务上进行，worker 等待时间计入端到端耗时。

Docker 强制禁网、只读根文件系统、只读候选文件、非 root、256MB 内存、1 CPU、32 进程与时间限制；输出读取有 64KB 上限。没有 Docker/镜像时直接失败，不在本机执行生成代码。Docker 共享宿主内核，请在专用可销毁 worker 上运行不可信任务；这不是防攻击的竞赛评分系统。

默认评测数据来自 [QuixBugs](https://github.com/jkoppel/QuixBugs) 固定提交的八个自包含算法：错误代码和测试均原样取自上游，未自行制造新 bug。第一条原有测试公开给模型，其余仅用于最终评估；来源、文件 SHA-256、选择规则及 MIT 许可证位于 data/quixbugs.manifest.json 与 data/QuixBugs-LICENSE.txt。公开基准可能已出现在模型预训练中，所以“隐藏于提示”不等于模型从未见过，八题成绩也不能称为完整 40 题 QuixBugs 或 SWE-bench 成绩。

data/tasks.json 的三道自编题仅为工程样例，需显式 --tasks 才使用。测试中的脚本化模型仅验证状态闭环，不计为模型修复能力。真实模型结果需 CLI 运行后保存，单轮与多轮应使用同一模型与任务集；多 Agent、路由属于后续实验。
