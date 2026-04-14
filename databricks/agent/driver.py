# Databricks notebook source
# MAGIC %md
# MAGIC #Tool-calling Agent
# MAGIC
# MAGIC This is an auto-generated notebook created by an AI playground export. In this notebook, you will:
# MAGIC - Author a tool-calling [MLflow's `ResponsesAgent`](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.pyfunc.html#mlflow.pyfunc.ResponsesAgent) that uses the OpenAI client
# MAGIC - Manually test the agent's output
# MAGIC - Evaluate the agent with Mosaic AI Agent Evaluation
# MAGIC - Log and deploy the agent
# MAGIC
# MAGIC This notebook should be run on serverless or a cluster with DBR<17.
# MAGIC
# MAGIC  **_NOTE:_**  This notebook uses the OpenAI SDK, but AI Agent Framework is compatible with any agent authoring framework, including LlamaIndex or LangGraph. To learn more, see the [Authoring Agents](https://docs.databricks.com/generative-ai/agent-framework/author-agent) Databricks documentation.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC - Address all `TODO`s in this notebook.

# COMMAND ----------

# MAGIC %pip install -U -qqqq backoff databricks-openai uv databricks-agents mlflow-skinny[databricks]
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md ## Define the agent in code
# MAGIC Below we define our agent code in a single cell, enabling us to easily write it to a local Python file for subsequent logging and deployment using the `%%writefile` magic command.
# MAGIC
# MAGIC For more examples of tools to add to your agent, see [docs](https://docs.databricks.com/generative-ai/agent-framework/agent-tool.html).

# COMMAND ----------

