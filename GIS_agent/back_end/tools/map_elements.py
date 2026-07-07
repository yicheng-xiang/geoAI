import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

METERS_PER_DEG_LAT = 111_000
METERS_PER_DEG_LON_HK = 102_700  # ~111 km * cos(22.3°) at Hong Kong latitude
SCALE_BAR_GID = "_scale_bar_"


def _remove_scale_bar(ax):
    for artist in list(ax.lines) + list(ax.texts):
        if artist.get_gid() == SCALE_BAR_GID:
            artist.remove()


def add_scale_bar(state, length_km=10, position=(0.05, 0.05)):
    """
    [Category 3 Tool: International Line Scale Bar Overlay Operator]
    Draws a ground-distance scale bar in the lower-left margin using Hong Kong longitude scaling.
    """
    ax = state["ax"]

    _remove_scale_bar(ax)

    delta_x = (length_km * 1000) / METERS_PER_DEG_LON_HK

    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x_span = xmax - xmin
    y_span = ymax - ymin

    pos_x, pos_y = position
    x0 = xmin + pos_x * x_span
    y0 = ymin + pos_y * y_span
    x1 = x0 + delta_x

    line_kwargs = dict(color="#1e293b", linewidth=2.5, zorder=6, gid=SCALE_BAR_GID)

    ax.plot([x0, x1], [y0, y0], **line_kwargs)

    tick_height = y_span * 0.01
    ax.plot([x0, x0], [y0, y0 + tick_height], **line_kwargs)
    ax.plot([x1, x1], [y0, y0 + tick_height], **line_kwargs)

    label_text = f"{int(length_km) if length_km == int(length_km) else length_km} km"
    ax.text(
        x0 + delta_x / 2,
        y0 + y_span * 0.015,
        label_text,
        fontsize=8,
        color="#1e293b",
        weight="bold",
        ha="center",
        va="bottom",
        zorder=6,
        gid=SCALE_BAR_GID,
    )

    return (
        f"Success: Line scale bar overlayed at lower-left position {position} "
        f"representing {label_text} (longitude span {delta_x:.5f}°)."
    )


def add_title(state, text="Hong Kong Spatial Distribution Map", fontsize=15):
    """
    [Category 3 Tool: Canvas Main Title Overwriting Operator]
    Wipes out historical titles entirely to avoid overlapping characters during multi-turn updates.
    """
    ax = state["ax"]
    fig = state["fig"]

    ax.set_title("", fontsize=fontsize, pad=12)
    ax.set_title(text, fontsize=fontsize, pad=12, weight='bold', color='#1e293b')
    fig.tight_layout()

    return f"Success: Main title overwritten successfully to: '{text}'."

COMPASS_GID = "_compass_"


def add_compass(state, x=0.92, y=0.84, scale=0.06):
    """
    [Category 3 Tool: Standard Geographic Compass Overlay Operator]
    Draws a bold, clearly visible north arrow in the top-right corner.
    """
    ax = state["ax"]

    # Remove any previous compass artifacts
    for art in list(ax.texts) + list(ax.patches) + list(ax.lines):
        if art.get_gid() == COMPASS_GID:
            art.remove()

    arrow_kw = dict(
        arrowstyle="-|>,head_length=0.5,head_width=0.3",
        edgecolor="#1e293b",
        facecolor="#1e293b",
        lw=2.6,
        gid=COMPASS_GID,
    )

    ax.annotate(
        "",
        xy=(x, y),
        xytext=(x, y - scale),
        arrowprops=arrow_kw,
        xycoords="axes fraction",
    )

    ax.text(
        x,
        y + scale * 0.5,
        "N",
        fontsize=15,
        weight="bold",
        color="#1e293b",
        ha="center",
        va="bottom",
        transform=ax.transAxes,
        zorder=6,
        gid=COMPASS_GID,
    )

    return "Success: Bold north arrow compass overlayed in the top-right corner."

def add_gridlines(state):
    """
    [Category 3 Tool: Journal-Grade Map Frame, Graticule & Coordinate Label Operator]
    在画布上构建高对比度、Arial加粗字体的经纬度标签、加粗硬朗的实体地图框以及清晰的轻量化虚线网格。
    """
    ax = state["ax"]
    fig = state["fig"]
    gdf = state["gdf"]

    frame_color = '#334155'  # 硬朗的深石板色实体框
    label_color = '#1e293b'  # 高对比度深色文本

    # 1. 物理强开坐标轴，确保标签与框线绝对显性化
    ax.axis('on')

    # 2. 物理锁死 1:1 数据轴像素等比例投影，防拉伸
    ax.set_aspect('equal', adjustable='box')

    # 3. 显性化四周的地图矩形黑框线（Map Spine Box），增加清晰边界感
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(frame_color)
        spine.set_linewidth(1.5)  # 加粗边框至 1.5

    # 4. 动态计算并锁定 5 个等分刻度线位置
    bounds = gdf.total_bounds
    ax.set_xticks(np.linspace(bounds[0], bounds[2], 5))
    ax.set_yticks(np.linspace(bounds[1], bounds[3], 5))

    # 5. 终极国际化高级格式化：动态注入 °N 和 °E 符号并保留两位小数
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{x:.2f}°E"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, p: f"{y:.2f}°N"))

    # 6. 全量调大刻度线、内边距，并将经纬度文字飙升至 10 号、Arial加粗
    ax.tick_params(
        axis='both',
        which='major',
        direction='out',       # 刻度朝向框线外侧
        colors=frame_color,    # 刻度线颜色
        labelcolor=label_color,# 经纬度文字颜色
        labelsize=10,          # 放大字号
        length=6,              # 刻度线长度
        width=1.2,             # 刻度线粗细与框线呼应
        pad=8,                 # 增加文字与地图框的物理安全呼吸间距
    )

    # 锁死标签只在外侧 Bottom 和 Left 显示，防止遮挡右上角指北针
    ax.tick_params(axis='x', which='major', bottom=True, top=False, labelbottom=True, labeltop=False)
    ax.tick_params(axis='y', which='major', left=True, right=False, labelleft=True, labelright=False)

    # 7. 强行覆写全部标签的字体字重
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily('Arial')
        label.set_fontweight('bold')  # 强行设置为 bold 加粗

    # 8. 绘制半隐形高级虚线网格
    ax.set_axisbelow(True)  # 网格必须沉在数据图层下方
    ax.grid(
        True,
        which='major',
        linestyle=':',
        linewidth=0.5,
        alpha=0.6,
        color='#94a3b8',        # 优雅的灰蓝色，在浅蓝色海洋底图上清晰可辨
        zorder=1.5,
    )

    # 9. 刚性安全微调：使用精确 padding 刷新布局，绝对防止框外经纬度字样被边缘裁切吞噬
    fig.subplots_adjust(left=0.12, right=0.88, top=0.90, bottom=0.12)
    ax.set_aspect('equal', adjustable='box')

    return (
        "Success: Professional-grade map frame and graticule activated — "
        "thicker charcoal border (#334155), bold Arial outward °E/°N labels, optimized gridlines visibility."
    )