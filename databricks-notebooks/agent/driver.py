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
# MAGIC LLM_ENDPOINT_NAME = "databricks-gpt-oss-20b"
# MAGIC
# MAGIC SYSTEM_PROMPT = """"""
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
# MAGIC def create_tool_info(tool_spec, exec_fn_param: Optional[Callable] = None):
# MAGIC     tool_spec["function"].pop("strict", None)
# MAGIC     tool_name = tool_spec["function"]["name"]
# MAGIC     udf_name = tool_name.replace("__", ".")
# MAGIC
# MAGIC     # Define a wrapper that accepts kwargs for the UC tool call,
# MAGIC     # then passes them to the UC tool execution client
# MAGIC     def exec_fn(**kwargs):
# MAGIC         function_result = uc_function_client.execute_function(udf_name, kwargs)
# MAGIC         if function_result.error is not None:
# MAGIC             return function_result.error
# MAGIC         else:
# MAGIC             return function_result.value
# MAGIC     return ToolInfo(name=tool_name, spec=tool_spec, exec_fn=exec_fn_param or exec_fn)
# MAGIC
# MAGIC
# MAGIC TOOL_INFOS = []
# MAGIC
# MAGIC # You can use UDFs in Unity Catalog as agent tools
# MAGIC # TODO: Add additional tools
# MAGIC UC_TOOL_NAMES = ["workspace.default.rag_search", "workspace.default.sql_query", "workspace.default.get_facility", "workspace.default.find_facilities_near", "workspace.default.external_data", "workspace.default.find_cold_spots"]
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
# MAGIC         return self._tools_dict[tool_name].exec_fn(**args)
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
# MAGIC             if last_msg.get("role", None) == "assistant":
# MAGIC                 return
# MAGIC             elif last_msg.get("type", None) == "function_call":
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
# MAGIC         messages = to_chat_completions_input([i.model_dump() for i in request.input])
# MAGIC         if SYSTEM_PROMPT:
# MAGIC             messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
# MAGIC         yield from self.call_and_run_tools(messages=messages)
# MAGIC
# MAGIC
# MAGIC # Log the model using MLflow
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
    {"input": [{"role": "user", "content": "What services does 2BN Military Hospital"}], "custom_inputs": {"session_id": "test-session-123"}},
)

# COMMAND ----------

for chunk in AGENT.predict_stream(
    {"input": [{"role": "user", "content": "What services does 2BN Military Hospital"}], "custom_inputs": {"session_id": "test-session-123"}}
):
    print(chunk.model_dump(exclude_none=True))

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
# MAGIC ## Evaluate the agent with [Agent Evaluation](https://docs.databricks.com/mlflow3/genai/eval-monitor)
# MAGIC
# MAGIC You can edit the requests or expected responses in your evaluation dataset and run evaluation as you iterate your agent, leveraging mlflow to track the computed quality metrics.
# MAGIC
# MAGIC Evaluate your agent with one of our [predefined LLM scorers](https://docs.databricks.com/mlflow3/genai/eval-monitor/predefined-judge-scorers), or try adding [custom metrics](https://docs.databricks.com/mlflow3/genai/eval-monitor/custom-scorers).

# COMMAND ----------

import mlflow
from mlflow.genai.scorers import RelevanceToQuery, Safety, RetrievalRelevance, RetrievalGroundedness

