# -*- coding: utf-8 -*-
"""IndexTTS-2.5 情感语音：参考音色 + 文本 + 8 维情绪向量 -> 一段音频。

用法：python speak.py --model MODEL_DIR --ref REF.wav --text "要说的内容" --out OUT.wav
                      [--emotion "[0,0,0.9,0,0,0.2,0,0]"] [--alpha 1.0] [--speed 1.0] [--lang ZH]
情绪向量顺序：[高兴, 愤怒, 悲伤, 害怕, 厌恶, 忧郁, 惊讶, 平静]
"""
import argparse
import json
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--text', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--emotion', default='[0.9,0,0,0,0,0,0.1,0]')
    parser.add_argument('--alpha', type=float, default=1.0)
    parser.add_argument('--speed', type=float, default=1.0)
    parser.add_argument('--lang', default='ZH')
    args = parser.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from indextts.infer_v2_5 import IndexTTS2

    emo = json.loads(args.emotion)
    if not isinstance(emo, list) or len(emo) != 8:
        raise SystemExit('emotion 需要 8 个 0~1 的数')

    print('[voice] loading IndexTTS-2.5 from', args.model, flush=True)
    t0 = time.time()
    tts = IndexTTS2(
        cfg_path=os.path.join(args.model, 'config.yaml'),
        model_dir=args.model,
        use_bf16=False,
        device='cpu',
        use_qwen_emo=False,
    )
    print('[voice] loaded in %.1fs' % (time.time() - t0), flush=True)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    t0 = time.time()
    tts.infer(
        spk_audio_prompt=args.ref,
        text=args.text,
        lang=args.lang,
        output_path=args.out,
        emo_vector=emo,
        emo_alpha=args.alpha,
        duration_factor=args.speed,
        verbose=True,
    )
    print('[voice] generated in %.1fs -> %s' % (time.time() - t0, args.out), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
