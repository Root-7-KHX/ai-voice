/**
 * ai-voice · 本地引擎调用
 *
 * 每个引擎各自跑在独立的 Python 虚拟环境里（CPU）：
 *   - VoxCPM2（声音设计 / 参考音生成 / 克隆）
 *   - IndexTTS-2.5（音色复刻 + 情绪表演）
 *   - Qwen3-TTS 0.6B（自带说话人 + 情绪指令 / 参考音克隆）
 *   - Spark-TTS / CosyVoice3 / OpenAudio S1-mini / GPT-SoVITS / F5-TTS / Kokoro
 *     （2026-11-03 接入，统一走 extra()，参数由 config.js 的 EXTRA_ENGINES 描述）
 * 这里只负责拼命令、起子进程、记任务状态；具体推理在 scripts/*.py。
 */
import { spawn } from 'node:child_process'
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { cpus } from 'node:os'
import { join } from 'node:path'
import { EXTRA_ENGINES, PLUGIN_DIR, promptBase, safeName } from './config.js'

/**
 * 推理线程数：默认只占一半逻辑核心（至少 4 个），给界面/系统留余量。
 * 面板设置里可以用 inferenceThreads 覆盖（0 = 自动）。
 */
function autoThreads() {
  let cores = 8
  try { cores = cpus().length || 8 } catch { cores = 8 }
  return Math.max(4, Math.floor(cores / 2))
}

/** 生成音频用「提示词」当文件名：先清洗、截短，重名就在后面加 (1)、(2)… */
function promptFileName(dir, prompt, fallbackPrefix) {
  const clipped = promptBase(prompt)
  const base = clipped !== '' ? clipped : fallbackPrefix + '_' + Date.now().toString(36)
  let candidate = base
  let n = 1
  while (existsSync(join(dir, candidate + '.wav')) || existsSync(join(dir, candidate + '.json'))) {
    candidate = base + '(' + n + ')'
    n += 1
  }
  return candidate + '.wav'
}

export const EMOTIONS = {
  neutral: { label: '平静', vector: [0, 0, 0, 0, 0, 0, 0, 1] },
  happy: { label: '开心', vector: [0.9, 0, 0, 0, 0, 0, 0.1, 0] },
  laugh: { label: '大笑', vector: [1, 0, 0, 0, 0, 0, 0.2, 0] },
  sad: { label: '悲伤', vector: [0, 0, 0.9, 0, 0, 0.2, 0, 0] },
  crying: { label: '哭腔', vector: [0, 0, 1, 0.1, 0, 0.2, 0, 0] },
  angry: { label: '生气', vector: [0, 0.9, 0, 0, 0.2, 0, 0, 0] },
  afraid: { label: '害怕', vector: [0, 0, 0, 0.9, 0, 0, 0.2, 0] },
  surprised: { label: '惊讶', vector: [0, 0, 0, 0, 0, 0, 1, 0] },
  spoiled: { label: '撒娇', vector: [0.6, 0, 0.1, 0, 0, 0, 0.1, 0.3] },
  tired: { label: '疲惫', vector: [0, 0, 0.2, 0, 0, 0.3, 0, 0.5] },
}

export class VoiceEngines {
  constructor(manager) {
    this.manager = manager
  }

  emitJob(job) {
    for (const listener of this.manager.listeners) {
      try { listener(job) } catch { /* ignore */ }
    }
  }

  /** 这次推理用几个线程（配置 inferenceThreads > 0 时以配置为准，否则自动一半）。 */
  threadCount() {
    const configured = Number(this.manager.config && this.manager.config.inferenceThreads)
    if (Number.isFinite(configured) && configured >= 1) return Math.min(64, Math.round(configured))
    return autoThreads()
  }

  /** 给子进程限线程的通用环境变量（torch / numpy / MKL 都会读）。 */
  inferenceEnv() {
    const threads = String(this.threadCount())
    return {
      ...process.env,
      OMP_NUM_THREADS: threads,
      MKL_NUM_THREADS: threads,
      NUMEXPR_NUM_THREADS: threads,
    }
  }

