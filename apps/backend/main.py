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
    allow_origins=["*"],  # For dev, update this in production
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


def parse_structured_response(result: dict) -> dict:
    """
    Parse the Databricks agent response into structured sections:
    - answer: The final agent message
    - steps: List of intermediate tool calls / reasoning steps
    - citations: List of RAG citations (if any)
    """
    if "error" in result:
        return {"answer": f"Error: {result['error']}", "steps": [], "citations": []}

    raw = result.get("raw_data", {})
    preds = raw.get("predictions", {})
    output_items = []

    if isinstance(preds, dict) and "output" in preds:
        output_items = preds["output"]
    elif isinstance(preds, list):
        output_items = preds

    answer = ""
    steps = []
    citations = []
    step_num = 1

    # print("raw:", raw)
    # print("preds:", preds)
    # print("output_items", output_items)

    if not output_items:
        return {
            "answer": result.get("answer", str(raw)),
            "steps": [],
            "citations": []
        }

    for item in output_items:
        if not isinstance(item, dict):
            continue

        item_type = item.get("type", "")

        # ── Tool / Function Call ──
        if item_type == "function_call":
            tool_name = item.get("name", "unknown_tool")
            display_name = tool_name.replace("workspace__default__", "").replace("_", " ").title()
            try:
                args = json.loads(item.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                args = item.get("arguments", "{}")

            steps.append({
                "step_number": step_num,
                "type": "tool_call",
                "icon": "🔧",
                "title": f"Tool Call → {display_name}",
                "content": args if isinstance(args, dict) else {"raw": args},
            })
            step_num += 1

        # ── Tool / Function Call Output ──
        elif item_type == "function_call_output":
            try:
                output_data = json.loads(item.get("output", "{}"))
            except (json.JSONDecodeError, TypeError):
                output_data = item.get("output", "")

            step_content = {}
            if isinstance(output_data, dict):
                if "sql_query" in output_data:
                    step_content["sql_query"] = output_data["sql_query"]
                if "results" in output_data:
                    step_content["results"] = output_data["results"]
                if "answer" in output_data:
                    step_content["tool_answer"] = output_data["answer"]
                if "num_rows" in output_data:
                    step_content["num_rows"] = output_data["num_rows"]
                if not step_content:
                    step_content = output_data
            else:
                step_content = {"raw": str(output_data)}

            steps.append({
                "step_number": step_num,
                "type": "tool_result",
                "icon": "📊",
                "title": "Tool Result",
                "content": step_content,
            })
            step_num += 1

        # ── Reasoning ──
        elif item_type == "reasoning":
            summaries = item.get("summary", [])
            reasoning_texts = []
            for s in summaries:
                if isinstance(s, dict) and "text" in s:
                    reasoning_texts.append(s["text"])
                elif isinstance(s, str):
                    reasoning_texts.append(s)
            if reasoning_texts:
                steps.append({
                    "step_number": step_num,
                    "type": "reasoning",
                    "icon": "🧠",
                    "title": "Reasoning",
                    "content": {"thoughts": reasoning_texts},
                })
                step_num += 1

        # ── Final Message ──
        elif item_type == "message":
            content = item.get("content", "")
            if isinstance(content, str):
                answer = content
            elif isinstance(content, list):
                texts = []
                for sub in content:
                    if isinstance(sub, dict) and "text" in sub:
                        texts.append(sub["text"])
                    elif isinstance(sub, str):
                        texts.append(sub)
                answer = "\n".join(texts)
            else:
                answer = str(content)

            # Extract citations from the message content metadata
            attachments = item.get("attachments", [])
            for att in attachments:
                if isinstance(att, dict):
                    citations.append({
                        "source": att.get("title", att.get("name", "Unknown source")),
                        "content": att.get("content", att.get("text", "")),
                        "url": att.get("url", ""),
                    })
    
    # Also check for citations at the top-level predictions
    if isinstance(preds, dict):
        raw_citations = preds.get("citations", [])
        if isinstance(raw_citations, list):
            for c in raw_citations:
                if isinstance(c, dict):
                    citations.append({
                        "source": c.get("title", c.get("doc_uri", c.get("source", "Unknown source"))),
                        "content": c.get("content", c.get("text", c.get("page_content", ""))),
                        "url": c.get("doc_uri", c.get("url", "")),
                    })

    if not answer:
        answer = result.get("answer", str(raw))

    import re
    extracted_citations = []
    mappable_facilities = []
    
    # Extract CITATIONS_JSON
    citations_match = re.search(r'CITATIONS_JSON_START(.*?)CITATIONS_JSON_END', answer, re.DOTALL)
    if citations_match:
        try:
            extracted_citations = json.loads(citations_match.group(1).strip())
        except Exception:
            pass
        answer = re.sub(r'CITATIONS_JSON_START.*?CITATIONS_JSON_END', '', answer, flags=re.DOTALL)
        
    # Extract MAPPABLE_JSON
    mappable_match = re.search(r'MAPPABLE_JSON_START(.*?)MAPPABLE_JSON_END', answer, re.DOTALL)
    if mappable_match:
        try:
            mappable_facilities = json.loads(mappable_match.group(1).strip())
        except Exception:
            pass
        answer = re.sub(r'MAPPABLE_JSON_START.*?MAPPABLE_JSON_END', '', answer, flags=re.DOTALL)

    return {
        "answer": answer.strip(),
        "steps": steps,
        "citations": citations,
        "extracted_citations": extracted_citations,
        "mappable_facilities": mappable_facilities
    }


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

        if "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
            answer = data["choices"][0].get("message", {}).get("content", "")
        elif "predictions" in data:
            preds = data["predictions"]
            extracted = False

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

@app.get("/")
def read_root():
    return {"status": "healthy"}

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    result = chat_with_agent(request.message, request.session_id)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    structured = parse_structured_response(result)

    return structured
