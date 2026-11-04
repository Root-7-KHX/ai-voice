# -*- coding: utf-8 -*-
"""VoxCPM2 声音设计 / 参考音克隆：生成一段音频。

用法：
  python design.py --model MODEL_DIR --out OUT.wav --text "要念的内容" [--desc "音色描述"]
                    [--ref 参考音.wav] [--timesteps 10] [--cfg 2.0]

不给 --ref 时按「音色描述 + 文字」造一个新声音；给了 --ref 就用那个参考音
（voice cloning，描述会被忽略）。
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
    parser.add_argument('--ref', default='')
    parser.add_argument('--timesteps', type=int, default=10)
    parser.add_argument('--cfg', type=float, default=2.0)
    args = parser.parse_args()

    import soundfile as sf
    from voxcpm import VoxCPM

    ref = args.ref.strip()
    if ref != '' and not os.path.exists(ref):
        raise SystemExit('参考音不存在：' + ref)

    print('[voice] loading VoxCPM2 from', args.model, flush=True)
    t0 = time.time()
    model = VoxCPM.from_pretrained(args.model, load_denoiser=False, device='cpu', optimize=False)
    print('[voice] loaded in %.1fs' % (time.time() - t0), flush=True)

    text = args.text
    desc = args.desc.strip()
    if ref == '' and desc != '':
        if not desc.startswith('('):
            desc = '(' + desc + ') '
        text = desc + ' ' + text

    sr = model.tts_model.sample_rate
    t0 = time.time()
    kwargs = dict(cfg_value=args.cfg, inference_timesteps=args.timesteps)
    if ref != '':
        kwargs['reference_wav_path'] = ref
        print('[voice] cloning from', ref, flush=True)
    wav = model.generate(text=text, **kwargs)
    dur = len(wav) / sr if sr else 0
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sf.write(args.out, wav, sr)
    print('[voice] audio %.2fs, generated in %.1fs -> %s' % (dur, time.time() - t0, args.out), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
