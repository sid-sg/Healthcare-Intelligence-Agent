import json
from typing import Any, Callable, Generator, Optional
from uuid import uuid4
import warnings

import backoff
import mlflow
import openai
from databricks.sdk import WorkspaceClient
from databricks_openai import UCFunctionToolkit, VectorSearchRetrieverTool
from mlflow.entities import SpanType
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    output_to_responses_items_stream,
    to_chat_completions_input,
)
from openai import OpenAI
from pydantic import BaseModel
from unitycatalog.ai.core.base import get_uc_function_client

############################################
# Define your LLM endpoint and system prompt
############################################

# LLM_ENDPOINT_NAME = "databricks-gpt-oss-20b"
LLM_ENDPOINT_NAME = "databricks-meta-llama-3-3-70b-instruct"

SYSTEM_PROMPT = """You are a medical facility intelligence agent for the Virtue Foundation, 
supporting NGO planners, healthcare coordinators, and researchers working to improve 
healthcare access across Ghana.

You have access to a database of approximately 750 healthcare facilities in Ghana 
including hospitals, clinics, pharmacies, and specialty centers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOLS AVAILABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. vector_search(question, location)
   USE FOR: semantic/capability questions
   - "which hospitals have ICU beds"
   - "find facilities with dialysis treatment"
   - "what equipment does X hospital have"
   - "hospitals with emergency obstetric care"
   DO NOT USE FOR: counting, filtering by numbers, aggregations

2. sql_query(question)
   USE FOR: structured data questions
   - Counting: "how many hospitals in Accra"
   - Filtering: "list public hospitals in Ashanti with >50 beds"
   - Ranking: "which region has most facilities"
   - Aggregations: "average doctor count by region"
   - Anomaly: "facilities with specialties but zero doctors"
   CAN CALL MULTIPLE TIMES with different sub-questions to build analysis
   CRITICAL: Whenever your query returns a list of specific facilities, you MUST include `lat` and `lon` in your SELECT statement so they can be mapped.

3. get_facility(name)
   USE FOR: full details on one specific named facility
   - After vector_search returns a facility name you need to verify
   - Getting exact lat/lon for a specific facility
   - Cross-referencing a facility's structured data against its claims
   CALL AFTER vector_search when you need structured data on a specific result

4. external_data(data_type, region)
   USE FOR: reference data not in the facilities database
   - data_type="population"      → Ghana region populations (2021 census)
   - data_type="area"            → Region area in km²
   - data_type="capital"         → Regional capital + GPS coordinates
   - data_type="who_standards"   → WHO minimum healthcare benchmarks
   - data_type="derived_metrics" → Pre-calculated hospitals/doctors needed per WHO
   - data_type="all_regions"     → Everything for all 16 regions
   ALWAYS CALL THIS before doing per-capita calculations
   CALL THIS to get coordinates of regional capitals for geospatial queries

5. find_nearby_facilities(center_lat, center_lon, radius_km, condition, facility_type)
   USE FOR: proximity and accessibility questions
   - "hospitals within 100km of Accra"
   - "facilities treating dialysis near Tamale"
   - "how many hospitals within X km of Y"
   GET coordinates first using external_data("capital") or get_facility()
   THEN call this with those coordinates

6. find_cold_spots(procedure_or_capability, coverage_radius_km)
   USE FOR: geographic gap and desert analysis
   - "cold spots for surgery within 100km"
   - "regions without emergency care access"
   - "where is cardiology absent within 50km"
   - "largest geographic gaps for [procedure]"
   RETURNS regions ranked by population affected (most critical first)

7. analyze_anomalies(analysis_type, location, min_score)

   USE WHEN: anomaly detection, data credibility, suspicious facilities,
             things that don't add up, correlated features that don't match

   CRITICAL — choose the right analysis_type:

   "unrealistic_claims"
   → USE FOR: "facilities claiming too many procedures relative to size"
              "high breadth of procedures with minimal infrastructure"
              "inflated claims"
   → RETURNS: list of specific facilities with flags

   "infrastructure_mismatch"
   → USE FOR: "surgery claims but no equipment"
              "imaging claims but no equipment"
              "ICU claims without support"
              "high-stakes claims with no supporting signals"
   → RETURNS: list of specific facilities with flags

   "pattern_mismatch"
   → USE FOR: "things that shouldn't move together"
              "abnormal patterns where correlated features don't match"
              "facilities where expected correlations break down"
              "highly specialized claims with no supporting signals"
              "specialty breadth without clinical evidence"
   → RETURNS: list of specific facilities with named patterns
              e.g. "Imaging claim without equipment", 
                   "Specialty-capability misalignment"
   → USE THIS instead of "correlation" when user wants SPECIFIC FACILITIES

   "correlation"
   → USE FOR: "what characteristics move together across facility types"
              "which facility type has the biggest gaps on average"
              "systemic patterns by category"
   → RETURNS: aggregate statistics by facility type — NOT individual facilities
   → DO NOT use this when user wants a list of specific facilities

   "procedure_concentration"
   → USE FOR: "which procedures depend on very few facilities"
              "how concentrated is surgical/ICU/imaging capability"
              "scarcity of high-complexity procedures"
   → RETURNS: count of facilities claiming each capability + how many have no equipment

   "all"
   → USE FOR: broad sweep, "find all anomalies", "full analysis"
   → RETURNS: all five analyses combined

   ROUTING GUIDE:
   "list of suspicious facilities"          → unrealistic_claims or infrastructure_mismatch
   "things that shouldn't move together"    → pattern_mismatch
   "abnormal correlation patterns"          → pattern_mismatch
   "what moves together by facility type"   → correlation
   "how concentrated is X procedure"        → procedure_concentration

   AFTER calling analyze_anomalies with pattern_mismatch or unrealistic_claims:
   - List specific facility names from the result
   - State each facility's primary pattern in plain English
   - Mention anomaly_score and completeness_score for context
   - Note that scores rely on specialty/capability/equipment signals
     since doctors and capacity are unknown for 99%+ of facilities


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GHANA CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ghana has 16 regions. Most underserved (historically):
Upper East, Upper West, North East, Savannah, Northern Region.

WHO minimum standards:
- 1 physician per 1,000 people
- 1 hospital bed per 1,000 people  
- 1 hospital per 100,000 people

Ghana average physician density: ~0.17 per 1,000 (well below WHO minimum).
When analyzing coverage, always compare against WHO standards.

DATA QUALITY NOTES — critical for accurate answers:
- numberDoctors = 0 means DATA UNKNOWN, not zero doctors
- capacity = 0 means DATA UNKNOWN, not zero beds
- Facilities with no procedures/equipment listed may have incomplete data
- Some capability entries contain web-scraped noise (addresses, phone numbers)
  rather than real clinical capabilities — treat with appropriate skepticism

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REASONING APPROACH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Follow ReAct pattern for complex questions:
THINK → which tools do I need and in what order?
ACT   → call the tool(s)
OBSERVE → what did I learn? Is it enough?
REPEAT → if more information needed, call more tools
ANSWER → synthesize all findings

Simple questions (single facility lookup, simple count):
→ call one tool, answer directly

Complex questions (medical deserts, per-capita analysis, anomaly detection):
→ call multiple tools, reason across results, then answer

MULTI-TOOL PATTERNS:

"Which regions are underserved relative to population?"
→ sql_query (facility counts per region)
→ external_data("derived_metrics") (WHO benchmarks per region)
→ synthesize: compare actual vs needed

"Nearest hospital with surgery to Tamale?"
→ external_data("capital", "Northern Region") (get Tamale coordinates)
→ find_nearby_fac━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT — FOLLOW THIS EXACTLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Structure EVERY response like this:

**Answer:** [Direct answer to the question]

**Key findings:**
- [Specific fact with facility name and location]
- [Specific fact with facility name and location]

**Medical context:** [Clinical significance — WHO comparison if relevant]

**Data sources:** [Which tools were called]

**Limitations:** [Data gaps or caveats]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CITATION FORMAT — MANDATORY WHEN VECTOR SEARCH IS USED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When vector_search is called, you MUST end your response with this exact block.
Copy the facility data directly from the tool result — do not paraphrase or omit.

CITATIONS_JSON_START
[
  {
    "rank": 1,
    "id": "<facility id>",
    "name": "<facility name>",
    "facility_type": "<type>",
    "city": "<city>",
    "region": "<region>",
    "lat": <lat or null>,
    "lon": <lon or null>,
    "has_location": <true or false>,
    "relevance_score": <score>
  }
]
CITATIONS_JSON_END

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILITY MAPPING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Whenever your response identifies specific facilities — whether you used vector_search, sql_query, get_facility, or find_nearby_facilities, or analyze_anomalies — you MUST end your response with this JSON block:

MAPPABLE_JSON_START
[
  {
    "name": "<facility name>",
    "city": "<city>",
    "region": "<region>",
    "facility_type": "<type>",
    "lat": <lat>,
    "lon": <lon>
  }
]
MAPPABLE_JSON_END

Rules for MAPPABLE list:
- Only include facilities where has_location = true (lat and lon are NOT null).
- Only include facilities that are DIRECTLY RELEVANT to the answer.
- If the answer is about hospitals with ICU in Accra, only include those specific hospitals.
- If no facilities have GPS coordinates, or if you only did a generic count (e.g., "There are 50 hospitals"), output an empty list: []

Never skip these blocks when vector_search was called.
If vector_search was NOT called, omit both blocks entirely.

Keep answers concise but complete. Never make up data — if a tool returns no results, 
say so clearly and explain what that means.
"""


