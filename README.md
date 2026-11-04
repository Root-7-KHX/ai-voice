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
- **每个结果都带小字备注**：生成的音频旁边会标出当时写的音色描述 / 台词 / 情绪参数（参数同时存进音频旁边的同名 `.json`，删音频时一起删）。
- **参考音克隆（VoxCPM2）**：声音设计卡片顶部可以选一个参考音（wav），选好后就「用那个声音继续说」，不用再写音色描述；参考音可以上传，也可以把生成结果「存为参考音」。
- **情感指令（Qwen3-TTS 0.6B，本地 CPU）**：自带 9 个说话人，写一句自然语言指令（"用开心的语气说"）就能控情绪 / 语气；也可以选参考音做声音克隆（用额外的 Base 模型）；短句在 CPU 上约 10~20 秒，是三个引擎里最快的。
- **另有 6 个本地引擎（2026-11-03 接入）**：Spark-TTS、CosyVoice3、OpenAudio S1-mini（Fish-Speech）、GPT-SoVITS、F5-TTS、Kokoro —— 都是本地 CPU 跑，界面卡片和上面几个一样：选参考音 / 填台词 / 生成 / 列表试听下载。Kokoro 是预设音色（不用参考音），速度最快；其余 5 个是声音克隆（部分支持年代语气指令 / 参考音台词）。
- **文件名就是提示词**：声音设计用音色描述当文件名、带情绪说话用台词当文件名；重名自动在后面加 `(1)`、`(2)`…；已经生成的旧样本也会在插件启动时自动改名。存为参考音同样用提示词命名。中文文件名也能正常播放 / 下载 / 删除。
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
| VoxCPM2 | 文字描述造声音 / 参考音克隆 | VoxCPM2 Python 路径、VoxCPM2 模型目录 |
| IndexTTS-2.5 | 参考音 + 情绪合成 | IndexTTS-2.5 Python 路径、IndexTTS-2.5 模型目录 |
| Qwen3-TTS 0.6B（CustomVoice） | 文本 + 9 个说话人 + 情绪指令 | Qwen3-TTS Python 路径、CustomVoice 模型目录 |
| Qwen3-TTS 0.6B（Base） | 参考音克隆（用参考音的声音念） | Base 模型目录（设置里单独一项） |
| Spark-TTS | 参考音克隆 | Spark-TTS Python 路径、模型目录 |
| CosyVoice3 | 参考音克隆 + 语气指令 | CosyVoice3 Python 路径、模型目录 |
| OpenAudio S1-mini（Fish-Speech） | 参考音克隆（台词可写 [laugh] 等情绪标记） | OpenAudio S1-mini Python 路径、模型目录 |
| GPT-SoVITS | 参考音 + 参考音台词克隆 | GPT-SoVITS Python 路径、模型目录 |
| F5-TTS | 参考音 + 参考音台词克隆 | F5-TTS Python 路径、模型目录 |
| Kokoro-82M | 预设音色（不用参考音）+ 语速 | Kokoro Python 路径、模型目录 |

每个引擎各跑在自己的 Python 虚拟环境里（互相不干扰）。模型目录里要有对应的权重文件（见 `D:\AI\语音POC\TTS模型清单.md` 的清单）；模型和虚拟环境要自己下载 / 创建，插件不打包。

### 数据目录

默认 `<DSH_HOME>/ai-voice/`（桌面版一般是 `C:\Users\<你>\.dsh\ai-voice`）：

- `audio/design/`：声音设计生成的音频（旁边同名 `.json` 记录提示词 / 台词 / 用时）
- `audio/speak/`：带情绪说话合成的音频（旁边同名 `.json` 记录台词 / 情绪 / 强度 / 语速 / 参考音 / 用时）
- `audio/qwen/`：Qwen3-TTS 情感指令合成的音频（旁边同名 `.json` 记录台词 / 说话人 / 情绪指令）
- `audio/spark/`、`audio/cosyvoice/`、`audio/fish/`、`audio/gptsovits/`、`audio/f5/`、`audio/kokoro/`：
  六个新引擎各自生成的音频（旁边同名 `.json` 记录台词 / 参考音 / 参考音台词 / 语气指令 / 音色 / 语速）
