# DojoAgents 文档站维护说明

本目录包含 DojoAgents 的 MkDocs 在线文档源码。除本维护说明外，所有可发布文档和文档资源都必须放在 `docs/site/` 中，禁止再在 `docs/` 根目录新增独立设计文档。

## 目录结构

```text
docs/
├── README.md                  # 仅供维护者阅读的文档治理说明
└── site/                      # MkDocs 的唯一 docs_dir
    ├── assets/                # 中英文共享的图片、动图等静态资源
    │   ├── images/
    │   └── gifs/
    ├── zh/                    # 中文站点，默认发布到 /
    │   ├── getting-started/   # 安装和首次运行
    │   ├── user-guide/        # 面向使用者的操作指南
    │   ├── architecture/      # 系统级组件关系和数据流
    │   ├── design/            # 子系统设计、技术决策和集成契约
    │   ├── reference/         # 稳定接口、协议和配置参考
    │   ├── development/       # 开发、测试、扩展和发布操作
    │   ├── plans/             # 实施计划、迁移步骤和历史决策
    │   └── community/         # 社区入口
    └── en/                    # 英文站点；与 zh 保持相同相对路径
```

## 分类边界

- `architecture/`：解释系统由哪些组件组成、组件如何协作和数据如何流动。
- `design/`：记录一个具体子系统当前有效的设计、所有权边界和外部适配器契约。
- `plans/`：记录尚未完成的方案、迁移顺序、backlog 或历史决策；它不是当前 API 契约。
- `reference/`：记录调用者可以依赖的接口、协议、配置项和清单。
- `development/`：记录如何开发、测试、扩展、构建和发布。
- `assets/`：只存放站点共享静态资源，不存放 Markdown 正文。

计划实施完成后，要把长期有效的结论迁移到 `architecture/`、`design/`、`reference/` 或 `development/`，并删除或归档失效计划。不要让同一份权威说明同时存在于多个分类。

金融 Agent 工具与 Task 的权威说明在正式站：

- `docs/site/*/reference/dojo-sdk.md`（`dojo.sdk.*` 清单与待补能力）
- `docs/site/*/user-guide/tasks-and-pipelines.md`（流水线与 Theme Deep Dive）

`docs/site/*/plans/` 中的能力盘点 / backlog 应与上述正式说明保持方向一致（SDK 为主路径），但当前行为仍以正式分类和代码为准。

## 本地预览

从仓库根目录执行：

```bash
uv run --extra docs mkdocs serve
```

默认访问：

```text
http://127.0.0.1:8000/
```

英文站点路径：

```text
http://127.0.0.1:8000/en/
```

页面右上角提供 `中文` / `English` 语言切换。

## 编译文档

从仓库根目录执行严格构建：

```bash
uv run --extra docs mkdocs build --strict
```

默认输出目录是仓库根目录下的 `site/`。该目录是构建产物，已加入 `.gitignore`，不要把它当作文档源文件维护。

如果只想验证构建而不污染仓库根目录，可以输出到临时目录：

```bash
uv run --extra docs mkdocs build --strict --site-dir /private/tmp/dojoagents-mkdocs-site
```

## 打包文档

构建后可以将静态站点打包为 tarball。推荐输出到 `dist/`：

```bash
uv run --extra docs mkdocs build --strict
mkdir -p dist
tar -czf dist/dojoagents-docs-site.tar.gz -C site .
```

打包内容是纯静态 HTML/CSS/JS 文件，可以部署到任意静态文件服务。

如需避免在仓库根目录留下 `site/`，可以直接构建到临时目录再打包：

```bash
uv run --extra docs mkdocs build --strict --site-dir /private/tmp/dojoagents-mkdocs-site
mkdir -p dist
tar -czf dist/dojoagents-docs-site.tar.gz -C /private/tmp/dojoagents-mkdocs-site .
```

## 部署方式

### 静态文件服务器

将构建输出目录中的全部文件上传到静态服务器根目录即可：

```text
site/
├── index.html
├── en/
├── assets/
├── search/
└── sitemap.xml
```

中文默认站点位于 `/`，英文站点位于 `/en/`。

### Nginx 示例

假设构建产物部署到 `/var/www/dojoagents-docs`：

```nginx
server {
    listen 80;
    server_name docs.example.com;

    root /var/www/dojoagents-docs;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }
}
```

### 对象存储或 CDN

对象存储、CDN、Netlify、Vercel、Cloudflare Pages 等静态托管平台都可以直接托管构建输出目录。部署时需要保持目录结构不变，尤其是 `/en/`、`/assets/` 和 `/search/`。

## 维护规则

- 中文页面放在 `docs/site/zh/`。
- 英文页面放在 `docs/site/en/`。
- 中英文页面尽量保持相同相对路径，方便语言切换。
- 新增正式页面后，需要同步更新 `mkdocs.yml` 的 `nav`。
- 图片和动图统一放在 `docs/site/assets/images/` 与 `docs/site/assets/gifs/`，不要从站点文档跨目录引用前端源码资源。
- 不要在 `docs/` 根目录新增可发布 Markdown；`docs/README.md` 只承担维护规则说明。
- 新增文档构建依赖时，必须同步更新 `pyproject.toml` 和 `uv.lock`。
- 不要编辑 `site/` 构建产物。
- 不要使用 git 命令。