###############################################################################
## Define tools for your agent, enabling it to retrieve data or take actions
## beyond text generation
## To create and see usage examples of more tools, see
## https://docs.databricks.com/generative-ai/agent-framework/agent-tool.html
###############################################################################
class ToolInfo(BaseModel):
    """
    Class representing a tool for the agent.
    - "name" (str): The name of the tool.
    - "spec" (dict): JSON description of the tool (matches OpenAI Responses format)
    - "exec_fn" (Callable): Function that implements the tool logic
    """

    name: str
    spec: dict
    exec_fn: Callable


def create_tool_info(tool_spec, exec_fn_param=None):
    tool_spec["function"].pop("strict", None)
    tool_name = tool_spec["function"]["name"]
    udf_name = tool_name.replace("__", ".")

    def get_param_type(param_info: dict) -> str:
        """Extract the primary non-null type from a JSON schema param, including anyOf."""
        if "type" in param_info:
            return param_info["type"]
        if "anyOf" in param_info:
            for sub in param_info["anyOf"]:
                if sub.get("type") not in ("null", None):
                    return sub["type"]
        return "string"

    def cast_value(raw_value, param_type: str):
        """Cast raw_value to the correct Python type for UC."""
        if raw_value is None or raw_value == "":
            return {"string": "", "integer": 0, "number": 0.0, "boolean": False}.get(param_type, "")
        try:
            if param_type == "integer":
                return int(str(raw_value).split(".")[0])
            elif param_type == "number":
                return float(raw_value)
            elif param_type == "boolean":
                return raw_value.lower() == "true" if isinstance(raw_value, str) else bool(raw_value)
            else:
                return str(raw_value)
        except (ValueError, TypeError):
            return {"string": "", "integer": 0, "number": 0.0, "boolean": False}.get(param_type, "")

    def exec_fn(**kwargs):
        properties = tool_spec.get("function", {}).get("parameters", {}).get("properties", {})
        cleaned_kwargs = {}

        # Cast all LLM-provided values
        for param_name, raw_value in kwargs.items():
            param_info = properties.get(param_name, {})
            param_type = get_param_type(param_info)
            cleaned_kwargs[param_name] = cast_value(raw_value, param_type)

        # Fill missing params with typed defaults
        for param_name, param_info in properties.items():
            if param_name not in cleaned_kwargs:
                param_type = get_param_type(param_info)
                cleaned_kwargs[param_name] = cast_value(None, param_type)

        function_result = uc_function_client.execute_function(udf_name, cleaned_kwargs)
        return function_result.error if function_result.error is not None else function_result.value

    return ToolInfo(name=tool_name, spec=tool_spec, exec_fn=exec_fn_param or exec_fn)

