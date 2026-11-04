# -*- coding: utf-8 -*-
"""GPT-SoVITS 本地推理适配脚本（CPU，零样本 / 参考音克隆）。

基于 repo 自带的 GPT_SoVITS/TTS_infer_pack/TTS.py 的 TTS 类，不自己拼模型。

用法（插件按此调用）：
  python gptsovits.py --model <模型快照目录> --out <输出.wav> --text "要念的内容" \\
      --ref <参考音.wav> --ref-text "参考音里说的那句话" [--lang Chinese] [--speed 1.0]

支持版本（按 --model 目录里存在的文件自动选择，默认 v4）：
  v4        : gsv-v4-pretrained/s2Gv4.pth + gsv-v4-pretrained/vocoder.pth + s1v3.ckpt
  v2ProPlus : v2Pro/s2Gv2ProPlus.pth + s1v3.ckpt + sv/
  v2        : gsv-v2final-pretrained/s2G2333k.pth + gsv-v2final-pretrained/s1bert25hz-5kh-*.ckpt
  v1        : s2G488k.pth + s1bert25hz-2kh-*.ckpt

说明：
  - 只有中文（--lang Chinese）经过测试；--instruct / --voice 该引擎不支持（接受但忽略）。
  - 参考音必须 3~10 秒（TTS 类内部限制）。
  - 本脚本不联网、不下载模型；G2PW 拼音模型缺失时自动退回 pypinyin。
"""
import argparse
import gc
import os
import subprocess
import sys
import time
import traceback
import types

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join("D:\\AI", "语音POC", "src", "GPT-SoVITS")
WORK_ROOT = os.path.join("D:\\AI", "语音POC", "work", "gptsovits")
RUN_ROOT = os.path.join(WORK_ROOT, "runroot")

# 各版本需要的文件（相对模型快照根目录）
VERSION_REQUIRED = {
    "v4": [
        "gsv-v4-pretrained/s2Gv4.pth",
        "gsv-v4-pretrained/vocoder.pth",
        "s1v3.ckpt",
        "chinese-hubert-base/config.json",
        "chinese-roberta-wwm-ext-large/config.json",
    ],
    "v2ProPlus": [
        "v2Pro/s2Gv2ProPlus.pth",
        "s1v3.ckpt",
        "sv/pretrained_eres2netv2w24s4ep4.ckpt",
        "chinese-hubert-base/config.json",
        "chinese-roberta-wwm-ext-large/config.json",
    ],
    "v3": [
        "s2Gv3.pth",
        "s1v3.ckpt",
        "chinese-hubert-base/config.json",
        "chinese-roberta-wwm-ext-large/config.json",
    ],
    "v2": [
        "gsv-v2final-pretrained/s2G2333k.pth",
        "gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
        "chinese-hubert-base/config.json",
        "chinese-roberta-wwm-ext-large/config.json",
    ],
    "v1": [
        "s2G488k.pth",
        "s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt",
        "chinese-hubert-base/config.json",
        "chinese-roberta-wwm-ext-large/config.json",
    ],
}

# 各版本需要硬编码相对路径的模型子目录（TTS.py 内部用 os.getcwd() 拼路径）
VERSION_LINK_DIRS = {
    "v4": ["gsv-v4-pretrained"],
    "v2ProPlus": ["v2Pro", "sv"],
    "v2": [],
    "v1": [],
}

AUTO_ORDER = ["v4", "v2ProPlus", "v2", "v1"]


def log(msg, *args):
    if args:
        msg = msg % args
    print(msg, flush=True)


def err(msg):
    print("[voice] 失败：%s" % msg, flush=True)


def normalize_lang(lang):
    """把插件传进来的 --lang 归一成 GPT-SoVITS 的语言 id（目前只支持中文）。"""
    s = (lang or "").strip().lower()
    if s in ("", "chinese", "zh", "zh-cn", "zh_cn", "中文", "汉语", "普通话", "all_zh", "auto"):
        return "all_zh"
    raise SystemExit("GPT-SoVITS 适配脚本目前只支持中文，--lang 收到：%r（可用：Chinese）" % lang)


