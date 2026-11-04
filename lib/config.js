/**
 * ai-voice · 配置与数据目录
 *
 * 数据默认放 {DSH_HOME}/ai-voice（默认 C:\Users\<你>\.dsh\ai-voice）：
 *   config.json   面板设置（python 路径、模型目录等）
 *   refs/         参考音（音色库）
 *   audio/design/ 声音设计生成的音频
 *   audio/speak/  带情绪说话生成的音频
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const PLUGIN_DIR = join(dirname(fileURLToPath(import.meta.url)), '..')

export const DEFAULTS = {
  enabled: true,
  voxcpmPython: 'D:\\AI\\语音POC\\venv\\Scripts\\python.exe',
  voxcpmModel: 'D:\\AI\\语音POC\\models\\models\\OpenBMB--VoxCPM2\\snapshots\\master',
  indexttsPython: 'D:\\AI\\语音POC\\venv-tts\\Scripts\\python.exe',
  indexttsModel: 'D:\\AI\\语音POC\\models\\models\\IndexTeam--IndexTTS-2.5\\snapshots\\master',
  qwen3ttsPython: 'D:\\AI\\语音POC\\venv-qwen3tts\\Scripts\\python.exe',
  qwen3ttsModel: 'D:\\AI\\语音POC\\models\\models\\Qwen3-TTS-12Hz-0.6B-CustomVoice',
  qwen3ttsBaseModel: 'D:\\AI\\语音POC\\models\\models\\Qwen3-TTS-12Hz-0.6B-Base',
  defaultRef: '',
  // 本地推理占几个线程：0 = 自动（一半逻辑核心，给界面留余量）
  inferenceThreads: 0,
  // ── 2026-11-03 新接入的 6 个引擎 ──
  sparkPython: 'D:\\AI\\语音POC\\venv-spark\\Scripts\\python.exe',
  sparkModel: 'D:\\AI\\语音POC\\models\\models\\SparkAudio--Spark-TTS-0.5B\\snapshots\\master',
  cosyvoicePython: 'D:\\AI\\语音POC\\venv-cosyvoice\\Scripts\\python.exe',
  cosyvoiceModel: 'D:\\AI\\语音POC\\models\\models\\FunAudioLLM--Fun-CosyVoice3-0.5B-2512\\snapshots\\master',
  fishPython: 'D:\\AI\\语音POC\\venv-fish\\Scripts\\python.exe',
  fishModel: 'D:\\AI\\语音POC\\models\\models\\fishaudio--openaudio-s1-mini\\snapshots\\master',
  gptsovitsPython: 'D:\\AI\\语音POC\\venv-gptsovits\\Scripts\\python.exe',
  gptsovitsModel: 'D:\\AI\\语音POC\\models\\models\\AI-ModelScope--GPT-SoVITS\\snapshots\\master',
  f5Python: 'D:\\AI\\语音POC\\venv-f5\\Scripts\\python.exe',
  f5Model: 'D:\\AI\\语音POC\\models\\models\\AI-ModelScope--F5-TTS\\snapshots\\master',
  kokoroPython: 'D:\\AI\\语音POC\\venv-kokoro\\Scripts\\python.exe',
  kokoroModel: 'D:\\AI\\语音POC\\models\\models\\AI-ModelScope--Kokoro-82M\\snapshots\\master',
}

/**
 * 新接入引擎的统一描述：key 同时用作 audio/<key>/ 目录名、面板卡片 key、接口路由。
 * ref: 'required' | 'optional' | 'none'（是否需要参考音）
 * refText / instruct / speed / lang：这些输入框是否显示、是否必填
 */