# MAGIC %%writefile agent.py
# MAGIC import json
# MAGIC from typing import Any, Callable, Generator, Optional
# MAGIC from uuid import uuid4
# MAGIC import warnings
# MAGIC
# MAGIC import backoff
# MAGIC import mlflow
# MAGIC import openai
# MAGIC from databricks.sdk import WorkspaceClient
# MAGIC from databricks_openai import UCFunctionToolkit, VectorSearchRetrieverTool
# MAGIC from mlflow.entities import SpanType
# MAGIC from mlflow.pyfunc import ResponsesAgent
# MAGIC from mlflow.types.responses import (
# MAGIC     ResponsesAgentRequest,
# MAGIC     ResponsesAgentResponse,
# MAGIC     ResponsesAgentStreamEvent,
# MAGIC     output_to_responses_items_stream,
# MAGIC     to_chat_completions_input,
# MAGIC )
# MAGIC from openai import OpenAI
# MAGIC from pydantic import BaseModel
# MAGIC from unitycatalog.ai.core.base import get_uc_function_client
# MAGIC
# MAGIC ############################################
# MAGIC # Define your LLM endpoint and system prompt
# MAGIC ############################################
# MAGIC
# MAGIC # LLM_ENDPOINT_NAME = "databricks-gpt-oss-20b"
# MAGIC LLM_ENDPOINT_NAME = "databricks-meta-llama-3-3-70b-instruct"
# MAGIC
# MAGIC SYSTEM_PROMPT = """You are a medical facility intelligence agent for the Virtue Foundation, 
# MAGIC supporting NGO planners, healthcare coordinators, and researchers working to improve 
# MAGIC healthcare access across Ghana.
# MAGIC
# MAGIC You have access to a database of approximately 750 healthcare facilities in Ghana 
# MAGIC including hospitals, clinics, pharmacies, and specialty centers.
# MAGIC
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC TOOLS AVAILABLE
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC
# MAGIC 1. vector_search(question, location)
# MAGIC    USE FOR: semantic/capability questions
# MAGIC    - "which hospitals have ICU beds"
# MAGIC    - "find facilities with dialysis treatment"
# MAGIC    - "what equipment does X hospital have"
# MAGIC    - "hospitals with emergency obstetric care"
# MAGIC    DO NOT USE FOR: counting, filtering by numbers, aggregations
# MAGIC
# MAGIC 2. sql_query(question)
# MAGIC    USE FOR: structured data questions
# MAGIC    - Counting: "how many hospitals in Accra"
# MAGIC    - Filtering: "list public hospitals in Ashanti with >50 beds"
# MAGIC    - Ranking: "which region has most facilities"
# MAGIC    - Aggregations: "average doctor count by region"
# MAGIC    - Anomaly: "facilities with specialties but zero doctors"
# MAGIC    CAN CALL MULTIPLE TIMES with different sub-questions to build analysis
# MAGIC    CRITICAL: Whenever your query returns a list of specific facilities, you MUST include `lat` and `lon` in your SELECT statement so they can be mapped.
# MAGIC
# MAGIC 3. get_facility(name)
# MAGIC    USE FOR: full details on one specific named facility
# MAGIC    - After vector_search returns a facility name you need to verify
# MAGIC    - Getting exact lat/lon for a specific facility
# MAGIC    - Cross-referencing a facility's structured data against its claims
# MAGIC    CALL AFTER vector_search when you need structured data on a specific result
# MAGIC
# MAGIC 4. external_data(data_type, region)
# MAGIC    USE FOR: reference data not in the facilities database
# MAGIC    - data_type="population"      → Ghana region populations (2021 census)
# MAGIC    - data_type="area"            → Region area in km²
# MAGIC    - data_type="capital"         → Regional capital + GPS coordinates
# MAGIC    - data_type="who_standards"   → WHO minimum healthcare benchmarks
# MAGIC    - data_type="derived_metrics" → Pre-calculated hospitals/doctors needed per WHO
# MAGIC    - data_type="all_regions"     → Everything for all 16 regions
# MAGIC    ALWAYS CALL THIS before doing per-capita calculations
# MAGIC    CALL THIS to get coordinates of regional capitals for geospatial queries
# MAGIC
# MAGIC 5. find_nearby_facilities(center_lat, center_lon, radius_km, condition, facility_type)
# MAGIC    USE FOR: proximity and accessibility questions
# MAGIC    - "hospitals within 100km of Accra"
# MAGIC    - "facilities treating dialysis near Tamale"
# MAGIC    - "how many hospitals within X km of Y"
# MAGIC    GET coordinates first using external_data("capital") or get_facility()
# MAGIC    THEN call this with those coordinates
# MAGIC
# MAGIC 6. find_cold_spots(procedure_or_capability, coverage_radius_km)
# MAGIC    USE FOR: geographic gap and desert analysis
# MAGIC    - "cold spots for surgery within 100km"
# MAGIC    - "regions without emergency care access"
# MAGIC    - "where is cardiology absent within 50km"
# MAGIC    - "largest geographic gaps for [procedure]"
# MAGIC    RETURNS regions ranked by population affected (most critical first)
# MAGIC
# MAGIC 7. analyze_anomalies(analysis_type, location, min_score)
# MAGIC
# MAGIC    USE WHEN: anomaly detection, data credibility, suspicious facilities,
# MAGIC              things that don't add up, correlated features that don't match
# MAGIC
# MAGIC    CRITICAL — choose the right analysis_type:
# MAGIC
# MAGIC    "unrealistic_claims"
# MAGIC    → USE FOR: "facilities claiming too many procedures relative to size"
# MAGIC               "high breadth of procedures with minimal infrastructure"
# MAGIC               "inflated claims"
# MAGIC    → RETURNS: list of specific facilities with flags
# MAGIC
# MAGIC    "infrastructure_mismatch"
# MAGIC    → USE FOR: "surgery claims but no equipment"
# MAGIC               "imaging claims but no equipment"
# MAGIC               "ICU claims without support"
# MAGIC               "high-stakes claims with no supporting signals"
# MAGIC    → RETURNS: list of specific facilities with flags
# MAGIC
# MAGIC    "pattern_mismatch"
# MAGIC    → USE FOR: "things that shouldn't move together"
# MAGIC               "abnormal patterns where correlated features don't match"
# MAGIC               "facilities where expected correlations break down"
# MAGIC               "highly specialized claims with no supporting signals"
# MAGIC               "specialty breadth without clinical evidence"
# MAGIC    → RETURNS: list of specific facilities with named patterns
# MAGIC               e.g. "Imaging claim without equipment", 
# MAGIC                    "Specialty-capability misalignment"
# MAGIC    → USE THIS instead of "correlation" when user wants SPECIFIC FACILITIES
# MAGIC
# MAGIC    "correlation"
# MAGIC    → USE FOR: "what characteristics move together across facility types"
# MAGIC               "which facility type has the biggest gaps on average"
# MAGIC               "systemic patterns by category"
# MAGIC    → RETURNS: aggregate statistics by facility type — NOT individual facilities
# MAGIC    → DO NOT use this when user wants a list of specific facilities
# MAGIC
# MAGIC    "procedure_concentration"
# MAGIC    → USE FOR: "which procedures depend on very few facilities"
# MAGIC               "how concentrated is surgical/ICU/imaging capability"
# MAGIC               "scarcity of high-complexity procedures"
# MAGIC    → RETURNS: count of facilities claiming each capability + how many have no equipment
# MAGIC
# MAGIC    "all"
# MAGIC    → USE FOR: broad sweep, "find all anomalies", "full analysis"
# MAGIC    → RETURNS: all five analyses combined
# MAGIC
# MAGIC    ROUTING GUIDE:
# MAGIC    "list of suspicious facilities"          → unrealistic_claims or infrastructure_mismatch
# MAGIC    "things that shouldn't move together"    → pattern_mismatch
# MAGIC    "abnormal correlation patterns"          → pattern_mismatch
# MAGIC    "what moves together by facility type"   → correlation
# MAGIC    "how concentrated is X procedure"        → procedure_concentration
# MAGIC
# MAGIC    AFTER calling analyze_anomalies with pattern_mismatch or unrealistic_claims:
# MAGIC    - List specific facility names from the result
# MAGIC    - State each facility's primary pattern in plain English
# MAGIC    - Mention anomaly_score and completeness_score for context
# MAGIC    - Note that scores rely on specialty/capability/equipment signals
# MAGIC      since doctors and capacity are unknown for 99%+ of facilities
# MAGIC
# MAGIC
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC GHANA CONTEXT
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC
# MAGIC Ghana has 16 regions. Most underserved (historically):
# MAGIC Upper East, Upper West, North East, Savannah, Northern Region.
# MAGIC
# MAGIC WHO minimum standards:
# MAGIC - 1 physician per 1,000 people
# MAGIC - 1 hospital bed per 1,000 people  
# MAGIC - 1 hospital per 100,000 people
# MAGIC
# MAGIC Ghana average physician density: ~0.17 per 1,000 (well below WHO minimum).
# MAGIC When analyzing coverage, always compare against WHO standards.
# MAGIC
# MAGIC DATA QUALITY NOTES — critical for accurate answers:
# MAGIC - numberDoctors = 0 means DATA UNKNOWN, not zero doctors
# MAGIC - capacity = 0 means DATA UNKNOWN, not zero beds
# MAGIC - Facilities with no procedures/equipment listed may have incomplete data
# MAGIC - Some capability entries contain web-scraped noise (addresses, phone numbers)
# MAGIC   rather than real clinical capabilities — treat with appropriate skepticism
# MAGIC
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC REASONING APPROACH
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC
# MAGIC Follow ReAct pattern for complex questions:
# MAGIC THINK → which tools do I need and in what order?
# MAGIC ACT   → call the tool(s)
# MAGIC OBSERVE → what did I learn? Is it enough?
# MAGIC REPEAT → if more information needed, call more tools
# MAGIC ANSWER → synthesize all findings
# MAGIC
# MAGIC Simple questions (single facility lookup, simple count):
# MAGIC → call one tool, answer directly
# MAGIC
# MAGIC Complex questions (medical deserts, per-capita analysis, anomaly detection):
# MAGIC → call multiple tools, reason across results, then answer
# MAGIC
# MAGIC MULTI-TOOL PATTERNS:
# MAGIC
# MAGIC "Which regions are underserved relative to population?"
# MAGIC → sql_query (facility counts per region)
# MAGIC → external_data("derived_metrics") (WHO benchmarks per region)
# MAGIC → synthesize: compare actual vs needed
# MAGIC
# MAGIC "Nearest hospital with surgery to Tamale?"
# MAGIC → external_data("capital", "Northern Region") (get Tamale coordinates)
# MAGIC → find_nearby_fac━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC OUTPUT FORMAT — FOLLOW THIS EXACTLY
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC
# MAGIC Structure EVERY response like this:
# MAGIC
# MAGIC **Answer:** [Direct answer to the question]
# MAGIC
# MAGIC **Key findings:**
# MAGIC - [Specific fact with facility name and location]
# MAGIC - [Specific fact with facility name and location]
# MAGIC
# MAGIC **Medical context:** [Clinical significance — WHO comparison if relevant]
# MAGIC
# MAGIC **Data sources:** [Which tools were called]
# MAGIC
# MAGIC **Limitations:** [Data gaps or caveats]
# MAGIC
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC CITATION FORMAT — MANDATORY WHEN VECTOR SEARCH IS USED
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC
# MAGIC When vector_search is called, you MUST end your response with this exact block.
# MAGIC Copy the facility data directly from the tool result — do not paraphrase or omit.
# MAGIC
# MAGIC CITATIONS_JSON_START
# MAGIC [
# MAGIC   {
# MAGIC     "rank": 1,
# MAGIC     "id": "<facility id>",
# MAGIC     "name": "<facility name>",
# MAGIC     "facility_type": "<type>",
# MAGIC     "city": "<city>",
# MAGIC     "region": "<region>",
# MAGIC     "lat": <lat or null>,
# MAGIC     "lon": <lon or null>,
# MAGIC     "has_location": <true or false>,
# MAGIC     "relevance_score": <score>
# MAGIC   }
# MAGIC ]
# MAGIC CITATIONS_JSON_END
# MAGIC
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC FACILITY MAPPING
# MAGIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAGIC
# MAGIC Whenever your response identifies specific facilities — whether you used vector_search, sql_query, get_facility, or find_nearby_facilities, or analyze_anomalies — you MUST end your response with this JSON block:
# MAGIC
# MAGIC MAPPABLE_JSON_START
# MAGIC [
# MAGIC   {
# MAGIC     "name": "<facility name>",
# MAGIC     "city": "<city>",
# MAGIC     "region": "<region>",
# MAGIC     "facility_type": "<type>",
# MAGIC     "lat": <lat>,
# MAGIC     "lon": <lon>
# MAGIC   }
# MAGIC ]
# MAGIC MAPPABLE_JSON_END
# MAGIC
# MAGIC Rules for MAPPABLE list:
# MAGIC - Only include facilities where has_location = true (lat and lon are NOT null).
# MAGIC - Only include facilities that are DIRECTLY RELEVANT to the answer.
# MAGIC - If the answer is about hospitals with ICU in Accra, only include those specific hospitals.
# MAGIC - If no facilities have GPS coordinates, or if you only did a generic count (e.g., "There are 50 hospitals"), output an empty list: []
# MAGIC
# MAGIC Never skip these blocks when vector_search was called.
# MAGIC If vector_search was NOT called, omit both blocks entirely.
# MAGIC
# MAGIC Keep answers concise but complete. Never make up data — if a tool returns no results, 
# MAGIC say so clearly and explain what that means.
# MAGIC """
# MAGIC
# MAGIC
# MAGIC ###############################################################################
# MAGIC ## Define tools for your agent, enabling it to retrieve data or take actions
# MAGIC ## beyond text generation
# MAGIC ## To create and see usage examples of more tools, see
# MAGIC ## https://docs.databricks.com/generative-ai/agent-framework/agent-tool.html
# MAGIC ###############################################################################
# MAGIC class ToolInfo(BaseModel):
# MAGIC     """
# MAGIC     Class representing a tool for the agent.
# MAGIC     - "name" (str): The name of the tool.
# MAGIC     - "spec" (dict): JSON description of the tool (matches OpenAI Responses format)
# MAGIC     - "exec_fn" (Callable): Function that implements the tool logic
# MAGIC     """
# MAGIC
# MAGIC     name: str
# MAGIC     spec: dict
# MAGIC     exec_fn: Callable
# MAGIC
# MAGIC
# MAGIC def create_tool_info(tool_spec, exec_fn_param=None):
# MAGIC     tool_spec["function"].pop("strict", None)
# MAGIC     tool_name = tool_spec["function"]["name"]
# MAGIC     udf_name = tool_name.replace("__", ".")
# MAGIC
# MAGIC     def get_param_type(param_info: dict) -> str:
# MAGIC         """Extract the primary non-null type from a JSON schema param, including anyOf."""
# MAGIC         if "type" in param_info:
# MAGIC             return param_info["type"]
# MAGIC         if "anyOf" in param_info:
# MAGIC             for sub in param_info["anyOf"]:
# MAGIC                 if sub.get("type") not in ("null", None):
# MAGIC                     return sub["type"]
# MAGIC         return "string"
# MAGIC
# MAGIC     def cast_value(raw_value, param_type: str):
# MAGIC         """Cast raw_value to the correct Python type for UC."""
# MAGIC         if raw_value is None or raw_value == "":
# MAGIC             return {"string": "", "integer": 0, "number": 0.0, "boolean": False}.get(param_type, "")
# MAGIC         try:
# MAGIC             if param_type == "integer":
# MAGIC                 return int(str(raw_value).split(".")[0])
# MAGIC             elif param_type == "number":
# MAGIC                 return float(raw_value)
# MAGIC             elif param_type == "boolean":
# MAGIC                 return raw_value.lower() == "true" if isinstance(raw_value, str) else bool(raw_value)
# MAGIC             else:
# MAGIC                 return str(raw_value)
# MAGIC         except (ValueError, TypeError):
# MAGIC             return {"string": "", "integer": 0, "number": 0.0, "boolean": False}.get(param_type, "")
# MAGIC
# MAGIC     def exec_fn(**kwargs):
# MAGIC         properties = tool_spec.get("function", {}).get("parameters", {}).get("properties", {})
# MAGIC         cleaned_kwargs = {}
# MAGIC
# MAGIC         # Cast all LLM-provided values
# MAGIC         for param_name, raw_value in kwargs.items():
# MAGIC             param_info = properties.get(param_name, {})
# MAGIC             param_type = get_param_type(param_info)
# MAGIC             cleaned_kwargs[param_name] = cast_value(raw_value, param_type)
# MAGIC
# MAGIC         # Fill missing params with typed defaults
# MAGIC         for param_name, param_info in properties.items():
# MAGIC             if param_name not in cleaned_kwargs:
# MAGIC                 param_type = get_param_type(param_info)
# MAGIC                 cleaned_kwargs[param_name] = cast_value(None, param_type)
# MAGIC
# MAGIC         function_result = uc_function_client.execute_function(udf_name, cleaned_kwargs)
# MAGIC         return function_result.error if function_result.error is not None else function_result.value
# MAGIC
# MAGIC     return ToolInfo(name=tool_name, spec=tool_spec, exec_fn=exec_fn_param or exec_fn)
# MAGIC
# MAGIC TOOL_INFOS = []
# MAGIC
# MAGIC # You can use UDFs in Unity Catalog as agent tools
# MAGIC UC_TOOL_NAMES = [
# MAGIC     "workspace.default.vector_search", 
# MAGIC     "workspace.default.sql_query", 
# MAGIC     "workspace.default.get_facility", 
# MAGIC     "workspace.default.external_data", 
# MAGIC     "workspace.default.find_cold_spots", 
# MAGIC     "workspace.default.find_nearby_facilities", 
# MAGIC     "workspace.default.analyze_anomalies"
# MAGIC     ]
# MAGIC
# MAGIC
# MAGIC uc_toolkit = UCFunctionToolkit(function_names=UC_TOOL_NAMES)
# MAGIC uc_function_client = get_uc_function_client()
# MAGIC for tool_spec in uc_toolkit.tools:
# MAGIC     TOOL_INFOS.append(create_tool_info(tool_spec))
# MAGIC
# MAGIC
# MAGIC VECTOR_SEARCH_TOOLS = []
# MAGIC for vs_tool in VECTOR_SEARCH_TOOLS:
# MAGIC     TOOL_INFOS.append(create_tool_info(vs_tool.tool, vs_tool.execute))
# MAGIC
# MAGIC
# MAGIC
# MAGIC class ToolCallingAgent(ResponsesAgent):
# MAGIC     """
# MAGIC     Class representing a tool-calling Agent
# MAGIC     """
# MAGIC
# MAGIC     def __init__(self, llm_endpoint: str, tools: list[ToolInfo]):
# MAGIC         """Initializes the ToolCallingAgent with tools."""
# MAGIC         self.llm_endpoint = llm_endpoint
# MAGIC         self.workspace_client = WorkspaceClient()
# MAGIC         self.model_serving_client: OpenAI = (
# MAGIC             self.workspace_client.serving_endpoints.get_open_ai_client()
# MAGIC         )
# MAGIC         self._tools_dict = {tool.name: tool for tool in tools}
# MAGIC
# MAGIC     def get_tool_specs(self) -> list[dict]:
# MAGIC         """Returns tool specifications in the format OpenAI expects."""
# MAGIC         return [tool_info.spec for tool_info in self._tools_dict.values()]
# MAGIC     
# MAGIC     @mlflow.trace(span_type=SpanType.TOOL)
# MAGIC     def execute_tool(self, tool_name: str, args: dict) -> Any:
# MAGIC         """Executes the specified tool with the given arguments."""
# MAGIC         if tool_name not in self._tools_dict:
# MAGIC             for registered_name in self._tools_dict:
# MAGIC                 if tool_name.startswith(registered_name):
# MAGIC                     tool_name = registered_name
# MAGIC                     break
# MAGIC             else:
# MAGIC                 raise KeyError(f"Unknown tool: {tool_name}")
# MAGIC         return self._tools_dict[tool_name].exec_fn(**args)
# MAGIC
# MAGIC     def _get_msg_attr(self, msg: Any, attr: str, default: Any = None) -> Any:
# MAGIC         """Helper to get attribute from either dict or Pydantic object."""
# MAGIC         if isinstance(msg, dict):
# MAGIC             return msg.get(attr, default)
# MAGIC         else:
# MAGIC             return getattr(msg, attr, default)
# MAGIC
# MAGIC     def call_llm(self, messages: list[dict[str, Any]]) -> Generator[dict[str, Any], None, None]:
# MAGIC         with warnings.catch_warnings():
# MAGIC             warnings.filterwarnings("ignore", message="PydanticSerializationUnexpectedValue")
# MAGIC             for chunk in self.model_serving_client.chat.completions.create(
# MAGIC                 model=self.llm_endpoint,
# MAGIC                 messages=to_chat_completions_input(messages),
# MAGIC                 tools=self.get_tool_specs(),
# MAGIC                 stream=True,
# MAGIC             ):
# MAGIC                 chunk_dict = chunk.to_dict()
# MAGIC                 if len(chunk_dict.get("choices", [])) > 0:
# MAGIC                     yield chunk_dict
# MAGIC
# MAGIC     def handle_tool_call(
# MAGIC         self,
# MAGIC         tool_call: dict[str, Any],
# MAGIC         messages: list[dict[str, Any]],
# MAGIC     ) -> ResponsesAgentStreamEvent:
# MAGIC         """
# MAGIC         Execute tool calls, add them to the running message history, and return a ResponsesStreamEvent w/ tool output
# MAGIC         """
# MAGIC         try:
# MAGIC             args = json.loads(tool_call.get("arguments"))
# MAGIC         except Exception as e:
# MAGIC             args = {}
# MAGIC         result = str(self.execute_tool(tool_name=tool_call["name"], args=args))
# MAGIC
# MAGIC         tool_call_output = self.create_function_call_output_item(tool_call["call_id"], result)
# MAGIC         messages.append(tool_call_output)
# MAGIC         return ResponsesAgentStreamEvent(type="response.output_item.done", item=tool_call_output)
# MAGIC
# MAGIC     def call_and_run_tools(
# MAGIC         self,
# MAGIC         messages: list[dict[str, Any]],
# MAGIC         max_iter: int = 10,
# MAGIC     ) -> Generator[ResponsesAgentStreamEvent, None, None]:
# MAGIC         for _ in range(max_iter):
# MAGIC             last_msg = messages[-1]
# MAGIC             if self._get_msg_attr(last_msg, "role") == "assistant":
# MAGIC                 return
# MAGIC             elif self._get_msg_attr(last_msg, "type") == "function_call":
# MAGIC                 yield self.handle_tool_call(last_msg, messages)
# MAGIC             else:
# MAGIC                 yield from output_to_responses_items_stream(
# MAGIC                     chunks=self.call_llm(messages), aggregator=messages
# MAGIC                 )
# MAGIC
# MAGIC         yield ResponsesAgentStreamEvent(
# MAGIC             type="response.output_item.done",
# MAGIC             item=self.create_text_output_item("Max iterations reached. Stopping.", str(uuid4())),
# MAGIC         )
# MAGIC
# MAGIC     def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
# MAGIC         session_id = None
# MAGIC         if request.custom_inputs and "session_id" in request.custom_inputs:
# MAGIC             session_id = request.custom_inputs.get("session_id")
# MAGIC         elif request.context and request.context.conversation_id:
# MAGIC             session_id = request.context.conversation_id
# MAGIC
# MAGIC         if session_id:
# MAGIC             mlflow.update_current_trace(
# MAGIC                 metadata={
# MAGIC                     "mlflow.trace.session": session_id,
# MAGIC                 }
# MAGIC             )
# MAGIC
# MAGIC         outputs = [
# MAGIC             event.item
# MAGIC             for event in self.predict_stream(request)
# MAGIC             if event.type == "response.output_item.done"
# MAGIC         ]
# MAGIC         return ResponsesAgentResponse(output=outputs, custom_outputs=request.custom_inputs)
# MAGIC
# MAGIC     def predict_stream(self, request: ResponsesAgentRequest) -> Generator[ResponsesAgentStreamEvent, None, None]:
# MAGIC         session_id = None
# MAGIC         if request.custom_inputs and "session_id" in request.custom_inputs:
# MAGIC             session_id = request.custom_inputs.get("session_id")
# MAGIC         elif request.context and request.context.conversation_id:
# MAGIC             session_id = request.context.conversation_id
# MAGIC
# MAGIC         if session_id:
# MAGIC             mlflow.update_current_trace(
# MAGIC                 metadata={
# MAGIC                     "mlflow.trace.session": session_id,
# MAGIC                 }
# MAGIC             )
# MAGIC
# MAGIC         messages = request.input.copy()
# MAGIC         messages.insert(
# MAGIC             0,
# MAGIC             {"role": "system", "content": SYSTEM_PROMPT},
# MAGIC         )
# MAGIC         yield from self.call_and_run_tools(messages)
# MAGIC
# MAGIC
# MAGIC mlflow.openai.autolog()
# MAGIC AGENT = ToolCallingAgent(llm_endpoint=LLM_ENDPOINT_NAME, tools=TOOL_INFOS)
# MAGIC mlflow.models.set_model(AGENT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test the agent
# MAGIC
# MAGIC Interact with the agent to test its output. Since we manually traced methods within `ResponsesAgent`, you can view the trace for each step the agent takes, with any LLM calls made via the OpenAI SDK automatically traced by autologging.
# MAGIC
# MAGIC Replace this placeholder input with an appropriate domain-specific example for your agent.

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from agent import AGENT

