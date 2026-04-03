import gradio as gr
import json

print(f"Gradio version: {gr.__version__}")

def format_response(result: dict) -> str:
    """Build a rich markdown response that shows reasoning steps + final answer."""
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
        # Fallback: just return the extracted answer
        return result.get("answer", str(raw))

    sections = []
    step_num = 1

    for item in output_items:
        if not isinstance(item, dict):
            continue

        item_type = item.get("type", "")

        # ── Tool / Function Call ──
        if item_type == "function_call":
            tool_name = item.get("name", "unknown_tool")
            # Make tool name more readable
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

        # ── Tool / Function Call Output ──
        elif item_type == "function_call_output":
            try:
                output_data = json.loads(item.get("output", "{}"))
            except (json.JSONDecodeError, TypeError):
                output_data = item.get("output", "")

            if isinstance(output_data, dict):
                # Show SQL query if present
                parts = []
                if "sql_query" in output_data:
                    parts.append(f"**SQL Query:**\n```sql\n{output_data['sql_query']}\n```")
                if "results" in output_data:
                    parts.append(f"**Results:** `{json.dumps(output_data['results'])}`")
                if "answer" in output_data:
                    parts.append(f"**Tool Answer:** {output_data['answer']}")
                if "num_rows" in output_data:
                    parts.append(f"**Rows returned:** {output_data['num_rows']}")

                # If no known keys matched, show raw
                if not parts:
                    parts.append(f"```json\n{json.dumps(output_data, indent=2)}\n```")

                sections.append(
                    f"**Step {step_num}: 📊 Tool Result**\n" + "\n".join(parts)
                )
            else:
                sections.append(
                    f"**Step {step_num}: 📊 Tool Result**\n{output_data}"
                )
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
                reasoning_str = "\n".join(f"- {t}" for t in reasoning_texts)
                sections.append(
                    f"**Step {step_num}: 🧠 Reasoning**\n{reasoning_str}"
                )
                step_num += 1

        # ── Final Message ──
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

    # Fallback
    return result.get("answer", str(raw))


def respond(message, history):
    result = chat_with_agent(message)
    return format_response(result)

chatbot = gr.Chatbot(
    height=600,
    render_markdown=True,
)

with gr.Blocks(title="Healthcare Agent Assistant") as demo:
    gr.Markdown("## 🏥 Healthcare Agent UI")
    gr.Markdown("Ask questions to the Healthcare Agent powered by Databricks.")

    gr.ChatInterface(
        fn       = respond,
        chatbot  = chatbot,
        examples = [
            ["What services does 2BN Military Hospital offer?"],
            ["Which hospitals have emergency care?"],
            ["How many hospitals have cardiology?"],
            ["Find facilities with maternity services"],
        ],
        title = "",
    )

demo.launch(share=False)
