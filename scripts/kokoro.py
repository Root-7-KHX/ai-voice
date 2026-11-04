# -*- coding: utf-8 -*-
"""Kokoro-82M（轻量预设音色 TTS）适配脚本。

特点：
  - 82M 参数、CPU 秒级合成、24000Hz 输出；
  - 预设音色（中文 8 个：zf_xiaobei / zf_xiaoni / zf_xiaoxiao / zf_xiaoyi /
    zm_yunjian / zm_yunxi / zm_yunxia / zm_yunyang），**不需要参考音**；
  - 模型完全从本地目录读取，不联网（KModel 直接吃本地 config.json + *.pth，
    音色从本地 voices/<voice>.pt 读取，绕开 huggingface 下载）。

用法：
  python kokoro.py --model <模型目录> --out OUT.wav --text "要说的话" \
      [--voice zf_xiaoxiao] [--speed 1.0] [--lang Chinese]
  --ref / --ref-text / --instruct 仅为统一 CLI 兼容而接受，本引擎不使用。
"""
import argparse
import os
import sys
import time

# 本脚本文件名就叫 kokoro.py，直接运行时脚本所在目录会排在 sys.path[0]，
# 会遮蔽已安装的 kokoro 包（import kokoro 变成 import 自己）。导入依赖前先摘掉它。
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path
               if os.path.abspath(p or os.getcwd()) != _SCRIPT_DIR]

ENGINE_NAME = 'Kokoro-82M'
DEFAULT_VOICE = 'zf_xiaoxiao'
# 中文可用音色（模型 voices/ 目录里的文件名，不带 .pt）
ZH_VOICES = [
    'zf_xiaobei', 'zf_xiaoni', 'zf_xiaoxiao', 'zf_xiaoyi',
    'zm_yunjian', 'zm_yunxi', 'zm_yunxia', 'zm_yunyang',
]
ZH_VOICE_LABELS = {
    'zf_xiaobei': '小北（女声·中文）',
    'zf_xiaoni': '小妮（女声·中文）',
    'zf_xiaoxiao': '小小（女声·中文）',
    'zf_xiaoyi': '小艺（女声·中文）',
    'zm_yunjian': '云健（男声·中文）',
    'zm_yunxi': '云希（男声·中文）',
    'zm_yunxia': '云夏（男声·中文）',
    'zm_yunyang': '云扬（男声·中文）',
}
# 音色 id 首字母 → KPipeline 的 lang_code
VOICE_PREFIX_LANG = {
    'a': 'a', 'b': 'b', 'e': 'e', 'f': 'f', 'h': 'h',
    'i': 'i', 'j': 'j', 'p': 'p', 'z': 'z',
}
LANG_ALIASES = {
    'z': 'z', 'zh': 'z', 'chinese': 'z', 'mandarin': 'z', '中文': 'z', '普通话': 'z',
    'a': 'a', 'en': 'a', 'english': 'a', 'en-us': 'a', 'american english': 'a',
    'b': 'b', 'en-gb': 'b', 'british english': 'b',
    'j': 'j', 'ja': 'j', 'japanese': 'j', '日文': 'j', '日语': 'j',
    'e': 'e', 'es': 'e', 'spanish': 'e',
    'f': 'f', 'fr': 'f', 'french': 'f',
    'h': 'h', 'hi': 'h', 'hindi': 'h',
    'i': 'i', 'it': 'i', 'italian': 'i',
    'p': 'p', 'pt': 'p', 'pt-br': 'p', 'portuguese': 'p',
}
LANG_NAMES = {
    'a': 'American English', 'b': 'British English', 'e': 'Spanish', 'f': 'French',
    'h': 'Hindi', 'i': 'Italian', 'j': 'Japanese', 'p': 'Brazilian Portuguese',
    'z': 'Mandarin Chinese',
}


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def fail(msg, code=1):
    print('[voice] ERROR: ' + msg, file=sys.stderr, flush=True)
    return code


def build_parser():
    p = argparse.ArgumentParser(
        description='Kokoro-82M 本地 TTS 适配脚本（预设音色，无需参考音）')
    p.add_argument('--model', required=True, help='Kokoro 模型目录（含 config.json / kokoro-v1_0.pth / voices/）')
    p.add_argument('--out', required=True, help='输出 wav 路径（父目录自动创建）')
    p.add_argument('--text', required=True, help='要合成的文本')
    p.add_argument('--voice', default='',
                   help='音色 ID（本引擎必填），如 zf_xiaoxiao / zf_xiaobei / zm_yunjian（中文）')
    p.add_argument('--speed', type=float, default=1.0, help='语速，默认 1.0（0.5~2.0）')
    # 以下参数仅用于兼容统一 CLI，本引擎不使用
    p.add_argument('--ref', default='', help='（可选，本引擎不使用）参考音路径')
    p.add_argument('--ref-text', dest='ref_text', default='', help='（可选，本引擎不使用）参考音文本')
    p.add_argument('--instruct', default='', help='（可选，本引擎不使用）风格指令')
    p.add_argument('--lang', default='', help='语言（可选，Chinese/English/...；默认由音色前缀推断）')
    return p


