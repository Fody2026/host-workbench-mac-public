# -*- coding: utf-8 -*-
"""内置可商用字体的加载"""
import os
import logging

logger = logging.getLogger(__name__)

BUILTIN_FONTS = []          # 已注册的字体家族名
BUILTIN_FILES = {}          # 家族名 -> 文件


def font_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")


def load_builtin_fonts():
    """把 assets/fonts 下的字体注册进 Qt（需在 QApplication 之后调用）"""
    from PySide6.QtGui import QFontDatabase
    global BUILTIN_FONTS, BUILTIN_FILES
    BUILTIN_FONTS = []
    BUILTIN_FILES = {}
    d = font_dir()
    if not os.path.isdir(d):
        logger.warning("字体目录不存在: %s", d)
        return []
    for fn in sorted(os.listdir(d)):
        if not fn.lower().endswith((".ttf", ".otf", ".ttc")):
            continue
        path = os.path.join(d, fn)
        try:
            fid = QFontDatabase.addApplicationFont(path)
            if fid < 0:
                logger.warning("字体注册失败: %s", fn)
                continue
            for fam in QFontDatabase.applicationFontFamilies(fid):
                if fam not in BUILTIN_FONTS:
                    BUILTIN_FONTS.append(fam)
                    BUILTIN_FILES[fam] = path
        except Exception:
            logger.exception("字体注册异常: %s", fn)
    logger.info("已加载内置字体: %s", BUILTIN_FONTS)
    return BUILTIN_FONTS


def available_fonts():
    """内置字体 + 系统中文字体，供下拉选择（须在 QApplication 之后调用）"""
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    names = list(BUILTIN_FONTS)
    if QApplication.instance() is None:
        return names or ["Microsoft YaHei UI"]
    sys_names = QFontDatabase.families()
    prefer = ["Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "苹方", "PingFang SC",
              "SimHei", "黑体", "SimSun", "宋体", "KaiTi", "楷体", "FangSong", "仿宋",
              "LiSu", "隶书", "YouYuan", "幼圆", "STXingkai", "华文行楷", "STLiti",
              "华文隶书", "STCaizi", "华文彩云",
              # 更多可商用 / 系统常见中文字体
              "DengXian", "等线", "NSimSun", "新宋体", "STZhongsong", "华文中宋",
              "STHupo", "华文琥珀", "STXinwei", "华文新魏", "FZShuTi", "方正舒体",
              "FZYaoti", "方正姚体", "Source Han Sans SC", "思源黑体",
              "Source Han Serif SC", "思源宋体", "LXGW WenKai", "霞鹜文楷",
              "Smiley Sans", "得意黑", "ZCOOL QingKe HuangYou", "站酷庆科黄油体",
              "ZCOOL XiaoWei", "站酷文艺体", "Alibaba PuHuiTi", "阿里妈妈普惠体",
              "HarmonyOS Sans SC", "鸿蒙黑体", "MiSans", "小米兰亭 Pro"]
    for p in prefer:
        if p in sys_names and p not in names:
            names.append(p)
    return names
