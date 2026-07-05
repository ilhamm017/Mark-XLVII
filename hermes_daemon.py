import os
import sys
from pathlib import Path
import threading
import json
import logging
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import uvicorn

# Add project root and hermes-agent to sys.path
project_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(project_dir))
sys.path.insert(0, str(project_dir / "hermes-agent"))

class TaskFileHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s"))
        self._local = threading.local()
        self.task_logs = {}

    def set_task_context(self, task_id: str, log_path: str):
        self._local.task_id = task_id
        self.task_logs[task_id] = log_path

    def clear_task_context(self):
        self._local.task_id = None

    def emit(self, record):
        try:
            task_id = getattr(self._local, 'task_id', None)
            if task_id and task_id in self.task_logs:
                log_path = self.task_logs[task_id]
                msg = self.format(record)
                with open(log_path, "a", encoding="utf-8", errors="ignore") as f:
                    f.write(msg + "\n")
        except Exception:
            self.handleError(record)

task_handler = TaskFileHandler()
task_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(task_handler)

# --- Firefox DevTools MCP Bridge Variables ---
import queue
firefox_proc = None
firefox_lock = threading.Lock()
firefox_stdout_queue = queue.Queue()
firefox_active_requests = {}

# --- Active Hermes Tasks Tracking ---
active_tasks = set()
active_tasks_lock = threading.Lock()

def read_firefox_stdout(p):
    while True:
        try:
            line = p.stdout.readline()
            if not line:
                break
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                firefox_stdout_queue.put(line_str)
        except Exception:
            break

def firefox_dispatcher():
    while True:
        try:
            line = firefox_stdout_queue.get()
            try:
                data = json.loads(line)
                if isinstance(data, dict) and "id" in data:
                    req_id = data["id"]
                    if req_id in firefox_active_requests:
                        firefox_active_requests[req_id].put(data)
            except Exception:
                pass
        except Exception:
            break

def start_firefox_mcp():
    global firefox_proc
    cmd = [
        r"C:\Users\Administrator\AppData\Roaming\npm\firefox-devtools-mcp.cmd",
        "--connectExisting",
        "--marionettePort",
        "6000"
    ]
    try:
        kwargs = {}
        import subprocess as sp
        if os.name == 'nt':
            kwargs["creationflags"] = sp.CREATE_NO_WINDOW if hasattr(sp, "CREATE_NO_WINDOW") else 0x08000000
        firefox_proc = sp.Popen(
            cmd,
            stdin=sp.PIPE,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            **kwargs
        )
        
        t1 = threading.Thread(target=read_firefox_stdout, args=(firefox_proc,), daemon=True)
        t1.start()
        
        t2 = threading.Thread(target=firefox_dispatcher, daemon=True)
        t2.start()
        
        print("[Daemon] Firefox DevTools MCP bridge started.")
    except Exception as e:
        print(f"[Daemon] Failed to start Firefox DevTools MCP subprocess: {e}")

app = FastAPI()

@app.on_event("startup")
def startup_event():
    start_firefox_mcp()

class QueryRequest(BaseModel):
    query: str
    task_id: str

class FileRedirector:
    def __init__(self, log_path):
        self.log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def __enter__(self):
        sys.stdout = self
        sys.stderr = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.stdout
        sys.stderr = self.stderr
        self.log_file.close()

    def write(self, s):
        self.stdout.write(s)
        self.stdout.flush()
        self.log_file.write(s)
        self.log_file.flush()

    def flush(self):
        self.stdout.flush()
        self.log_file.flush()

