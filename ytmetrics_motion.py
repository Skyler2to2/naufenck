"""
ytmetrics_motion.py
-------------------
为 YTMetrics Streamlit 应用注入"DDNA 风格"动效与微交互。

设计原则：
1. 零功能侵入：仅注入 CSS + JS overlay，不改任何业务代码。
2. 抗 Streamlit rerun：用 MutationObserver 监听 DOM，新元素自动绑定动画。
3. 借鉴 DDNA：标题 stagger 进场、power3.out 缓动、卡片悬浮抬升、
   平滑锚点滚动、图片淡入、滚动视差（仅装饰层）。
4. 完全可降级：尊重 prefers-reduced-motion;移动端自动关闭重型效果。

用法：
    from ytmetrics_motion import inject_motion
    # 在 st.set_page_config 之后调用一次即可
    inject_motion()
"""
from __future__ import annotations

import streamlit as st


_MOTION_CSS = r"""
<style id="ytmetrics-motion-style">
/* ---------- 缓动语言（统一沿用 DDNA 风格 power3.out 的 cubic-bezier 等价） ---------- */
:root {
    --ytm-ease-out: cubic-bezier(0.215, 0.61, 0.355, 1);   /* power3.out */
    --ytm-ease-inout: cubic-bezier(0.645, 0.045, 0.355, 1);
    --ytm-dur-fast: 0.35s;
    --ytm-dur-base: 0.7s;
    --ytm-dur-slow: 1.1s;
}

/* ---------- 1. 标题入场 stagger：mounted 时从 translateY(40%) opacity:0 揭示 ---------- */
.stApp h1[data-ytm-anim],
.stApp h2[data-ytm-anim],
.stApp h3[data-ytm-anim] {
    opacity: 0;
    transform: translate3d(0, 28px, 0);
    transition:
        opacity var(--ytm-dur-base) var(--ytm-ease-out),
        transform var(--ytm-dur-base) var(--ytm-ease-out);
    will-change: opacity, transform;
}
.stApp h1[data-ytm-anim].is-in,
.stApp h2[data-ytm-anim].is-in,
.stApp h3[data-ytm-anim].is-in {
    opacity: 1;
    transform: translate3d(0, 0, 0);
}

/* ---------- 2. 通用块级元素入场：段落、表格、图表、columns ---------- */
[data-testid="stMarkdownContainer"][data-ytm-anim],
[data-testid="stDataFrame"][data-ytm-anim],
[data-testid="stTable"][data-ytm-anim],
[data-testid="stPlotlyChart"][data-ytm-anim],
[data-testid="stAltairChart"][data-ytm-anim],
[data-testid="stPyplotChart"][data-ytm-anim],
[data-testid="stImage"][data-ytm-anim],
[data-testid="stMetric"][data-ytm-anim],
[data-testid="stExpander"][data-ytm-anim] {
    opacity: 0;
    transform: translate3d(0, 22px, 0);
    transition:
        opacity var(--ytm-dur-base) var(--ytm-ease-out),
        transform var(--ytm-dur-base) var(--ytm-ease-out);
    will-change: opacity, transform;
}
[data-ytm-anim].is-in {
    opacity: 1 !important;
    transform: translate3d(0, 0, 0) !important;
}

/* ---------- 3. Metric 卡片悬浮抬升 ---------- */
[data-testid="stMetric"] {
    border-radius: 14px;
    padding: 16px 18px;
    background: rgba(255, 255, 255, 0.55);
    border: 1px solid rgba(15, 23, 42, 0.06);
    transition:
        transform var(--ytm-dur-fast) var(--ytm-ease-out),
        box-shadow var(--ytm-dur-fast) var(--ytm-ease-out),
        background-color var(--ytm-dur-fast) var(--ytm-ease-out);
}
[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    box-shadow: 0 14px 28px rgba(15, 23, 42, 0.10);
    background: rgba(255, 255, 255, 0.85);
}

/* ---------- 4. 按钮微动效 ---------- */
.stApp button[kind="primary"],
.stApp button[kind="secondary"] {
    transition:
        transform var(--ytm-dur-fast) var(--ytm-ease-out),
        box-shadow var(--ytm-dur-fast) var(--ytm-ease-out),
        background-color var(--ytm-dur-fast) var(--ytm-ease-out) !important;
    position: relative;
    overflow: hidden;
}
.stApp button[kind="primary"]:hover,
.stApp button[kind="secondary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 22px rgba(15, 23, 42, 0.14);
}
.stApp button[kind="primary"]:active,
.stApp button[kind="secondary"]:active {
    transform: translateY(0);
    box-shadow: 0 4px 10px rgba(15, 23, 42, 0.10);
}

/* 按钮内部的水波涟漪 */
.stApp button[kind="primary"]::after,
.stApp button[kind="secondary"]::after {
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at var(--ytm-rx, 50%) var(--ytm-ry, 50%),
                                rgba(255, 255, 255, 0.45) 0%,
                                rgba(255, 255, 255, 0) 55%);
    opacity: 0;
    transition: opacity 0.6s var(--ytm-ease-out);
    pointer-events: none;
}
.stApp button[kind="primary"]:active::after,
.stApp button[kind="secondary"]:active::after {
    opacity: 1;
    transition: opacity 0.05s linear;
}

/* ---------- 5. expander / 选项卡 hover ---------- */
[data-testid="stExpander"] {
    transition:
        transform var(--ytm-dur-fast) var(--ytm-ease-out),
        box-shadow var(--ytm-dur-fast) var(--ytm-ease-out);
    border-radius: 10px;
}
[data-testid="stExpander"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 18px rgba(15, 23, 42, 0.07);
}

/* ---------- 6. 图片淡入（matplotlib 生成的 PNG） ---------- */
[data-testid="stImage"] img,
[data-testid="stPyplotChart"] img {
    transition: opacity var(--ytm-dur-base) var(--ytm-ease-out),
                transform var(--ytm-dur-base) var(--ytm-ease-out);
}
[data-testid="stImage"][data-ytm-anim]:not(.is-in) img,
[data-testid="stPyplotChart"][data-ytm-anim]:not(.is-in) img {
    opacity: 0;
    transform: scale(1.015);
}

/* ---------- 7. 平滑锚点跳转（侧边栏目录的 #summary-metrics 等） ---------- */
html {
    scroll-behavior: smooth;
}

/* ---------- 8. Tab 选中下划线动效 ---------- */
.stTabs [data-baseweb="tab-highlight"] {
    transition: all var(--ytm-dur-base) var(--ytm-ease-out) !important;
}

/* ---------- 9. 顶部细长进度条（rerun 时短暂可见） ---------- */
#ytm-top-progress {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #4F46E5, transparent);
    transform: scaleX(0);
    transform-origin: 0 50%;
    z-index: 99999;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.3s ease;
}
#ytm-top-progress.is-loading {
    opacity: 1;
    animation: ytm-top-progress-loop 1.2s linear infinite;
}
@keyframes ytm-top-progress-loop {
    0%   { transform: scaleX(0);   transform-origin: 0 50%; }
    50%  { transform: scaleX(1);   transform-origin: 0 50%; }
    50.01% { transform-origin: 100% 50%; }
    100% { transform: scaleX(0);   transform-origin: 100% 50%; }
}

/* ---------- 10. 降级：尊重系统偏好 ---------- */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
    }
    [data-ytm-anim] {
        opacity: 1 !important;
        transform: none !important;
    }
}
</style>
"""