def pick_versions(model_dir, forced):
    if forced and forced != "auto":
        missing = [p for p in VERSION_REQUIRED.get(forced, []) if not os.path.exists(os.path.join(model_dir, p))]
        if missing:
            raise SystemExit("模型目录缺少 %s 版本所需文件：%s" % (forced, "; ".join(missing)))
        return [forced]
    available = []
    for v in AUTO_ORDER:
        if all(os.path.exists(os.path.join(model_dir, p)) for p in VERSION_REQUIRED[v]):
            available.append(v)
    if not available:
        lines = ["模型目录里没有可用的 GPT-SoVITS 权重：%s" % model_dir]
        for v in AUTO_ORDER:
            lines.append("  需要的 %s：%s" % (v, ", ".join(VERSION_REQUIRED[v])))
        raise SystemExit("\n".join(lines))
    return available


def make_junctions(model_dir, version):
    """TTS.py 里 vocoder/SV 的路径是相对 cwd 的，这里在工作区造 junction 顶替，不改源码目录。"""
    pred_root = os.path.join(RUN_ROOT, "GPT_SoVITS", "pretrained_models")
    os.makedirs(pred_root, exist_ok=True)
    for rel in VERSION_LINK_DIRS.get(version, []):
        target = os.path.join(model_dir, rel)
        link = os.path.join(pred_root, rel)
        if not os.path.exists(target):
            raise SystemExit("模型目录缺少 %s（%s 版本需要）" % (rel, version))
        if os.path.exists(link):
            if os.path.isdir(link):
                continue
            os.remove(link)
        out = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, target],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if out.returncode != 0:
            raise SystemExit("创建模型目录链接失败（%s -> %s）：%s" %
                             (link, target, out.stderr.decode("gbk", "replace").strip()))
        log("[voice] linked %s -> %s" % (rel, target))


def install_fake_lang_modules():
    """LangSegmenter 会初始化 fast_langdetect（首次使用会联网下模型），
    本脚本只需中文、按整段处理，所以用轻量桩替代，保证离线可跑。"""
    fl = types.ModuleType("fast_langdetect")

    class _LangDetectConfig:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _LangDetector:
        def __init__(self, *args, **kwargs):
            self.config = args[0] if args else None

        def detect(self, text):
            return [{"lang": "zh", "score": 1.0}]

    infer = types.ModuleType("fast_langdetect.infer")
    infer._default_detector = None
    infer.LangDetector = _LangDetector
    infer.LangDetectConfig = _LangDetectConfig
    fl.infer = infer
    sys.modules["fast_langdetect"] = fl
    sys.modules["fast_langdetect.infer"] = infer

    sl = types.ModuleType("split_lang")

    class _LangSplitter:
        def __init__(self, *args, **kwargs):
            pass

        def split_by_lang(self, text):
            return []

    sl.LangSplitter = _LangSplitter
    sys.modules["split_lang"] = sl


def ensure_jieba_fast():
    """jieba_fast 只有源码包（Windows 上可能要编译）；装不上时用 jieba 做一个同接口替身。"""
    try:
        import jieba_fast  # noqa: F401
        import jieba_fast.posseg  # noqa: F401
        return
    except Exception as e:  # noqa: BLE001
        log("[voice] jieba_fast 不可用（%s），改用 jieba 替身", type(e).__name__)
    import jieba

    mod = types.ModuleType("jieba_fast")
    for name in dir(jieba):
        if not name.startswith("_"):
            setattr(mod, name, getattr(jieba, name))
    mod.setLogLevel = getattr(jieba, "setLogLevel", lambda level: None)
    import jieba.posseg as jb_posseg

    posseg = types.ModuleType("jieba_fast.posseg")
    for name in dir(jb_posseg):
        if not name.startswith("_"):
            setattr(posseg, name, getattr(jb_posseg, name))
    mod.posseg = posseg
    mod.__path__ = []
    sys.modules["jieba_fast"] = mod
    sys.modules["jieba_fast.posseg"] = posseg


def install_text_patches():
    """repo 的 text/chinese2.py 在导入时就会实例化 G2PW（需要 G2PWModel，且缺失时会联网下载）。
    我们跳过它，改用 pypinyin 回退路径；只替换内存里的模块，不改 repo 文件。"""
    import text  # noqa: F401  确保 text 包已定位到 repo

    src_path = os.path.join(REPO, "GPT_SoVITS", "text", "chinese2.py")
    with open(src_path, "r", encoding="utf-8-sig") as f:
        src = f.read()
    if "is_g2pw = True" not in src:
        raise SystemExit("text/chinese2.py 结构变化，找不到 is_g2pw 开关：%s" % src_path)
    src = src.replace("is_g2pw = True", "is_g2pw = False", 1)
    mod = types.ModuleType("text.chinese2")
    mod.__file__ = src_path
    mod.__package__ = "text"
    mod.__dict__["__name__"] = "text.chinese2"
    sys.modules["text.chinese2"] = mod
    exec(compile(src, src_path, "exec"), mod.__dict__)
    log("[voice] text patch: chinese2 g2pw 已关闭（改用 pypinyin）")