eval_dataset = [
    {
        "inputs": {
            "input": [
                {
                    "role": "user",
                    "content": "hi"
                }
            ]
        },
        "expected_response": None
    },
    {
        "inputs": {
            "input": [
                {
                    "role": "user",
                    "content": "hi"
                },
                {
                    "role": "assistant",
                    "content": "Hello! 👋 How can I assist you today?"
                },
                {
                    "role": "user",
                    "content": "Where are the largest geographic \"cold spots\" where radiology is absent within 50 km?"
                }
            ]
        },
        "expected_response": None
    },
    {
        "inputs": {
            "input": [
                {
                    "role": "user",
                    "content": "hi"
                },
                {
                    "role": "assistant",
                    "content": "Hello! 👋 How can I assist you today?"
                },
                {
                    "role": "user",
                    "content": "Where are the largest geographic \"cold spots\" where radiology is absent within 50 km?"
                },
                {
                    "role": "assistant",
                    "content": "User wants regions lacking radiology coverage within 50 km.\n\n<uc_function_call>{\"id\":\"8sPf95nLYKFesQG9GykI\",\"name\":\"workspace.default.find_cold_spots\",\"arguments\":\"{\\\"procedure_or_capability\\\":\\\"radiology\\\",\\\"coverage_radius_km\\\":50}\"}</uc_function_call>\n\n<uc_function_result>{\"id\":\"8sPf95nLYKFesQG9GykI\",\"content\":\"{\\\"is_truncated\\\":false,\\\"columns\\\":[\\\"output\\\"],\\\"rows\\\":[[\\\"{\\\\\\\"procedure\\\\\\\": \\\\\\\"radiology\\\\\\\", \\\\\\\"radius_km\\\\\\\": 50.0, \\\\\\\"cold_spots\\\\\\\": [{\\\\\\\"region\\\\\\\": \\\\\\\"Western Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Sekondi\\\\\\\", \\\\\\\"population\\\\\\\": 2060585, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Life Sciences Medical Centre\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 55.2}, {\\\\\\\"region\\\\\\\": \\\\\\\"Volta Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Ho\\\\\\\", \\\\\\\"population\\\\\\\": 1652772, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Sogakope - MDC\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 68.4}, {\\\\\\\"region\\\\\\\": \\\\\\\"Upper West Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Wa\\\\\\\", \\\\\\\"population\\\\\\\": 901502, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Cape Coast Teaching Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 196.7}, {\\\\\\\"region\\\\\\\": \\\\\\\"Oti Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Dambai\\\\\\\", \\\\\\\"population\\\\\\\": 747248, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Akatsi South Municipal Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 139.2}, {\\\\\\\"region\\\\\\\": \\\\\\\"Savannah Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Damongo\\\\\\\", \\\\\\\"population\\\\\\\": 653266, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Cape Coast Teaching Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 112.8}, {\\\\\\\"region\\\\\\\": \\\\\\\"North East Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Nalerigu\\\\\\\", \\\\\\\"population\\\\\\\": 650856, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Eastside Life Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 59.6}], \\\\\\\"num_cold_spots\\\\\\\": 6, \\\\\\\"coverage_pct\\\\\\\": 62.5, \\\\\\\"total_population_affected\\\\\\\": 6666229}\\\"]]}\"}</uc_function_result>\n\n**Cold‑spot regions (radiology ≥ 50 km away)**  \n\n| Rank | Region | Capital | Population (2021) | Nearest facility *outside* 50 km | Distance |\n|------|--------|---------|-------------------|----------------------------------|----------|\n| 1 | **Western Region** | Sekondi | 2,060,585 | Life Sciences Medical Centre | 55.2 km |\n| 2 | **Volta Region** | Ho | 1,652,772 | Sogakope – MDC | 68.4 km |\n| 3 | **Upper West Region** | Wa | 901,502 | Cape Coast Teaching Hospital | 196.7 km |\n| 4 | **Oti Region** | Dambai | 747,248 | Akatsi South Municipal Hospital | 139.2 km |\n| 5 | **Savannah Region** | Damongo | 653,266 | Cape Coast Teaching Hospital | 112.8 km |\n| 6 | **North East Region** | Nalerigu | 650,856 | Eastside Life Hospital | 59.6 km |\n\n**Key take‑aways**\n\n- 6/16 Ghanaian regions are “radiology deserts” within a 50‑km radius, covering ~6.7 million people (≈ 62 % of the country’s population).  \n- The biggest gaps are in the *Western* and *Volta* regions (≈ 3.7 million people combined) where the nearest radiology‑capable facility lies 55–70 km away.  \n- The *Upper West* region is the most distant cold spot, with the nearest facility over 190 km away.  \n\n**Implications**\n\nThese regions lack a radiology service that is reachable within the WHO‑recommended 50‑km radius for emergency and diagnostic care.  If you’re planning a mobile imaging clinic, focusing first on the Western and Volta regions would address service gaps for the largest number of people."
                },
                {
                    "role": "user",
                    "content": "Where are the largest geographic \"cold spots\" where radiology is absent within 1 hour and 30 minutes of travel time?"
                }
            ]
        },
        "expected_response": None
    },
    {
        "inputs": {
            "input": [
                {
                    "role": "user",
                    "content": "hi"
                },
                {
                    "role": "assistant",
                    "content": "Hello! 👋 How can I assist you today?"
                },
                {
                    "role": "user",
                    "content": "Where are the largest geographic \"cold spots\" where radiology is absent within 50 km?"
                },
                {
                    "role": "assistant",
                    "content": "User wants regions lacking radiology coverage within 50 km.\n\n<uc_function_call>{\"id\":\"8sPf95nLYKFesQG9GykI\",\"name\":\"workspace.default.find_cold_spots\",\"arguments\":\"{\\\"procedure_or_capability\\\":\\\"radiology\\\",\\\"coverage_radius_km\\\":50}\"}</uc_function_call>\n\n<uc_function_result>{\"id\":\"8sPf95nLYKFesQG9GykI\",\"content\":\"{\\\"is_truncated\\\":false,\\\"columns\\\":[\\\"output\\\"],\\\"rows\\\":[[\\\"{\\\\\\\"procedure\\\\\\\": \\\\\\\"radiology\\\\\\\", \\\\\\\"radius_km\\\\\\\": 50.0, \\\\\\\"cold_spots\\\\\\\": [{\\\\\\\"region\\\\\\\": \\\\\\\"Western Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Sekondi\\\\\\\", \\\\\\\"population\\\\\\\": 2060585, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Life Sciences Medical Centre\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 55.2}, {\\\\\\\"region\\\\\\\": \\\\\\\"Volta Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Ho\\\\\\\", \\\\\\\"population\\\\\\\": 1652772, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Sogakope - MDC\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 68.4}, {\\\\\\\"region\\\\\\\": \\\\\\\"Upper West Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Wa\\\\\\\", \\\\\\\"population\\\\\\\": 901502, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Cape Coast Teaching Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 196.7}, {\\\\\\\"region\\\\\\\": \\\\\\\"Oti Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Dambai\\\\\\\", \\\\\\\"population\\\\\\\": 747248, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Akatsi South Municipal Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 139.2}, {\\\\\\\"region\\\\\\\": \\\\\\\"Savannah Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Damongo\\\\\\\", \\\\\\\"population\\\\\\\": 653266, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Cape Coast Teaching Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 112.8}, {\\\\\\\"region\\\\\\\": \\\\\\\"North East Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Nalerigu\\\\\\\", \\\\\\\"population\\\\\\\": 650856, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Eastside Life Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 59.6}], \\\\\\\"num_cold_spots\\\\\\\": 6, \\\\\\\"coverage_pct\\\\\\\": 62.5, \\\\\\\"total_population_affected\\\\\\\": 6666229}\\\"]]}\"}</uc_function_result>\n\n**Cold‑spot regions (radiology ≥ 50 km away)**  \n\n| Rank | Region | Capital | Population (2021) | Nearest facility *outside* 50 km | Distance |\n|------|--------|---------|-------------------|----------------------------------|----------|\n| 1 | **Western Region** | Sekondi | 2,060,585 | Life Sciences Medical Centre | 55.2 km |\n| 2 | **Volta Region** | Ho | 1,652,772 | Sogakope – MDC | 68.4 km |\n| 3 | **Upper West Region** | Wa | 901,502 | Cape Coast Teaching Hospital | 196.7 km |\n| 4 | **Oti Region** | Dambai | 747,248 | Akatsi South Municipal Hospital | 139.2 km |\n| 5 | **Savannah Region** | Damongo | 653,266 | Cape Coast Teaching Hospital | 112.8 km |\n| 6 | **North East Region** | Nalerigu | 650,856 | Eastside Life Hospital | 59.6 km |\n\n**Key take‑aways**\n\n- 6/16 Ghanaian regions are “radiology deserts” within a 50‑km radius, covering ~6.7 million people (≈ 62 % of the country’s population).  \n- The biggest gaps are in the *Western* and *Volta* regions (≈ 3.7 million people combined) where the nearest radiology‑capable facility lies 55–70 km away.  \n- The *Upper West* region is the most distant cold spot, with the nearest facility over 190 km away.  \n\n**Implications**\n\nThese regions lack a radiology service that is reachable within the WHO‑recommended 50‑km radius for emergency and diagnostic care.  If you’re planning a mobile imaging clinic, focusing first on the Western and Volta regions would address service gaps for the largest number of people."
                },
                {
                    "role": "user",
                    "content": "Where are the largest geographic \"cold spots\" where radiology is absent within 1 hour and 30 minutes of travel time?"
                },
                {
                    "role": "assistant",
                    "content": "I'm going to use workspace.default.find_cold_spots\n\n<uc_function_call>{\"id\":\"qzEp9bfdYCvEhwVDrbOq\",\"name\":\"workspace.default.find_cold_spots\",\"arguments\":\"{\\\"procedure_or_capability\\\":\\\"radiology\\\",\\\"coverage_radius_km\\\":75}\"}</uc_function_call>\n\n<uc_function_result>{\"id\":\"qzEp9bfdYCvEhwVDrbOq\",\"content\":\"{\\\"is_truncated\\\":false,\\\"columns\\\":[\\\"output\\\"],\\\"rows\\\":[[\\\"{\\\\\\\"procedure\\\\\\\": \\\\\\\"radiology\\\\\\\", \\\\\\\"radius_km\\\\\\\": 75.0, \\\\\\\"cold_spots\\\\\\\": [{\\\\\\\"region\\\\\\\": \\\\\\\"Upper West Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Wa\\\\\\\", \\\\\\\"population\\\\\\\": 901502, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Cape Coast Teaching Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 196.7}, {\\\\\\\"region\\\\\\\": \\\\\\\"Oti Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Dambai\\\\\\\", \\\\\\\"population\\\\\\\": 747248, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Akatsi South Municipal Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 139.2}, {\\\\\\\"region\\\\\\\": \\\\\\\"Savannah Region\\\\\\\", \\\\\\\"capital\\\\\\\": \\\\\\\"Damongo\\\\\\\", \\\\\\\"population\\\\\\\": 653266, \\\\\\\"nearest_facility\\\\\\\": \\\\\\\"Cape Coast Teaching Hospital\\\\\\\", \\\\\\\"nearest_dist_km\\\\\\\": 112.8}], \\\\\\\"num_cold_spots\\\\\\\": 3, \\\\\\\"coverage_pct\\\\\\\": 81.2, \\\\\\\"total_population_affected\\\\\\\": 2302016}\\\"]]}\"}</uc_function_result>\n\n### Radiology “cold‑spot” regions that are **> 1 h 30 min (~75 km)** away from any facility  \n\n| Rank | Region | Capital | Population (2021) | Nearest radiology‑capable facility | Distance |\n|------|--------|---------|-------------------|------------------------------------|----------|\n| **1** | Upper West Region | Wa | 901,502 | Cape Coast Teaching Hospital | 196.7 km |\n| **2** | Oti Region | Dambai | 747,248 | Akatsi South Municipal Hospital | 139.2 km |\n| **3** | Savannah Region | Damongo | 653,266 | Cape Coast Teaching Hospital | 112.8 km |\n\n---\n\n#### Key points\n| Metric | Value |\n|--------|-------|\n| Number of cold‑spot regions | 3 of 16 (≈ 19 %) |\n| Total population affected | **2,302,016** people (~ 62 % of Ghana’s population) |\n| Earliest location | **Upper West Region** – the nearest radiology centre is nearly 197 km away (≈ 3 h 58 min at 50 km/h). |\n\n### Why this matters\n- **1 h 30 min travel time** (≈ 75 km at an average 50 km/h regional speed) is a common threshold for emergency or diagnostic care in Ghana.  \n- In these three regions, residents would need to travel *well beyond* the WHO‑recommended emergency window to access radiology services, creating significant inequity in timely diagnosis and treatment.  \n- Prioritizing mobile imaging units or upgrading facilities in these regions would immediately reduce the service gap for over 2.3 million people.\n\nFeel free to let me know if you’d like more detail on potential mitigation strategies or the specific facilities involved."
                },
                {
                    "role": "user",
                    "content": "Where are the largest geographic \"cold spots\" where radiology is absent within 1 hour of travel time?"
                }
            ]
        },
        "expected_response": None
    }
]

eval_results = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=lambda input: AGENT.predict({"input": input, "custom_inputs": {"session_id": "evaluation-session"}}),
    scorers=[RelevanceToQuery(), Safety()], # add more scorers here if they're applicable
)

# Review the evaluation results in the MLfLow UI (see console output)

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
