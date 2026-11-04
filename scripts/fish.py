# -*- coding: utf-8 -*-
"""OpenAudio S1-mini（Fish-Speech dual_ar / 0.5B）本地零样本克隆 TTS 适配脚本。

插件调用方式（统一 CLI）：
    python fish.py --model <模型目录> --out <输出.wav> --text "<要念的内容>" \
        [--ref <参考音.wav>] [--ref-text "<参考音台词>"] \
        [--instruct "<风格/情绪指令>"] [--voice <音色ID>] [--speed 1.0] [--lang Chinese]

说明：
- 模型目录需要包含 model.pth / codec.pth / config.json / tokenizer.tiktoken / special_tokens.json
  （即 HF `fishaudio/s1-mini` 快照，本机路径 models\\models\\fishaudio--openaudio-s1-mini\\snapshots\\master）。
- 推理代码用的是该模型发布时代的官方代码（HF Space fishaudio/s1-mini 里的 fish_speech 包），
  已作为 fish-speech-s1 装进 venv-fish；与新版 fish-speech 3.x（S2-Pro / Drama3）的 tokenizer 不兼容，
  所以这里不用 D:\\AI\\语音POC\\src\\fish-speech 里的新版代码。
- --ref 必填（S1-mini 只支持零样本克隆，没有内置音色库）；--ref-text 可选。
- 情绪/语气标记：S1-mini 支持把标记直接写进台词，例如 "(sad)"、"(laughing)"、"(whispering)"、
  "[laugh]" 之类，脚本原样透传，不做特殊处理。--instruct 非空时原样拼在台词最前面。
- --speed / --voice / --lang 在本引擎没有对应实现，接受但忽略（会打印提示）。
"""
import argparse
import os
import sys
import time

# Windows 下默认 cp936，插件按 utf-8 读，这里统一成 utf-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 推理代码里的 tqdm 进度条会把插件日志刷满（\r 刷屏），关掉
os.environ.setdefault("TQDM_DISABLE", "1")


def log(msg):
    print(msg, flush=True)


def die(msg, code=1):
    print("[voice] 失败：" + msg, flush=True)
    sys.exit(code)


REQUIRED_FILES = ("model.pth", "codec.pth", "config.json", "tokenizer.tiktoken")
CODEC_CONFIG_NAME = "modded_dac_vq"
MAX_REF_SECONDS = 30.0


def parse_args():
    p = argparse.ArgumentParser(
        description="OpenAudio S1-mini (fish-speech dual_ar) 零样本克隆 TTS"
    )
    # 有意不设 required：缺参数时自己打印中文原因（插件要看得懂）
    p.add_argument("--model", default=None, help="模型快照目录")
    p.add_argument("--out", default=None, help="输出 wav 路径")
    p.add_argument("--text", default=None, help="要念的内容")
    p.add_argument("--ref", default=None, help="参考音 wav（零样本克隆，必填）")
    p.add_argument("--ref-text", default=None, help="参考音里说的那句话（可选）")
    p.add_argument(
        "--instruct",
        nargs="?",
        const="",
        default="",
        help="风格/情绪标记，原样拼到台词前",
    )
    p.add_argument("--voice", default="", help="本引擎无音色库，忽略")
    p.add_argument("--speed", type=float, default=1.0, help="本引擎无变速，忽略")
    p.add_argument("--lang", default="Chinese", help="本引擎多语种自适应，忽略")
    return p.parse_args()


def resolve_model_dir(raw):
    """--model 既可以是快照目录，也可以给上一层（自动找 snapshots/master）。"""
    if not raw:
        die("缺少 --model（模型目录）")
    candidates = [raw, os.path.join(raw, "snapshots", "master"), os.path.join(raw, "master")]
    for c in candidates:
        c = os.path.abspath(c)
        if os.path.isdir(c) and all(
            os.path.isfile(os.path.join(c, f)) for f in REQUIRED_FILES
        ):
            return c
    checked = "\n  ".join(os.path.abspath(c) for c in candidates)
    die(
        "模型目录不完整，需要包含 %s：\n  %s" % ("、".join(REQUIRED_FILES), checked)
    )