def patch_lang_segmenter():
    """中文整段处理：绕开 LangSegmenter 的自动语种切分。"""
    from text.LangSegmenter import LangSegmenter

    def _get_texts(text, default_lang=""):
        lang = (default_lang or "zh").strip() or "zh"
        return [{"lang": lang, "text": text}]

    LangSegmenter.getTexts = staticmethod(_get_texts)


def tts_config_dict(model_dir, version):
    cfg = {
        "device": "cpu",
        "is_half": False,
        "version": version,
        "bert_base_path": os.path.join(model_dir, "chinese-roberta-wwm-ext-large"),
        "cnhuhbert_base_path": os.path.join(model_dir, "chinese-hubert-base"),
    }
    if version == "v4":
        cfg["t2s_weights_path"] = os.path.join(model_dir, "s1v3.ckpt")
        cfg["vits_weights_path"] = os.path.join(model_dir, "gsv-v4-pretrained", "s2Gv4.pth")
    elif version == "v2ProPlus":
        cfg["t2s_weights_path"] = os.path.join(model_dir, "s1v3.ckpt")
        cfg["vits_weights_path"] = os.path.join(model_dir, "v2Pro", "s2Gv2ProPlus.pth")
    elif version == "v3":
        cfg["t2s_weights_path"] = os.path.join(model_dir, "s1v3.ckpt")
        cfg["vits_weights_path"] = os.path.join(model_dir, "s2Gv3.pth")
    elif version == "v2":
        cfg["t2s_weights_path"] = os.path.join(
            model_dir, "gsv-v2final-pretrained", "s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt")
        cfg["vits_weights_path"] = os.path.join(model_dir, "gsv-v2final-pretrained", "s2G2333k.pth")
    elif version == "v1":
        cfg["t2s_weights_path"] = os.path.join(
            model_dir, "s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt")
        cfg["vits_weights_path"] = os.path.join(model_dir, "s2G488k.pth")
    else:
        raise SystemExit("不支持的 GPT-SoVITS 版本：%s" % version)
    return {"custom": cfg}


def synth_once(tts, text, text_lang, ref_path, ref_text, speed):
    inputs = {
        "text": text,
        "text_lang": text_lang,
        "ref_audio_path": ref_path,
        "aux_ref_audio_paths": [],
        "prompt_text": ref_text,
        "prompt_lang": text_lang,
        "top_k": 15,
        "top_p": 1.0,
        "temperature": 1.0,
        "text_split_method": "cut5",
        "batch_size": 1,
        "batch_threshold": 0.75,
        "split_bucket": True,
        "speed_factor": float(speed),
        "fragment_interval": 0.3,
        "seed": -1,
        "parallel_infer": True,
        "repetition_penalty": 1.35,
        "sample_steps": 32,
        "super_sampling": False,
        "return_fragment": False,
        "streaming_mode": False,
    }
    last = None
    for item in tts.run(inputs):
        last = item
    if last is None:
        raise RuntimeError("TTS 没有返回音频")
    sr, audio = last
    if audio is None or len(audio) == 0:
        raise RuntimeError("TTS 返回了空音频")
    return int(sr), audio


