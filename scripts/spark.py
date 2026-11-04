# -*- coding: utf-8 -*-
"""Spark-TTS 0.5B：零样本声音克隆（参考音 + 台词 → 语音）。

用法：
  python spark.py --model <模型目录> --out OUT.wav --text "要说的话" --ref 参考音.wav
                  [--ref-text "参考音里说的那句话"]

说明：
  - Spark-TTS 是零样本克隆引擎，--ref 必填，走「仅参考音」零样本克隆（已实测稳定）。
  - --ref-text 参数接受但忽略：本仓库自带的「参考文本」推理模式在这版模型上会立刻输出
    EOS（空音频），实测不可用，因此统一走仅参考音模式（不需要参考台词）。
  - 引擎本身不支持自然语言风格指令 / 音色 ID / 语言切换；--instruct/--voice/--lang 接受但忽略。
  - 输出为 16kHz 单声道 wav（模型原生采样率）。
"""
import argparse
import os
import sys
import time


# Spark-TTS 源码目录（仓库没有 setup.py，直接把仓库根塞进 sys.path 后用 cli/SparkTTS.py）
DEFAULT_SRC = r'D:\AI\语音POC\src\Spark-TTS'


def _fail(msg, code=1):
    print('[voice] 错误：' + msg, file=sys.stderr, flush=True)
    return code


def main():
    # 中文日志统一走 UTF-8，避免 Windows 管道下 GBK 乱码
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    parser = argparse.ArgumentParser(description='Spark-TTS zero-shot voice cloning')
    parser.add_argument('--model', required=True, help='模型目录（含 LLM/ BiCodec/ wav2vec2-large-xlsr-53/）')
    parser.add_argument('--out', required=True, help='输出 wav 路径')
    parser.add_argument('--text', required=True, help='要念的内容')
    parser.add_argument('--ref', default='', help='参考音 wav（必填）')
    parser.add_argument('--ref-text', dest='ref_text', default='', help='参考音台词（本模型不支持，忽略）')
    parser.add_argument('--instruct', default='', help='风格指令（Spark-TTS 不支持，忽略）')
    parser.add_argument('--voice', default='', help='音色 ID（Spark-TTS 不支持，忽略）')
    parser.add_argument('--speed', default='1.0', help='语速（Spark-TTS 克隆模式不支持，忽略）')
    parser.add_argument('--lang', default='Chinese', help='语言（Spark-TTS 自动判断，忽略）')
    args = parser.parse_args()

    text = (args.text or '').strip()
    if text == '':
        return _fail('要念的内容不能为空（--text）')

    model_dir = os.path.abspath(args.model)
    if not os.path.isdir(model_dir):
        return _fail('模型目录不存在：' + model_dir)
    for sub in ('LLM', 'BiCodec', 'wav2vec2-large-xlsr-53'):
        if not os.path.isdir(os.path.join(model_dir, sub)):
            return _fail('模型目录不完整，缺少 %s 子目录：%s' % (sub, model_dir))

    ref = (args.ref or '').strip()
    if ref == '':
        return _fail('Spark-TTS 是零样本克隆引擎，必须提供 --ref 参考音')
    ref = os.path.abspath(ref)
    if not os.path.isfile(ref):
        return _fail('参考音不存在：' + ref)

    if args.instruct.strip() != '':
        print('[voice] 提示：Spark-TTS 不支持风格指令 --instruct，已忽略', flush=True)
    if args.voice.strip() != '':
        print('[voice] 提示：Spark-TTS 不支持音色 ID --voice，已忽略', flush=True)
    if args.ref_text.strip() != '':
        print('[voice] 提示：Spark-TTS 的「参考音台词」模式在 0.5B 模型上实测会立即输出空音频，'
              '已忽略 --ref-text，改用仅参考音克隆', flush=True)
    if args.lang.strip() not in ('', 'Chinese', '中文'):
        print('[voice] 提示：Spark-TTS 自动判断中英文，--lang 已忽略', flush=True)

    out_abs = os.path.abspath(args.out)
    out_dir = os.path.dirname(out_abs)
    if out_dir != '':
        os.makedirs(out_dir, exist_ok=True)

    # 模型全部本地，禁止联网
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

    src_dir = os.environ.get('SPARK_TTS_SRC', DEFAULT_SRC)
    if not os.path.isdir(os.path.join(src_dir, 'cli')):
        return _fail('Spark-TTS 源码目录不存在（需要 cli/SparkTTS.py）：' + src_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    try:
        import numpy as np
        import soundfile as sf
        import torch
        from cli.SparkTTS import SparkTTS
    except Exception as exc:
        return _fail('导入 Spark-TTS 依赖失败：%s（venv 是否需要装 torch/torchaudio/transformers？）' % exc)

    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

    print('[voice] loading Spark-TTS from %s' % model_dir, flush=True)
    t0 = time.time()
    try:
        model = SparkTTS(model_dir=model_dir, device=device)
    except Exception as exc:
        return _fail('加载模型失败：%s' % exc)
    print('[voice] loaded in %.1fs' % (time.time() - t0), flush=True)

    print('[voice] cloning from %s（仅参考音零样本克隆）' % ref, flush=True)

    t0 = time.time()
    try:
        # prompt_text=None：走稳定的仅参考音模式（本模型参考文本模式会立即 EOS 出空音频）
        wav = model.inference(text, prompt_speech_path=ref, prompt_text=None)
    except Exception as exc:
        return _fail('推理失败：%s' % exc)

    wav = np.asarray(wav).squeeze()
    if wav.ndim != 1 or wav.size == 0:
        return _fail('模型返回了空音频（shape=%s）' % (np.asarray(wav).shape,))
    sample_rate = int(getattr(model, 'sample_rate', 16000) or 16000)
    try:
        sf.write(out_abs, wav.astype('float32'), sample_rate)
    except Exception as exc:
        return _fail('写 wav 失败：%s' % exc)

    if not os.path.isfile(out_abs) or os.path.getsize(out_abs) == 0:
        return _fail('没有写出有效 wav：' + out_abs)

    duration = float(wav.size) / float(sample_rate)
    print('[voice] generated in %.1fs -> %s（%.1fs 音频, %d Hz）'
          % (time.time() - t0, out_abs, duration, sample_rate), flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:  # 兜底：保证中文报错 + 非 0 退出
        import traceback
        traceback.print_exc()
        print('[voice] 错误：未预期异常 %s' % exc, file=sys.stderr, flush=True)
        sys.exit(1)