_MOTION_JS = r"""
<script id="ytmetrics-motion-script">
(function () {
    if (window.__ytmetricsMotionReady) return;
    window.__ytmetricsMotionReady = true;

    // -------- 0. 容器：Streamlit 把页面挂在 parent.document（iframe）外 --------
    // 在 Streamlit 中本脚本通过 components.v1.html 注入会被 iframe 包裹，
    // 因此这里取 window.parent.document，且仅在能拿到时才生效。
    var doc;
    try { doc = window.parent.document; } catch (e) { doc = document; }
    if (!doc) return;

    var prefersReduce = window.matchMedia &&
                        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // -------- 1. 顶部进度条 --------
    function ensureTopProgress() {
        if (doc.getElementById("ytm-top-progress")) return;
        var bar = doc.createElement("div");
        bar.id = "ytm-top-progress";
        doc.body.appendChild(bar);
    }

    // -------- 2. IntersectionObserver：进入视口添加 .is-in --------
    var io = null;
    function ensureObserver() {
        if (io || !("IntersectionObserver" in window)) return;
        io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    var el = entry.target;
                    // 同一行的兄弟元素做轻微 stagger
                    var idx = parseInt(el.dataset.ytmIdx || "0", 10);
                    el.style.transitionDelay = Math.min(idx, 6) * 60 + "ms";
                    el.classList.add("is-in");
                    io.unobserve(el);
                }
            });
        }, {
            root: null,
            rootMargin: "0px 0px -8% 0px",
            threshold: 0.08
        });
    }

    // -------- 3. 给目标元素打标记并 observe --------
    var TARGET_SELECTOR = [
        '.stApp h1', '.stApp h2', '.stApp h3',
        '[data-testid="stMarkdownContainer"]',
        '[data-testid="stDataFrame"]',
        '[data-testid="stTable"]',
        '[data-testid="stPlotlyChart"]',
        '[data-testid="stAltairChart"]',
        '[data-testid="stPyplotChart"]',
        '[data-testid="stImage"]',
        '[data-testid="stMetric"]',
        '[data-testid="stExpander"]'
    ].join(',');

    function tagAndObserve() {
        if (!io) return;
        var nodes = doc.querySelectorAll(TARGET_SELECTOR);
        var lastParent = null, idx = 0;
        nodes.forEach(function (el) {
            if (el.hasAttribute("data-ytm-anim")) return;
            // 跳过被收起的 expander 内部子节点（避免初次就触发）
            el.setAttribute("data-ytm-anim", "");
            // 同一父级里给 stagger 索引
            if (el.parentElement === lastParent) {
                idx += 1;
            } else {
                lastParent = el.parentElement;
                idx = 0;
            }
            el.dataset.ytmIdx = String(idx);
            // 已经在视口内的（首屏）立即触发
            var rect = el.getBoundingClientRect();
            if (rect.top < (window.innerHeight || 800) * 0.95 && rect.bottom > 0) {
                requestAnimationFrame(function () {
                    el.style.transitionDelay = Math.min(idx, 6) * 60 + "ms";
                    el.classList.add("is-in");
                });
            } else {
                io.observe(el);
            }
        });
    }

    // -------- 4. 按钮水波点：记录点击坐标 --------
    function bindRipple() {
        doc.addEventListener("pointerdown", function (e) {
            var btn = e.target && e.target.closest && e.target.closest('button[kind]');
            if (!btn) return;
            var rect = btn.getBoundingClientRect();
            btn.style.setProperty("--ytm-rx", ((e.clientX - rect.left) / rect.width * 100) + "%");
            btn.style.setProperty("--ytm-ry", ((e.clientY - rect.top) / rect.height * 100) + "%");
        }, { passive: true, capture: true });
    }

    // -------- 5. Streamlit rerun 检测 --------
    // Streamlit 在 rerun 时会清空主区并重建，body 上短暂出现 data-status 等变化。
    // 通过 MutationObserver 监听主容器即可。
    var debounceTimer = null;
    function scheduleScan() {
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(tagAndObserve, 80);
    }

    function bindGlobalObserver() {
        var root = doc.querySelector('[data-testid="stAppViewContainer"]') ||
                   doc.querySelector('.stApp') ||
                   doc.body;
        if (!root) return;
        var mo = new MutationObserver(function (mutations) {
            // 只要有节点新增就排队扫描
            for (var i = 0; i < mutations.length; i++) {
                if (mutations[i].addedNodes && mutations[i].addedNodes.length) {
                    scheduleScan();
                    break;
                }
            }
        });
        mo.observe(root, { childList: true, subtree: true });
    }

    // -------- 6. 顶部进度条：监听 Streamlit 运行状态 --------
    function bindTopProgress() {
        var bar = doc.getElementById("ytm-top-progress");
        if (!bar) return;
        // Streamlit 把"running"挂在 status widget 上
        var statusWidget = function () {
            return doc.querySelector('[data-testid="stStatusWidget"]') ||
                   doc.querySelector('[data-testid="stToolbar"]');
        };
        var lastRunning = false;
        function check() {
            var w = statusWidget();
            var running = !!(w && /Running/i.test(w.textContent || ""));
            if (running !== lastRunning) {
                bar.classList.toggle("is-loading", running);
                lastRunning = running;
            }
        }
        setInterval(check, 250);
    }

    // -------- 7. 锚点平滑滚动兜底（Streamlit 偶尔禁用 scroll-behavior） --------
    function bindAnchorClick() {
        doc.addEventListener("click", function (e) {
            var a = e.target && e.target.closest && e.target.closest("a[href^='#']");
            if (!a) return;
            var hash = a.getAttribute("href");
            if (!hash || hash.length < 2) return;
            var target = doc.querySelector(hash) ||
                         doc.querySelector('[id="' + hash.slice(1) + '"]');
            if (!target) return;
            e.preventDefault();
            target.scrollIntoView({ behavior: "smooth", block: "start" });
        }, false);
    }

    // -------- 8. 启动 --------
    function boot() {
        if (!doc.body) {
            return setTimeout(boot, 60);
        }
        ensureTopProgress();
        if (!prefersReduce) {
            ensureObserver();
            tagAndObserve();
            bindRipple();
            bindGlobalObserver();
            bindAnchorClick();
        }
        bindTopProgress();
    }
    boot();
})();
</script>
"""


def inject_motion() -> None:
    """在 Streamlit 应用中注入 DDNA 风格动效。

    必须在 ``st.set_page_config`` 之后、任何业务渲染之前调用一次。
    重复调用安全(JS 端有 ``__ytmetricsMotionReady`` 守卫)。
    """
    # CSS 直接通过 st.markdown 注入到主文档（Streamlit 会原样输出到主页面 head）
    st.markdown(_MOTION_CSS, unsafe_allow_html=True)
    # JS 必须通过 components.html 才能拿到执行上下文,
    # 然后用 window.parent.document 反向操作主页面 DOM。
    try:
        import streamlit.components.v1 as components
        components.html(_MOTION_JS, height=0, width=0)
    except Exception:
        # 兜底:即便组件不可用,CSS 部分仍然生效。
        st.markdown(_MOTION_JS, unsafe_allow_html=True)
