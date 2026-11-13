# corpus

**Agent 一直在加文档，没人删。corpus 给这一堆建索引，并报出坏在哪。**

写之前先问有没有，写完之后问哪里坏了。下面是一个六文件 demo 仓库的真实输出：

```
$ corpus find "deploy to staging"
Closest artifacts to 'deploy to staging':
  1.00  active doc    docs/guide.md  -  Guide
  1.00  active doc    docs/guide-copy.md  -  Guide

Extend docs/guide.md instead of writing a new document.

$ corpus report --noise
6 artifacts · ~67 tokens if all loaded · 2 incorrect · 0 stale · 3 noise

## Incorrect (2)
### broken-link (1)
- `README.md` - links to missing local target(s): docs/missing.md
  - fix the link target, or remove the link
### duplicate-exact (1)
- `docs/guide-copy.md` - byte-identical to docs/guide.md
  - keep docs/guide.md, archive docs/guide-copy.md

## Noise (3)
### orphan (2)
- `docs/notes-old.md` - nothing links to it, no index names it
  - link it from an index, merge it, or archive it
### scratch (1)
- `tmp-draft.md` - looks like a scratch or draft file
  - delete it, or rename it if it is real
```

## 为什么做这个

Agent 写文档的成本几乎为零，维护成本极高。几周之后一个仓库里会有：同一功能的两份计划、描述了已经搬走的 API 的 README、结论早就上线的调研笔记、四十个没人链接的文件——而每一份看起来都很权威。

相邻工具各自管一段：linter 管风格和外链，记忆工具管事实去重，spec 框架再建一个目录。**没有人管这套文档的整体**：有什么、谁取代了谁、谁没人读。

## 安装

纯标准库，Python 3.8+。

```bash
pip install git+https://github.com/Libres-coder/corpus
```

作为 Claude Code 技能：

```bash
git clone https://github.com/Libres-coder/corpus ~/.claude/skills/corpus
pip install ~/.claude/skills/corpus        # 或者 PYTHONPATH=~/.claude/skills/corpus 直接跑
```

## 命令

| 命令 | 作用 |
|---|---|
| `corpus find "主题"` | 动笔之前：是不是已经有文档讲这个 |
| `corpus report` | 哪些是错的、哪些过期了（`--noise` 看孤儿/草稿/无索引目录，`--json` 给机器读） |
| `corpus check` | CI 门禁：有 incorrect 就 exit 1（`--strict` 连 stale 也拦） |
| `corpus dupes` | 重复对，并告诉你该留哪份 |
| `corpus supersede 旧 --by 新` | 记录"新文档取代了旧文档" |
| `corpus archive / restore` | 退休 / 恢复一份文档 |
| `corpus retired` | 列出已记录的决定 |
| `corpus scan` | 重建索引缓存 `.corpus/index.json` |

`--repo` 指定仓库（默认当前目录）。`--glob` 在默认的 `**/*.md` 之上**追加**模式；`--ignore` 追加要跳过的目录。

## 严重级别

| 级别 | 含义 | 例子 | 是否拦提交 |
|---|---|---|---|
| **incorrect** | 读者会被误导 | 坏掉的本地链接、逐字节相同的副本、相似度 ≥85%、链到已退休文档 | 拦 |
| **stale** | 写的时候对，现在不对 | 它引用的代码一周后改了；相似度 70–85% | `--strict` 才拦 |
| **noise** | 没错，只是太多 | 孤儿、草稿文件、没有索引的目录 | 只报告 |

两个刻意的例外：`note`/`report` 类文件（`research/`、`notes/`、`drafts/`、`examples/`、`vendor/` 下）里的坏链只算 noise，因为这些文件常在引用别的项目；`links-retired` 只看 active 的来源。

## 它记什么

只有一个文件，建议提交进 git：

```json
// .corpus/status.json
{"paths": {"docs/plan-v1.md": {"status": "superseded", "by": "docs/plan-v2.md"}}}
```

其余（索引、链接图、相似度）每次运行都从文件本身重算。`.corpus/index.json` 只是缓存，应该进 `.gitignore`。

## 它不做什么

- 不删除、不移动、不重命名、不改写任何文件。只报告，由你决定。
- 不查外链、不查文风、不判断事实正确性。
- 找不到"换了说法说同一件事"的两份文档——近似重复基于 shingle，且只比较 400 字符以上的文件；报告只会说"在该阈值下没找到"。
- 默认不扫描 agent 状态目录（`.claude/`、`.cursor/`、`.projtruth/`、`.remember/`）和 fixtures——那是另一个语料。
- 不会报告"已经不存在的路径"，只报告"在你写完之后变了的路径"。

## 设计取向

- **预防优先于清理。** `find` 是第一个命令：最省维护成本的文档，是那份没被写出来的。
- **正确优先于整洁。** 会误导人的重复是门禁失败；孤儿只是建议。靠整洁度拦提交的工具，第三天就会被关掉。
- **决定也是数据。** `supersede`/`archive` 被记下来，"这份被取代了"能活过做决定的那个会话。
- **零依赖**，任何仓库、任何 CI 都能跑，不需要 lockfile。

## 相关项目

- [projtruth](https://github.com/Libres-coder/projtruth) —— 需求与证据：做完了没有，证据还成不成立
- [skill-audit](https://github.com/Libres-coder/skill-audit) —— 同一问题在技能集合上的版本
- [verify-first](https://github.com/Libres-coder/verify-first) —— 产出 projtruth 所读证据的流水线

## 许可证

MIT
