import os
import sys
from pathlib import Path
import threading
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Add project root and hermes-agent to sys.path
project_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(project_dir))
sys.path.insert(0, str(project_dir / "hermes-agent"))

app = FastAPI()

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
        
        # Set the same environment variables oneshot mode expects
        os.environ["HERMES_YOLO_MODE"] = "1"
        os.environ["HERMES_ACCEPT_HOOKS"] = "1"
        
        # Ensure HERMES_HOME points to the internal .hermes directory
        os.environ["HERMES_HOME"] = str(project_dir / ".hermes")
        
        with FileRedirector(log_path):
            response, result = _run_agent(query)
            
        with open(done_path, "w", encoding="utf-8") as f:
            json.dump({"response": response, "status": "success"}, f)
            
    except Exception as e:
        import traceback
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\nError running agent: {str(e)}\n")
            traceback.print_exc(file=f)
        with open(done_path, "w", encoding="utf-8") as f:
            json.dump({"response": "", "status": "error", "error": str(e)}, f)

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
            
    t = threading.Thread(
        target=run_agent_bg,
        args=(req.task_id, req.query, log_path, done_path),
        daemon=True
    )
    t.start()
    
    return {"status": "started"}

@app.post("/shutdown")
async def shutdown():
    def stop_server():
        import time
        time.sleep(0.5)
        os._exit(0)
    
    import threading
    threading.Thread(target=stop_server, daemon=True).start()
    return {"status": "shutting down"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8085)
