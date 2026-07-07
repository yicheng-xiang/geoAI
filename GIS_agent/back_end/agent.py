import json
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from openai import AzureOpenAI
from tools import init_canvas, export_map_to_base64, REGISTRY_TOOLS
from agent_schemas.tools_definition import MAP_TOOLS

AVAILABLE_TOOLS = {
    "draw_choropleth": REGISTRY_TOOLS["draw_choropleth"],
    "add_points_layer": REGISTRY_TOOLS["add_points_layer"],
    "aggregate_points_to_districts": REGISTRY_TOOLS["aggregate_points_to_districts"],
    "add_title": REGISTRY_TOOLS["add_title"],
    "add_compass": REGISTRY_TOOLS["add_compass"],
    "add_gridlines": REGISTRY_TOOLS["add_gridlines"],
    "add_scale_bar": REGISTRY_TOOLS["add_scale_bar"],
}

from dotenv import load_dotenv
load_dotenv()

client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2024-12-01-preview"
)

# Stateful global context variables
GLOBAL_MAP_STATE = None
GLOBAL_MESSAGES = []

def clear_agent_session():
    global GLOBAL_MAP_STATE, GLOBAL_MESSAGES
    GLOBAL_MAP_STATE = None
    GLOBAL_MESSAGES = []
    print("[Session] Global state and conversational buffer cleared.")