def main():
    _reconfigure_stdio()
    args = build_parser().parse_args()

    text = (args.text or '').strip()
    if not text:
        return fail('--text 不能为空，请传入要合成的文本')
    model_dir = os.path.abspath(os.path.expanduser(args.model.strip()))
    if not os.path.isdir(model_dir):
        return fail('模型目录不存在：' + model_dir)
    config_path = os.path.join(model_dir, 'config.json')
    model_path = os.path.join(model_dir, 'kokoro-v1_0.pth')
    if not os.path.isfile(config_path):
        return fail('模型目录缺少 config.json：' + config_path)
    if not os.path.isfile(model_path):
        return fail('模型目录缺少 kokoro-v1_0.pth：' + model_path)
    out_path = os.path.abspath(os.path.expanduser(args.out.strip()))
    if not out_path.lower().endswith(('.wav', '.flac')):
        return fail('--out 必须是 .wav 文件：' + out_path)

    voice_arg = (args.voice or '').strip()
    if not voice_arg:
        return fail('--voice 必填，中文可用音色：' + ', '.join(ZH_VOICES))
    voices_dir = os.path.join(model_dir, 'voices')
    if voice_arg.lower().endswith('.pt') and os.path.isfile(voice_arg):
        voice_path = os.path.abspath(voice_arg)
        voice_id = os.path.splitext(os.path.basename(voice_path))[0]
    else:
        voice_id = voice_arg[:-3] if voice_arg.lower().endswith('.pt') else voice_arg
        voice_path = os.path.join(voices_dir, voice_id + '.pt')
        if not os.path.isfile(voice_path):
            avail = sorted(os.path.splitext(f)[0] for f in os.listdir(voices_dir)) \
                if os.path.isdir(voices_dir) else []
            return fail('音色不存在：%s；本模型可用音色：%s' % (voice_arg, ', '.join(avail)))

    # 语言：优先按音色前缀推断，其次 --lang，默认中文
    lang_code = VOICE_PREFIX_LANG.get(voice_id[:1].lower())
    if lang_code is None:
        lang_code = LANG_ALIASES.get((args.lang or '').strip().lower(), 'z')
    if lang_code in ('a', 'b'):
        return fail('英文音色 %s 需要 spaCy 的 en_core_web_sm 模型（离线环境未安装），'
                    '面板请先只提供中文音色：%s' % (voice_id, ', '.join(ZH_VOICES)))

    speed = float(args.speed) if args.speed is not None else 1.0
    if speed < 0.5 or speed > 2.0:
        speed = min(2.0, max(0.5, speed))
        print('[voice] note: --speed 超出 0.5~2.0，已收敛为 %.2f' % speed, flush=True)

    if args.ref.strip() or args.ref_text.strip() or args.instruct.strip():
        print('[voice] note: Kokoro 为预设音色引擎，已忽略 --ref/--ref-text/--instruct', flush=True)

    try:
        import numpy as np
        import soundfile as sf
        import torch
        from kokoro import KModel, KPipeline
    except Exception as e:  # 依赖缺失时给出可读的中文原因
        return fail('依赖导入失败（%s），请确认已 pip install kokoro soundfile 并装好 CPU torch' % e)

    if lang_code == 'j':
        try:
            import misaki.ja  # noqa: F401
        except Exception:
            return fail('日文音色需要额外安装 misaki[ja]，当前环境未安装')

    # ---- 加载模型（全部走本地文件，不触发 HF 下载）----
    print('[voice] loading %s from %s' % (ENGINE_NAME, model_dir), flush=True)
    t0 = time.time()
    try:
        kmodel = KModel(
            repo_id='hexgrad/Kokoro-82M',   # 仅用于语言/版本判断，不到网上下载
            config=config_path,
            model=model_path,
        ).to('cpu').eval()
        pipeline = KPipeline(lang_code=lang_code, repo_id='hexgrad/Kokoro-82M', model=kmodel)
        pack = torch.load(voice_path, map_location='cpu', weights_only=True)
        pipeline.voices[voice_id] = pack  # 预置音色，跳过 HF 音色下载
    except Exception as e:
        return fail('模型加载失败（%s）' % e)
    print('[voice] loaded in %.1fs' % (time.time() - t0), flush=True)
    print('[voice] voice=%s lang=%s(%s) speed=%.2f'
          % (voice_id, lang_code, LANG_NAMES.get(lang_code, lang_code), speed), flush=True)

    # ---- 合成 ----
    t0 = time.time()
    try:
        chunks = []
        for _gs, ps, audio in pipeline(text, voice=voice_id, speed=speed):
            if not ps:
                continue
            if audio is None:
                continue
            arr = audio.detach().cpu().numpy() if hasattr(audio, 'detach') else np.asarray(audio)
            chunks.append(np.asarray(arr, dtype=np.float32).reshape(-1))
        if not chunks:
            return fail('合成失败：没有生成任何音频（文本可能全是无效字符）')
        wav = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        # 防止爆音：峰值超过 1.0 时归一化
        peak = float(np.max(np.abs(wav))) if wav.size else 0.0
        if peak > 1.0:
            wav = (wav / peak * 0.98).astype(np.float32)
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        sf.write(out_path, wav, 24000, subtype='PCM_16')
    except Exception as e:
        return fail('合成失败（%s）' % e)

    dur = float(wav.shape[0]) / 24000.0
    print('[voice] generated in %.1fs -> %s' % (time.time() - t0, out_path), flush=True)
    print('[voice] audio: %.2fs @24000Hz, %d samples, %.3f MB'
          % (dur, wav.shape[0], os.path.getsize(out_path) / 1024.0 / 1024.0), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
