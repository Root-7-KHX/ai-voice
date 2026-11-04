# -*- coding: utf-8 -*-
"""Qwen3-TTS 0.6B：自带说话人 / 参考音克隆。

用法：
  CustomVoice（9 个自带说话人 + 情绪指令）：
    python qwen3tts.py --model CustomVoice模型 --out OUT.wav --text "要说的话" --speaker Vivian --instruct "用开心的语气说"
  Base（参考音克隆，音色来自参考音）：
    python qwen3tts.py --model Base模型 --out OUT.wav --text "要说的话" --ref 参考音.wav
"""
import argparse
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--text', required=True)
    parser.add_argument('--speaker', default='Vivian')
    parser.add_argument('--instruct', default='')
    parser.add_argument('--language', default='Chinese')
    parser.add_argument('--ref', default='')
    args = parser.parse_args()

    os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')

    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel

    ref = args.ref.strip()
    if ref != '' and not os.path.exists(ref):
        raise SystemExit('参考音不存在：' + ref)

    print('[voice] loading Qwen3-TTS from', args.model, flush=True)
    t0 = time.time()
    model = Qwen3TTSModel.from_pretrained(args.model, device_map='cpu', dtype=torch.float32)
    print('[voice] loaded in %.1fs' % (time.time() - t0), flush=True)

    t0 = time.time()
    if ref != '':
        print('[voice] voice clone from', ref, flush=True)
        wavs, sr = model.generate_voice_clone(
            text=args.text,
            language=args.language,
            ref_audio=ref,
            x_vector_only_mode=True,
        )
    else:
        wavs, sr = model.generate_custom_voice(
            text=args.text,
            language=args.language,
            speaker=args.speaker,
            instruct=args.instruct,
        )
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sf.write(args.out, wavs[0], sr)
    print('[voice] generated in %.1fs -> %s' % (time.time() - t0, args.out), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
