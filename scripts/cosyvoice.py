# -*- coding: utf-8 -*-
"""Fun-CosyVoice3-0.5B 零样本音色克隆适配脚本（ai-voice 插件用）。

把本地 FunAudioLLM/CosyVoice 源码 + Fun-CosyVoice3-0.5B-2512 模型快照包装成
插件统一的 CLI：

    python cosyvoice.py --model <模型目录> --out <输出.wav> --text "要念的内容" \
        --ref <参考音.wav> [--ref-text "参考音里说的那句话"] \
        [--instruct "<风格/情绪/方言指令>"] [--speed 1.0]

- 零样本克隆：同时给 --ref 和 --ref-text 时走 CosyVoice3 zero-shot（音色+韵律最像）。
- 只给 --ref（没有台词）时自动退化为 cross-lingual：同样克隆音色，只是少了
  参考音台词的约束。
- --instruct：走 CosyVoice3 instruct2（仍用 --ref 提供音色）。
- 该模型没有自带说话人，--voice 忽略；语种自动判定，--lang 忽略。
- 全程只读本机，不联网。

坑位记录（本机实测）：
1) CosyVoice3 的 prompt_text / 指令文本里必须含 <|endofprompt|>，否则模型内部
   assert 直接失败；所以脚本会自动补 "You are a helpful assistant.<|endofprompt|>"。
2) 当 --text 和 --ref-text 是同一句话时，CosyVoice3 zero-shot 第 0 步就容易采样到
   eos，只生成 0.04s 甚至 0（flow/hift 报卷积尺寸错误）。脚本检测到“说要念的内容
   与参考音台词重复”会直接改走 cross-lingual 兜底。
3) 参考音 30s 以内、>=16kHz；hf 侧一次只装载一份模型（CPU 约 7~8GB 内存）。

环境：D:\\AI\\语音POC\\venv-cosyvoice（CPU 版 torch 2.3.1），
源码：D:\\AI\\语音POC\\src\\CosyVoice（third_party/Matcha-TTS 空子模块，已在 venv
site-packages 放了一份可用的 matcha 精简副本）。
"""
import argparse
import os
import re
import sys
import time
import traceback

DEFAULT_REPO = r'D:\AI\语音POC\src\CosyVoice'
SYS_PROMPT = 'You are a helpful assistant.'
ENDOFPROMPT = '<|endofprompt|>'
# 短于这个时长视为“退化输出”，换兜底路径重试
DEGENERATE_SECONDS = 0.15


