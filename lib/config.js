/**
 * ai-voice · 配置与数据目录
 *
 * 数据默认放 {DSH_HOME}/ai-voice（默认 C:\Users\<你>\.dsh\ai-voice）：
 *   config.json   面板设置（python 路径、模型目录等）
 *   refs/         参考音（音色库）
 *   audio/        生成的语音
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
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
  defaultRef: '',
}

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
  const base = raw.replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^\.+/, '').slice(0, 80)
  return base
}

export class VoiceManager {
  constructor(ctx, config = {}) {
    this.ctx = ctx
    this.root = resolveRoot(config)
    this.configFile = join(this.root, 'config.json')
    this.audioDir = join(this.root, 'audio')
    this.refDir = join(this.root, 'refs')
    this.config = this.readConfig()
    this.jobs = new Map()
    this.listeners = new Set()
    this.logs = []
    mkdirSync(this.audioDir, { recursive: true })
    mkdirSync(this.refDir, { recursive: true })
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
    return {
      enabled: this.config.enabled !== false,
      dataDir: this.root,
      audioDir: this.audioDir,
      refDir: this.refDir,
      voxcpmPython: this.config.voxcpmPython,
      voxcpmModel: this.config.voxcpmModel,
      indexttsPython: this.config.indexttsPython,
      indexttsModel: this.config.indexttsModel,
      defaultRef: this.config.defaultRef || '',
    }
  }

  saveConfig(patch = {}) {
    const next = { ...this.config }
    if (typeof patch.enabled === 'boolean') next.enabled = patch.enabled
    for (const key of ['voxcpmPython', 'voxcpmModel', 'indexttsPython', 'indexttsModel', 'defaultRef']) {
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
    return {
      voxcpm: { python: voxPython, model: voxModel, ready: voxPython && voxModel },
      indextts: { python: ttsPython, model: ttsModel, ready: ttsPython && ttsModel },
    }
  }

  listAudio(kind) {
    const dir = kind === 'ref' ? this.refDir : this.audioDir
    const items = []
    try {
      for (const name of readdirSync(dir)) {
        if (!/\.wav$/i.test(name)) continue
        const file = join(dir, name)
        try {
          const info = statSync(file)
          items.push({ name, kb: Math.round(info.size / 1024), at: info.mtime.toISOString(), dir: kind === 'ref' ? 'ref' : 'audio' })
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
