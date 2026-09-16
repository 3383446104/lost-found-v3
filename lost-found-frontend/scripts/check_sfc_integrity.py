# -*- coding: utf-8 -*-
"""前端 SFC 完整性静态检查：抓「构建能过、浏览器运行时才炸」的导入缺陷。

用法：python scripts/check_sfc_integrity.py   （退出码 0=通过 / 1=有问题）

检查三类问题（历史事故：MatchView 缺 computed 导入 → /match 整页空白；
ItemDetailView 缺 Checked 图标导入 → 图标静默不渲染）：
1) <script setup> 中使用的 Vue API（computed/watch/ref/...）是否从 'vue' 导入；
2) 模板中的 PascalCase 组件/图标是否已导入（El* 前缀视为 Element Plus 全局注册）；
3) 模板中调用的函数是否在 script 中定义。

为什么构建发现不了：未定义的运行时引用在 ESM 下是合法的全局读取，
rolldown/vite build 不做静态报错，只有浏览器执行到那一行才抛错。
"""
import os, re, sys, json

# 基于脚本位置推导 src 目录（可移植，不依赖绝对路径）
FE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
VUE_APIS = ["computed", "watch", "watchEffect", "ref", "reactive", "toRef", "toRefs",
            "onMounted", "onUnmounted", "onBeforeMount", "onBeforeUnmount", "nextTick",
            "provide", "inject", "defineProps", "defineEmits", "defineExpose", "useTemplateRef"]
# 全局注册的组件前缀（Element Plus 组件、路由占位等）
GLOBAL_PREFIXES = ("el-", "El", "router-view", "router-link", "transition", "keep-alive",
                   "teleport", "suspense", "component", "template", "slot", "svg", "img")

issues = []
for root, _, files in os.walk(FE):
    for fn in files:
        if not fn.endswith(".vue"):
            continue
        p = os.path.join(root, fn)
        txt = open(p, encoding="utf-8", errors="ignore").read()
        tpl = txt.split("<template>", 1)[-1].split("</template>", 1)[0] if "<template>" in txt else ""
        script = txt.split("<script", 1)[-1].split("</script>", 1)[0] if "<script" in txt else ""

        # --- 1) vue API 导入 ---
        m = re.search(r"""import\s*\{([^}]+)\}\s*from\s*['"]vue['"]""", script)
        imported = [x.strip().split(" as ")[0].strip() for x in m.group(1).split(",")] if m else []
        for api in VUE_APIS:
            # 排除 defineProps 等在 <script setup> 中无需导入的编译宏
            if api.startswith("define"):
                continue
            if re.search(r"(?<![\w.])" + api + r"\s*\(", script) and api not in imported:
                issues.append((fn, "vue-api-missing", api))

        # --- 2) 模板 PascalCase 组件 ---
        used_tags = set(re.findall(r"<([A-Z][A-Za-z0-9]*)\b", tpl))
        # script 中 import 的标识符
        imported_ids = set()
        for im in re.finditer(r"""import\s*\{([^}]+)\}\s*from\s*['"][^'"]+['"]""", script):
            for x in im.group(1).split(","):
                imported_ids.add(x.strip().split(" as ")[-1].strip())
        for im in re.finditer(r"""import\s+([A-Za-z_$][\w$]*)\s+from""", script):
            imported_ids.add(im.group(1))
        # 全局注册（main.js 里注册的 Element Plus 组件：El* 前缀 / el- 短横线不算 PascalCase 命中）
        for tag in sorted(used_tags):
            if tag.startswith("El") or tag in imported_ids:
                continue
            if any(tag.lower().startswith(gp.rstrip("-").lower()) for gp in GLOBAL_PREFIXES):
                continue
            issues.append((fn, "component-not-imported", tag))

        # --- 3) 模板调用的函数是否在 script 定义 ---
        calls = set(re.findall(r"""[^\w.'"]([a-z_$][\w$]*)\s*\(""", tpl))
        tpl_builtins = {"if", "for", "in", "of", "true", "false", "null", "undefined", "typeof", "new"}
        for c in sorted(calls - tpl_builtins):
            if c in imported_ids or c in imported:
                continue
            # 变量声明 / 函数定义
            if re.search(r"(?:const|let|var|function)\s+" + re.escape(c) + r"\b", script):
                continue
            if re.search(r"\b" + re.escape(c) + r"\s*[:=]\s*(?:async\s*)?\(", script):
                continue
            issues.append((fn, "template-fn-missing", c))

print("=== 检查结果 ===")
if issues:
    for fn, kind, name in issues:
        print(f"  !! {fn}: [{kind}] {name}")
else:
    print("  全部通过：无缺失导入 / 无未定义组件 / 无未定义模板函数")
print(f"\n共 {len(issues)} 处问题")
sys.exit(1 if issues else 0)