  /**
   * 把生成进程降到 BelowNormal（Windows）：界面优先拿 CPU，滚动/点击不会被饿死。
   * venv 的 python.exe 是个 Launcher，真正干活的是它拉起的子进程（base python），
   * 所以这里直接扫 python.exe 进程统一降优先级（生成期间机器上只有我们的推理进程）。
   * PowerShell 的 -Command 里多条语句必须用换行分隔（用空格拼会解析失败，实测踩过）。
   */
  lowerPriority(pid, scriptPath = '') {
    const debugFile = join(this.manager.root, 'priority-debug.log')
    const logDebug = (text) => {
      try { appendFileSync(debugFile, new Date().toISOString() + ' ' + text + '\n', 'utf8') } catch { /* ignore */ }
    }
    const command = [
      '$ErrorActionPreference = "SilentlyContinue"',
      '$deadline = (Get-Date).AddSeconds(10)',
      'while ((Get-Date) -lt $deadline) {',
      '  $procs = Get-Process python -ErrorAction SilentlyContinue',
      '  foreach ($p in $procs) {',
      '    try { if ($p.PriorityClass -ne "BelowNormal") { $p.PriorityClass = "BelowNormal" } } catch {}',
      '  }',
      '  Start-Sleep -Milliseconds 500',
      '}',
    ].join('\n')
    try {
      const child = spawn('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', command], {
        windowsHide: true,
        stdio: 'ignore',
      })
      logDebug('spawn pid=' + String(pid) + ' ps=' + String(child.pid))
      child.on('error', (error) => logDebug('ps-error ' + String(error && error.message ? error.message : error)))
      child.on('close', (code) => logDebug('ps-close code=' + String(code)))
      if (typeof child.unref === 'function') child.unref()
    } catch (error) {
      logDebug('spawn-fail ' + String(error && error.message ? error.message : error))
    }
  }

  /** 把这次生成的参数（提示词 / 台词 / 情绪）写进同名 .json，面板里就能显示小字标注。 */
  writeMeta(outFile, meta, log) {
    if (!outFile || !meta || typeof meta !== 'object') return ''
    try {
      const match = /generated in ([0-9.]+)s/.exec(String(log || ''))
      const payload = {
        ...meta,
        at: new Date().toISOString(),
        seconds: match ? Math.round(Number(match[1])) : null,
      }
      const file = outFile.replace(/\.wav$/i, '.json')
      writeFileSync(file, JSON.stringify(payload, null, 2) + '\n', 'utf8')
      return file
    } catch { return '' }
  }

  startJob(kind, python, script, args, outFile, meta = null) {
    const manager = this.manager
    const jobId = 'job_' + Date.now().toString(36) + '_' + Math.random().toString(16).slice(2, 6)
    const job = {
      id: jobId, kind, status: 'running', startedAt: new Date().toISOString(),
      finishedAt: '', file: '', error: '', log: '', outFile, meta, args: args.slice(), threads: this.threadCount(),
    }
    manager.jobs.set(jobId, job)
    manager.addLog(kind + ' 开始：' + script.split('/').pop())
    let child
    try {
      child = spawn(python, [script, ...args], {
        cwd: manager.root,
        windowsHide: true,
        env: this.inferenceEnv(),
      })
    } catch (error) {
      job.status = 'failed'
      job.error = String(error && error.message ? error.message : error)
      job.finishedAt = new Date().toISOString()
      return job
    }
    // 本地推理会把 CPU 打满：把生成进程降到 BelowNormal，让桌面端/浏览器优先拿到 CPU，
    // 否则生成那几十秒里界面会卡到滚轮都不响应（2026-11-03 实测）。
    this.lowerPriority(child.pid, script)
    const append = (chunk) => {
      job.log = (job.log + chunk).slice(-6000)
    }
    child.stdout.on('data', (buf) => append(String(buf)))
    child.stderr.on('data', (buf) => append(String(buf)))
    child.on('error', (error) => {
      job.status = 'failed'
      job.error = String(error && error.message ? error.message : error)
      job.finishedAt = new Date().toISOString()
      manager.addLog(kind + ' 失败：' + job.error)
      this.emitJob(job)
    })
    child.on('close', (code) => {
      if (job.status === 'cancelled') return
      const okFile = outFile !== '' && existsSync(outFile)
      if (code === 0 && okFile) {
        job.status = 'done'
        job.file = outFile
        this.writeMeta(outFile, job.meta, job.log)
        manager.addLog(kind + ' 完成：' + outFile.split(/[\\/]/).pop())
      } else {
        job.status = 'failed'
        job.error = 'exit=' + code + (okFile ? '' : '（没有产出音频）')
        manager.addLog(kind + ' 失败：' + job.error)
      }
      job.finishedAt = new Date().toISOString()
      this.emitJob(job)
    })
    job.cancel = () => {
      try { child.kill() } catch { /* ignore */ }
      job.status = 'cancelled'
      job.finishedAt = new Date().toISOString()
    }
    return job
  }

  /** VoxCPM2：文字描述 → 一个声音 / 参考音 */
  design(input = {}) {
    const cfg = this.manager.config
    const script = join(PLUGIN_DIR, 'scripts', 'design.py')
    const text = String(input.text || '').trim()
    if (text === '') throw new Error('要生成的内容不能为空')
    const desc = String(input.desc || '').trim()
    const ref = safeName(input.ref || '')
    if (ref !== '') {
      const refFile = join(this.manager.refDir, ref)
      if (!existsSync(refFile)) throw new Error('参考音不存在：' + ref)
    }
    const name = promptFileName(this.manager.designDir, desc || text, 'design')
    const outFile = join(this.manager.designDir, name)
    const args = ['--model', cfg.voxcpmModel, '--out', outFile, '--text', text, '--desc', desc]
    if (ref !== '') args.push('--ref', join(this.manager.refDir, ref))
    if (Number.isFinite(Number(input.timesteps))) args.push('--timesteps', String(Number(input.timesteps)))
    return this.startJob('design', cfg.voxcpmPython, script, args, outFile, { kind: 'design', desc, text, ref })
  }

  /** IndexTTS-2.5：参考音 + 文本 + 情绪 → 语音 */
  speak(input = {}) {
    const cfg = this.manager.config
    const script = join(PLUGIN_DIR, 'scripts', 'speak.py')
    const text = String(input.text || '').trim()
    if (text === '') throw new Error('要说的内容不能为空')
    const refName = safeName(input.ref || cfg.defaultRef || '')
    if (refName === '') throw new Error('请先选一个参考音（或上传录音）')
    const refFile = join(this.manager.refDir, refName)
    if (!existsSync(refFile)) throw new Error('参考音不存在：' + refName)
    const emotionKey = String(input.emotion || 'happy')
    let vector = EMOTIONS[emotionKey] ? EMOTIONS[emotionKey].vector : EMOTIONS.happy.vector
    if (Array.isArray(input.vector) && input.vector.length === 8) {
      vector = input.vector.map((v) => Math.max(0, Math.min(1, Number(v) || 0)))
    }
    const alpha = Number.isFinite(Number(input.alpha)) ? Math.max(0, Math.min(1, Number(input.alpha))) : 1
    const speed = Number.isFinite(Number(input.speed)) ? Math.max(0.5, Math.min(2, Number(input.speed))) : 1
    const lang = ['ZH', 'EN', 'JA', 'ES', 'AR'].includes(String(input.lang)) ? String(input.lang) : 'ZH'
    const name = promptFileName(this.manager.speakDir, text, 'voice')
    const outFile = join(this.manager.speakDir, name)
    const args = ['--model', cfg.indexttsModel, '--ref', refFile, '--text', text, '--out', outFile, '--emotion', JSON.stringify(vector), '--alpha', String(alpha), '--speed', String(speed), '--lang', lang]
    const emotionLabel = EMOTIONS[emotionKey] ? EMOTIONS[emotionKey].label : EMOTIONS.happy.label
    return this.startJob('speak', cfg.indexttsPython, script, args, outFile, { kind: 'speak', text, ref: refName, emotion: emotionKey, emotionLabel, alpha, speed, lang })
  }

  /** Qwen3-TTS 0.6B：文本 + 自带说话人 + 自然语言情绪指令 → 语音 */
  qwen(input = {}) {
    const cfg = this.manager.config
    const script = join(PLUGIN_DIR, 'scripts', 'qwen3tts.py')
    const text = String(input.text || '').trim()
    if (text === '') throw new Error('要说的内容不能为空')
    const speaker = String(input.speaker || 'Vivian').trim() || 'Vivian'
    const instruct = String(input.instruct || '').trim()
    const language = ['Chinese', 'English', 'Japanese', 'Korean', 'German', 'French', 'Russian', 'Portuguese', 'Spanish', 'Italian'].includes(String(input.language))
      ? String(input.language)
      : 'Chinese'
    const ref = safeName(input.ref || '')
    const useClone = ref !== ''
    if (useClone && !existsSync(join(this.manager.refDir, ref))) throw new Error('参考音不存在：' + ref)
    const name = promptFileName(this.manager.qwenDir, useClone ? text : (instruct || text), 'qwen')
    const outFile = join(this.manager.qwenDir, name)
    const modelPath = useClone ? cfg.qwen3ttsBaseModel : cfg.qwen3ttsModel
    const args = ['--model', modelPath, '--out', outFile, '--text', text, '--language', language]
    if (useClone) {
      args.push('--ref', join(this.manager.refDir, ref))
    } else {
      args.push('--speaker', speaker, '--instruct', instruct)
    }
    const meta = useClone
      ? { kind: 'qwen', mode: 'clone', text, ref, language }
      : { kind: 'qwen', mode: 'custom', text, speaker, instruct, language }
    return this.startJob('qwen', cfg.qwen3ttsPython, script, args, outFile, meta)
  }

  /**
   * 2026-11-03 新接入的 6 个引擎：spark / cosyvoice / fish / gptsovits / f5 / kokoro。
   * 参数形态统一走 config.js 的 EXTRA_ENGINES 描述，面板卡片和这里共用同一份定义。
   */
  extra(key, input = {}) {
    const engineKey = String(key)
    const def = EXTRA_ENGINES[engineKey]
    if (!def) throw new Error('未知引擎：' + key)
    const cfg = this.manager.config
    const script = join(PLUGIN_DIR, 'scripts', def.script)
    const text = String(input.text || '').trim()
    if (text === '') throw new Error('要念的内容不能为空')
    const dir = this.manager.extraDirs[engineKey]
    const ref = safeName(input.ref || '')
    const refText = String(input.refText || '').trim()
    const instruct = String(input.instruct || '').trim()
    const voice = String(input.voice || '').trim()
    const speed = Number.isFinite(Number(input.speed)) ? Math.max(0.5, Math.min(2, Number(input.speed))) : 1
    const lang = String(input.lang || 'Chinese').trim() || 'Chinese'

    if (def.ref === 'required') {
      if (ref === '') throw new Error('这个引擎需要先选一个参考音（克隆）')
      if (!existsSync(join(this.manager.refDir, ref))) throw new Error('参考音不存在：' + ref)
    } else if (ref !== '' && !existsSync(join(this.manager.refDir, ref))) {
      throw new Error('参考音不存在：' + ref)
    }
    if (def.refTextRequired && refText === '') throw new Error('这个引擎还需要填「参考音里说的那句话」（参考音台词）')
    if (def.voice && voice === '') throw new Error('先选一个音色')

    const name = promptFileName(dir, instruct || text, engineKey)
    const outFile = join(dir, name)
    const args = ['--model', cfg[def.modelKey], '--out', outFile, '--text', text]
    if (ref !== '') args.push('--ref', join(this.manager.refDir, ref))
    if (def.refText) args.push('--ref-text', refText)
    if (def.instruct) args.push('--instruct', instruct)
    if (def.voice) args.push('--voice', voice)
    if (def.speed) args.push('--speed', String(speed))
    if (def.threads) args.push('--threads', String(this.threadCount()))
    if (def.lang) args.push('--lang', lang)
    const meta = { kind: engineKey, text, ref, refText, instruct, voice, speed, lang }
    return this.startJob(engineKey, cfg[def.pythonKey], script, args, outFile, meta)
  }
}
