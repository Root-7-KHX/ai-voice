/**
 * ai-voice · 本地引擎调用
 *
 * 两个引擎各自跑在独立的 Python 虚拟环境里：
 *   - VoxCPM2（声音设计 / 参考音生成 / 克隆）
 *   - IndexTTS-2.5（音色复刻 + 情绪表演）
 * 这里只负责拼命令、起子进程、记任务状态；具体推理在 scripts/*.py。
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { PLUGIN_DIR, safeName } from './config.js'

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

  startJob(kind, python, script, args, outFile) {
    const manager = this.manager
    const jobId = 'job_' + Date.now().toString(36) + '_' + Math.random().toString(16).slice(2, 6)
    const job = {
      id: jobId, kind, status: 'running', startedAt: new Date().toISOString(),
      finishedAt: '', file: '', error: '', log: '', outFile,
    }
    manager.jobs.set(jobId, job)
    manager.addLog(kind + ' 开始：' + script.split('/').pop())
    let child
    try {
      child = spawn(python, [script, ...args], { cwd: manager.root, windowsHide: true })
    } catch (error) {
      job.status = 'failed'
      job.error = String(error && error.message ? error.message : error)
      job.finishedAt = new Date().toISOString()
      return job
    }
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
    const name = 'design_' + Date.now().toString(36) + '_' + Math.random().toString(16).slice(2, 5) + '.wav'
    const outFile = join(this.manager.audioDir, name)
    const args = ['--model', cfg.voxcpmModel, '--out', outFile, '--text', text, '--desc', desc]
    if (Number.isFinite(Number(input.timesteps))) args.push('--timesteps', String(Number(input.timesteps)))
    return this.startJob('design', cfg.voxcpmPython, script, args, outFile)
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
    const name = 'voice_' + Date.now().toString(36) + '_' + Math.random().toString(16).slice(2, 5) + '.wav'
    const outFile = join(this.manager.audioDir, name)
    const args = ['--model', cfg.indexttsModel, '--ref', refFile, '--text', text, '--out', outFile, '--emotion', JSON.stringify(vector), '--alpha', String(alpha), '--speed', String(speed), '--lang', lang]
    return this.startJob('speak', cfg.indexttsPython, script, args, outFile)
  }
}
