# -*- coding: utf-8 -*-
"""F5-TTS 零样本音色克隆适配脚本（CPU）。

用法：
  python f5.py --model <模型目录> --out OUT.wav --text "要念的内容" \
      --ref <参考音.wav> --ref-text "参考音里说的那句话" [--speed 1.0]

说明：
  - F5-TTS 必须提供参考音 + 参考音台词（零样本克隆）；--instruct / --voice / --lang 不支持，传了会忽略并提示。
  - --model 可以传 F5TTS_v1_Base 目录，也可以传 modelscope snapshot 的 master 目录，脚本会自己找权重和 vocab.txt。
  - vocos 声码器默认找本脚本所在 venv 根目录下的 vocos-mel-24khz/（config.yaml + pytorch_model.bin），
    也可以用 --vocoder 或环境变量 F5_VOCODER_DIR 指定；全程离线，不联网。
"""

import argparse
import os
import sys
import time
import traceback

# 插件是用 child_process 管道读 stdout（默认 utf8 解码），统一成 utf-8 输出，
# 避免中文日志/报错在面板里变成乱码。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_NFE_STEP = 16
ENGINE_NAME = "F5-TTS"


# ---------------------------------------------------------------- 路径解析

def _find_ckpt(model_arg):
    """返回 (ckpt_path, model_dir)；找不到返回 (None, None)。"""
    p = os.path.abspath(os.path.expanduser(model_arg))
    if os.path.isfile(p):
        if p.lower().endswith(".safetensors") or p.lower().endswith(".pt"):
            return p, os.path.dirname(p)
        return None, None
    if not os.path.isdir(p):
        return None, None

    # 1) 目录里带 F5TTS_v1_Base 子目录的（modelscope snapshot 布局）
    for sub in ("F5TTS_v1_Base", "F5TTS_Base", "F5TTS_v1_Base_no_zero_init"):
        d = os.path.join(p, sub)
        if not os.path.isdir(d):
            continue
        exact = os.path.join(d, "model_1250000.safetensors")
        if os.path.isfile(exact):
            return exact, d
        ckpts = [f for f in os.listdir(d) if f.startswith("model_") and (f.endswith(".safetensors") or f.endswith(".pt"))]
        if ckpts:
            ckpts.sort(key=_step_of, reverse=True)
            return os.path.join(d, ckpts[0]), d

    # 2) 目录本身就放权重
    ckpts = [f for f in os.listdir(p) if f.startswith("model_") and (f.endswith(".safetensors") or f.endswith(".pt"))]
    if ckpts:
        ckpts.sort(key=_step_of, reverse=True)
        return os.path.join(p, ckpts[0]), p

    # 3) 兜底：浅层递归找 safetensors
    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if not d.startswith(".") and "incomplete" not in d]
        for f in files:
            if f.startswith("model_") and f.endswith(".safetensors"):
                return os.path.join(root, f), root
        if root.count(os.sep) - p.count(os.sep) > 2:
            dirs[:] = []
    return None, None


def _step_of(name):
    """从文件名里抽 step 数字，用于排序。"""
    digit = ""
    for ch in name:
        if ch.isdigit():
            digit += ch
        elif digit:
            break
    return int(digit) if digit else 0


