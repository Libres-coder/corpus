# corpus

**Agent 一直在加文档，没人删。corpus 管这一堆。**

写之前先问有没有，写完之后问哪里坏了：

```
$ corpus find "如何发布到 staging"
Closest artifacts to '如何发布到 staging':
  0.71  active readme skill-audit/README.md  - Audit installed Claude Code skills
  0.43  active doc    projtruth/README.md    - projtruth
Extend skill-audit/README.md instead of writing a new document.

$ corpus report
292 artifacts · ~528888 tokens if all loaded · 1 incorrect · 1 stale · 19 noise
```

## 为什么做这个

Agent 写文档的成本几乎为零，维护成本极高。几周之后一个仓库里会有：同一功能的两份计划、描述了已经搬走的 API 的 README、结论早就上线的调研笔记、四十个没人链接的文件——而每一份看起来都很权威。

现有工具各自管一段：linter 管风格和外链，记忆工具管事实去重，spec 框架再建一个目录。**没有人管这套文档的整体**：有什么、谁取代了谁、谁没人读。

## 安装

纯标准库，Python 3.8+。

```bash
pip install git+https://github.com/Libres-coder/corpus
# 或作为 Claude Code 技能：
git clone https://github.com/Libres-coder/corpus ~/.claude/skills/corpus
```

## 命令

| 命令 | 作用 |
|---|---|
| `corpus find "主题"` | 动笔之前：是不是已经有文档讲这个 |
| `corpus report` | 哪些是错的、哪些过期了（`--noise` 看孤儿/草稿/无索引目录） |
| `corpus check` | CI 门禁：有 incorrect 就 exit 1（`--strict` 连 stale 也拦） |
| `corpus dupes` | 近似重复对，并告诉你该留哪份 |
| `corpus supersede 旧 --by 新` | 记录"新文档取代了旧文档" |
| `corpus archive / restore` | 退休 / 恢复一份文档 |
| `corpus scan` | 重建索引缓存 `.corpus/index.json` |

## 严重级别

| 级别 | 含义 | 例子 | 是否拦提交 |
|---|---|---|---|
| **incorrect** | 读者会被误导 | 坏掉的本地链接、逐字节相同的副本、链到已退休文档 | 拦 |
| **stale** | 写的时候对，现在不对 | 它引用的代码一周后改了 | `--strict` 才拦 |
| **noise** | 没错，只是太多 | 孤儿、草稿文件、没有索引的目录 | 只报告 |

只有 incorrect 默认拦提交；其余是判断，每条都给出一个建议动作。

## 它记什么

只有一个文件，建议提交进 git：

```json
// .corpus/status.json
{"paths": {"docs/plan-v1.md": {"status": "superseded", "by": "docs/plan-v2.md"}}}
```

其余（索引、链接图、相似度）每次运行都从文件本身重算，没有需要同步的状态。

## 它不做什么

- 不删除、不移动、不重命名、不改写任何文件。只报告，由你决定。
- 不查外链、不查文风、不判断事实正确性。
- 找不到"换了说法说同一件事"的两份文档——近似重复是基于 shingle 的，报告只会说"在该阈值下没找到"。
- 不替代 git：每个决定也应该写进 commit message。

## 相关项目

- [projtruth](https://github.com/Libres-coder/projtruth) —— 需求与证据：做完了没有，证据还成不成立
- [skill-audit](https://github.com/Libres-coder/skill-audit) —— 同一问题在技能集合上的版本
- [verify-first](https://github.com/Libres-coder/verify-first) —— 产出 projtruth 所读证据的流水线

## 许可证

MIT