def main():
    parser = argparse.ArgumentParser(description="GPT-SoVITS CPU 适配脚本")
    parser.add_argument("--model", required=True, help="模型快照目录（含 gsv-v4-pretrained/ 等）")
    parser.add_argument("--out", required=True, help="输出 wav 路径")
    parser.add_argument("--text", required=True, help="要念的内容")
    parser.add_argument("--ref", required=True, help="参考音 wav（3~10 秒）")
    parser.add_argument("--ref-text", default="", help="参考音里说的那句话")
    parser.add_argument("--lang", default="Chinese", help="语言，目前只支持中文")
    parser.add_argument("--instruct", nargs="?", const="", default="", help="（该引擎不支持，忽略）")
    parser.add_argument("--voice", nargs="?", const="", default="", help="（该引擎不支持，忽略）")
    parser.add_argument("--speed", nargs="?", const=1.0, type=float, default=1.0, help="语速倍率，默认 1.0")
    parser.add_argument("--version", default="auto",
                        choices=["auto", "v4", "v2ProPlus", "v2", "v1"],
                        help="模型版本，默认按模型目录自动选（优先 v4）")
    args = parser.parse_args()

    # 插件用 Node 的 utf8 解码子进程输出
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    text = (args.text or "").strip()
    ref = (args.ref or "").strip()
    ref_text = (args.ref_text or "").strip()
    if text == "":
        err("--text 不能为空")
        return 2
    if ref == "":
        err("--ref 不能为空（GPT-SoVITS 需要参考音）")
        return 2
    if not os.path.exists(ref):
        err("参考音不存在：%s" % ref)
        return 2
    if ref_text == "":
        err("--ref-text 不能为空（GPT-SoVITS 需要参考音台词）")
        return 2
    if not os.path.isdir(args.model):
        err("模型目录不存在：%s" % args.model)
        return 2
    text_lang = normalize_lang(args.lang)
    speed = float(args.speed) if args.speed else 1.0
    if speed <= 0 or speed > 3:
        speed = 1.0
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    if args.instruct:
        log("[voice] 注意：GPT-SoVITS 不支持 --instruct，已忽略")
    if args.voice:
        log("[voice] 注意：GPT-SoVITS 音色只由参考音决定，已忽略 --voice")

    t_start = time.time()
    log("[voice] loading GPT-SoVITS from %s", args.model)
    # 只读本机：禁用所有 HF/Transformers 联网行为
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    try:
        os.makedirs(RUN_ROOT, exist_ok=True)
        os.chdir(RUN_ROOT)

        sys.path.insert(0, REPO)
        sys.path.insert(0, os.path.join(REPO, "GPT_SoVITS"))
        sys.path.append(os.path.join(REPO, "GPT_SoVITS", "eres2net"))

        from tools.portable_runtime import activate as activate_portable_runtime
        activate_portable_runtime(change_cwd=False)
        os.environ.setdefault("G2PW", "0")

        install_fake_lang_modules()
        ensure_jieba_fast()
        install_text_patches()

        versions = pick_versions(args.model, args.version)
        log("[voice] 候选版本：%s", ", ".join(versions))

        import soundfile as sf
        import numpy as np  # noqa: F401
        from TTS_infer_pack.TTS import TTS, TTS_Config

        patch_lang_segmenter()

        last_err = None
        for version in versions:
            log("[voice] 尝试 GPT-SoVITS %s ...", version)
            make_junctions(args.model, version)
            t_load = time.time()
            tts = None
            try:
                tts = TTS(TTS_Config(tts_config_dict(args.model, version)))
                log("[voice] loaded in %.1fs", time.time() - t_load)
                t_gen = time.time()
                sr, audio = synth_once(tts, text, text_lang, ref, ref_text, speed)
                sf.write(args.out, audio, sr, subtype="PCM_16")
                duration = len(audio) / float(sr)
                size_mb = os.path.getsize(args.out) / 1024.0 / 1024.0
                log("[voice] generated in %.1fs -> %s", time.time() - t_gen, args.out)
                log("[voice] 版本=%s, 采样率=%d, 时长=%.2fs, 大小=%.2fMB, 总耗时=%.1fs",
                    version, sr, duration, size_mb, time.time() - t_start)
                text_chars = len("".join(ch for ch in text if not ch.isspace()))
                if duration < 0.09 * max(text_chars, 1):
                    log("[voice] 警告：输出只有 %.2fs（文本 %d 字），明显偏短；"
                        "通常是 --ref-text 与参考音里实际说的话不一致导致模型提前停止，请核对参考音台词。",
                        duration, text_chars)
                return 0
            except (ImportError, ModuleNotFoundError) as e:
                last_err = e
                err("缺少 Python 依赖：%s" % e)
                break
            except BaseException as e:  # noqa: BLE001 - 载入/推理失败时尝试下一个版本
                last_err = e
                log("[voice] %s 版本失败：%s: %s", version, type(e).__name__, e)
                traceback.print_exc()
                tts = None
                gc.collect()
                continue
            finally:
                tts = None
                gc.collect()
        if last_err is not None:
            err("所有可用版本都失败了：%s: %s" % (type(last_err).__name__, last_err))
            return 3
        err("没有可用的 GPT-SoVITS 版本")
        return 3
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001
        traceback.print_exc()
        err("%s: %s" % (type(e).__name__, e))
        return 3


if __name__ == "__main__":
    sys.exit(main())
