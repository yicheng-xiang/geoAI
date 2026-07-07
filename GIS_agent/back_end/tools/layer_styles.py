import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from data_catalog import resolve_csv_path

# 保持西式现代字体首位加载，提供极致清晰的英文字型
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False 

def refresh_clean_legend(ax, title="Map Layer Legend", fontsize=8, ncol=1, bbox_to_anchor=(1.0, 0.0)):
    """
    Global Legend Deduplication & Advanced Styling Purifier.
    Legend is placed INSIDE the map frame at the lower-right corner, over the ocean background.
    """
    handles, labels = ax.get_legend_handles_labels()

    if not handles:
        if ax.get_legend():
            ax.get_legend().remove()
        return

    unique_legend = {}
    for handle, label in zip(handles, labels):
        if label and not label.startswith('_'):
            unique_legend[label] = handle

    clean_labels = list(unique_legend.keys())
    clean_handles = list(unique_legend.values())

    actual_ncol = ncol
    if len(clean_labels) > 12:
        actual_ncol = 3
    elif len(clean_labels) > 6:
        actual_ncol = 2

    ax.legend(
        clean_handles,
        clean_labels,
        loc='lower right',
        title=title,
        frameon=True,
        facecolor='#ffffff',
        edgecolor='#334155',
        shadow=False,
        framealpha=0.92,
        fontsize=fontsize,
        title_fontsize=fontsize + 1,
        ncol=actual_ncol,
        bbox_to_anchor=bbox_to_anchor,

        borderpad=0.7,
        labelspacing=0.6,
        handletextpad=1.2,
        handlelength=1.0,
    )


def draw_choropleth(state, column="OBJECTID", cmap="tab20", k=5):
    """
    [Category 2 Tool: Vector Polygon Choropleth/Categorical Map Engine - Topo Z-Order Fixed]
    - 🔑 核心更新：加入 zorder=1 刚性底图安全锁，确保行政多边形永远留在最底层，绝不遮挡点层。
    """
    gdf = state["gdf"]
    ax = state["ax"]
    
    if cmap.lower() in ["black", "binary", "gray", "greys", "#000000"]:
        cmap = "tab20"
    
    # 🛡️ 仅清除老的多边形面要素，严禁删除 ax.lines，为增量叠加的图例留出完整生命周期
    for collection in list(ax.collections):
        if type(collection).__name__ == 'PolyCollection':
            collection.remove()
        
    user_prompt_text = str(state.get("user_prompt", "")).upper()
    is_pure_points_job = any(kw in user_prompt_text for kw in ["SCHOOL", "PRIMARY", "FACILITY", "POINT", "PARK", "CAMPUS", "STATION", "AMBULANCE", "POOL", "SWIMMING"])
    
    columns_upper = [c.upper() for c in gdf.columns]
    
    requested_col = column.upper()
    if requested_col in ["CNAME", "名称", "区名", "CHINESE", "C_NAME"] or requested_col not in columns_upper:
        english_candidates = ["DISTRICT", "ENAME", "D_NAME", "NAME", "ENG_NAME"]
        found_col = None
        for cand in english_candidates:
            if cand in columns_upper:
                found_col = gdf.columns[columns_upper.index(cand)]
                break
        if found_col:
            actual_col = found_col
            print(f"[GIS Engine Override]: Anti-Chinese guardrail triggered. Re-routed column to English field: [{actual_col}].")
        else:
            text_fields = gdf.select_dtypes(include=['object']).columns.tolist()
            actual_col = text_fields[0] if text_fields else gdf.columns[0]
    else:
        actual_col = gdf.columns[columns_upper.index(requested_col)]

    if actual_col == "OBJECTID" and is_pure_points_job:
        print("[GIS Engine]: Point-mapping task detected. Rendering background boundary only.")
        # 🔑 显式注入 zorder=1
        gdf.plot(ax=ax, cmap=cmap, edgecolor='#FFFFFF', linewidth=0.6, alpha=0.5, zorder=1)
        return "Success: Administrative background boundary initialized smoothly."

    is_categorical = False
    unique_count = gdf[actual_col].nunique()
    
    if gdf[actual_col].dtype == 'object' or (gdf[actual_col].dtype in ['int64', 'float64'] and unique_count <= 10):
        is_categorical = True
        if cmap in ["Purples", "Blues", "Reds", "YlOrRd", "viridis"]:
            cmap = "tab20" if unique_count > 10 else "Set3"

    cmap_obj = plt.get_cmap(cmap)

    if is_categorical:
        legend_fontsize = 7 if unique_count > 5 else 9
        unique_vals = sorted(gdf[actual_col].dropna().unique())
        num_vals = len(unique_vals)
        
        if num_vals == 1:
            colors_pool = [cmap_obj(0.7)]
        else:
            if cmap in ["Greens", "Blues", "Purples", "Reds", "Oranges", "YlOrRd", "viridis"]:
                colors_pool = cmap_obj(np.linspace(0.25, 0.85, num_vals))
            else:
                colors_pool = [cmap_obj(i % cmap_obj.N) if hasattr(cmap_obj, 'N') else cmap_obj(i / (num_vals - 1)) for i in range(num_vals)]
        
        val_to_color = dict(zip(unique_vals, colors_pool))
        row_colors = gdf[actual_col].map(val_to_color).fillna('#ffffff')
        
        # 🔑 显式注入 zorder=1，确保底图多边形在最底层填充
        gdf.plot(color=row_colors, ax=ax, edgecolor='#FFFFFF', linewidth=0.6, zorder=1)
        
        # 手动注入纯英文地名方形标记到图例池，设定 zorder=1 的代理层
        for val, color in val_to_color.items():
            ax.plot([], [], color=color, label=str(val), marker="s", linestyle="None", markersize=7, zorder=1)
            
        refresh_clean_legend(ax, title="Map Layer Legend", fontsize=legend_fontsize, ncol=2)
        log_msg = f"Success: Administrative choropleth rendered based on English category column [{actual_col}]."
        
    else:
        import mapclassify
        actual_k = min(k, unique_count)
        classifier = mapclassify.Quantiles(gdf[actual_col], k=actual_k)
        bin_ids = classifier(gdf[actual_col])
        
        if cmap in ["Greens", "Blues", "Purples", "Reds", "Oranges", "YlOrRd", "viridis"]:
            bin_colors = cmap_obj(np.linspace(0.25, 0.85, actual_k))
        else:
            bin_colors = [cmap_obj(i / (actual_k - 1) if actual_k > 1 else 0.5) for i in range(actual_k)]
            
        row_colors = [bin_colors[bid] for bid in bin_ids]
        # 🔑 显式注入 zorder=1
        gdf.plot(color=row_colors, ax=ax, edgecolor='#FFFFFF', linewidth=0.8, zorder=1)
        
        fmt = "{:.0f}"
        for i, upperbound in enumerate(classifier.bins):
            lowerbound = classifier.bins[i-1] if i > 0 else gdf[actual_col].min()
            label_text = f"{fmt.format(lowerbound)} - {fmt.format(upperbound)}"
            ax.plot([], [], color=bin_colors[i], label=label_text, linewidth=10, zorder=1)
            
        refresh_clean_legend(ax, title="Map Layer Legend", fontsize=9, ncol=1)
        log_msg = f"Success: Numeric thematic map rendered via Quantiles on column [{actual_col}]."
        
    return log_msg


