# Official pricing fixture provenance

这些文件是用于确定性测试的最小 HTML snapshots，只保留验证核心价格语义所需的官方页面片段，不包含搜索 snippet 或完整网页副本。

| Fixture | Official source | Observed |
|---|---|---|
| `github-copilot.html` | <https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-copilot/about-billing-for-github-copilot> | 2026-09-06 |
| `cursor.html` | <https://cursor.com/pricing> | 2026-09-06 |
| `replit.html` | <https://replit.com/pricing> | 2026-09-06 |
| `claude.html` | <https://support.claude.com/en/articles/11049762-choose-a-claude-plan> | 2026-09-06 |

价格页面会变化。更新 fixture 时必须同时更新 `cases.json` 的 golden claims，并说明内容变化；live 页面不能自动覆盖这些 snapshots。
