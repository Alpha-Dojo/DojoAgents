# Skills

Skills 是给 Agent 使用的过程性知识、工具说明和工作流提示。DojoAgents 会在 runtime 初始化时从多个目录加载 `*/SKILL.md`，并通过 `skills_list`、`skill_view` 和 skill 管理工具暴露给 Agent。

## 默认加载路径

默认配置下，DojoAgents 会加载：

| 来源 | 路径 | 说明 |
| --- | --- | --- |
| 用户 skills | `~/.dojo/skills` | 主要的个人 skill 目录 |
| 生成 skills | `~/.dojo/skills/generated` | memory 或工具生成的 skill |
| 内置 skills | `dojoagents/skills/built_in/` | 仓库随包提供的 skill |
| 外部目录 | `skills.external_dirs` | 用户在配置中额外声明的目录 |
| 插件目录 | plugin registry 提供 | 插件可以贡献 skill 目录 |

每个 skill 使用一个目录，目录下放置 `SKILL.md`：

```text
~/.dojo/skills/
└── my-skill/
    └── SKILL.md
```

`SKILL.md` 推荐带 YAML frontmatter：

```markdown
---
name: my-skill
description: When to use this skill.
category: finance
platforms:
  - macos
---

# My Skill

具体步骤、约束和示例。
```

## 配置

在 `~/.dojo/agents.yaml` 中配置：

```yaml
skills:
  dir: ~/.dojo/skills
  generated_skill_dir: ~/.dojo/skills/generated
  external_dirs:
    - ~/work/shared-dojo-skills
  disabled:
    - old-skill
  platform_disabled:
    dashboard:
      - terminal-heavy-skill
  read_claude_skills: false
```

字段说明：

- `dir`：主用户 skill 目录，也是 skill 管理工具创建/编辑 skill 的默认目录。
- `generated_skill_dir`：自动生成 skill 的目录。
- `external_dirs`：额外 skill 根目录列表。
- `disabled`：全局禁用的 skill 名称。
- `platform_disabled`：按平台禁用 skill。
- `read_claude_skills`：是否额外读取 Claude Code skills。

## 开启 Claude Code Skills 适配

Claude Code skills 通常位于：

```text
~/.claude/skills
```

开启适配：

```yaml
skills:
  read_claude_skills: true
```

开启后，runtime 会把 `~/.claude/skills` 追加到 skill 搜索路径。目录格式仍按 DojoAgents 的 loader 规则读取：每个 skill 是一个子目录，子目录中包含 `SKILL.md`。

示例：

```text
~/.claude/skills/
└── spreadsheet-helper/
    └── SKILL.md
```

如果只想加载某个 Claude skills 目录，也可以不用全局开关，改用 `external_dirs`：

```yaml
skills:
  external_dirs:
    - ~/.claude/skills
```

两种方式的区别：

| 方法 | 适用场景 |
| --- | --- |
| `read_claude_skills: true` | 直接兼容默认 Claude Code skills 目录 |
| `external_dirs: [~/.claude/skills]` | 想显式控制加载目录，或加载非默认位置 |

## 加载行为

- `agent.lazy_skills: true` 时，Agent 先看到 skill catalog，需要通过 `skill_view` 读取完整内容。
- `agent.enable_skill_cache: true` 时，解析结果会缓存在主 skill 目录的 `.skills_cache.json`。
- frontmatter 中的 `platforms` 可限制 skill 只在指定系统加载。
- frontmatter 中的 `requires_tools` 可要求指定工具可用后才加载。
- 同名 skill 只加载第一次出现的版本；路径顺序由 runtime 组装顺序决定。

## 相关模块

| 模块 | 说明 |
| --- | --- |
| `dojoagents/skills/loader.py` | 读取 skill prompt block |
| `dojoagents/skills/cache.py` | 缓存 skill 内容 |
| `dojoagents/skills/manager.py` | 解析、过滤和管理 skill |
| `dojoagents/tools/skill_manage.py` | 暴露 skill 创建、列表、查看工具 |
| `dojoagents/agent/runtime.py` | 组装 skill 搜索路径 |

## 下一步

- 需要扩展工具能力时，阅读 [添加工具](../development/adding-tools.md)。
- 需要了解配置字段时，阅读 [配置](../reference/configuration.md)。
