# blog-skill

面向 Codex 的中文图文生产技能：资料核查、选题、博客/帖子/公众号成文、真实截图、解释图、封面、Markdown、公众号富文本、预览、打包与修改反馈。

## 安装与开始

将整个 `blog-skill` 目录放到 `~/.codex/skills/`（自定义 CODEX_HOME 时使用对应目录），打开新会话。依赖为真实 Python 3.10+、Node.js >=20.18.1 和中文字体。Windows 自动尝试 Codex 提供的 Node 运行时；也可通过 BLOG_SKILL_NODE 指定。

从技能目录运行：

```text
python scripts/bootstrap.py
python scripts/blog.py doctor
```

安装器使用本技能独立的 `.runtime/`，不修改其他技能。可用 `--index-url`、`--npm-registry` 为本次安装指定镜像。基础 Python 库按需安装，Node 依赖按锁文件安装；浏览器使用 Playwright Chromium。没有付费 API、FFmpeg 或 TTS 要求。

在 Codex 中直接说：

```text
用 $blog-skill，围绕【题材】联网查资料，面向【读者】写一篇公众号文章。
直接完成正文、真实相关截图、封面和公众号排版，检查后把成品给我。
```

```text
用 $blog-skill 把这个题材分别写成博客、微信公众号文章和社区帖子。
共享事实材料，分别改写结构；交付成稿、配图、元数据和预览。
```

Codex 负责研究、写作和审稿，命令行工具负责可重复的执行与检查；仅运行 init 不会自动产生一篇文章。按 [SKILL.md](SKILL.md) 完整运行到 finalize 才交付。

新建公众号项目默认开启 `include_cover: true` 和 `summary_max_chars: 120`：封面随正文复制，推广描述限制在120字符以内。博客、帖子保持自己的配置；用户本次明确要求不放首图时可在项目中关闭。

## 成品怎么用

打开成品包的 `index.html` 查看各平台文章。Markdown 用于编辑或博客导入；`wechat.html` 的复制按钮包含正文排版和实际图片数据；`wechat-copy.html` 是可离线使用的内嵌图片图文，`wechat-body.html` 是搭配 `assets/` 的普通正文片段。浏览器检查会实际粘贴并在阻断来源请求后比对图片，不代表已验证公众号后台接收。教程用图须遮盖用户名、头像、邮箱等身份资料；核查与素材许可另存文件，不自动追加在正文末尾。横、方封面与发布标题、摘要一起提供。

公众号另交付 `wechat-description.txt`，用于文章推广页。本账号要求 120 字符以内，文案与元数据一致。横版封面默认放在正文首段之前，随复制按钮、离线图文与Markdown一起导出，无重复图注。用户手改稿优先作为底稿；封面、标题、描述和开头覆盖同一目标人群，示例金额不能缩窄领取范围。

本地成品、公众号后台草稿、公开发布分别记录。基础工具不读取公众号密钥，也不会自动对外发文。用户需要账号操作时，再按明确请求接入并核验。

## 检查与来源

```text
python -m unittest discover -s scripts -p "test_*.py"
```

`verify` 实际检查正文首图的位置和图像字节，并在关闭来源页面、阻断请求后，将富文本粘贴到独立编辑框，逐图比对像素。每张配图和代码块都生成可供审查的截图。缺少实际图文粘贴证明时，`finalize` 会拒绝完成；开启正文封面时也须通过首图核验。这些检查不能代替文案编辑和逐图隐私复核。

测试还覆盖代码保真、缺图、截图记录、旧稿失效、便携源项目、反馈和数据窗口。

研究采集和运行助手从 video-skill 独立改造；中文编辑指导改编自 MIT 授权的 Humanizer-zh，记录与许可证见 `third_party/`。Markdown、代码高亮和 CSS 内联使用锁定的 marked、highlight.js、juice 包，各依赖保留其许可证。方法依据与使用范围见技能参考。