export const EXTRA_ENGINES = {
  spark: {
    label: 'Spark-TTS',
    script: 'spark.py',
    pythonKey: 'sparkPython',
    modelKey: 'sparkModel',
    readyFile: 'LLM/model.safetensors',
    ref: 'required', refText: false, instruct: false, speed: false, lang: false, voice: false,
  },
  cosyvoice: {
    label: 'CosyVoice3',
    script: 'cosyvoice.py',
    pythonKey: 'cosyvoicePython',
    modelKey: 'cosyvoiceModel',
    readyFile: 'llm.pt',
    ref: 'required', refText: true, refTextRequired: false, instruct: true, speed: false, lang: false, voice: false, threads: true,
  },
  fish: {
    label: 'OpenAudio S1-mini',
    script: 'fish.py',
    pythonKey: 'fishPython',
    modelKey: 'fishModel',
    readyFile: 'model.pth',
    ref: 'required', refText: false, instruct: true, speed: false, lang: false, voice: false,
  },
  gptsovits: {
    label: 'GPT-SoVITS',
    script: 'gptsovits.py',
    pythonKey: 'gptsovitsPython',
    modelKey: 'gptsovitsModel',
    readyFile: 'gsv-v4-pretrained/s2Gv4.pth',
    ref: 'required', refText: true, refTextRequired: true, instruct: false, speed: false, lang: true, voice: false,
  },
  f5: {
    label: 'F5-TTS',
    script: 'f5.py',
    pythonKey: 'f5Python',
    modelKey: 'f5Model',
    readyFile: 'F5TTS_v1_Base/model_1250000.safetensors',
    ref: 'required', refText: true, refTextRequired: true, instruct: false, speed: false, lang: false, voice: false, threads: true,
  },
  kokoro: {
    label: 'Kokoro',
    script: 'kokoro.py',
    pythonKey: 'kokoroPython',
    modelKey: 'kokoroModel',
    readyFile: 'kokoro-v1_0.pth',
    ref: 'none', refText: false, instruct: false, speed: true, lang: false, voice: true,
  },
}

export const EXTRA_ENGINE_KEYS = Object.keys(EXTRA_ENGINES)

function resolveRoot(config = {}) {
  const configured = typeof config.dataDir === 'string' ? config.dataDir.trim() : ''
  if (configured !== '') return configured
  const home = process.env.DSH_HOME
  if (typeof home === 'string' && home !== '') return join(home, 'ai-voice')
  return join(homedir(), '.dsh', 'ai-voice')
}

export function safeName(value) {
  const raw = String(value ?? '').trim()
  if (raw === '') return ''
  const base = raw
    .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, '_')
    .replace(/[^\p{L}\p{N}._\-() ，,。、！？!?：；;…（）]+/gu, '_')
    .replace(/^[.\s]+/, '')
    .replace(/[.\s]+$/, '')
    .slice(0, 80)
  return base
}

/** 生成样本/参考音用「提示词」当名字：清洗后截到 40 字。 */
export function promptBase(prompt) {
  const cleaned = safeName(String(prompt || '').replace(/\s+/g, ' ').trim())
  return [...cleaned].slice(0, 40).join('').trim()
}

export class VoiceManager {
  constructor(ctx, config = {}) {
    this.ctx = ctx
    this.root = resolveRoot(config)
    this.configFile = join(this.root, 'config.json')
    this.audioDir = join(this.root, 'audio')
    this.designDir = join(this.audioDir, 'design')
    this.speakDir = join(this.audioDir, 'speak')
    this.qwenDir = join(this.audioDir, 'qwen')
    this.extraDirs = {}
    for (const key of EXTRA_ENGINE_KEYS) this.extraDirs[key] = join(this.audioDir, key)
    this.refDir = join(this.root, 'refs')
    this.config = this.readConfig()
    this.jobs = new Map()
    this.listeners = new Set()
    this.logs = []
    mkdirSync(this.designDir, { recursive: true })
    mkdirSync(this.speakDir, { recursive: true })
    mkdirSync(this.qwenDir, { recursive: true })
    for (const dir of Object.values(this.extraDirs)) mkdirSync(dir, { recursive: true })
    mkdirSync(this.refDir, { recursive: true })
    this.migrateLegacyAudio()
    this.renameSamplesByPrompt()
  }

