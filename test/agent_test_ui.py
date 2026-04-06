from dotenv import load_dotenv
import os

load_dotenv()   

DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
AGENT_ENDPOINT = os.getenv("AGENT_ENDPOINT")

HEADERS = {
    "Authorization": f"Bearer {DATABRICKS_TOKEN}",
    "Content-Type" : "application/json"
}

print(f"Endpoint URL: {AGENT_ENDPOINT}")
print(f"Token set : {'Yes' if DATABRICKS_TOKEN else 'NO - check .env file'}")



import requests
import json

def chat_with_agent(question: str) -> dict:
    # Construct payload using the agent's expected schema
    payload = {
        "dataframe_records": [
            {
                "input": [{"role": "user", "content": question}],
                "custom_inputs": {"session_id": "ui-testing-session"}
            }
        ]
    }
    
    response = requests.post(
        AGENT_ENDPOINT,
        headers = HEADERS,
        json    = payload,
        timeout = 180
    )

    if response.status_code != 200:
        # Try fallback payload format widely used by MLflow 2.x
        if "BAD_REQUEST" in response.text or "MALFORMED_REQUEST" in response.text or "schema" in response.text.lower():
            payload_fallback = {
                "inputs": {
                    "input": [{"role": "user", "content": question}],
                    "custom_inputs": {"session_id": "ui-testing-session"}
                }
            }
            response = requests.post(
                AGENT_ENDPOINT,
                headers = HEADERS,
                json    = payload_fallback,
                timeout = 180
            )
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}: {response.text}"}
        else:
            return {"error": f"HTTP {response.status_code}: {response.text}"}

    data = response.json()
    answer = ""
    try:
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
        answer = f"Response Parsing Error: {str(e)}\n\nRaw Data: {json.dumps(data, indent=2)}"

    return {
        "answer": answer,
        "raw_data": data
    }

