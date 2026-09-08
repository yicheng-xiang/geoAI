import json
from io import BytesIO
import os
import sys
import traceback
import re
import uuid

from flask import Flask, Request, request, Response, jsonify
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from agent import (
    clear_agent_session,
    get_agent_session_state,
    run_gis_agent_stream,
    set_agent_uploaded_dataset,
)
from upload_service import (
    MAX_UPLOAD_BYTES,
    UploadDatasetError,
    parse_excel_upload,
    public_upload_summary,
)


class InMemoryUploadRequest(Request):
    """Keep accepted multipart files in memory instead of temporary disk files."""

    def _get_file_stream(
        self,
        total_content_length,
        content_type,
        filename=None,
        content_length=None,
    ):
        return BytesIO()

app = Flask(__name__)
app.request_class = InMemoryUploadRequest
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + (512 * 1024)
CORS(app)

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify({
        "status": "failed",
        "error": "The upload request exceeds the server size limit.",
        "error_code": "UPLOAD_REQUEST_TOO_LARGE",
    }), 413


def _resolve_session_id(data):
    session_id = str(data.get("session_id", "")).strip()
    if not session_id:
        return str(uuid.uuid4())
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("session_id 格式无效")
    return session_id


@app.route('/api/health', methods=['GET'])
def health_check():
    """Lightweight readiness endpoint used by the local one-click launcher."""
    return jsonify({"status": "ok", "service": "geoai-backend"})


@app.route('/api/csdi', methods=['GET', 'POST'])
def csdi_session_sources():
    from agent import SESSION_STORE
    from tools import init_map_state
    from csdi_sources import catalog, public_datasets
    from csdi_tools import csdi_download
    try:
        data = (request.get_json(silent=True) or {}) if request.method == 'POST' else request.args
        if not data.get('session_id'):
            raise ValueError('session_id is required')
        session_id = _resolve_session_id(data)
        session = SESSION_STORE.get_or_create(session_id)
        with session['lock']:
            store = session.setdefault('temporary_datasets', {})
            if request.method == 'GET':
                return jsonify({'catalog': catalog(data.get('query', '')),
                                'temporary_datasets': public_datasets({'temporary_datasets': store})})
            if session['map_state'] is None:
                session['map_state'] = init_map_state()
            state = session['map_state']
            state['temporary_datasets'] = store
            result = csdi_download(state, data.get('dataset_id'), bool(data.get('refresh', False)))
            return jsonify(result), 200 if result['ok'] else 400
    except Exception as exc:
        return jsonify({'ok': False, 'message': str(exc)}), 400


@app.route('/api/session_state', methods=['GET'])
def session_state():
    """Restore public session metadata after a browser refresh."""
    try:
        session_id = _resolve_session_id(request.args)
    except ValueError as exc:
        return jsonify({
            "status": "failed",
            "error": str(exc),
            "error_code": "INVALID_SESSION_ID",
        }), 400
    return jsonify({
        "status": "success",
        "session_id": session_id,
        **get_agent_session_state(session_id),
    })


@app.route('/api/chat_and_map_stream', methods=['POST'])
def chat_and_map_stream():
    """有状态的流式制图网关：基于 SSE 实时增量分发图文状态。"""
    data = request.json or {}
    user_prompt = data.get("prompt", "")

    try:
        session_id = _resolve_session_id(data)
    except ValueError as exc:
        return Response(
            "data: " + json.dumps({"error": str(exc), "status": "failed"}, ensure_ascii=False) + "\n\n",
            mimetype="text/event-stream",
        )

    if not user_prompt:
        return Response(
            "data: " + json.dumps({
                "session_id": session_id,
                "error": "指令不能为空",
                "error_code": "EMPTY_PROMPT",
                "status": "failed",
            }, ensure_ascii=False) + "\n\n",
            mimetype="text/event-stream",
        )

    def sse_generator():
        try:
            for step_data in run_gis_agent_stream(user_prompt, session_id):
                yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            print("\n=== [流式运行错误] ===")
            traceback.print_exc()
            yield f"data: {json.dumps({'session_id': session_id, 'error': str(e), 'error_code': 'STREAM_RUNTIME_ERROR', 'status': 'failed'}, ensure_ascii=False)}\n\n"

    return Response(
        sse_generator(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Session-ID": session_id},
    )


@app.route('/api/upload_dataset', methods=['POST'])
def upload_dataset():
    """Validate one Excel point table and bind it to the requesting browser session."""
    try:
        session_id = _resolve_session_id(request.form)
    except ValueError as exc:
        return jsonify({
            "status": "failed",
            "error": str(exc),
            "error_code": "INVALID_SESSION_ID",
        }), 400

    try:
        uploaded_dataset = parse_excel_upload(request.files.get("file"))
        set_agent_uploaded_dataset(session_id, uploaded_dataset)
    except UploadDatasetError as exc:
        return jsonify({
            "status": "failed",
            "session_id": session_id,
            "error": exc.message,
            "error_code": exc.code,
        }), exc.http_status
    except Exception:
        app.logger.exception("Unexpected Excel upload failure")
        return jsonify({
            "status": "failed",
            "session_id": session_id,
            "error": "The Excel dataset could not be processed.",
            "error_code": "UPLOAD_RUNTIME_ERROR",
        }), 500

    return jsonify({
        "status": "success",
        "session_id": session_id,
        **public_upload_summary(uploaded_dataset),
        "message": "The Excel point dataset is ready for this browser session.",
    })


@app.route('/api/clear_session', methods=['POST'])
def reset_session():
    """重置 Agent 会话与地图画布状态。"""
    data = request.json or {}
    try:
        session_id = str(data.get("session_id", "")).strip()
        if not session_id or not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("必须提供有效的 session_id")
    except ValueError as exc:
        return jsonify({"status": "failed", "error": str(exc), "error_code": "INVALID_SESSION_ID"}), 400

    cleared = clear_agent_session(session_id)
    return jsonify({
        "status": "success",
        "session_id": session_id,
        "cleared": cleared,
        "message": "当前会话已重置",
    })


if __name__ == '__main__':
    debug_enabled = os.getenv("GEOAI_DEBUG", "0").strip() == "1"
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=debug_enabled,
        use_reloader=False,
    )
