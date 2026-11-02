<p align="center">
  <img src="https://raw.githubusercontent.com/Root-7-KHX/ai-voice/main/icon.svg" width="96" height="96" alt="ai-voice icon" />
</p>

<h1 align="center">AI语音 · ai-voice</h1>

<p align="center">
  给 DeepSeek Harness 用的本地语音工作台：文字描述造声音、录音/参考音复刻、哭腔笑声等情绪表演。<br/>
  两个引擎都在本机 CPU 上跑，模型与 Python 环境放在插件外，由你在面板里指定路径。
</p>

<p align="center">
  <a href="https://github.com/Root-7-KHX/ai-voice/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Root-7-KHX/ai-voice?color=blue" alt="license" /></a>
  <img src="https://img.shields.io/badge/DSH-plugin-6f42c1" alt="DSH plugin" />
  <img src="https://img.shields.io/badge/Node-%E2%89%A522-339933" alt="node" />
</p>

---

## 这是什么

AI语音 是 DeepSeek Harness 的一个独立插件（`@local/ai-voice`），提供一个本地音色工作台：

- **声音设计（VoxCPM2）**：写一句音色描述（例：「温柔软糯的年轻女声，二十多岁，语速偏慢」）+ 要念的内容，生成一段音频；可以试听、下载，或一键存进参考音库。
- **带情绪说话（IndexTTS-2.5）**：选一个参考音，写台词，从 10 种情绪里挑（平静 / 开心 / 大笑 / 悲伤 / 哭腔 / 生气 / 害怕 / 惊讶 / 撒娇 / 疲惫），再调情绪强度和语速，合成带情绪的语音。
- **台词栏回车即合成**：单行输入，回车直接开始合成；合成完自动清空，生成的语音就排在输入栏下面（每行都带生成时间和用时）。
- **同一个页面只放一条**：点哪条音频就停掉正在放的那条，换一条播自动切过去，不会几条声音同时响。
- **参考音库**：生成的声音或上传的 wav 录音都能当参考音，可试听、下载、删除。
- **本机生成、本机保存**：参考音和生成结果只存在本机数据目录，不上传任何服务器。

> 模型、Python 虚拟环境不随仓库分发（体积太大，也方便你换模型 / 升级）；仓库里只有 DSH 插件代码和两个调用脚本。

## 界面在哪里

AI语音 的 Host 半边只注册 `/ai-voice/api/*` 接口。界面挂在 **AI记忆（companion-memory）插件** 的「接入软件」页里：装好两个插件后，打开侧边栏「AI记忆 → 接入软件 → AI语音 → 打开」即可（插件启动时会自动登记一张清单卡片）。

## 安装

1. 把本仓库放进 DSH profile 的 `node_modules`（或在 profile 目录里 `pnpm add file:D:/path/to/ai-voice`）；
2. 装好 [AI记忆 companion-memory](https://github.com/Root-7-KHX/companion-memory)（提供「接入软件」页与应用页壳）；
3. 重载 DSH 插件（桌面版可以完全退出 DSH Desktop 再打开）；
4. 打开 AI记忆 → 接入软件，找到「AI语音」，点「打开」，在「设置」里填 Python 路径和模型目录。

### 引擎与模型

| 引擎 | 用途 | 设置里要填 |
| --- | --- | --- |
| VoxCPM2 | 文字描述造声音 | VoxCPM2 Python 路径、VoxCPM2 模型目录 |
| IndexTTS-2.5 | 参考音 + 情绪合成 | IndexTTS-2.5 Python 路径、IndexTTS-2.5 模型目录 |

两个引擎各自跑在独立的 Python 虚拟环境里。模型目录里分别要有 VoxCPM2 的 `config.json` 和 IndexTTS-2.5 的 `config.yaml`；模型和虚拟环境要你自己下载 / 创建，插件不打包。

### 数据目录

默认 `<DSH_HOME>/ai-voice/`（桌面版一般是 `C:\Users\<你>\.dsh\ai-voice`）：

- `audio/`：生成的音频
- `refs/`：参考音库
- `config.json`：面板里保存的 Python / 模型路径与开关

## 接口

面板通过同源 `GET/POST /ai-voice/api/*` 使用：`status`、`emotions`、`files`、`file`、`job`、`design`、`speak`、`enabled`、`job/cancel`、`upload`、`copy-to-ref`、`delete`、`open`、`config`。响应统一为 `{ ok: true, value }` / `{ ok: false, error: { message } }`，且只接受本机请求。

## 本地校验

纯 ESM、无构建步骤（Node ≥ 22 即可）：

```bash
node --check index.js
for f in lib/*.js; do node --check "$f"; done
```

## 来源与声明

- 引擎来源：**VoxCPM2**（OpenBMB，Apache-2.0 许可）· https://github.com/OpenBMB/VoxCPM ；**IndexTTS-2.5**（bilibili IndexTeam，bilibili 模型使用许可）· https://github.com/index-tts/index-tts 。
- 本插件只负责本机调用与界面；模型与权重的版权归原作者，使用请遵守各自许可证。
- 所有语音都在本机生成、只存本机，不上传网络。
- 克隆或使用他人声音须事先取得本人同意；禁止冒充他人、诈骗等违法用途，由此产生的后果由使用者自己承担。

## License

[MIT](LICENSE) © 2026 [Root-7-KHX](https://github.com/Root-7-KHX)
