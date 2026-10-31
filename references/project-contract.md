# 项目契约与运行

需要 Python 3.10+、Node.js >=20.18.1、中文字体。`bootstrap.py` 将缺少的 Python 库和锁定的 Node 依赖放进技能 `.runtime/`；使用已有或安装 Playwright Chromium。无 FFmpeg、TTS、Easel 或外部模型要求。`doctor` 的通过表示本地工具可用，不代表文章已审或微信后台已验证。

主命令：init、doctor、discover、fetch、capture、annotate、cover、diagram、preflight、render、verify、review-hashes、finalize、feedback、brief、metrics。通过 --help 查看每项实际参数。

项目与所有素材路径相对于 project.json，或使用明确的绝对路径。输出目录必须与输入稿件/素材分开。init 只创建任务骨架，后续由 Codex 填写研究和文章，不生成假资料。

```json
{
  "title": "文章标题",
  "summary": "实际撰写的摘要",
  "audience": "目标读者和已有基础",
  "purpose": "本文解决的具体问题",
  "approval_status": "direct",
  "research_mode": "web",
  "research_file": "research.json",
  "review_file": "review.json",
  "platforms": {
    "wechat": {"file": "drafts/wechat.md", "title": "平台标题", "summary": "推广页描述", "summary_max_chars": 120, "include_cover": true, "tags": ["AI", "写作"]}
  },
  "assets": [
    {"id": "flow", "path": "assets/flow.png", "role": "diagram", "rights": {"kind": "owned"}}
  ],
  "evidence_map": [
    {"platform": "wechat", "section": "正文中实际出现的标题", "claim_ids": ["c1"], "asset_ids": ["flow"]}
  ]
}
```

platforms 可选 blog、wechat、post，都是独立文件。可选字段：author、tags、cover.title/cover.subtitle、每个平台的 slug。Markdown 稿件用首个 H1 表示标题，正文保持普通 Markdown；图片仅支持注册的 asset:id 形式。文章中的代码与图解要有解释。

每个平台可用 summary_max_chars 设正整数上限；预检计入标点、空格及英文字符，超限直接报错，不自动截断正文或破坏限定条件。本账号公众号设 120，并为推广页单独撰写 summary。渲染导出 wechat-description.txt，publication.json 记录同一文案及实际字符数。

`init` 为公众号默认设置 `summary_max_chars: 120` 和 `include_cover: true`，博客与帖子不受影响；现有项目不自动改写。`platforms.wechat.include_cover` 为布尔值，将横版封面加入正文开头、导出Markdown和实际图文剪贴板；源稿无需手动加入封面资产，重渲染仍只插入一次。封面保持独立用途和权利记录，教程证据素材的真实截图校验继续执行。用户本次明确不放首图时可设 false。

操作教程使用 `visual_policy: "real_ui_only"`。该模式所有正文注册图片必须为带真实捕获记录的 `role: "screenshot"`，生成示意图在预检阶段被拒绝；未另行指定推广封面时，`cover` 用 `wide_asset` 和 `square_asset` 指向已有截图 ID。截图可重复用作封面；若需要不同裁切，单独捕获并注册相应图片。渲染保留这些实际图像和来源，不自动生成封面。非教程项目默认 `visual_policy: "flexible"`，保留现有能力；这不是用来跳过用户禁用自制图要求的开关。

用户明确要求独立推广封面时，`cover` 也可设为 `{"design":{"wide_file":"covers/wide.png","square_file":"covers/square.png","rights":{"kind":"owned"}}}`。两张实际栅格文件都须存在；它与截图封面ID互斥。此项仅更换封面，`real_ui_only` 对正文图的验证仍完整执行，不能以此导入自制教程图。导出后文件与路径随包保存，可独立重渲染。

`annotate --input <原截图> --output <新 PNG> --source-asset <原截图ID> --operations <JSON>` 可在全局截图上标注。operations 为数组：`{"type":"rect","box":[左,上,右,下],"width":6}`、`{"type":"arrow","points":[起点X,起点Y,终点X,终点Y],"width":6}`，或用于遮盖个人资料的 `redact` 框；坐标使用原图像素。原图与标注图都注册为 screenshot。标注记录以 `source_asset_id` 引用原截图，预检会验证原图哈希、画布尺寸，并重放处理来确认其他像素未变化。完整原图和处理记录在导出包中可重用。

`capture --full-page` 截取整个页面；若同时传入 `--selector`，则截取整个选中元素（例如完整设置窗口或公开教程原图），不按 height/clip-height 裁断。普通视口截图仍可用于已完整显示操作上下文的页面。

research_mode：web 用于联网核查的新事实，provided 用于提供的材料，none 用于不需要外部事实的创作。不能为了跳过研究把新闻标 none。research 包含实际 searches（query/result_urls）、sources（id/url/title/checked_at）和 claims（id/text/source_ids/status）。关键条件可额外放 scope 字段。各平台 evidence_map 的 section 必须在对应稿件标题中，源和素材 ID 必须存在，成品不接受 unverified 结论。

preflight --stage draft 用于尚在计划/草稿阶段的检查；produce 必须有已写稿、实际素材、权利声明、研究对应和 approved/direct 授权状态。待用户批准的项目不能先渲染成品。

render 产生 rendered_pending_review 和 render_id。verify 成功生成 verification.json 和实际截图，其中 cover_in_body 记录首图检查，clipboard 记录真实复制粘贴检查。每个图/代码块都生成审查截图。审稿人在 review.json 保存 status=reviewed、reviewer、review-hashes 输出的 content_hashes、findings，以及 visual_review 的 render_id、实际看过的 screenshots 和具体 notes。findings 每条写 issue、change、status=resolved 或 accepted_with_reason。

finalize 校验当前项目/稿件哈希、渲染文件、浏览器核验和审稿对应；公众号必须有成功的实际图文粘贴证明，开启首图时还须有对应的首图核验。通过后生成 ready_local 状态、交付说明和 ZIP。它不凭技术校验保证文案质量，不会调用任何发布接口。包中 source/ 保留可重渲染项目，图片和草稿路径已经调整为包内相对路径。

文章变更后重新 render、verify、全文/视觉复核、finalize；旧检查不能沿用。网络失败、缺图、未完成占位内容、错误图解源、损坏的截图记录、代码变化或页面溢出会阻止完成；按实际失败修复，不把失败报告改成成功。
