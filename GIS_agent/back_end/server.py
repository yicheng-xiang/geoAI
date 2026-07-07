import json
import os
import sys
import traceback

from flask import Flask, request, Response, jsonify
from flask_cors import CORS

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from agent import run_gis_agent_stream, clear_agent_session

app = Flask(__name__)
CORS(app)


@app.route('/api/chat_and_map_stream', methods=['POST'])
def chat_and_map_stream():
    """有状态的流式制图网关：基于 SSE 实时增量分发图文状态。"""
    data = request.json or {}
    user_prompt = data.get("prompt", "")

    if not user_prompt:
        return Response(
            "data: " + json.dumps({"error": "指令不能为空"}) + "\n\n",
            mimetype="text/event-stream",
        )

    def sse_generator():
        try:
            for step_data in run_gis_agent_stream(user_prompt):
                yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            print("\n=== [流式运行错误] ===")
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e), 'status': 'failed'}, ensure_ascii=False)}\n\n"

    return Response(sse_generator(), mimetype="text/event-stream")


@app.route('/api/clear_session', methods=['POST'])
def reset_session():
    """重置 Agent 会话与地图画布状态。"""
    clear_agent_session()
    return jsonify({"status": "success", "message": "会话已完全初始化重置"})


if __name__ == '__main__':
    app.run(port=5000, debug=True)
