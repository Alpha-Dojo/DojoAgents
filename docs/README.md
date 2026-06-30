# DojoAgents 文档站维护说明

本目录包含 DojoAgents 的 MkDocs 在线文档源文件和历史规划文档。

## 目录结构

```text
docs/
├── README.md          # 本文件
├── site/              # MkDocs 正式站点内容
│   ├── zh/            # 中文站点，默认发布到 /
│   └── en/            # 英文站点，发布到 /en/
└── plans/             # 设计方案、升级规划和历史计划
```

正式文档只维护在 `docs/site/` 下。正式站点只包含当前指南、架构、Reference 和开发文档；历史规划、迁移记录、原型讨论保存在 `docs/plans/`，不进入正式站点导航。

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
- 新增文档构建依赖时，必须同步更新 `pyproject.toml` 和 `uv.lock`。
- 不要编辑 `site/` 构建产物。
- 不要使用 git 命令。