def add_points_layer(state, csv_name="AllTogether.csv", facility_types=None, cmap="Set1"):
    """
    [Category 2 Tool: Heterogeneous Multi-Category Point Layer Vector Operator - Topo Z-Order Fixed]
    - 🔑 核心更新：加入 zorder=5 刚性高亮锁，确保无论何时呼叫打点，散点永远悬浮在底图最上方！
    """
    ax = state["ax"]
    user_prompt_text = str(state.get("user_prompt", "")).upper()
    
    csv_path = resolve_csv_path(csv_name)
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Database asset file not found at: {csv_path}")
        
    df = pd.read_csv(csv_path)
    if df.empty: 
        return f"Warning: Targeted database CSV [{csv_name}] is empty."
        
    lat_cols = [c for c in df.columns if 'LAT' in c.upper()]
    lon_cols = [c for c in df.columns if 'LON' in c.upper() or 'LNG' in c.upper()]
    type_cols = [c for c in df.columns if 'TYPE' in c.upper() or 'FACILITY' in c.upper() or 'CLASS' in c.upper()]
    
    if not lat_cols or not lon_cols or not type_cols:
        return "Failed: Missing standard spatial coordinates fields."
        
    actual_lat = lat_cols[0]
    actual_lon = lon_cols[0]
    actual_type = type_cols[0]
    
    df[actual_type] = df[actual_type].astype(str).str.strip()
    filtered_df = df.copy()
    
    if facility_types and len(facility_types) > 0:
        matched_rows = []
        for requested_type in facility_types:
            req_upper = requested_type.upper()
            mask = df[actual_type].str.upper().str.contains(req_upper)
            matched_rows.append(df[mask])
        if matched_rows:
            filtered_df = pd.concat(matched_rows).drop_duplicates()
    else:
        return "Skipped: Facility filtering types array is empty."
        
    if filtered_df.empty:
        return f"Notice: No entities matched criteria {facility_types}."
        
    ax.set_aspect('equal')
    unique_types = filtered_df[actual_type].unique()
    num_types = len(unique_types)
    
    literal_color = None
    if cmap.startswith("#") or cmap.lower() in ["black", "red", "blue", "green", "yellow", "orange", "purple"]:
        literal_color = cmap
    elif "BLACK" in user_prompt_text or "黑色" in user_prompt_text:
        literal_color = "#000000"
        
    if literal_color:
        colors_pool = [literal_color] * num_types
    else:
        try:
            cmap_obj = plt.get_cmap(cmap)
            if num_types == 1:
                if cmap in ["Greens", "Blues", "Purples", "Reds", "Oranges", "YlOrRd", "viridis"]:
                    colors_pool = [cmap_obj(0.7)]
                else:
                    colors_pool = [cmap_obj(0)]
            else:
                colors_pool = cmap_obj(np.linspace(0.25, 0.85, num_types))
        except Exception:
            colors_pool = ["#1e293b"] * num_types
            
    for path_collection in list(ax.collections):
        if type(path_collection).__name__ == 'PathCollection':
            if path_collection.get_label() in unique_types:
                path_collection.remove()
    
    # 🔑 关键绘制行：显式注入 zorder=5 锁死最顶层，且图例手柄同步强制绑定为 zorder=5 散点
    for idx, f_type in enumerate(unique_types):
        sub_df = filtered_df[filtered_df[actual_type] == f_type]
        ax.scatter(
            sub_df[actual_lon], 
            sub_df[actual_lat], 
            color=colors_pool[idx], 
            marker="o", 
            s=55,                   # 稍微放大让视觉对比更刚猛
            alpha=0.95,
            edgecolors='#FFFFFF', 
            linewidths=0.8,
            label=f_type,
            zorder=5                # 🚀 永远悬浮于多边形行政底图之上
        )
        
    refresh_clean_legend(ax, title="Map Layer Legend", fontsize=8, ncol=1)
    
    return f"Success: Extracted [{', '.join(unique_types)}] point layer and updated legend dynamically."