AGENT.predict(
    {"input": [{"role": "user", "content": "Which facilities claim an unrealistic number of procedures relative to their size?"}], "custom_inputs": {"session_id": "test-session-123"}},
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Log the `agent` as an MLflow model
# MAGIC Determine Databricks resources to specify for automatic auth passthrough at deployment time
# MAGIC - **TODO**: If your Unity Catalog Function queries a [vector search index](https://docs.databricks.com/generative-ai/agent-framework/unstructured-retrieval-tools.html) or leverages [external functions](https://docs.databricks.com/generative-ai/agent-framework/external-connection-tools.html), you need to include the dependent vector search index and UC connection objects, respectively, as resources. See [docs](https://docs.databricks.com/generative-ai/agent-framework/log-agent.html#specify-resources-for-automatic-authentication-passthrough) for more details.
# MAGIC
# MAGIC Log the agent as code from the `agent.py` file. See [MLflow - Models from Code](https://mlflow.org/docs/latest/models.html#models-from-code).

# COMMAND ----------

# Determine Databricks resources to specify for automatic auth passthrough at deployment time
import mlflow
from agent import LLM_ENDPOINT_NAME, VECTOR_SEARCH_TOOLS, uc_toolkit
from mlflow.models.resources import DatabricksFunction, DatabricksServingEndpoint
from pkg_resources import get_distribution

resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT_NAME)]
for tool in VECTOR_SEARCH_TOOLS:
    resources.extend(tool.resources)
