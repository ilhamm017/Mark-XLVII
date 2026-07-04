import os
import sys
from pathlib import Path

# Add project root and hermes-agent to sys.path
project_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(project_dir))
sys.path.insert(0, str(project_dir / "hermes-agent"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI()

class QueryRequest(BaseModel):
    query: str

@app.post("/query")
async def handle_query(req: QueryRequest):
    # Set the same environment variables oneshot mode expects
    os.environ["HERMES_YOLO_MODE"] = "1"
    os.environ["HERMES_ACCEPT_HOOKS"] = "1"
    
    # Ensure HERMES_HOME points to the internal .hermes directory
    os.environ["HERMES_HOME"] = str(project_dir / ".hermes")
    
    try:
        from hermes_cli.oneshot import _run_agent
        import asyncio
        loop = asyncio.get_event_loop()
        
        # Run agent in executor to avoid blocking the event loop
        response, result = await loop.run_in_executor(
            None,
            lambda: _run_agent(req.query)
        )
        return {"response": response, "status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