  /** 把已经生成好的样本按「提示词」改名（旧文件是随机名；重名加 (1)、(2)…）。 */
  renameSamplesByPrompt() {
    const kinds = [
      ['design', this.designDir, (meta) => meta.desc || meta.text],
      ['speak', this.speakDir, (meta) => meta.text],
      ['qwen', this.qwenDir, (meta) => meta.instruct || meta.text],
    ]
    for (const key of EXTRA_ENGINE_KEYS) {
      kinds.push([key, this.extraDirs[key], (meta) => meta.instruct || meta.text || meta.voice])
    }
    let renamed = 0
    for (const [kind, dir, pick] of kinds) {
      let names = []
      try { names = readdirSync(dir) } catch { continue }
      for (const name of names) {
        if (!/\.wav$/i.test(name)) continue
        const current = name.replace(/\.wav$/i, '')
        const jsonFile = join(dir, current + '.json')
        let meta = null
        try { meta = JSON.parse(readFileSync(jsonFile, 'utf8').replace(/^\uFEFF/, '')) } catch { continue }
        if (!meta || meta.kind !== kind) continue
        const base = promptBase(pick(meta))
        if (base === '' || base === current) continue
        let candidate = base
        let n = 1
        while (existsSync(join(dir, candidate + '.wav')) || existsSync(join(dir, candidate + '.json'))) {
          candidate = base + '(' + n + ')'
          n += 1
        }
        try {
          renameSync(join(dir, name), join(dir, candidate + '.wav'))
          renameSync(jsonFile, join(dir, candidate + '.json'))
          renamed += 1
        } catch { /* ignore */ }
      }
    }
    return renamed
  }

  /** 旧版本把两种音频都放在 audio/ 根目录：按文件名前缀搬进 design/ 和 speak/。 */
  migrateLegacyAudio() {
    let names = []
    try { names = readdirSync(this.audioDir) } catch { return 0 }
    let moved = 0
    for (const name of names) {
      if (!/\.wav$/i.test(name)) continue
      let target = ''
      if (name.startsWith('design_')) target = this.designDir
      else if (name.startsWith('voice_')) target = this.speakDir
      if (target === '') continue
      const src = join(this.audioDir, name)
      const dst = join(target, name)
      try {
        if (!existsSync(dst)) renameSync(src, dst)
        else unlinkSync(src)
        moved += 1
      } catch { /* ignore */ }
    }
    return moved
  }

  /** 音频类目录：ref / design / speak / qwen / 六个新引擎 / audio（旧文件根目录）。 */
  audioDirOf(kind) {
    if (kind === 'ref') return this.refDir
    if (kind === 'design') return this.designDir
    if (kind === 'speak') return this.speakDir
    if (kind === 'qwen') return this.qwenDir
    if (this.extraDirs[kind]) return this.extraDirs[kind]
    return this.audioDir
  }

  readConfig() {
    try {
      const parsed = JSON.parse(readFileSync(this.configFile, 'utf8').replace(/^\uFEFF/, ''))
      return { ...DEFAULTS, ...(parsed && typeof parsed === 'object' ? parsed : {}) }
    } catch {
      return { ...DEFAULTS }
    }
  }

  publicConfig() {
    const extra = {}
    for (const key of EXTRA_ENGINE_KEYS) {
      const def = EXTRA_ENGINES[key]
      extra[def.pythonKey] = this.config[def.pythonKey]
      extra[def.modelKey] = this.config[def.modelKey]
      extra[key + 'Dir'] = this.extraDirs[key]
    }
    return {
      enabled: this.config.enabled !== false,
      dataDir: this.root,
      audioDir: this.audioDir,
      designDir: this.designDir,
      speakDir: this.speakDir,
      qwenDir: this.qwenDir,
      refDir: this.refDir,
      voxcpmPython: this.config.voxcpmPython,
      voxcpmModel: this.config.voxcpmModel,
      indexttsPython: this.config.indexttsPython,
      indexttsModel: this.config.indexttsModel,
      qwen3ttsPython: this.config.qwen3ttsPython,
      qwen3ttsModel: this.config.qwen3ttsModel,
      qwen3ttsBaseModel: this.config.qwen3ttsBaseModel,
      defaultRef: this.config.defaultRef || '',
      inferenceThreads: Number(this.config.inferenceThreads) || 0,
      ...extra,
    }
  }