def run_gis_agent_stream(user_prompt):
    """
    [Ironclad Resilient Stateful ReAct GIS Engine - English Version]
    - Dynamically addresses the 'dict' vs 'object' attribute alignment flaw.
    - Completely eliminates OpenAI 400 transaction blocking via runtime type adaptation.
    """
    global GLOBAL_MAP_STATE, GLOBAL_MESSAGES
    
    if GLOBAL_MAP_STATE is None:
        GLOBAL_MAP_STATE = init_canvas()
        
        system_prompt = (
            "You are an internationally acclaimed, professional Multi-Source Autonomous GIS Copilot (MapGPT).\n"
            "Your mission is to parse user intents and coordinate various cartographic layout operators via stateful [Thought -> Action -> Observation] ReAct cycles.\n\n"
            
            "【📊 Heterogeneous Data Dictionary Alignment】\n"
            "1. Administrative Base Layer (Polygon): Bound to HKDistrict18.shp. If the user wants a categoric legend, pass 'NAME' into `draw_choropleth`; if a numeric breakdown is requested, pass 'OBJECTID' as default.\n"
            "2. Facility Grid Layers (Points): Bound to data/AllTogether.csv. You MUST extract strict string matches into the `facility_types` string array argument:\n"
            "   - If user asks for 'Ambulance' / 'Rescue' ──> facility_types=['Ambulance Depot']\n"
            "   - If user asks for 'Fire Station' / 'Firefighting' ──> facility_types=['Fire Station']\n"
            "   - If user asks for 'Primary School' ──> facility_types=['Primary School']\n"
            "   - If user asks for 'Secondary School' ──> facility_types=['Secondary School']\n"
            "   - If user asks for 'Country Park' ──> facility_types=['Country Park']\n"
            "   - If user asks for 'Higher Education' / 'University' ──> facility_types=['Higher Education Institutions']\n"
            "3. Spatial Aggregation (Quantitative Choropleth): When the user requests per-district counts, density, statistics, or aggregated facility totals mapped by district boundaries, use `aggregate_points_to_districts` with the same `facility_types` mapping rules above. Do NOT use `draw_choropleth` for count-based district thematic maps.\n\n"
            
            "【🥞 Rigid Stacking Staging Order】\n"
            "You must trigger exactly ONE tool operator per iteration loop following this architectural hierarchy:\n"
            "  - Step 1 (Bottom): Render the polygon layer using `aggregate_points_to_districts` (count/density tasks) OR `draw_choropleth` (categorical/numeric attribute tasks).\n"
            "  - Step 2 (Middle): Optionally overlay individual target markers with `add_points_layer` when the user also wants visible point symbols.\n"
            "  - Step 3 (Top): Finalize cosmetic elements orderly via `add_title`, `add_compass`, `add_scale_bar`, and `add_gridlines`.\n"
            "  - ⚠️ MANDATORY FINAL STEP: You MUST always call `add_gridlines` as the LAST cosmetic tool before finishing. Without it the map has no coordinate frame, no degree labels, and no border. Never skip it, even for simple requests.\n\n"
            
            "【⚙️ Operational Constraints】\n"
            "1. Your final thoughts, text explanations, and intermediate logs MUST be fully compiled in professional, fluent English.\n"
            "2. Self-Check: Continue calling pending decoration tools if any are missing. Once base map, asset points, compass, scale bar, title, and gridlines are all cleanly overlayed, cease tool deployment and output a cohesive summary wrap-up. The map is NOT complete until `add_gridlines` has been called.\n"
            "3. The string arguments inside JSON block must NOT contain any trailing carriage returns or raw newlines."
        )
        GLOBAL_MESSAGES = [{"role": "system", "content": system_prompt}]
    
    # 🛡️ 🔑 [CRITICAL FIX]: Robust runtime type check line for structural auditing
    # Gracefully bypasses the 'dict has no attribute role' crashing vector by unifying dict and object schemas
    if GLOBAL_MESSAGES:
        last_msg = GLOBAL_MESSAGES[-1]
        
        # Safe extraction of the message role string identifier
        last_role = last_msg.get("role") if isinstance(last_msg, dict) else getattr(last_msg, "role", None)
        
        if last_role == "assistant":
            # Safe extraction of potential hanging tool calling blocks
            last_calls = last_msg.get("tool_calls") if isinstance(last_msg, dict) else getattr(last_msg, "tool_calls", None)
            
            if last_calls:
                print(f"[Guardrail Engine]: Resolving structural discrepancies for {len(last_calls)} pending transactions...")
                for hanging_call in last_calls:
                    # Resolve ID depending on object runtime schemas
                    c_id = hanging_call.get("id") if isinstance(hanging_call, dict) else hanging_call.id
                    c_name = hanging_call.get("function", {}).get("name") if isinstance(hanging_call, dict) else hanging_call.function.name
                    
                    GLOBAL_MESSAGES.append({
                        "role": "tool",
                        "tool_call_id": c_id,
                        "name": c_name,
                        "content": "Skipped: Synchronized and closed automatically by orchestrator node."
                    })

    # Sync context inputs with background properties
    GLOBAL_MAP_STATE["user_prompt"] = user_prompt
    GLOBAL_MESSAGES.append({"role": "user", "content": user_prompt})
    
    max_iterations = 8
    iteration = 0
    executed_tools = []
    
    while iteration < max_iterations:
        iteration += 1
        
        response = client.chat.completions.create(
            model="gpt-5-mini",  # 👈 Keep your Azure deployment slot label unchanged
            messages=GLOBAL_MESSAGES,
            tools=MAP_TOOLS,
            tool_choice="auto"
        )
        
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        GLOBAL_MESSAGES.append(response_message)
        
        # Staging completed terminal state
        if not tool_calls:
            # Guarantee journal-grade frame & graticule are always present on final export
            if "add_gridlines" not in executed_tools:
                try:
                    AVAILABLE_TOOLS["add_gridlines"](GLOBAL_MAP_STATE)
                    print("[Finalizer]: Auto-injected add_gridlines before final export.")
                except Exception as e:
                    print(f"[Finalizer]: Auto add_gridlines failed: {e}")
            final_image = export_map_to_base64(GLOBAL_MAP_STATE, close_fig=False)
            yield {
                "thought": "All spatial feature layers and descriptive cosmetic attachments are fully generated. Pipeline completed.",
                "log": f"🎉 [Task Success] Copilot finalized: {response_message.content or 'The canvas layout has been locked.'}",
                "image": final_image,
                "status": "completed"
            }
            return
            
        primary_tool_call = tool_calls[0]
        func_name = primary_tool_call.function.name
        raw_arguments = primary_tool_call.function.arguments
        clean_arguments = raw_arguments.replace('\n', ' ').replace('\r', '')
        
        print(f"[ReAct Agent Loop {iteration}] Deploying function: {func_name}")
        executed_tools.append(func_name)
        
        try:
            func_args = json.loads(clean_arguments)
            if func_name in AVAILABLE_TOOLS:
                log_msg = AVAILABLE_TOOLS[func_name](GLOBAL_MAP_STATE, **func_args)
                primary_observation = f"Success: {log_msg}"
            else:
                primary_observation = f"Error: Tool name [{func_name}] mismatch."
        except Exception as e:
            primary_observation = f"Runtime Error: {str(e)}"
            
        intermediate_image = export_map_to_base64(GLOBAL_MAP_STATE, close_fig=False)
        
        yield {
            "thought": f"[Iteration Layer {iteration}] Appending layout instance -> [{func_name}]...",
            "log": f"[ReAct Connection] {primary_observation}",
            "image": intermediate_image,
            "status": "processing"
        }
        
        GLOBAL_MESSAGES.append({
            "role": "tool",
            "tool_call_id": primary_tool_call.id,
            "name": func_name,
            "content": primary_observation
        })
        
        # Batch settlement mechanism inside individual loop turns
        if tool_calls and len(tool_calls) > 1:
            for extra_call in tool_calls[1:]:
                extra_id = extra_call.get("id") if isinstance(extra_call, dict) else extra_call.id
                extra_name = extra_call.get("function", {}).get("name") if isinstance(extra_call, dict) else extra_call.function.name
                GLOBAL_MESSAGES.append({
                    "role": "tool",
                    "tool_call_id": extra_id,
                    "name": extra_name,
                    "content": "Skipped: Deferred by scheduling thread safely."
                })

    # Safety backup: also guarantee gridlines on max-iterations exhaustion path
    if "add_gridlines" not in executed_tools:
        try:
            AVAILABLE_TOOLS["add_gridlines"](GLOBAL_MAP_STATE)
            print("[Finalizer]: Auto-injected add_gridlines on iteration cap exit.")
        except Exception as e:
            print(f"[Finalizer]: Auto add_gridlines failed: {e}")
    final_image = export_map_to_base64(GLOBAL_MAP_STATE, close_fig=False)
    yield {
        "thought": "Maximum execution threshold reached. Forcing session backup snapshot.",
        "log": "[Session Interrupted] Frame buffers preserved safely.",
        "image": final_image,
        "status": "completed"
    }