def main():
    args = parse_args()

    if not args.text or not args.text.strip():
        die("缺少 --text（要念的内容）")
    if not args.out:
        die("缺少 --out（输出 wav 路径）")
    if not args.ref:
        die("缺少 --ref（S1-mini 只支持零样本克隆，必须给参考音 wav）")
    if not os.path.isfile(args.ref):
        die("参考音文件不存在：%s" % args.ref)

    model_dir = resolve_model_dir(args.model)
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    text = args.text.strip()
    instruct = (args.instruct or "").strip()
    if instruct:
        # S1-mini 只认台词里的括号标记，这里把指令原样放最前面
        text = instruct + (" " if not instruct.endswith(" ") else "") + text
        log("[voice] 提示：--instruct 已原样拼到台词前（S1-mini 建议只写情绪标记，如 (sad)、(laughing)）")
    for name, value, why in (
        ("--speed", args.speed, "本引擎无变速参数"),
        ("--voice", args.voice, "本引擎没有音色库"),
        ("--lang", args.lang, "多语种自动识别"),
    ):
        if value not in (None, "", 1.0, "Chinese"):
            log("[voice] 提示：%s 已忽略（%s）" % (name, why))

    ref_text = (args.ref_text or "").strip()

    dtype = os.environ.get("AIVOICE_FISH_DTYPE", "float32").strip().lower()
    device = "cpu"

    import numpy as np
    import torch

    if dtype in ("bf16", "bfloat16"):
        precision = torch.bfloat16
    elif dtype in ("fp16", "float16", "half"):
        precision = torch.float16
    else:
        precision = torch.float32
    if device == "cpu" and precision is torch.float16:
        log("[voice] 提示：CPU 上 float16 不稳定，改回 float32")
        precision = torch.float32

    log("[voice] loading OpenAudio S1-mini from %s" % model_dir)
    t_load = time.time()

    # ---- 导入本模型发布时代的官方推理代码（fish-speech-s1，装在 venv 里） ----
    try:
        from fish_speech.models.dac.modded_dac import DAC  # noqa: F401
        from fish_speech.models.text2semantic.inference import (
            generate_long,
            init_model,
        )
    except Exception as exc:  # 依赖缺失时给中文提示
        die("导入 fish_speech 推理代码失败（venv 环境不完整？）：%r" % (exc,))

    # ---- 加载 LLM（text2semantic 主干） ----
    try:
        t0 = time.time()
        model, decode_one_token = init_model(
            model_dir, device, precision, compile=False
        )
        log("[voice] 主干模型加载 %.1fs" % (time.time() - t0))
    except Exception as exc:
        die("加载 model.pth 失败：%r" % (exc,))

    # ---- 加载 DAC 声码器 ----
    try:
        codec = load_codec(model_dir, device, precision)
    except Exception as exc:
        die("加载 codec.pth 失败：%r" % (exc,))

    log("[voice] loaded in %.1fs" % (time.time() - t_load))

    # ---- 参考音 -> VQ codes ----
    try:
        import torchaudio

        wav, sr = torchaudio.load(args.ref)
        if wav.dim() == 2 and wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)
        if wav.dim() == 1:
            wav = wav[None]
        if sr != codec.sample_rate:
            wav = torchaudio.functional.resample(wav, sr, codec.sample_rate)
        max_len = int(MAX_REF_SECONDS * codec.sample_rate)
        if wav.shape[-1] > max_len:
            log(
                "[voice] 提示：参考音 %.1fs，截断到 %.0fs"
                % (wav.shape[-1] / codec.sample_rate, MAX_REF_SECONDS)
            )
            wav = wav[:, :max_len]
        codec_dtype = next(codec.parameters()).dtype
        audios = wav[None].to(device=device, dtype=codec_dtype)
        audio_lengths = torch.tensor(
            [audios.shape[2]], device=device, dtype=torch.long
        )
        with torch.inference_mode():
            indices, _ = codec.encode(audios, audio_lengths)
        ref_codes = indices[0].cpu()
        log(
            "[voice] 参考音 %.2fs -> VQ %s"
            % (audios.shape[2] / codec.sample_rate, tuple(ref_codes.shape))
        )
    except Exception as exc:
        die("参考音编码失败：%r" % (exc,))

    # ---- 生成 ----
    prompt_text = [ref_text if ref_text else ""]
    torch.manual_seed(42)
    # 只在没给参考音台词时提示一下（S1 官方 webui 也允许留空）
    if not ref_text:
        log("[voice] 提示：没给 --ref-text，参考音台词留空（音色能克隆，稳定性略降）")

    n_chars = len(text)
    max_new_tokens = int(min(2048, max(256, 24 * n_chars)))

    log("[voice] 开始生成：%d 字（max_new_tokens=%d）" % (n_chars, max_new_tokens))
    t_gen = time.time()
    codes = []
    try:
        generator = generate_long(
            model=model,
            device=device,
            decode_one_token=decode_one_token,
            text=text,
            num_samples=1,
            max_new_tokens=max_new_tokens,
            top_p=0.7,
            repetition_penalty=1.2,
            temperature=0.7,
            compile=False,
            iterative_prompt=False,
            chunk_length=0,
            prompt_text=prompt_text,
            prompt_tokens=[ref_codes],
        )
        for response in generator:
            if response.action == "sample":
                if response.codes is not None:
                    codes.append(response.codes)
            elif response.action == "next":
                break
    except Exception as exc:
        import traceback

        traceback.print_exc()
        die("推理失败：%r" % (exc,))

    if not codes:
        die("模型没有生成任何音频帧（text 或参考音可能有问题）")

    merged = torch.cat(codes, dim=1).to(device=device, dtype=torch.long)
    log("[voice] 生成 %d 帧 VQ" % merged.shape[1])

    # ---- VQ -> wav ----
    try:
        with torch.inference_mode():
            feature_lengths = torch.tensor([merged.shape[1]], device=device)
            audio_tensor, _ = codec.decode(
                indices=merged[None], feature_lengths=feature_lengths
            )
        audio = audio_tensor[0, 0].float().cpu().numpy()
    except Exception as exc:
        die("声码器解码失败：%r" % (exc,))

    if not np.isfinite(audio).all():
        die("生成的音频含 NaN/Inf，模型输出异常")
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 1.0:
        audio = audio / peak
    if audio.size < codec.sample_rate * 0.1:
        log("[voice] 警告：生成音频很短（%.2fs），台词可能被模型跳过" % (audio.size / codec.sample_rate))

    try:
        import soundfile as sf

        sf.write(out_path, audio, codec.sample_rate, subtype="PCM_16")
    except Exception as exc:
        die("写 wav 失败：%r" % (exc,))

    dur = audio.size / codec.sample_rate
    log(
        "[voice] generated in %.1fs -> %s (%.2fs, %.2f MB)"
        % (
            time.time() - t_gen,
            out_path,
            dur,
            os.path.getsize(out_path) / 1024.0 / 1024.0,
        )
    )
    return 0