  saveConfig(patch = {}) {
    const next = { ...this.config }
    if (typeof patch.enabled === 'boolean') next.enabled = patch.enabled
    if (patch.inferenceThreads !== undefined && patch.inferenceThreads !== null && String(patch.inferenceThreads).trim() !== '') {
      const threads = Math.round(Number(patch.inferenceThreads))
      if (Number.isFinite(threads) && threads >= 0) next.inferenceThreads = Math.min(64, threads)
    }
    const keys = ['voxcpmPython', 'voxcpmModel', 'indexttsPython', 'indexttsModel', 'qwen3ttsPython', 'qwen3ttsModel', 'qwen3ttsBaseModel', 'defaultRef']
    for (const key of EXTRA_ENGINE_KEYS) {
      keys.push(EXTRA_ENGINES[key].pythonKey, EXTRA_ENGINES[key].modelKey)
    }
    for (const key of keys) {
      if (typeof patch[key] === 'string') next[key] = patch[key].trim()
    }
    this.config = next
    try {
      mkdirSync(this.root, { recursive: true })
      writeFileSync(this.configFile, JSON.stringify(next, null, 2) + '\n', 'utf8')
    } catch { /* ignore */ }
    return this.publicConfig()
  }

  status() {
    const config = this.publicConfig()
    return { enabled: config.enabled !== false, config, engines: this.engineStatus(), jobs: this.jobList() }
  }

  engineStatus() {
    const has = (file) => file !== '' && existsSync(file)
    const voxPython = has(this.config.voxcpmPython)
    const voxModel = has(join(this.config.voxcpmModel, 'config.json'))
    const ttsPython = has(this.config.indexttsPython)
    const ttsModel = has(join(this.config.indexttsModel, 'config.yaml'))
    const qwenPython = has(this.config.qwen3ttsPython)
    const qwenModel = has(join(this.config.qwen3ttsModel, 'config.json'))
    const qwenBase = has(join(this.config.qwen3ttsBaseModel, 'config.json'))
    const status = {
      voxcpm: { python: voxPython, model: voxModel, ready: voxPython && voxModel },
      indextts: { python: ttsPython, model: ttsModel, ready: ttsPython && ttsModel },
      qwen3tts: { python: qwenPython, model: qwenModel, baseModel: qwenBase, ready: qwenPython && qwenModel, cloneReady: qwenPython && qwenBase },
    }
    for (const key of EXTRA_ENGINE_KEYS) {
      const def = EXTRA_ENGINES[key]
      const py = has(this.config[def.pythonKey])
      const model = has(join(this.config[def.modelKey], def.readyFile))
      const script = existsSync(join(PLUGIN_DIR, 'scripts', def.script))
      status[key] = { python: py, model, script, ready: py && model && script }
    }
    return status
  }

  listAudio(kind) {
    const valid = ['ref', 'design', 'speak', 'qwen', 'audio'].concat(EXTRA_ENGINE_KEYS)
    const key = valid.includes(String(kind)) ? String(kind) : 'audio'
    const dir = this.audioDirOf(key)
    const items = []
    try {
      for (const name of readdirSync(dir)) {
        if (!/\.wav$/i.test(name)) continue
        const file = join(dir, name)
        try {
          const info = statSync(file)
          let meta = null
          try {
            const parsed = JSON.parse(readFileSync(join(dir, name.replace(/\.wav$/i, '.json')), 'utf8').replace(/^\uFEFF/, ''))
            if (parsed && typeof parsed === 'object') meta = parsed
          } catch { /* 没有记录就算了 */ }
          items.push({ name, kb: Math.round(info.size / 1024), at: info.mtime.toISOString(), dir: key, meta })
        } catch { /* ignore */ }
      }
    } catch { /* ignore */ }
    items.sort((a, b) => b.at.localeCompare(a.at))
    return items
  }

  addLog(text) {
    this.logs.unshift({ at: new Date().toISOString(), text })
    this.logs = this.logs.slice(0, 200)
  }

  jobList() {
    const out = []
    for (const [id, job] of this.jobs) out.push({ id, kind: job.kind, status: job.status, startedAt: job.startedAt, finishedAt: job.finishedAt || '', file: job.file || '', error: job.error || '' })
    return out.sort((a, b) => b.startedAt.localeCompare(a.startedAt)).slice(0, 50)
  }
}