def run_agent_bg(task_id: str, query: str, log_path: Path, done_path: Path):
    try:
        from hermes_cli.oneshot import _run_agent
        
        task_handler.set_task_context(task_id, str(log_path))
        
        # Set the same environment variables oneshot mode expects
        os.environ["HERMES_YOLO_MODE"] = "1"
        os.environ["HERMES_ACCEPT_HOOKS"] = "1"
        
        # Ensure HERMES_HOME points to the internal .hermes directory
        os.environ["HERMES_HOME"] = str(project_dir / ".hermes")
        
        def daemon_clarify_callback(question: str, choices=None) -> str:
            # Write to clarify file
            clarify_data = {
                "question": question,
                "choices": choices
            }
            clarify_file = log_path.parent / f"{task_id}.clarify"
            try:
                import tempfile
                with tempfile.NamedTemporaryFile('w', dir=str(log_path.parent), delete=False, encoding="utf-8") as tf:
                    json.dump(clarify_data, tf)
                    temp_name = tf.name
                os.replace(temp_name, str(clarify_file))
                print(f"[Daemon] [Clarify] Wrote clarification request to {clarify_file}: {question}")
            except Exception as w_err:
                print(f"[Daemon] [Clarify] Error writing clarify request: {w_err}")
                return f"[clarify error writing request: {w_err}]"
                
            response_file = log_path.parent / f"{task_id}.clarify_response"
            
            import time
            timeout = 180.0  # 3 minutes timeout for user input
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if response_file.exists():
                    try:
                        with open(response_file, "r", encoding="utf-8") as rf:
                            resp = json.load(rf)
                        # Clean up files
                        try:
                            response_file.unlink()
                        except Exception:
                            pass
                        try:
                            clarify_file.unlink()
                        except Exception:
                            pass
                        user_ans = resp.get("response", "")
                        print(f"[Daemon] [Clarify] Received user response: {user_ans}")
                        return user_ans
                    except Exception as e:
                        # might be writing, wait
                        time.sleep(0.5)
                        continue
                time.sleep(0.5)
            
            # Timeout cleanup
            try:
                clarify_file.unlink()
            except Exception:
                pass
            print(f"[Daemon] [Clarify] Clarification timed out after {timeout} seconds.")
            return "[clarify timeout: User did not respond in time. Pick the best option using your own judgment.]"

        with FileRedirector(log_path):
            response, result = _run_agent(query, clarify_callback=daemon_clarify_callback)
            
        with open(done_path, "w", encoding="utf-8") as f:
            json.dump({"response": response, "status": "success"}, f)
            
    except Exception as e:
        import traceback
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\nError running agent: {str(e)}\n")
            traceback.print_exc(file=f)
        with open(done_path, "w", encoding="utf-8") as f:
            json.dump({"response": "", "status": "error", "error": str(e)}, f)
    finally:
        task_handler.clear_task_context()
        with active_tasks_lock:
            active_tasks.discard(task_id)

@app.post("/query")
async def handle_query(req: QueryRequest):
    logs_dir = project_dir / ".hermes" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    log_path = logs_dir / f"{req.task_id}.log"
    done_path = logs_dir / f"{req.task_id}.done"
    
    if log_path.exists():
        try:
            log_path.unlink()
        except Exception:
            pass
    if done_path.exists():
        try:
            done_path.unlink()
        except Exception:
            pass
            
    with active_tasks_lock:
        active_tasks.add(req.task_id)
            
    t = threading.Thread(
        target=run_agent_bg,
        args=(req.task_id, req.query, log_path, done_path),
        daemon=True
    )
    t.start()
    
    return {"status": "started"}

@app.get("/tasks")
async def get_active_tasks():
    with active_tasks_lock:
        return {"active_tasks": list(active_tasks)}

@app.post("/firefox/mcp")
async def handle_firefox_mcp(request: Request):
    global firefox_proc
    
    if firefox_proc is None or firefox_proc.poll() is not None:
        print("[Daemon] Firefox MCP process not running. Restarting...")
        start_firefox_mcp()
        
    try:
        req_body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
        
    req_id = req_body.get("id")
    if req_id is None:
        import uuid
        req_id = str(uuid.uuid4())
        req_body["id"] = req_id
        
    resp_queue = queue.Queue()
    firefox_active_requests[req_id] = resp_queue
    
    try:
        with firefox_lock:
            if firefox_proc and firefox_proc.stdin:
                payload = json.dumps(req_body) + "\n"
                firefox_proc.stdin.write(payload.encode('utf-8'))
                firefox_proc.stdin.flush()
            else:
                raise RuntimeError("Firefox MCP process stdin not available")
                
        resp_data = resp_queue.get(timeout=30.0)
        return resp_data
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Bridge error: {str(e)}"},
            "id": req_id
        }
    finally:
        firefox_active_requests.pop(req_id, None)

@app.post("/shutdown")
async def shutdown():
    global firefox_proc
    if firefox_proc:
        try:
            firefox_proc.terminate()
            firefox_proc.wait(timeout=2)
        except Exception:
            pass
            
    def stop_server():
        import time
        time.sleep(0.5)
        os._exit(0)
    
    import threading
    threading.Thread(target=stop_server, daemon=True).start()
    return {"status": "shutting down"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8085)