def fix_std_streams():
    """统一用 utf-8 输出，避免 Windows 管道下中文报错乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def log(msg):
    print(msg, flush=True)


def fail(msg, code=2):
    print('[voice] 生成失败：' + msg, file=sys.stderr, flush=True)
    sys.exit(code)


def force_fp32_qwen():
    """CosyVoice-BlankEN 的 config.json 标了 bfloat16，CPU 上固定成 fp32。

    Qwen2Encoder 在 yaml 反序列化时用 Qwen2ForCausalLM.from_pretrained 建模型，
    必须在 import cosyvoice 之前打补丁（随后 llm.pt 会覆盖这些权重）。
    """
    import torch
    import transformers

    orig = transformers.Qwen2ForCausalLM.from_pretrained

    def patched(*args, **kwargs):
        kwargs['torch_dtype'] = torch.float32
        return orig(*args, **kwargs)

    transformers.Qwen2ForCausalLM.from_pretrained = patched


def build_parser():
    p = argparse.ArgumentParser(
        description='Fun-CosyVoice3-0.5B 零样本克隆（本地 CPU 推理）',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument('--model', required=True, help='Fun-CosyVoice3-0.5B-2512 快照目录')
    p.add_argument('--out', required=True, help='输出 wav 路径（父目录自动创建）')
    p.add_argument('--text', required=True, help='要合成的内容')
    p.add_argument('--ref', default='', help='参考音 wav（音色克隆必填）')
    p.add_argument('--ref-text', default='', help='参考音里说的那句话（给质量更好，可省）')
    p.add_argument('--instruct', default='', help='风格/情绪/方言指令（可选）')
    p.add_argument('--voice', default='', help='音色 ID（该模型不支持，忽略）')
    p.add_argument('--speed', type=float, default=1.0, help='语速倍率，0.5~2.0')
    p.add_argument('--lang', default='Chinese', help='语种（该模型自动判定，忽略）')
    p.add_argument('--repo', default=DEFAULT_REPO, help='CosyVoice 源码仓库目录')
    p.add_argument('--threads', type=int, default=0, help='CPU 线程数，0=自动')
    return p


def check_ref_audio(path):
    """校验参考音：存在、可读、>=16k、<=30s。"""
    try:
        import soundfile as sf
        info = sf.info(path)
    except Exception as e:
        fail('参考音不可读：%s（%s）' % (path, e))
    if info.samplerate < 16000:
        fail('参考音采样率 %d Hz 太低，至少需要 16000 Hz' % info.samplerate)
    if info.duration > 30:
        fail('参考音时长 %.1fs 超过 30s，CosyVoice3 的语音 token 提取只支持 30s 以内'
             % info.duration)
    return info


def normalize_for_compare(text):
    """去掉标点/空白后比较，判断“要念的内容”是否就是参考音台词。"""
    return re.sub(r'[\s，。！？、,.!?;；:：""\'\'（）()\[\]【】…—\-~]+', '', text or '')


def with_sys_prompt(text):
    """CosyVoice3 要求文本里出现 <|endofprompt|>，没有就补 system prompt。"""
    if ENDOFPROMPT in text:
        return text
    return SYS_PROMPT + ENDOFPROMPT + text


def main():
    fix_std_streams()
    args = build_parser().parse_args()

    text = (args.text or '').strip()
    if text == '':
        fail('--text 不能为空')

    model_dir = os.path.abspath(args.model)
    if not os.path.isdir(model_dir):
        fail('模型目录不存在：%s' % model_dir)
    if not os.path.isfile(os.path.join(model_dir, 'cosyvoice3.yaml')):
        fail('模型目录里没有 cosyvoice3.yaml，不像是 Fun-CosyVoice3 模型：%s' % model_dir)
    for fn in ('llm.pt', 'flow.pt', 'hift.pt', 'campplus.onnx', 'speech_tokenizer_v3.onnx',
               os.path.join('CosyVoice-BlankEN', 'config.json')):
        if not os.path.isfile(os.path.join(model_dir, fn)):
            fail('模型文件缺失：%s' % os.path.join(model_dir, fn))

    repo_dir = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(repo_dir, 'cosyvoice')):
        fail('CosyVoice 源码目录不对（找不到 cosyvoice/ 包）：%s' % repo_dir)
    sys.path.insert(0, repo_dir)

    ref = (args.ref or '').strip()
    ref_text = (args.ref_text or '').strip()
    instruct = (args.instruct or '').strip()

    if args.voice.strip():
        log('[voice] 提示：该模型没有自带说话人，--voice 已忽略（音色由 --ref 决定）')
    if args.lang.strip() not in ('', 'Chinese', 'zh'):
        log('[voice] 提示：CosyVoice3 自动判定语种，--lang=%s 已忽略' % args.lang.strip())
    speed = float(args.speed)
    if not (0.5 <= speed <= 2.0):
        log('[voice] 警告：--speed=%.2f 超出建议范围 0.5~2.0，仍按原值执行' % speed)

    if ref == '' or not os.path.isfile(ref):
        fail('缺少参考音：零样本克隆需要 --ref 指向一个存在的 wav 文件')
    ref = os.path.abspath(ref)
    ref_info = check_ref_audio(ref)

    # 决定首选模式
    duplicate_ref_text = False
    if instruct != '':
        primary = 'instruct'
    elif ref_text != '':
        primary = 'zero'
        duplicate_ref_text = normalize_for_compare(ref_text) == normalize_for_compare(text)
    else:
        primary = 'fallback'

    log('[voice] ref=%s (%.2fs, %d Hz)' % (ref, ref_info.duration, ref_info.samplerate))
    log('[voice] mode=%s%s' % (primary, '（台词与参考音台词相同，自动改走兜底）'
                               if primary == 'zero' and duplicate_ref_text else ''))

    print('[voice] loading Fun-CosyVoice3 (CosyVoice3) from %s' % model_dir, flush=True)

    import logging
    logging.getLogger().setLevel(logging.WARNING)

    try:
        import torch
        torch.set_grad_enabled(False)
        if args.threads > 0:
            torch.set_num_threads(args.threads)
            log('[voice] torch threads=%d' % args.threads)
        force_fp32_qwen()

        t_load = time.time()
        from cosyvoice.cli.cosyvoice import AutoModel
        model = AutoModel(model_dir=model_dir)
        load_s = time.time() - t_load
        try:
            dt = next(model.model.llm.parameters()).dtype
        except Exception:
            dt = '?'
        log('[voice] loaded in %.1fs (sample_rate=%d, llm_dtype=%s)'
            % (load_s, model.sample_rate, dt))
    except SystemExit:
        raise
    except Exception as e:
        traceback.print_exc()
        fail('加载模型失败：%s: %s' % (type(e).__name__, e), code=3)

    # ---------- 推理 ----------
    def run_generator(gen):
        import torch
        chunks = []
        for item in gen:
            speech = item.get('tts_speech')
            if speech is not None and speech.numel() > 0:
                chunks.append(speech.detach().cpu())
        if not chunks:
            return None
        return torch.cat(chunks, dim=1).squeeze(0).float()

    def try_mode(mode):
        if mode == 'zero':
            prompt_text = with_sys_prompt(ref_text)
            return run_generator(model.inference_zero_shot(
                text, prompt_text, ref, stream=False, speed=speed, text_frontend=False))
        if mode == 'instruct':
            # 指令模式下 system prompt 后面直接接指令文本，再以 <|endofprompt|> 收尾
            if ENDOFPROMPT in instruct:
                ins = instruct
            elif instruct:
                ins = '%s %s%s' % (SYS_PROMPT, instruct, ENDOFPROMPT)
            else:
                ins = SYS_PROMPT + ENDOFPROMPT
            return run_generator(model.inference_instruct2(
                text, ins, ref, stream=False, speed=speed, text_frontend=False))
        # fallback: cross-lingual（不需要参考音台词，音色仍来自参考音）
        return run_generator(model.inference_cross_lingual(
            with_sys_prompt(text), ref, stream=False, speed=speed, text_frontend=False))

    attempt_order = []
    if primary == 'zero' and not duplicate_ref_text:
        attempt_order = ['zero', 'instruct', 'fallback']
    elif primary == 'instruct':
        attempt_order = ['instruct', 'fallback']
    else:
        attempt_order = ['fallback', 'instruct']

    t_gen = time.time()
    wav = None
    used_mode = None
    last_err = None
    for i, mode in enumerate(attempt_order):
        if i > 0:
            log('[voice] 上一次输出退化/失败，改用兜底模式 %s 重试' % mode)
        try:
            candidate = try_mode(mode)
        except Exception as e:
            last_err = e
            log('[voice] 模式 %s 失败：%s: %s' % (mode, type(e).__name__, e))
            traceback.print_exc()
            continue
        if candidate is None:
            log('[voice] 模式 %s 没有产出音频' % mode)
            continue
        dur = len(candidate) / float(model.sample_rate)
        log('[voice] 模式 %s 产出 %.2fs 音频' % (mode, dur))
        if dur >= DEGENERATE_SECONDS:
            wav, used_mode = candidate, mode
            break
        log('[voice] 模式 %s 输出过短（%.2fs），视为退化' % (mode, dur))

    if wav is None:
        if last_err is not None:
            fail('所有推理路径都失败，最后错误：%s: %s'
                 % (type(last_err).__name__, last_err), code=4)
        fail('所有推理路径都没有产出有效音频（参考音是否过短/无声？）', code=4)

    try:
        import numpy as np
        import soundfile as sf
        wav_np = np.clip(wav.numpy(), -1.0, 1.0).astype(np.float32)
        out_dir = os.path.dirname(os.path.abspath(args.out))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        sf.write(args.out, wav_np, int(model.sample_rate), subtype='PCM_16')
        gen_s = time.time() - t_gen
        log('[voice] generated in %.1fs -> %s' % (gen_s, os.path.abspath(args.out)))
        log('[voice] duration %.2fs, %d Hz, mode=%s'
            % (len(wav_np) / float(model.sample_rate), int(model.sample_rate), used_mode))
        return 0
    except SystemExit:
        raise
    except Exception as e:
        traceback.print_exc()
        fail('写 wav 失败：%s: %s' % (type(e).__name__, e), code=5)


if __name__ == '__main__':
    sys.exit(main())
