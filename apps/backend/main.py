from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Databricks Agent Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev, update this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
AGENT_ENDPOINT = os.getenv("AGENT_ENDPOINT")

HEADERS = {
    "Authorization": f"Bearer {DATABRICKS_TOKEN}",
    "Content-Type": "application/json"
}

class ChatRequest(BaseModel):
    message: str
    session_id: str = "frontend-user-session"

def format_response(result: dict) -> str:
    # Based on format_response from agent_test_ui.py
    if "error" in result:
        return f"❌ **Error:** {result['error']}"

    raw = result.get("raw_data", {})
    preds = raw.get("predictions", {})
    output_items = []

    if isinstance(preds, dict) and "output" in preds:
        output_items = preds["output"]
    elif isinstance(preds, list):
        output_items = preds

    if not output_items:
        return result.get("answer", str(raw))

    sections = []
    step_num = 1

    for item in output_items:
        if not isinstance(item, dict):
            continue

        item_type = item.get("type", "")

        if item_type == "function_call":
            tool_name = item.get("name", "unknown_tool")
            display_name = tool_name.replace("workspace__default__", "").replace("_", " ").title()
            try:
                args = json.loads(item.get("arguments", "{}"))
                args_str = json.dumps(args, indent=2)
            except (json.JSONDecodeError, TypeError):
                args_str = item.get("arguments", "{}")

            sections.append(
                f"**Step {step_num}: 🔧 Tool Call → `{display_name}`**\n"
                f"```json\n{args_str}\n```"
            )
            step_num += 1

        elif item_type == "function_call_output":
            try:
                output_data = json.loads(item.get("output", "{}"))
            except (json.JSONDecodeError, TypeError):
                output_data = item.get("output", "")

            if isinstance(output_data, dict):
                parts = []
                if "sql_query" in output_data:
                    parts.append(f"**SQL Query:**\n```sql\n{output_data['sql_query']}\n```")
                if "results" in output_data:
                    parts.append(f"**Results:** `{json.dumps(output_data['results'])}`")
                if "answer" in output_data:
                    parts.append(f"**Tool Answer:** {output_data['answer']}")
                if "num_rows" in output_data:
                    parts.append(f"**Rows returned:** {output_data['num_rows']}")

                if not parts:
                    parts.append(f"```json\n{json.dumps(output_data, indent=2)}\n```")

                sections.append(f"**Step {step_num}: 📊 Tool Result**\n" + "\n".join(parts))
            else:
                sections.append(f"**Step {step_num}: 📊 Tool Result**\n{output_data}")
            step_num += 1

        elif item_type == "reasoning":
            summaries = item.get("summary", [])
            reasoning_texts = []
            for s in summaries:
                if isinstance(s, dict) and "text" in s:
                    reasoning_texts.append(s["text"])
                elif isinstance(s, str):
                    reasoning_texts.append(s)
            if reasoning_texts:
                reasoning_str = "\n".join(f"- {t}" for t in reasoning_texts)
                sections.append(f"**Step {step_num}: 🧠 Reasoning**\n{reasoning_str}")
                step_num += 1

        elif item_type == "message":
            content = item.get("content", "")
            if isinstance(content, str):
                final_text = content
            elif isinstance(content, list):
                texts = []
                for sub in content:
                    if isinstance(sub, dict) and "text" in sub:
                        texts.append(sub["text"])
                    elif isinstance(sub, str):
                        texts.append(sub)
                final_text = "\n".join(texts)
            else:
                final_text = str(content)

            sections.append(f"---\n### ✅ Answer\n{final_text}")

    if sections:
        return "\n\n".join(sections)

    return result.get("answer", str(raw))

def chat_with_agent(question: str, session_id: str) -> dict:
    if not AGENT_ENDPOINT:
        return {"error": "Databricks Agent Endpoint is not configured."}
    
    payload = {
        "dataframe_records": [
            {
                "input": [{"role": "user", "content": question}],
                "custom_inputs": {"session_id": session_id}
            }
        ]
    }
    
    try:
        response = requests.post(
            AGENT_ENDPOINT,
            headers=HEADERS,
            json=payload,
            timeout=180
        )
        
        if response.status_code != 200:
            if "BAD_REQUEST" in response.text or "MALFORMED_REQUEST" in response.text or "schema" in response.text.lower():
                payload_fallback = {
                    "inputs": {
                        "input": [{"role": "user", "content": question}],
                        "custom_inputs": {"session_id": session_id}
                    }
                }
                response = requests.post(
                    AGENT_ENDPOINT,
                    headers=HEADERS,
                    json=payload_fallback,
                    timeout=180
                )
                if response.status_code != 200:
                    return {"error": f"HTTP {response.status_code}: {response.text}"}
            else:
                return {"error": f"HTTP {response.status_code}: {response.text}"}

        data = response.json()
        answer = ""
        
        # Parse standard Databricks Agent response (OpenAI format or MLflow Pyfunc format)
        if "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
            answer = data["choices"][0].get("message", {}).get("content", "")
        elif "predictions" in data:
            preds = data["predictions"]
            extracted = False
            
            # Handle the specific Databricks complex nested response containing 'reasoning' and 'message'
            if isinstance(preds, dict) and "output" in preds and isinstance(preds["output"], list):
                texts = []
                for item in preds["output"]:
                    if isinstance(item, dict) and item.get("type") == "message" and "content" in item:
                        content = item["content"]
                        if isinstance(content, str):
                            texts.append(content)
                        elif isinstance(content, list):
                            for sub in content:
                                if isinstance(sub, dict) and "text" in sub:
                                    texts.append(sub["text"])
                                elif isinstance(sub, str):
                                    texts.append(sub)
                if texts:
                    answer = "\n".join(texts)
                    extracted = True
            
            if not extracted:
                if isinstance(preds, list) and len(preds) > 0:
                    pred = preds[0]
                    if isinstance(pred, dict):
                         answer = pred.get("response", pred.get("content", pred.get("answer", pred.get("output", str(pred)))))
                    else:
                         answer = str(pred)
                elif isinstance(preds, dict):
                    # If predictions is a dict (e.g., column based output like {"output": ["..."]})
                    if "output" in preds and isinstance(preds["output"], list) and len(preds["output"]) > 0:
                         answer = str(preds["output"][0])
                    elif "response" in preds and isinstance(preds["response"], list) and len(preds["response"]) > 0:
                         answer = str(preds["response"][0])
                    else:
                         answer = str(preds)
                else:
                    answer = str(preds)
        else:
            answer = str(data)
            
    except Exception as e:
        answer = f"Response Parsing Error: {str(e)}\n\nRaw Data: {data if 'data' in locals() else 'No data'}"
        return {"error": answer}

    return {
        "answer": answer,
        "raw_data": data
    }


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    result = chat_with_agent(request.message, request.session_id)
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
        
    formatted_response = format_response(result)
    
    return {
        "answer": formatted_response,
        "raw_result": result
    }

@app.get("/health")
async def health_check():
    return {
        "status": "ok", 
        "endpoint_configured": AGENT_ENDPOINT is not None,
        "token_configured": DATABRICKS_TOKEN is not None
    }
