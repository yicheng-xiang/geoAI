import os
import geopandas as gpd

# 强约束：强制 Matplotlib 使用无 GUI 的纯图片渲染后端 Agg，防止 Flask 多线程崩溃
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from data_catalog import get_vector_dataset, get_vector_path

HK_DISTRICTS = get_vector_dataset("hong_kong_districts")
OSM_LAND = get_vector_dataset("osm_land_polygons")
DATA_PATH = get_vector_path("hong_kong_districts")
WORLD_SHP_PATH = get_vector_path("osm_land_polygons")


def init_canvas():
    """
    类别1工具：初始化 Matplotlib 画布，平铺浅蓝色海洋背景，并以最高性能增量剪裁并铺设 OSM 终极高清陆地底图（zorder=0）
    """
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"找不到 Shapefile 核心数据文件，请检查路径: {DATA_PATH}")

    gdf = gpd.read_file(DATA_PATH)
    if gdf.crs is None:
        gdf = gdf.set_crs(HK_DISTRICTS["crs"])
    elif gdf.crs.to_string() != HK_DISTRICTS["crs"]:
        gdf = gdf.to_crs(HK_DISTRICTS["crs"])

    # 线程安全地创建画布
    fig, ax = plt.subplots(figsize=(10, 8), dpi=100)

    # 1. 建立浅蓝色海洋背景，赋予整个画布海域质感
    fig.patch.set_facecolor('#e0f2fe')  # 浅水蓝
    ax.set_facecolor('#e0f2fe')

    # 默认隐藏原始无用坐标轴，由后置的网格线工具按需激活
    ax.axis('off')

    # 🔑 高性能核心更新：针对 OSM 超巨型数据，绝不能全量 read_file，必须利用香港范围的 BBox 执行增量加载
    if os.path.exists(WORLD_SHP_PATH):
        try:
            # 提取香港的外包矩形并向外适度外扩 0.5 度，作为环境底图的最佳感知视窗
            hk_total_bounds = gdf.total_bounds
            clip_bbox = (
                hk_total_bounds[0] - 0.5,  # xmin
                hk_total_bounds[1] - 0.5,  # ymin
                hk_total_bounds[2] + 0.5,  # xmax
                hk_total_bounds[3] + 0.5,  # ymax
            )

            # 🚀 利用 geopandas 底层空间索引，只读取落在香港及周边局部框内的米级多边形，速度提升上千倍
            world_bg = gpd.read_file(WORLD_SHP_PATH, bbox=clip_bbox)

            if world_bg.crs is None or world_bg.crs.to_string() != OSM_LAND["crs"]:
                world_bg = world_bg.to_crs(OSM_LAND["crs"])

            # 将 facecolor 调整为优雅的米白色或极淡灰，降低其与香港边界的对比度
            world_bg.plot(ax=ax, facecolor='#f8fafc', edgecolor='#e2e8f0', linewidth=0.2, zorder=0)
            print("[GIS Base Map Success]: 高清 OSM 陆地背景增量剪裁加载成功。")
        except Exception as e:
            print(f"[GIS Base Map Error]: OSM 高清底图增量加载失败，降级跳过: {e}")
    else:
        print(f"[GIS Base Map Warning]: 找不到 OSM 世界陆地背景数据，已跳过底层平铺: {WORLD_SHP_PATH}")

    return {
        "gdf": gdf,
        "fig": fig,
        "ax": ax
    }


def finalize_hong_kong_window(ax, hk_gdf, pad_ratio=0.15):
    """
    🌟 公共中台组件：在所有图层叠画完成后调用，强行将全球视窗裁切锁定回香港真实几何边界，并锁死等比例视差
    """
    hk_bounds = hk_gdf.total_bounds  # 提取香港的 [xmin, ymin, xmax, ymax]
    pad_x = (hk_bounds[2] - hk_bounds[0]) * pad_ratio
    pad_y = (hk_bounds[3] - hk_bounds[1]) * pad_ratio

    # 刚性卡死坐标轴的最大极值，防止被全球底图或经纬网格线撑大变形
    ax.set_xlim(hk_bounds[0] - pad_x, hk_bounds[2] + pad_x)
    ax.set_ylim(hk_bounds[1] - pad_y, hk_bounds[3] + pad_y)

    # 锁死横纵坐标轴物理像素比例为 1:1，防止地图变扁变胖
    ax.set_aspect('equal', adjustable='box')


def export_map_to_base64(state, close_fig=False):
    """
    类别1工具：将内存中叠加渲染完当前要素的画布导出为 Base64 字符串
    """
    import io
    import base64

    finalize_hong_kong_window(state["ax"], state["gdf"])

    fig = state["fig"]
    buf = io.BytesIO()

    fig.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')

    if close_fig:
        plt.close(fig)

    return f"data:image/png;base64,{img_base64}"
