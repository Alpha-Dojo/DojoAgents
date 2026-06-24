# SectorPrecomputedStore 加载逻辑优化设计与规划

## 1. 背景与目标
当前 `SectorPrecomputedStore` 加载宏观板块数据（`constituents_df`, `sector_daily_df`, `ticker_daily_df`）的逻辑主要依赖于两种方式：
1. **本地文件加载**：尝试从 `dataset_dir` 读取本地 `.parquet` 文件。这要求外部有定时任务或脚本去提前生成和更新这些文件。
2. **SDK Fallback**：若本地文件不存在，则调用 `client.sectors.get_precomputed_*()`。由于 API 返回的是 JSON 信封格式（List of dicts），再将其转为 `pandas.DataFrame` 存在较高的内存与时间开销。

**优化目标**：将数据加载逻辑统一改成从 `DojoSDK` 对应的 `dojo_sector_precomputed` 数据集中读取。这不仅能消除对外部文件生成脚本的依赖，还能利用底层数据集系统（HuggingFace Datasets 或 SDK 的离线缓存机制）实现高效的列式数据（Parquet）直读。

---

## 2. 方案反思与选项分析

在实施改动之前，需要深入反思“从数据集中读取”的具体落地形式。由于 `DojoSDK` 已经引入了 HuggingFace 离线数据源设计，我们有以下两种可选方案：

### 方案 A：直接利用 DojoSDK 提供的 `download_dataset` (推荐)
`DojoSDK` 提供了 `dojo.datasource.upload.download_dataset` 方法，它封装了 `snapshot_download`。
- **流程**：在 `reload` 方法中，首先调用 `download_dataset("dojo_sector_precomputed", target_dir)` 将数据集拉取/同步到 `target_dir`。然后直接复用原有的 `pd.read_parquet(target_dir / CONSTITUENTS_FILE)` 逻辑。
- **优点**：改动最小，完美复用了现有的 DataFrame 构建代码；自动利用 HuggingFace Hub 的本地缓存与断点续传能力；`manifest.json` 等非结构化数据也能一并同步。
- **反思**：如果是在无网的纯离线环境，`download_dataset` 可能会报错。因此需要结合环境变量（如 `DOJO_HF_OFFLINE` 或捕获网络异常）来优雅降级，允许只读本地已存在的 `.parquet`。

### 方案 B：使用 `datasets.load_dataset` 直接读取为 DataFrame
借助 `datasets` 库直接读取 HuggingFace 上的 parquet 文件并 `to_pandas()`。
- **流程**：`load_dataset("AlphaDojo/dojo_sector_precomputed", data_files="constituents.parquet").to_pandas()`
- **优点**：无需手动管理 `target_dir` 目录，完全交给 `~/.cache/huggingface/datasets` 管理。
- **反思**：`manifest.json` 不是合法的 dataset 结构，无法通过 `load_dataset` 读取，仍需额外的下载逻辑。此外，如果 `DojoAgents` 容器没有写入 `~/.cache` 的权限，或者用户希望将数据放在 `FinancialDashboardConfig.dashboard_data_root`，此方案会导致缓存目录不可控。

**结论**：方案 A 更加契合现有架构，能较好地与 `FinancialDashboardConfig.dashboard_data_root` 结合。

---

## 3. 具体修改规划

### 3.1 改造 `SectorPrecomputedStore.reload`
废弃掉原有单纯依赖外部生成文件的逻辑。在尝试读取本地 Parquet 之前，主动触发数据集的同步（如果配置允许联网）：

```python
from dojo.datasource.upload import download_dataset
import os
import logging

logger = logging.getLogger(__name__)

def reload(self, dataset_dir: Path | None = None) -> None:
    target_dir = Path(dataset_dir).expanduser().resolve() if dataset_dir else self.dataset_dir
    
    # 新增逻辑：主动从 DojoSDK 对应的数据集同步数据
    offline_only = os.environ.get("DOJO_HF_OFFLINE", "false").lower() in ("1", "true", "yes")
    if not offline_only:
        try:
            logger.info("Syncing dojo_sector_precomputed dataset from HuggingFace...")
            download_dataset("dojo_sector_precomputed", target_dir)
        except Exception as exc:
            logger.warning("Failed to sync dataset, will try to use existing local files: %s", exc)

    # 之后的逻辑与原来保持一致，直接从 target_dir 读取 parquet
    manifest_path = target_dir / MANIFEST_FILE
    if manifest_path.exists():
        try:
            constituents_df = self._normalize_constituents_frame(pd.read_parquet(target_dir / CONSTITUENTS_FILE))
            # ...
```

### 3.2 改造 `_load_from_sdk` 备用逻辑
原有的 `_load_from_sdk` 实际上是在做 HTTP 调用。如果我们已经在 `reload` 中集成了 Dataset 同步机制，那么 HTTP fallback 可能只在以下极端情况需要：
- HF 被墙或 HF Token 无效。
- 此时 `target_dir` 没有任何缓存文件。

因此，原有的 `_load_from_sdk` 代码结构可以保留作为最后一道防线（Fallback to Online HTTP API），但注释和日志需要更新，说明这是在 Dataset 加载失败后的最后兜底。

### 3.3 遗漏与边界情况反思
- **`HF_TOKEN` 的依赖**：`dojo_sector_precomputed` 如果是私有数据集，需要确保 `DojoAgents` 运行环境中注入了 `HF_TOKEN`。如果环境变量未提供，`download_dataset` 可能会抛出异常。
- **并发同步问题**：如果多个服务实例同时调用 `reload`，`snapshot_download` 内部是否做了文件锁保护？（注：HuggingFace Hub 的下载默认会先写临时文件再重命名，具备基础的并发安全，但高并发下仍需谨慎）。
- **同步延迟问题**：`reload()` 是一个同步函数，内部调用下载可能会阻塞当前线程，在 FastAPI 这种异步框架中，首次启动加载时如果下载耗时较长，可能会拖慢启动时间。是否应该引入后台异步刷新（如 `async_client.py` 中的 `start_offline_dataset_daemon`）？
- **移除无用的 `self.client` 强依赖**：使用直接读取数据集的模式后，`SectorPrecomputedStore` 的核心查询能力将不再强绑定在线的 `self.client`，增强了该 Store 的独立运行能力。

---

## 4. 待确认问题 (Open Questions)

在进入代码修改阶段前，我需要与您确认以下几个决策点：

1. **同步时机**：`download_dataset` 会产生网络 IO，目前的 `reload()` 有时在属性访问时懒加载（例如 `_load_constituents()` 内被触发）。我们是只在服务启动时显式加载一次，还是每次找不到数据时同步阻塞下载？是否考虑直接复用 `DojoSDK` 的 `start_offline_dataset_daemon` 后台刷新机制？
2. **私有数据集 Token**：`dojo_sector_precomputed` 是否为 Private Dataset？如果是，我们是否假定环境中已配置好 `HF_TOKEN`，遇到权限错误直接进入降级 Fallback？
3. **完全取代 HTTP**：目前的方案是“优先用 dataset 模式，失败再走原有的 SDK API (HTTP)”。您是希望彻底删掉 HTTP Fallback 逻辑（只用 dataset），还是作为双保险保留？
