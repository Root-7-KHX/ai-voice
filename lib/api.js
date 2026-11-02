/**
 * ai-voice · Host HTTP 接口（/ai-voice/api/*），全部同源、只给本地面板用。
 * 响应统一 { ok: true, value } / { ok: false, error: { message } }。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { EMOTIONS } from './engines.js'
import { safeName } from './config.js'

function writeJson(response, status, payload) {
  const body = JSON.stringify(payload)
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'content-length': Buffer.byteLength(body) })
  response.end(body)
}
function ok(response, value) { writeJson(response, 200, { ok: true, value }) }
function fail(response, status, message) { writeJson(response, status, { ok: false, error: { message } }) }

async function readBody(request) {
  const chunks = []
  let size = 0
  for await (const chunk of request) {
    size += chunk.length
    if (size > 64 * 1024 * 1024) throw new Error('请求体太大')
    chunks.push(chunk)
  }
  if (chunks.length === 0) return {}
  const text = Buffer.concat(chunks).toString('utf8')
  if (text.trim() === '') return {}
  try { return JSON.parse(text) } catch { throw new Error('请求体不是合法 JSON') }
}

function isLocalRequest(request) {
  try {
    const remote = request.socket && request.socket.remoteAddress ? String(request.socket.remoteAddress) : ''
    if (remote === '' ) return true
    return remote === '127.0.0.1' || remote === '::1' || remote === '::ffff:127.0.0.1'
  } catch {
    return false
  }
}

export function registerWebApi(ctx, manager, engines) {
  const webServer = safeGet(ctx, 'webServer')
  if (!webServer || typeof webServer.register !== 'function') return () => {}
  return webServer.register({
    kind: 'prefix',
    path: '/ai-voice/api',
    handler: (request, response) => handleRequest(ctx, manager, engines, request, response),
  })
}

function safeGet(ctx, name) {
  try { return ctx.get(name) } catch { return undefined }
}

async function handleRequest(ctx, manager, engines, request, response) {
  try {
    if (!isLocalRequest(request)) { fail(response, 403, 'forbidden'); return }
    const url = new URL(request.url ?? '/', 'http://dsh.internal')
    const route = url.pathname.replace(/^\/ai-voice\/api\/?/, '')

    if (request.method === 'GET') {
      switch (route) {
        case 'status': ok(response, manager.status()); return
        case 'emotions': ok(response, Object.entries(EMOTIONS).map(([key, item]) => ({ key, label: item.label, vector: item.vector }))); return
        case 'files': {
          const kind = url.searchParams.get('dir') === 'ref' ? 'ref' : 'audio'
          ok(response, { dir: kind === 'ref' ? manager.refDir : manager.audioDir, items: manager.listAudio(kind) })
          return
        }
        case 'file': {
          const kind = url.searchParams.get('dir') === 'ref' ? 'ref' : 'audio'
          const name = safeName(url.searchParams.get('name') || '')
          if (name === '' || !/\.wav$/i.test(name)) throw new Error('文件名不合法')
          const dir = kind === 'ref' ? manager.refDir : manager.audioDir
          const file = join(dir, name)
          if (!existsSync(file)) throw new Error('找不到音频：' + name)
          const bytes = readFileSync(file)
          const inline = url.searchParams.get('inline') === '1'
          response.writeHead(200, {
            'content-type': 'audio/wav',
            'content-length': String(bytes.length),
            'cache-control': 'no-store',
            ...(inline ? {} : { 'content-disposition': 'attachment; filename="' + name + '"' }),
          })
          response.end(bytes)
          return
        }
        case 'job': {
          const id = String(url.searchParams.get('id') || '')
          const job = manager.jobs.get(id)
          if (!job) throw new Error('任务不存在：' + id)
          ok(response, { id: job.id, kind: job.kind, status: job.status, error: job.error, file: job.file, log: job.log.slice(-2000) })
          return
        }
        default: fail(response, 404, 'unknown route'); return
      }
    }

    if (request.method === 'POST') {
      const body = await readBody(request)
      switch (route) {
        case 'design': {
          if (!manager.config.enabled) throw new Error('AI语音 总开关关着，先打开再生成')
          ok(response, { job: engines.design(body).id })
          return
        }
        case 'speak': {
          if (!manager.config.enabled) throw new Error('AI语音 总开关关着，先打开再生成')
          ok(response, { job: engines.speak(body).id })
          return
        }
        case 'enabled': {
          ok(response, manager.saveConfig({ enabled: body.enabled === true }))
          return
        }
        case 'job/cancel': {
          const id = String(body.id || '')
          const job = manager.jobs.get(id)
          if (!job) throw new Error('任务不存在：' + id)
          if (typeof job.cancel === 'function') job.cancel()
          ok(response, { id, status: job.status })
          return
        }
        case 'upload': {
          const name = safeName(body.name || '')
          const data = typeof body.data === 'string' ? body.data : ''
          if (!/\.wav$/i.test(name)) throw new Error('参考音需要 wav（mp3 请先转换）')
          if (data === '') throw new Error('缺少音频内容')
          mkdirSync(manager.refDir, { recursive: true })
          writeFileSync(join(manager.refDir, name), Buffer.from(data, 'base64'))
          ok(response, { name, dir: manager.refDir })
          return
        }
        case 'delete': {
          const kind = body.dir === 'ref' ? 'ref' : 'audio'
          const name = safeName(body.name || '')
          if (name === '') throw new Error('缺少文件名')
          const dir = kind === 'ref' ? manager.refDir : manager.audioDir
          const { unlinkSync } = await import('node:fs')
          const file = join(dir, name)
          if (existsSync(file)) unlinkSync(file)
          ok(response, { name, removed: true })
          return
        }
        case 'config': ok(response, manager.saveConfig(body)); return
        case 'open': {
          const kind = String(body.dir || '')
          const dir = kind === 'ref' ? manager.refDir : kind === 'data' ? manager.root : manager.audioDir
          const { spawn } = await import('node:child_process')
          spawn('explorer.exe', [dir], { detached: true, stdio: 'ignore' }).unref()
          ok(response, { dir })
          return
        }
        case 'copy-to-ref': {
          const name = safeName(body.name || '')
          if (name === '') throw new Error('缺少文件名')
          const src = join(manager.audioDir, name)
          if (!existsSync(src)) throw new Error('找不到音频：' + name)
          const target = join(manager.refDir, name)
          writeFileSync(target, readFileSync(src))
          manager.saveConfig({ defaultRef: name })
          ok(response, { name })
          return
        }
        case 'save-default-ref': {
          const name = safeName(body.name || '')
          manager.saveConfig({ defaultRef: name })
          ok(response, { defaultRef: name })
          return
        }
        default: fail(response, 404, 'unknown route'); return
      }
    }

    fail(response, 405, 'method not allowed')
  } catch (error) {
    fail(response, 400, String(error && error.message ? error.message : error))
  }
}