def _find_vocab(model_dir, ckpt_path, model_arg):
    cands = [
        os.path.join(model_dir, "vocab.txt"),
        os.path.join(os.path.dirname(ckpt_path), "vocab.txt"),
    ]
    if os.path.isdir(model_arg):
        for sub in ("F5TTS_v1_Base", "F5TTS_Base"):
            cands.append(os.path.join(os.path.abspath(model_arg), sub, "vocab.txt"))
        cands.append(os.path.join(os.path.abspath(model_arg), "vocab.txt"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return ""


def _has_vocoder(d):
    return bool(d) and os.path.isfile(os.path.join(d, "config.yaml")) and os.path.isfile(
        os.path.join(d, "pytorch_model.bin")
    )


def _find_vocoder(model_dir, model_arg, explicit):
    cands = []
    if explicit:
        cands.append(explicit)
    env = os.environ.get("F5_VOCODER_DIR") or os.environ.get("F5_VOCODER")
    if env:
        cands.append(env)

    roots = [model_dir, os.path.dirname(model_dir), os.path.dirname(os.path.dirname(model_dir))]
    if os.path.isdir(model_arg):
        roots.append(os.path.abspath(model_arg))
        roots.append(os.path.dirname(os.path.abspath(model_arg)))
    names = (
        "vocos-mel-24khz",
        "vocos_mel_24khz",
        "vocos",
        "vocoder",
        "charactr--vocos-mel-24khz",
        "models--charactr--vocos-mel-24khz",
    )
    for r in roots:
        if not r:
            continue
        for n in names:
            cands.append(os.path.join(r, n))

    # 脚本所在 venv 的根目录（venv-f5/vocos-mel-24khz）——推荐放这里
    venv_roots = []
    if sys.executable:
        venv_roots.append(os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))))
    venv_roots.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for r in venv_roots:
        for n in names:
            cands.append(os.path.join(r, n))
        # 再扫一层子目录
        try:
            for entry in os.listdir(r):
                full = os.path.join(r, entry)
                if os.path.isdir(full) and "vocos" in entry.lower():
                    cands.append(full)
        except OSError:
            pass

    seen = set()
    for c in cands:
        if not c:
            continue
        c = os.path.abspath(os.path.expanduser(c))
        if c in seen:
            continue
        seen.add(c)
        if _has_vocoder(c):
            return c
    return ""


# ---------------------------------------------------------------- 音频加载兼容

def _install_audio_loader():
    """torchaudio 新版默认走 torchcodec（需要系统 FFmpeg）；没有 FFmpeg 时退回 soundfile。

    只影响本进程，F5-TTS 内部 `torchaudio.load` 会走这里。
    """
    import numpy as np
    import torch
    import torchaudio

    orig_load = torchaudio.load

    try:
        import soundfile as sf
    except Exception:  # pragma: no cover
        return

    def _load(uri, frame_offset=0, num_frames=-1, normalize=True, channels_first=True,
              format=None, buffer_size=4096, backend=None):
        try:
            return orig_load(uri, frame_offset=frame_offset, num_frames=num_frames,
                             normalize=normalize, channels_first=channels_first)
        except Exception:
            frames = num_frames if (num_frames is not None and num_frames > 0) else -1
            data, sr = sf.read(str(uri), dtype="float32", always_2d=True,
                               start=max(0, int(frame_offset or 0)), frames=frames)
            tensor = torch.from_numpy(np.ascontiguousarray(data.T))
            if not channels_first:
                tensor = tensor.T
            return tensor, sr

    torchaudio.load = _load


# ---------------------------------------------------------------- 主流程