- `refs/`：参考音库
- `config.json`：面板里保存的 Python / 模型路径与开关

两个生成目录分开存：面板里「声音设计」和「带情绪说话」各看各的列表，磁盘上也各在各的文件夹。旧版本放在 `audio/` 根目录的音频，插件更新后启动时会按文件名前缀自动搬进 `design/`（`design_*`）和 `speak/`（`voice_*`），不认识的留在原地。

## 接口

面板通过同源 `GET/POST /ai-voice/api/*` 使用：`status`、`emotions`、`files`、`file`、`job`、`design`、`speak`、`qwen`、`enabled`、`job/cancel`、`upload`、`copy-to-ref`、`delete`、`open`、`config`；六个新引擎各有一条生成路由：`spark`、`cosyvoice`、`fish`、`gptsovits`、`f5`、`kokoro`。响应统一为 `{ ok: true, value }` / `{ ok: false, error: { message } }`，且只接受本机请求。

`files` / `file` 的 `dir` 支持 `design`（声音设计）、`speak`（情绪合成）、`qwen`（情感指令）、`ref`（参考音）、六个新引擎目录（`spark` / `cosyvoice` / `fish` / `gptsovits` / `f5` / `kokoro`）、`audio`（旧根目录）；`copy-to-ref` / `delete` 也按 `dir` 找文件。

## 本地校验

纯 ESM、无构建步骤（Node ≥ 22 即可）：

```bash
node --check index.js
for f in lib/*.js; do node --check "$f"; done
```

## 来源与声明

- 引擎来源：**VoxCPM2**（OpenBMB，Apache-2.0 许可）· https://github.com/OpenBMB/VoxCPM ；**IndexTTS-2.5**（bilibili IndexTeam，bilibili 模型使用许可）· https://github.com/index-tts/index-tts ；**Qwen3-TTS 0.6B**（阿里通义千问，Apache-2.0 许可）· https://github.com/QwenLM/Qwen3-TTS ；**Spark-TTS**（SparkAudio，Apache-2.0 许可）· https://github.com/SparkAudio/Spark-TTS ；**CosyVoice3**（FunAudioLLM / 阿里通义，Apache-2.0 许可）· https://github.com/FunAudioLLM/CosyVoice ；**OpenAudio S1-mini / Fish-Speech**（FishAudio）· https://github.com/fishaudio/fish-speech ；**GPT-SoVITS**（RVC-Boss 社区项目）· https://github.com/RVC-Boss/GPT-SoVITS ；**F5-TTS**（SWivid 等，MIT 代码许可）· https://github.com/SWivid/F5-TTS ；**Kokoro-82M**（hexgrad，Apache-2.0 许可）· https://huggingface.co/hexgrad/Kokoro-82M 。
- 本插件只负责本机调用与界面；模型与权重的版权归原作者，使用请遵守各自许可证。
- 所有语音都在本机生成、只存本机，不上传网络。
- 克隆或使用他人声音须事先取得本人同意；禁止冒充他人、诈骗等违法用途，由此产生的后果由使用者自己承担。

## 常见问题

- **IndexTTS 的 Python 一启动就报 `UnicodeDecodeError: 'gbk' codec can't decode ...`（堆栈在 `site.py`）**：多半是虚拟环境里 editable 安装的 `.pth` 文件被写成了 UTF-8；把那个 `.pth` 用记事本另存为 ANSI 编码即可。
- **两个列表是空的**：确认「设置」里的 Python / 模型目录填对，且「引擎」那一行显示「就绪」；生成完成后列表会自动刷新。
- **生成的时候电脑卡、鼠标滚轮像失灵**：本地 TTS 推理会把 CPU 打满（默认按核心数开线程），桌面渲染抢不到时间片。插件已经把生成进程降成 BelowNormal 优先级、并把推理线程默认限制到一半核心；「设置」里还能手动调「本地推理占用线程数」（0 = 自动，嫌慢调大、嫌卡调小）。生成结束界面立刻恢复。

## License

[MIT](LICENSE) © 2026 [Root-7-KHX](https://github.com/Root-7-KHX)
