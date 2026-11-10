# backend/scripts/build_eval_set_v3.7.0.py
"""用桌面素材图重建评测集（v3.7.0）—— 自包含、七分类、含字面子集。

为什么重建
----------
v3.5.0 评测集锚定在 ``backend/uploads/*.jpg`` + ``backend/lost_found.db``，两者都被
``.gitignore`` 排除（``uploads/`` 与 ``lost_found.db``）→ **新克隆上 6 个图片引用全缺失，
评测集无法运行**（见 ``eval/README.md`` §1.1）。且它只有 6 件真实物品、4 个类别，
``包袋箱包 / 服装配饰 / 其他`` 三个类别**没有任何正样本**。

v3.7.0 的做法：把素材图**复制进 ``eval/images/``**（该目录不被忽略），评测集与数据库、
运行环境彻底解耦；同时把类别扩到 7 个、物品扩到 70 件。

五类配对（同一批查询复用，方法与 v3.5.0 §8「复用正样本查询换 target」一致）
--------------------------------------------------------------------------
============  ====  ==========================================================
前缀           标签  含义
============  ====  ==========================================================
``P``          1    改写查询 → 目标图（**查询不得含 title 原词**，§3 硬约束）
``L``          1    字面查询（查询 == title）→ 目标图；``literal_query=true``
``NX``         0    跨类别负样本：A 的查询 → 别的类别的 B
``NH``         0    同类硬负样本：A 的查询 → 同类别相邻的 B（两副耳机盒这种）
``NI``         0    图片查询负样本：A 的图 → 别的类别的 B
============  ====  ==========================================================

为什么要 ``L`` 这一类
--------------------
v3.5.0 用「查询不得含 title 原词」保证评测的是**语义泛化**，代价是把生产里最常见的
「用户只打两三个字」整类排除掉了。``L`` 子集正是补这个盲区：它单独统计，
**不与 P 混报 Recall@1**（字面命中必然 Top-1，混进去会虚高）。

用法（backend 目录下）::

    venv\\Scripts\\python.exe scripts\\build_eval_set_v3.7.0.py --check   # 只校验
    venv\\Scripts\\python.exe scripts\\build_eval_set_v3.7.0.py           # 复制图片 + 写出 JSON
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = r"C:\Users\33834\Desktop\校园失物招领-素材图"
IMG_ROOT = "eval/images"          # 相对 backend/，**不被 .gitignore 排除**
OUT_PATH = os.path.join(BACKEND_DIR, "eval", "eval_set_v3.7.0.json")
TEXT_WINDOW = 50                  # Chinese-CLIP 文本塔可用汉字数

#: 目录 slug → 素材目录的中文名（源目录用中文分类，目标目录用 ASCII 以避免编码差异）
SRC_CAT = {
    "books": "书籍文具", "misc": "其他", "bags": "包袋箱包", "apparel": "服装配饰",
    "electronics": "电子产品", "cards": "证件卡片", "keys": "钥匙门禁",
}

# (目录 slug, 业务分类, 素材文件名, 标题, 描述, [改写查询...])
ITEMS: List[Tuple[str, str, str, str, str, List[str]]] = [
    # ---------------- 书籍文具 ----------------
    ("books", "书籍文具", "4603ab65bf8c1432cba97553cad087dc.jpg", "办公软件教材",
     "绿色封面，书角有折痕，扉页写了姓名", ["讲文档表格和幻灯片制作的那本上机课用书"]),
    ("books", "书籍文具", "53b8ce844d2bbfe67fb28fada5046b6e.jpg", "体育管理教材",
     "白色封面，印着红色运动人物", ["白皮那本讲俱乐部怎么运营的专业读物"]),
    ("books", "书籍文具", "7fb1bcfdb9be86c522f2d51181963b98.jpg", "黑色笔记本",
     "硬壳封面印着白色圆形图案和英文", ["硬皮的黑本子，封面上有一圈圈白色小图案"]),
    ("books", "书籍文具", "9915d5b8d61bc6da96081eb2c63c0ca1.jpg", "建设工程审计教材",
     "浅青色封面，右下角有建筑剪影", ["浅绿色封面的工程类专业课用书"]),
    ("books", "书籍文具", "Image_1792124867669_669.jpg", "白色文件夹",
     "带按扣的白色资料册，内页透明", ["装复印资料用的白色塑料夹，有个圆扣"]),
    ("books", "书籍文具", "Image_1792124877065_457.jpg", "深蓝色笔记本",
     "封面印着校徽和烫金字", ["深蓝色硬面本子，上面有学校标志"]),
    ("books", "书籍文具", "Image_1792125189503_434.jpg", "方格活页本",
     "活页装订，方格纸，写了半本笔记", ["记了半本公式，纸是小方格的"]),
    # 注：素材里另有一张「武昌工学院学生请假条」（Image_1792125196759_817.jpg，
    # 含姓名与辅导员签名）——**刻意不收**：本评测集会随仓库公开分发，不做个人信息入库。
    ("books", "书籍文具", "eec0ecc22a052b1e3a4452c03aafdfff.jpg", "高等数学教材",
     "白色封面印着蓝色几何图形，上册", ["白封面上有蓝色几何图案的数学课本"]),

    # ---------------- 其他 ----------------
    ("misc", "其他", "166ef9af541838eb6a2bc085560a28eb.jpg", "蓝色雨伞",
     "深蓝色折叠伞，收着放在地上", ["一把深蓝色的折叠伞，收好放地上"]),
    ("misc", "其他", "6664c0ab257bd236459323ddf5c5ef95.jpg", "格纹雨伞",
     "灰蓝色格纹伞面，带弯钩手柄", ["伞面是灰蓝格子的，手柄是弯的"]),
    ("misc", "其他", "82a410e2e7617468a385362a03054229.jpg", "粉色保温杯",
     "粉色杯身，落在教室桌洞里", ["粉色的喝水杯子，忘在桌肚里了"]),
    ("misc", "其他", "Image_1792124845498_948.jpg", "摄影冲印袋",
     "白色塑料袋，印着华林摄影字样", ["洗照片给的那种白色塑料袋"]),
    ("misc", "其他", "Image_1792124934140_467.jpg", "格子布袋",
     "黑白小格图案，可折叠", ["黑白小格子的布袋，能折起来那种"]),
    ("misc", "其他", "Image_1792125225041_650.jpg", "黑色伞套",
     "黑色长条布套，带挂绳", ["装伞用的黑色长布袋"]),
    ("misc", "其他", "e15beec23342e140a402d67b7d709f15.jpg", "条纹雨伞",
     "蓝棕相间宽条纹伞面", ["蓝和棕色宽条纹的伞，撑开放在地上"]),
    ("misc", "其他", "fd98d7e58bf9c8e62cc46b49457724ab.jpg", "黑色折叠伞",
     "纯黑色伞面，收拢放在课桌上", ["全黑的一把伞，收好了放桌上"]),

    # ---------------- 包袋箱包 ----------------
    ("bags", "包袋箱包", "7923744e1a9e5a01ebb891dbe416e4a2.jpg", "波点帆布袋",
     "白底黑色小波点，两条帆布提手", ["白底黑点的布袋子，有两条提手"]),

    # ---------------- 服装配饰 ----------------
    ("apparel", "服装配饰", "00934ccf65e1279ea48448224735a085.jpg", "毛绒玩偶挂件",
     "白色小玩偶，戴红色帽子", ["一个白色的毛绒小挂饰，戴着红帽子"]),
    ("apparel", "服装配饰", "388c62b7c1b96e779283cd688fc47e61.jpg", "串珠手链",
     "粉色珠串，坠着白色小玩偶", ["粉色珠子的手串，下面挂个小玩偶"]),
    ("apparel", "服装配饰", "4cb9469b1a26d70c0b6e913249062661.jpg", "白色发夹",
     "一排白色塑料抓夹", ["一排白色的塑料小夹子"]),
    ("apparel", "服装配饰", "5a237c1b1a1ec679e7752036eb695ad4.jpg", "粉色小熊",
     "粉色毛绒小熊，挂着蓝色胸牌", ["粉色的毛绒小熊玩偶，身上挂个蓝牌子"]),
    ("apparel", "服装配饰", "74402d090dce03e69cf29de711cf9067.jpg", "串珠手串",
     "深绿色圆珠，十几颗", ["深绿色珠子的手串，拿在手里"]),
    ("apparel", "服装配饰", "87c6c4a8ca940e071ac7739d862e6c27.jpg", "像素布贴",
     "像素风小人图案，蓝色帽子", ["卡通像素图案的小贴片，戴蓝帽子"]),
    ("apparel", "服装配饰", "Image_1792124937832_132.png", "条纹长袖",
     "黑白细条纹，V领，挂着衣架", ["黑白细条纹的长袖上衣，V字领"]),
    ("apparel", "服装配饰", "Image_1792124970013_67.jpg", "黄色拖鞋",
     "一只黄色拖鞋，落在椅子下", ["一只黄色的拖鞋，掉在椅子底下了"]),
    ("apparel", "服装配饰", "Image_1792124996092_547.jpg", "黑色外套",
     "黑色连帽外套，袖口有白色标志", ["黑色的连帽外套，扔在桌上"]),
    ("apparel", "服装配饰", "Image_1792125165915_579.jpg", "像素钥匙扣",
     "蓝色像素风小人，带钥匙圈", ["蓝颜色的像素小人钥匙挂件"]),
    ("apparel", "服装配饰", "Image_1792125220867_829.jpg", "刺绣贴片",
     "粉紫色像素图案，长条形", ["粉紫色像素风的长条贴布"]),
    ("apparel", "服装配饰", "b011818fccc83ae3d1f634e002f12858.jpg", "黄色挂件",
     "黄色像素风公仔，落在地上", ["地上一个黄颜色的小挂件"]),
    ("apparel", "服装配饰", "c3e7df181b9bc319b4aaaccc47430907.jpg", "橙色毛绒挂件",
     "橙色小狐狸毛绒，系格子领巾", ["橙色的毛绒小狐狸挂饰"]),

    # ---------------- 电子产品（同类相邻排列，便于取「硬负样本」） ----------------
    ("electronics", "电子产品", "03c5592df9f461723b0c2cb2763cbeb3.jpg", "蓝牙耳机",
     "白色充电盒，盖子打开露出一对耳机", ["白色的无线小耳机，盒子是开着的"]),
    ("electronics", "电子产品", "05281bd9d8382ea275bd977651067167.jpg", "耳机充电盒",
     "白色椭圆盒子，旁边有张红色卡片", ["白颜色的椭圆小盒，旁边压着张红卡"]),
    ("electronics", "电子产品", "1190ea943803889a10d512ca26f76d1b.jpg", "圆柱耳机盒",
     "蓝绿色圆柱形盒子，盖子半开", ["蓝绿色的圆筒形小盒，盖子是掀开的"]),
    ("electronics", "电子产品", "1ae07a4c50bf30506c6bd6c847d776e0.jpg", "白色耳机盒",
     "白色磨砂盒子，捏在手里", ["磨砂白的小方盒，拿在手上"]),
    ("electronics", "电子产品", "1fe4fc8ca72490fc0d379c8aaf267a53.jpg", "机械键盘",
     "黑色带背光键帽，旁边有鼠标", ["黑色会发光的键盘，边上放个鼠标"]),
    ("electronics", "电子产品", "3c413744599d6c8920cce56e94b192d6.jpg", "无线充电器",
     "白色圆形底座，中间一圈凸起", ["白颜色的圆盘状充电底座"]),
    ("electronics", "电子产品", "59389548edd73c2641623d724adf3dad.jpg", "猫耳耳机盒",
     "灰色盒子带两只猫耳，系粉色挂绳", ["灰颜色的盒子上面有两只猫耳朵"]),
    ("electronics", "电子产品", "63c12a647aa842932e09fc3bc6118fcf.jpg", "充电宝",
     "白色长方形移动电源，容量标注很大", ["白色的长方形移动电源"]),
    ("electronics", "电子产品", "6a153b7da449da8be50df50fe7f9e592.jpg", "移动电源",
     "白色扁平方形，放在课桌上", ["扁扁的白方块电池，放在桌上"]),
    ("electronics", "电子产品", "7185e5d5035a785bcfbd92d0b7b45948.jpg", "耳机收纳盒",
     "银灰色方形铁盒，印着品牌英文", ["银灰色的方铁盒，盒面有英文字母"]),
    ("electronics", "电子产品", "84f3cc4c977a21410104725be15bc0c8.jpg", "键盘鼠标",
     "黑色键盘和鼠标，中间放着一部手机", ["黑键盘黑鼠标，中间夹个手机"]),
    ("electronics", "电子产品", "9f9ef59b4488ac3535ee7e8ff59993c8.jpg", "透明收纳盒",
     "透明塑料盒，盖子印着两只小熊", ["透明的小塑料盒，盖上有两只小熊图案"]),
    ("electronics", "电子产品", "Image_1792124838625_222.jpg", "粉色耳机盒",
     "半透明粉色圆盒，里面装着耳机", ["半透明的粉色小圆盒，里面塞着耳机"]),
    ("electronics", "电子产品", "Image_1792124906104_154.jpg", "数据线",
     "粉色编织线，缠着卡通挂件", ["粉色的充电绳，上面挂个卡通小件"]),
    ("electronics", "电子产品", "Image_1792124913165_162.jpg", "无线耳机",
     "白色充电盒掉在地上，旁边一只耳机", ["白盒子掉地上了，边上还有只耳机"]),
    ("electronics", "电子产品", "Image_1792124930332_999.jpg", "充电线",
     "白色编织线，盘成一圈拿在手里", ["白的编织绳状线，绕成一圈"]),
    ("electronics", "电子产品", "Image_1792124962941_424.jpg", "白色耳机",
     "地上一只白色无线耳机", ["地上掉了一只白色的无线小耳机"]),
    ("electronics", "电子产品", "Image_1792124973584_243.jpg", "耳机盒",
     "白盒子放在桌肚里，旁边一串钥匙", ["桌肚里的白盒子，挨着一串钥匙"]),
    ("electronics", "电子产品", "Image_1792125092121_935.jpg", "椭圆耳机盒",
     "地上一只白色椭圆盒子", ["地上有个白色的椭圆小盒"]),
    ("electronics", "电子产品", "Image_1792125172752_764.jpg", "手机",
     "黑色直板机，屏幕亮着放在桌边", ["黑颜色的那台，屏还亮着"]),
    ("electronics", "电子产品", "Image_1792125203308_658.jpg", "绿盒耳机",
     "绿色盒子装着一只白色耳机", ["绿颜色的盒子，里头一只白耳机"]),
    ("electronics", "电子产品", "ab6ca039c7e08e4e505d7ad26d176776.jpg", "鹅卵石耳机盒",
     "白色鹅卵石造型，放在浅色桌面", ["白白的像鹅卵石一样的盒子"]),
    ("electronics", "电子产品", "b2ec385215e61467b4e5938769f28a6d.jpg", "卡通耳机盒",
     "盒面印着戴黑帽的卡通女孩，带珠链", ["盒子上印着戴帽子的小女孩，还挂串珠子"]),
    ("electronics", "电子产品", "c9574c43bbdd5afca7889340e5a9c88e.jpg", "白色圆盒",
     "白色圆形小盒，握在手心", ["白颜色的圆型小盒子，捏在手心"]),
    ("electronics", "电子产品", "cdba11985cfdbf07ac5fd27726fb15af.jpg", "米色耳机盒",
     "米白色盒子，放在木纹桌面", ["米白色的盒子，放在木桌上"]),
    ("electronics", "电子产品", "ed451513ceca8b516d9623e3e71bd94b.jpg", "键盘套装",
     "黑色键盘鼠标，和一部手机摆在一起", ["一整套黑色的键鼠，旁边放手机"]),

    # ---------------- 证件卡片 ----------------
    ("cards", "证件卡片", "5ae340ed6d1d0d8ef38ce283ecc4dcc1.jpg", "学生证",
     "深红色小本，印着武昌工学院", ["深红色的小本子，上面有学校名字"]),
    ("cards", "证件卡片", "6da3ef3195007ae124fd4bebd38834f3.jpg", "身份证",
     "二代证件，正面信息清晰", ["一张二代证件，正反面信息清楚"]),

    # ---------------- 钥匙门禁 ----------------
    ("keys", "钥匙门禁", "12e478f272ab79e4869c10e4889f0182.jpg", "门禁卡",
     "粉色卡套，挂着卡通挂件", ["粉色的门卡套，上面挂个小玩偶"]),
    ("keys", "钥匙门禁", "1e5bcb84be464f4b7c02fb500be2fb8c.jpg", "校园卡",
     "蓝色卡片配蓝色圆环挂绳", ["蓝颜色的卡片，连着个蓝色圆环"]),
    ("keys", "钥匙门禁", "484e336b57f3b18cb52fa9c0b694d123.jpg", "蓝色门禁卡",
     "深蓝色长方形卡，平放在桌上", ["深蓝色的长方形卡，摊在桌面"]),
    ("keys", "钥匙门禁", "Image_1792124871881_324.jpg", "卡套",
     "白色卡套印红色卡通图案，配银圈", ["白底印红图案的塑料套，连着个银色圆环"]),
    ("keys", "钥匙门禁", "Image_1792124953927_855.jpg", "毛绒猫挂件",
     "白色毛绒小猫，连着蓝色卡片", ["白色毛绒小猫，下面拴着张蓝卡"]),
    ("keys", "钥匙门禁", "Image_1792125084224_126.jpg", "红色卡套",
     "黑色卡套印红色图案，捏在手里", ["黑底上印红图案的，捏在手上"]),
    ("keys", "钥匙门禁", "Image_1792125237351_520.jpg", "蓝色卡片",
     "手里捏着蓝色卡片和一只白色耳机", ["手上捏着蓝卡和一只白耳机"]),
    ("keys", "钥匙门禁", "cd9d8e9d4d51bb23e8a90a517e30df01.jpg", "粉色卡套",
     "粉色卡套带挂绳，放在桌边", ["粉色的塑料套，带一根挂绳"]),
    ("keys", "钥匙门禁", "e089a23f3beaa10a7e423ea6855675fb.jpg", "校卡",
     "蓝色校园卡，印着武昌工学院", ["蓝底校牌，上面有学校名字"]),
    ("keys", "钥匙门禁", "ff4ebe6c701ed6b6898b68ae0ebaa683.jpg", "银色钥匙",
     "一把银色金属钥匙，躺在手心", ["手心里一把银色的金属小件，带齿的那种"]),
    ("keys", "钥匙门禁", "Image_1792124957946_843.jpg", "钥匙串",
     "一串钥匙挂在木桌上，带蓝色小牌", ["一串挂蓝牌子的金属件，摊在桌上"]),
]

LABEL_RULE = "人工判定：查询与目标是否指向同一件实物。相关=1 / 不相关=0。"
IMG_REL_TMPL = "{root}/{slug}/{file}"


#: 个别图片的**业务分类**与素材目录不一致时，按文件名指定源目录。
#: 例：钥匙串（Image_..._843.jpg）原本被归进「电子产品」目录，业务上属"钥匙门禁"。
SRC_DIR_OVERRIDE: Dict[str, str] = {
    "Image_1792124957946_843.jpg": "电子产品",
}


def _src_path(it: Dict[str, Any]) -> str:
    folder = SRC_DIR_OVERRIDE.get(it["file"], SRC_CAT[it["category_dir"]])
    return os.path.join(SRC_DIR, folder, it["file"])


#: 入库前需**打码**的图片：文件名 → [(x0, y0, x1, y1)]（归一化坐标 0~1）。
#: WHY：素材里的身份证「姓名」一行仍清晰可见，而本目录会随公开仓库分发。
#: 原有打码已覆盖照片、住址与身份证号，这里补上姓名行；**只改 eval/images/ 的副本**，
#: 桌面原图不动（每次重建都从原图重新复制再打码，避免二次编码累积失真）。
REDACT: Dict[str, List[Tuple[float, float, float, float]]] = {
    "6da3ef3195007ae124fd4bebd38834f3.jpg": [(0.165, 0.302, 0.455, 0.388)],   # 姓名行
}


def _apply_redaction(path: str, boxes: List[Tuple[float, float, float, float]]) -> None:
    from PIL import Image, ImageDraw

    with Image.open(path) as im:
        canvas = im.convert("RGB")
        draw = ImageDraw.Draw(canvas)
        w, h = canvas.size
        for x0, y0, x1, y1 in boxes:
            draw.rectangle([int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)],
                           fill=(0, 0, 0))
        canvas.save(path, quality=95)


def _item_id(i: int) -> str:
    return f"M{i + 1:02d}"


def _validate(items: List[Dict[str, Any]]) -> List[str]:
    """返回问题列表（空表示通过）。"""
    errs: List[str] = []
    titles = [it["title"] for it in items]
    dup = {t for t in titles if titles.count(t) > 1}
    if dup:
        errs.append(f"标题重复: {sorted(dup)}")

    for it in items:
        text = f"{it['title']} {it['desc']}"
        if len(text) > TEXT_WINDOW:
            errs.append(f"{it['id']} target.text 超 {TEXT_WINDOW} 字（{len(text)}）")
        for q in it["queries"]:
            if it["title"] in q:
                errs.append(f"{it['id']} 查询含标题原词「{it['title']}」: {q}")
            if len(q) < 8:
                errs.append(f"{it['id']} 查询过短（{len(q)} 字）: {q}")
            if len(q) > TEXT_WINDOW:
                errs.append(f"{it['id']} 查询超 {TEXT_WINDOW} 字（{len(q)}）: {q}")
        if not os.path.isfile(_src_path(it)):
            errs.append(f"{it['id']} 素材缺失: {_src_path(it)}")
    return errs


def _build(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    pairs: List[Dict[str, Any]] = []
    by_id = {it["id"]: it for it in items}
    cats: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        cats.setdefault(it["cat"], []).append(it)

    def tgt(it: Dict[str, Any], with_text: bool = True) -> Dict[str, Any]:
        return {
            "item_id": it["id"],
            "item_ref": it["item_ref"],
            "text": f"{it['title']} {it['desc']}" if with_text else None,
        }

    seq = 0

    # P：改写查询正样本
    for it in items:
        for q in it["queries"]:
            seq += 1
            pairs.append({
                "id": f"P{seq:02d}", "label": 1, "category": it["cat"], "subtype": "rewrite",
                "query": {"text": q, "image": None}, "target": tgt(it),
            })

    # L：字面查询正样本
    for n, it in enumerate(items, 1):
        pairs.append({
            "id": f"L{n:02d}", "label": 1, "category": it["cat"], "subtype": "literal",
            "literal_query": True,
            "query": {"text": it["title"], "image": None}, "target": tgt(it),
        })

    # NX：跨类别负样本（A 的查询 → 别的类别的 B；按固定偏移取，保证确定性）
    for n, it in enumerate(items):
        cat_seq = cats[it["cat"]]
        pos = cat_seq.index(it)
        # 同类里取下一个；再跳到另一个类别，避免「同类但不相邻」也算跨类
        other_cat = [c for c in cats if c != it["cat"]][n % len([c for c in cats if c != it["cat"]])]
        other = cats[other_cat][pos % len(cats[other_cat])]
        pairs.append({
            "id": f"NX{n + 1:02d}", "label": 0, "category": it["cat"], "subtype": "cross_category",
            "query": {"text": it["queries"][0], "image": None}, "target": tgt(other),
        })

    # NH：同类硬负样本（相邻物品，视觉相近）
    for n, it in enumerate(items):
        cat_seq = cats[it["cat"]]
        if len(cat_seq) < 2:
            continue
        pos = cat_seq.index(it)
        other = cat_seq[(pos + 1) % len(cat_seq)]
        pairs.append({
            "id": f"NH{n + 1:02d}", "label": 0, "category": it["cat"], "subtype": "same_category",
            "query": {"text": it["queries"][0], "image": None}, "target": tgt(other),
        })

    # NI：图片查询负样本（A 的图 → 别的类别的 B），每 4 件取一件
    ni = 0
    for n, it in enumerate(items):
        if n % 4:
            continue
        other_cat = [c for c in cats if c != it["cat"]][n % len([c for c in cats if c != it["cat"]])]
        other = cats[other_cat][(n // 4) % len(cats[other_cat])]
        ni += 1
        pairs.append({
            "id": f"NI{ni:02d}", "label": 0, "category": it["cat"], "subtype": "image_query",
            "query": {"text": None, "image": it["item_ref"]}, "target": tgt(other),
        })

    return {
        "version": "v3.7.0",
        "model_backend": "cn_clip",
        "model_name": "ViT-H-14",
        "source": ("桌面素材图（校园失物招领-素材图）经人工认物后复制到 eval/images/；"
                   "本评测集不依赖 backend/uploads 与 lost_found.db，可在任意克隆上运行"),
        "label_rule": LABEL_RULE,
        "pair_types": {
            "rewrite": "改写查询 → 目标图（查询不含 title 原词）",
            "literal": "字面查询（查询 == title）→ 目标图，literal_query=true，单独统计",
            "cross_category": "跨类别负样本",
            "same_category": "同类硬负样本（视觉相近的不同实物）",
            "image_query": "图片查询负样本",
        },
        "items": [
            {"item_id": it["id"], "category": it["cat"], "title": it["title"],
             "desc": it["desc"], "image": it["item_ref"], "source_file": it["file"]}
            for it in items
        ],
        "pairs": pairs,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="生成评测集 v3.7.0（自包含素材图）")
    p.add_argument("--check", action="store_true", help="只校验，不复制、不写文件")
    p.add_argument("--out", default=OUT_PATH)
    args = p.parse_args(argv)

    items: List[Dict[str, Any]] = []
    for i, (slug, cat, file, title, desc, queries) in enumerate(ITEMS):
        items.append({
            "id": _item_id(i), "category_dir": slug, "cat": cat, "file": file,
            "title": title, "desc": desc, "queries": queries,
            "item_ref": IMG_REL_TMPL.format(root=IMG_ROOT, slug=slug, file=file),
        })

    errs = _validate(items)
    if errs:
        print("校验失败：")
        for e in errs:
            print("  -", e)
        return 1
    print(f"清单校验通过：{len(items)} 件物品 / "
          f"{sum(len(it['queries']) for it in items)} 条改写查询")

    if args.check:
        data = _build(items)
        print(f"预计配对：{len(data['pairs'])}（未写盘）")
        return 0

    # 复制图片（保留原文件名，便于溯源）
    copied = 0
    redacted = 0
    for it in items:
        dst_dir = os.path.join(BACKEND_DIR, IMG_ROOT, it["category_dir"])
        os.makedirs(dst_dir, exist_ok=True)
        src = _src_path(it)
        dst = os.path.join(dst_dir, it["file"])
        need = (it["file"] in REDACT or not os.path.exists(dst)
                or os.path.getsize(dst) != os.path.getsize(src))
        if need:
            shutil.copy2(src, dst)
            copied += 1
        if it["file"] in REDACT:
            _apply_redaction(dst, REDACT[it["file"]])
            redacted += 1
    print(f"图片就绪：{len(items)} 张（本次复制 {copied} 张，打码 {redacted} 张）→ {IMG_ROOT}/")

    data = _build(items)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    pos = sum(1 for x in data["pairs"] if x["label"] == 1)
    kinds: Dict[str, int] = {}
    for x in data["pairs"]:
        kinds[x["subtype"]] = kinds.get(x["subtype"], 0) + 1
    print(f"写出：{os.path.abspath(args.out)}")
    print(f"  配对 {len(data['pairs'])}（正 {pos} / 负 {len(data['pairs']) - pos}）")
    print("  分布：" + "  ".join(f"{k}={v}" for k, v in kinds.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