def main():
    parser = argparse.ArgumentParser(description="F5-TTS 适配脚本（零样本音色克隆）")
    parser.add_argument("--model", required=True, help="F5-TTS 模型目录（F5TTS_v1_Base 或 master）")
    parser.add_argument("--out", required=True, help="输出 wav 路径")
    parser.add_argument("--text", required=True, help="要念的内容")
    parser.add_argument("--ref", default="", help="参考音 wav（零样本克隆必填）")
    parser.add_argument("--ref-text", "--ref_text", dest="ref_text", default="",
                        help="参考音里说的那句话（必填，否则会需要联网 ASR）")
    parser.add_argument("--instruct", default="", help="F5-TTS 不支持，忽略")
    parser.add_argument("--voice", default="", help="F5-TTS 不支持，忽略")
    parser.add_argument("--lang", "--language", dest="lang", default="", help="F5-TTS 不支持，忽略")
    parser.add_argument("--speed", type=float, default=1.0, help="语速（1.0 为原速）")
    parser.add_argument("--nfe-step", type=int, default=DEFAULT_NFE_STEP, help="采样步数，默认 16")
    parser.add_argument("--seed", type=int, default=-1, help="随机种子，-1 表示随机")
    parser.add_argument("--vocoder", default="", help="vocos 声码器目录（一般不用传，自动查找）")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--threads", type=int, default=0, help="CPU 线程数，0 表示自动")
    args = parser.parse_args()

    # ---- 参数校验（中文报错） ----
    text = (args.text or "").strip()
    if not text:
        print("错误：--text 不能为空", file=sys.stderr)
        return 2
    ref = (args.ref or "").strip().strip('"')
    if not ref:
        print("错误：F5-TTS 必须提供参考音：--ref 缺失（零样本克隆需要参考音）。", file=sys.stderr)
        return 2
    if not os.path.isfile(ref):
        print("错误：参考音不存在：%s" % ref, file=sys.stderr)
        return 2
    ref_text = (args.ref_text or "").strip()
    if not ref_text:
        print("错误：F5-TTS 必须提供 --ref-text（参考音里说的那句话）。"
              "缺少它引擎会尝试联网做 ASR，本地离线环境下会失败。", file=sys.stderr)
        return 2
    if args.speed <= 0:
        print("错误：--speed 必须是正数（当前 %s）" % args.speed, file=sys.stderr)
        return 2

    # ---- 找模型 ----
    ckpt, model_dir = _find_ckpt(args.model)
    if not ckpt:
        print("错误：在 --model 指定的位置找不到 F5-TTS 权重（model_*.safetensors）：%s" % args.model,
              file=sys.stderr)
        return 2
    vocab = _find_vocab(model_dir, ckpt, args.model)
    vocoder = _find_vocoder(model_dir, args.model, args.vocoder)
    if not vocoder:
        print("错误：找不到 vocos 声码器（需要含 config.yaml 和 pytorch_model.bin 的目录）。"
              "请用 --vocoder 指定，或把 vocos-mel-24khz 放到 venv 根目录下。", file=sys.stderr)
        return 2

    ignored = [n for n, v in (("--instruct", args.instruct), ("--voice", args.voice), ("--lang", args.lang))
               if str(v).strip()]
    if ignored:
        print("[voice] 提示：F5-TTS 不支持 %s，已忽略" % "/".join(ignored), flush=True)

    out_path = os.path.abspath(args.out)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print("[voice] loading %s from %s" % (ENGINE_NAME, model_dir), flush=True)
    print("[voice] ckpt=%s" % ckpt, flush=True)
    print("[voice] vocab=%s" % (vocab or "(内置)"), flush=True)
    print("[voice] vocoder=%s" % vocoder, flush=True)

    # 离线优先：权重和声码器都已本地，禁止引擎偷偷联网
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    t_load = time.time()
    import torch

    try:
        n_threads = args.threads if args.threads > 0 else min(16, os.cpu_count() or 4)
        torch.set_num_threads(max(1, int(n_threads)))
    except Exception:
        pass

    _install_audio_loader()

    from f5_tts.api import F5TTS  # noqa: E402  (重依赖，延后导入)

    seed = None if args.seed is None or args.seed < 0 else args.seed
    f5 = F5TTS(
        model="F5TTS_v1_Base",
        ckpt_file=ckpt,
        vocab_file=vocab,
        vocoder_local_path=vocoder,
        device=args.device,
    )
    print("[voice] loaded in %.1fs" % (time.time() - t_load), flush=True)

    print("[voice] generating ... (nfe_step=%d, speed=%s)" % (args.nfe_step, args.speed), flush=True)
    t_gen = time.time()
    wav, sr, _ = f5.infer(
        ref_file=ref,
        ref_text=ref_text,
        gen_text=text,
        nfe_step=max(1, int(args.nfe_step)),
        speed=float(args.speed),
        seed=seed,
    )
    gen_secs = time.time() - t_gen

    import soundfile as sf

    wav = wav.flatten() if hasattr(wav, "flatten") else wav
    sf.write(out_path, wav, int(sr))
    size_mb = os.path.getsize(out_path) / 1024.0 / 1024.0
    dur = len(wav) / float(sr) if sr else 0.0
    print("[voice] generated in %.1fs -> %s" % (gen_secs, out_path), flush=True)
    print("[voice] audio %.2fs, %.2f MB, sr=%d" % (dur, size_mb, int(sr)), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("错误：已中断", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        print("错误：F5-TTS 生成失败：%s" % exc, file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