for tool in uc_toolkit.tools:
    # TODO: If the UC function includes dependencies like external connection or vector search, please include them manually.
    # See the TODO in the markdown above for more information.
    udf_name = tool.get("function", {}).get("name", "").replace("__", ".")
    resources.append(DatabricksFunction(function_name=udf_name))

input_example = {
    "input": [
        {
            "role": "user",
            "content": "hi"
        }
    ],
    "custom_inputs": {
        "session_id": "test-session"
    }
}

with mlflow.start_run():
    logged_agent_info = mlflow.pyfunc.log_model(
        name="agent",
        python_model="agent.py",
        input_example=input_example,
        pip_requirements=[
            "databricks-openai",
            "backoff",
            f"databricks-connect=={get_distribution('databricks-connect').version}",
        ],
        resources=resources,
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Perform pre-deployment validation of the agent
# MAGIC Before registering and deploying the agent, we perform pre-deployment checks via the [mlflow.models.predict()](https://mlflow.org/docs/latest/python_api/mlflow.models.html#mlflow.models.predict) API. See [documentation](https://docs.databricks.com/machine-learning/model-serving/model-serving-debug.html#validate-inputs) for details

# COMMAND ----------

mlflow.models.predict(
    model_uri=f"runs:/{logged_agent_info.run_id}/agent",
    input_data={"input": [{"role": "user", "content": "Hello!"}], "custom_inputs": {"session_id": "validation-session"}},
    env_manager="uv",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Register the model to Unity Catalog
# MAGIC
# MAGIC Update the `catalog`, `schema`, and `model_name` below to register the MLflow model to Unity Catalog.

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")

# TODO: define the catalog, schema, and model name for your UC model
catalog = "workspace"
schema = "default"
model_name = "healthcare_agent"
UC_MODEL_NAME = f"{catalog}.{schema}.{model_name}"

# Register the model to UC
print(f"Registering model to Unity Catalog as: {UC_MODEL_NAME}")
uc_registered_model_info = mlflow.register_model(
    model_uri=logged_agent_info.model_uri, 
    name=UC_MODEL_NAME
)
print("Registration Complete!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Deploy the agent

# COMMAND ----------

from databricks import agents
# NOTE: pass scale_to_zero=True to agents.deploy() to enable scale-to-zero for cost savings.
# This is not recommended for production workloads, as capacity is not guaranteed when scaled to zero.
# Scaled to zero endpoints may take extra time to respond when queried, while they scale back up.
agents.deploy(UC_MODEL_NAME, uc_registered_model_info.version, scale_to_zero=True, tags = {"endpointSource": "playground"})

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next steps
# MAGIC
# MAGIC After your agent is deployed, you can chat with it in AI playground to perform additional checks, share it with SMEs in your organization for feedback, or embed it in a production application. See [docs](https://docs.databricks.com/generative-ai/deploy-agent.html) for details