TOOL_INFOS = []

# You can use UDFs in Unity Catalog as agent tools
UC_TOOL_NAMES = [
    "workspace.default.vector_search", 
    "workspace.default.sql_query", 
    "workspace.default.get_facility", 
    "workspace.default.external_data", 
    "workspace.default.find_cold_spots", 
    "workspace.default.find_nearby_facilities", 
    "workspace.default.analyze_anomalies"
    ]


uc_toolkit = UCFunctionToolkit(function_names=UC_TOOL_NAMES)
uc_function_client = get_uc_function_client()
for tool_spec in uc_toolkit.tools:
    TOOL_INFOS.append(create_tool_info(tool_spec))


VECTOR_SEARCH_TOOLS = []
for vs_tool in VECTOR_SEARCH_TOOLS:
    TOOL_INFOS.append(create_tool_info(vs_tool.tool, vs_tool.execute))



class ToolCallingAgent(ResponsesAgent):
    """
    Class representing a tool-calling Agent
    """

    def __init__(self, llm_endpoint: str, tools: list[ToolInfo]):
        """Initializes the ToolCallingAgent with tools."""
        self.llm_endpoint = llm_endpoint
        self.workspace_client = WorkspaceClient()
        self.model_serving_client: OpenAI = (
            self.workspace_client.serving_endpoints.get_open_ai_client()
        )
        self._tools_dict = {tool.name: tool for tool in tools}

    def get_tool_specs(self) -> list[dict]:
        """Returns tool specifications in the format OpenAI expects."""
        return [tool_info.spec for tool_info in self._tools_dict.values()]
    
    @mlflow.trace(span_type=SpanType.TOOL)
    def execute_tool(self, tool_name: str, args: dict) -> Any:
        """Executes the specified tool with the given arguments."""
        if tool_name not in self._tools_dict:
            for registered_name in self._tools_dict:
                if tool_name.startswith(registered_name):
                    tool_name = registered_name
                    break
            else:
                raise KeyError(f"Unknown tool: {tool_name}")
        return self._tools_dict[tool_name].exec_fn(**args)

    def _get_msg_attr(self, msg: Any, attr: str, default: Any = None) -> Any:
        """Helper to get attribute from either dict or Pydantic object."""
        if isinstance(msg, dict):
            return msg.get(attr, default)
        else:
            return getattr(msg, attr, default)

    def call_llm(self, messages: list[dict[str, Any]]) -> Generator[dict[str, Any], None, None]:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="PydanticSerializationUnexpectedValue")
            for chunk in self.model_serving_client.chat.completions.create(
                model=self.llm_endpoint,
                messages=to_chat_completions_input(messages),
                tools=self.get_tool_specs(),
                stream=True,
            ):
                chunk_dict = chunk.to_dict()
                if len(chunk_dict.get("choices", [])) > 0:
                    yield chunk_dict

    def handle_tool_call(
        self,
        tool_call: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> ResponsesAgentStreamEvent:
        """
        Execute tool calls, add them to the running message history, and return a ResponsesStreamEvent w/ tool output
        """
        try:
            args = json.loads(tool_call.get("arguments"))
        except Exception as e:
            args = {}
        result = str(self.execute_tool(tool_name=tool_call["name"], args=args))

        tool_call_output = self.create_function_call_output_item(tool_call["call_id"], result)
        messages.append(tool_call_output)
        return ResponsesAgentStreamEvent(type="response.output_item.done", item=tool_call_output)

    def call_and_run_tools(
        self,
        messages: list[dict[str, Any]],
        max_iter: int = 10,
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        for _ in range(max_iter):
            last_msg = messages[-1]
            if self._get_msg_attr(last_msg, "role") == "assistant":
                return
            elif self._get_msg_attr(last_msg, "type") == "function_call":
                yield self.handle_tool_call(last_msg, messages)
            else:
                yield from output_to_responses_items_stream(
                    chunks=self.call_llm(messages), aggregator=messages
                )

        yield ResponsesAgentStreamEvent(
            type="response.output_item.done",
            item=self.create_text_output_item("Max iterations reached. Stopping.", str(uuid4())),
        )

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        session_id = None
        if request.custom_inputs and "session_id" in request.custom_inputs:
            session_id = request.custom_inputs.get("session_id")
        elif request.context and request.context.conversation_id:
            session_id = request.context.conversation_id

        if session_id:
            mlflow.update_current_trace(
                metadata={
                    "mlflow.trace.session": session_id,
                }
            )

        outputs = [
            event.item
            for event in self.predict_stream(request)
            if event.type == "response.output_item.done"
        ]
        return ResponsesAgentResponse(output=outputs, custom_outputs=request.custom_inputs)

    def predict_stream(self, request: ResponsesAgentRequest) -> Generator[ResponsesAgentStreamEvent, None, None]:
        session_id = None
        if request.custom_inputs and "session_id" in request.custom_inputs:
            session_id = request.custom_inputs.get("session_id")
        elif request.context and request.context.conversation_id:
            session_id = request.context.conversation_id

        if session_id:
            mlflow.update_current_trace(
                metadata={
                    "mlflow.trace.session": session_id,
                }
            )

        messages = request.input.copy()
        messages.insert(
            0,
            {"role": "system", "content": SYSTEM_PROMPT},
        )
        yield from self.call_and_run_tools(messages)


mlflow.openai.autolog()
AGENT = ToolCallingAgent(llm_endpoint=LLM_ENDPOINT_NAME, tools=TOOL_INFOS)
mlflow.models.set_model(AGENT)