def load_codec(model_dir, device, precision):
    """加载 DAC 声码器（codec.pth）。

    不用 fish_speech.models.dac.inference.load_model，因为它 import 时依赖
    pyrootutils 的 .project-root（装进 site-packages 后找不到）。
    """
    from pathlib import Path

    import torch
    from hydra import compose, initialize_config_dir
    from hydra.utils import instantiate
    from omegaconf import OmegaConf

    import fish_speech

    codec_path = os.path.join(model_dir, "codec.pth")
    if not os.path.isfile(codec_path):
        raise FileNotFoundError("模型目录里没有 codec.pth：%s" % codec_path)

    config_dir = str(Path(fish_speech.__file__).parent / "configs")
    try:
        OmegaConf.register_new_resolver("eval", eval)
    except Exception:
        pass

    import hydra.core.global_hydra

    hydra.core.global_hydra.GlobalHydra.instance().clear()
    with initialize_config_dir(config_dir=config_dir, version_base="1.3"):
        cfg = compose(config_name=CODEC_CONFIG_NAME)
    codec = instantiate(cfg)

    state_dict = torch.load(
        codec_path, map_location="cpu", mmap=True, weights_only=True
    )
    if "state_dict" in state_dict:
        state_dict = state_dict["state_dict"]
    if any("generator" in k for k in state_dict):
        state_dict = {
            k.replace("generator.", ""): v
            for k, v in state_dict.items()
            if "generator." in k
        }
    result = codec.load_state_dict(state_dict, strict=False, assign=True)
    codec.eval()
    codec.to(device=device, dtype=precision)
    log("[voice] 声码器加载完成（missing=%d unexpected=%d）"
        % (len(result.missing_keys), len(result.unexpected_keys)))
    return codec


if __name__ == "__main__":
    sys.exit(main())
