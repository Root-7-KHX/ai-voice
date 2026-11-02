# -*- coding: utf-8 -*-
"""VoxCPM2 声音设计：文字描述 -> 一段音频（可作为参考音/直接导出）。

用法：python design.py --model MODEL_DIR --out OUT.wav --text "要念的内容" [--desc "音色描述"] [--timesteps 10] [--cfg 2.0]
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
    parser.add_argument('--desc', default='')
    parser.add_argument('--timesteps', type=int, default=10)
    parser.add_argument('--cfg', type=float, default=2.0)
    args = parser.parse_args()

    import soundfile as sf
    from voxcpm import VoxCPM

    print('[voice] loading VoxCPM2 from', args.model, flush=True)
    t0 = time.time()
    model = VoxCPM.from_pretrained(args.model, load_denoiser=False, device='cpu', optimize=False)
    print('[voice] loaded in %.1fs' % (time.time() - t0), flush=True)

    text = args.text
    desc = args.desc.strip()
    if desc != '':
        if not desc.startswith('('):
            desc = '(' + desc + ') '
        text = desc + ' ' + text

    sr = model.tts_model.sample_rate
    t0 = time.time()
    wav = model.generate(text=text, cfg_value=args.cfg, inference_timesteps=args.timesteps)
    dur = len(wav) / sr if sr else 0
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sf.write(args.out, wav, sr)
    print('[voice] audio %.2fs, generated in %.1fs -> %s' % (dur, time.time() - t0, args.out), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
