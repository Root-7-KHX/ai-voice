/**
 * AI语音（ai-voice）Host 半身。
 *
 * 本地音色工作台：
 *   - VoxCPM2：文字描述造声音 / 生成参考音（也可用录音或别人的音频当参考）
 *   - IndexTTS-2.5：用参考音 + 情绪向量说话（哭腔、笑、生气…）
 *   - 生成的 wav 可试听、导出下载，也可以存进参考音库
 *
 * 只注册 /ai-voice/api/*；界面由 AI记忆（companion-memory）的「接入软件」页承载，
 * 模型、Python 环境都在插件外，面板里可配路径。
 */
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { VoiceManager } from './lib/config.js'
import { VoiceEngines } from './lib/engines.js'
import { registerWebApi } from './lib/api.js'

export const inject = ['webServer']

/** 往 AI记忆 的「接入软件」清单里登记自己（只写一个 JSON，不执行代码）。 */
function registerIntegration() {
  try {
    const home = typeof process.env.DSH_HOME === 'string' && process.env.DSH_HOME !== '' ? process.env.DSH_HOME : join(homedir(), '.dsh')
    const dir = join(home, 'companion-memory', 'integrations')
    if (!existsSync(join(home, 'companion-memory'))) return false
    mkdirSync(dir, { recursive: true })
    const manifest = {
      id: 'ai-voice',
      name: 'AI语音',
      description: '本地音色工作台：文字描述造声音、录音/参考音频复刻、哭腔笑声等情绪表演，内置 9 个本地 TTS 引擎，可导出音频。',
      version: '0.2.0',
      author: 'Root-7-KHX',
      category: '应用',
      tags: ['语音', 'TTS', '声音设计', '情绪', '声音克隆'],
      capabilities: ['声音设计', '音色复刻', '情绪语音', '多引擎 TTS', '导出音频'],
      homepage: 'https://github.com/Root-7-KHX/ai-voice',
      entry: 'ai-voice',
      app: 'ai-voice',
      plugin: '@local/ai-voice',
      openable: true,
      statusUrl: '/ai-voice/api/status',
      enabledUrl: '/ai-voice/api/enabled',
    }
    writeFileSync(join(dir, 'ai-voice.json'), JSON.stringify(manifest, null, 2) + '\n', 'utf8')
    return true
  } catch {
    return false
  }
}

export function apply(ctx, config) {
  const manager = new VoiceManager(ctx, config ?? {})
  const engines = new VoiceEngines(manager)

  ctx.effect(() => registerWebApi(ctx, manager, engines), 'ai-voice: /ai-voice/api routes')
  ctx.effect(() => { registerIntegration(); return () => {} }, 'ai-voice: integration manifest')

  return () => {
    for (const job of manager.jobs.values()) {
      if (typeof job.cancel === 'function') try { job.cancel() } catch { /* ignore */ }
    }
  }
}
