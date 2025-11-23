"""ReAct agent executor for autonomous task completion."""

import json
import re
from typing import Dict, List, Any, AsyncIterator
from pydantic import BaseModel

from app.core.agent.tools.base import ToolRegistry, ToolResult
from app.core.llm.provider import LLMProvider


class AgentStep(BaseModel):
    """A single step in the agent's reasoning process."""
    thought: str | None = None
    action: str | None = None
    action_input: Dict[str, Any | None] = None
    observation: str | None = None
    step_number: int


class AgentResponse(BaseModel):
    """Response from the agent."""
    final_answer: str | None = None
    steps: List[AgentStep] = []
    error: str | None = None
    completed: bool = False


class ReActAgent:
    """ReAct (Reasoning + Acting) agent for autonomous task completion.

    The agent follows a loop:
    1. Thought: Reason about what to do next
    2. Action: Choose a tool to use
    3. Observation: Observe the result of the tool
    4. Repeat until task is complete
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        max_iterations: int = 10,
        system_instructions: str | None = None,
        max_validation_retries: int = 3,
        max_same_tool_retries: int = 5,
    ):
        """Initialize the ReAct agent.

        Args:
            llm_provider: LLM provider for generating responses
            tool_registry: Registry of available tools
            max_iterations: Maximum number of reasoning iterations
            system_instructions: Custom system instructions for the agent
            max_validation_retries: Maximum validation retry attempts before giving up
            max_same_tool_retries: Maximum retries for same tool to prevent loops
        """
        self.llm = llm_provider
        self.tools = tool_registry
        self.max_iterations = max_iterations
        self.system_instructions = system_instructions or self._default_system_instructions()
        self.max_validation_retries = max_validation_retries
        self.max_same_tool_retries = max_same_tool_retries

        # Track retries per iteration (reset each iteration)
        self.validation_retry_count = 0
        # Track tool usage to detect loops
        self.tool_call_history = []

    def _default_system_instructions(self) -> str:
        """Get default system instructions for the agent."""
        return """You are an autonomous coding agent with access to a sandbox environment.

Your task is to help users write, test, and debug code by using the available tools.

You have access to the following tools:
{tools}

When solving a task, follow the ReAct pattern:
1. Think about what needs to be done
2. Choose an action (tool) to use
3. Observe the result
4. Repeat until the task is complete

IMPORTANT: You MUST use function calls to invoke tools. Do not describe what tools you would use - actually use them!

When you have completed the task, provide a final answer summarizing what you did.

Available tools will be provided as function calling options. Use them to accomplish the user's request.
"""

    def _build_system_message(self) -> str:
        """Build the system message with tool descriptions."""
        tool_descriptions = "\n".join(
            [f"- {tool.name}: {tool.description}" for tool in self.tools.list_tools()]
        )
        return self.system_instructions.format(tools=tool_descriptions)

    async def run(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str | None]] = None,
        cancel_event: Any = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Run the agent on a user message.

        Args:
            user_message: The user's request
            conversation_history: Previous conversation messages
            cancel_event: Optional asyncio.Event for cancelling execution

        Yields:
            Agent steps and final response
        """
        print(f"\n[REACT AGENT] Starting run()")
        print(f"  User message: {user_message[:100]}...")
        print(f"  Max iterations: {self.max_iterations}")
        print(f"  Available tools: {[t.name for t in self.tools.list_tools()]}")

        # Build messages
        messages = [{"role": "system", "content": self._build_system_message()}]

        if conversation_history:
            messages.extend(conversation_history)
            print(f"  Conversation history: {len(conversation_history)} messages")

        messages.append({"role": "user", "content": user_message})

        # Agent loop
        steps: List[AgentStep] = []

        for iteration in range(self.max_iterations):
            print(f"\n[REACT AGENT] Iteration {iteration + 1}/{self.max_iterations}")

            # Check for cancellation
            if cancel_event and cancel_event.is_set():
                print(f"[REACT AGENT] Cancellation requested")
                yield {
                    "type": "cancelled",
                    "content": "Response cancelled by user",
                    "step": iteration + 1,
                }
                return

            try:
                # Get LLM response with function calling
                llm_messages = messages.copy()
                tools_for_llm = self.tools.get_tools_for_llm()
                print(f"[REACT AGENT] Tools for LLM: {len(tools_for_llm) if tools_for_llm else 0}")

                # Stream response from LLM
                full_response = ""
                # Support multiple tool calls - track by index
                tool_calls = {}  # {index: {"name": str, "arguments": str}}

                print(f"[REACT AGENT] Calling LLM generate_stream...")
                chunk_count = 0
                async for chunk in self.llm.generate_stream(
                    messages=llm_messages,
                    tools=tools_for_llm if tools_for_llm else None,
                ):
                    # Check for cancellation during streaming
                    if cancel_event and cancel_event.is_set():
                        print(f"[REACT AGENT] Cancellation during streaming")
                        yield {
                            "type": "cancelled",
                            "content": "Response cancelled by user",
                            "partial_content": full_response,
                            "step": iteration + 1,
                        }
                        return

                    chunk_count += 1
                    # Handle regular content
                    if isinstance(chunk, str):
                        full_response += chunk
                        if chunk_count <= 3:  # Only print first few chunks
                            print(f"[REACT AGENT] Text chunk #{chunk_count}: {chunk[:50]}...")
                        # Emit chunks immediately for better UX and cancellation support
                        yield {
                            "type": "chunk",
                            "content": chunk,
                            "step": iteration + 1,
                        }
                    # Handle function call (if LLM returns structured data)
                    elif isinstance(chunk, dict) and "function_call" in chunk:
                        print(f"[REACT AGENT] Function call chunk: {chunk}")
                        function_call = chunk["function_call"]
                        # Get index (default to 0 for backward compatibility with single tool calls)
                        index = chunk.get("index", 0)

                        # Initialize tool call entry if needed
                        if index not in tool_calls:
                            tool_calls[index] = {"name": None, "arguments": ""}

                        # IMPORTANT: Only set function_name if it's not None (preserve from first chunk)
                        if function_call.get("name") is not None:
                            tool_calls[index]["name"] = function_call.get("name")
                        # Accumulate arguments from all chunks for this specific tool call index
                        if function_call.get("arguments"):
                            tool_calls[index]["arguments"] += function_call.get("arguments", "")

                print(f"[REACT AGENT] Stream complete. Total chunks: {chunk_count}")
                print(f"[REACT AGENT] Full response length: {len(full_response)}")
                print(f"[REACT AGENT] Tool calls: {list(tool_calls.keys())}")

                # Check if LLM wants to call any functions
                # ReAct pattern: Execute ONE tool per iteration (use first/lowest index)
                if tool_calls:
                    # Get the first tool call (lowest index)
                    first_index = min(tool_calls.keys())
                    tool_call = tool_calls[first_index]
                    function_name = tool_call["name"]
                    function_args = tool_call["arguments"]

                    if len(tool_calls) > 1:
                        print(f"[REACT AGENT] WARNING: LLM suggested {len(tool_calls)} tool calls, but ReAct pattern supports one per iteration. Executing first: {function_name}")

                    if function_name and self.tools.has_tool(function_name):
                        print(f"[REACT AGENT] Executing function: {function_name}")

                        # Add assistant's function call to conversation for proper context
                        # This is critical so the LLM remembers what it decided to do in previous iterations
                        messages.append({
                            "role": "assistant",
                            "content": full_response or None,
                            "function_call": {
                                "name": function_name,
                                "arguments": function_args if isinstance(function_args, str) else json.dumps(function_args)
                            }
                        })

                        # Note: reasoning text before function call was already emitted as chunks during streaming

                        # Parse function arguments
                        try:
                            args = json.loads(function_args) if isinstance(function_args, str) else function_args
                        except json.JSONDecodeError:
                            args = {}

                        # Execute tool
                        tool = self.tools.get(function_name)
                        if tool:
                            # Use validate_and_execute for parameter validation
                            result = await tool.validate_and_execute(**args)

                            # Handle validation errors internally (don't show in frontend)
                            if result.is_validation_error:
                                print(f"[REACT AGENT] Validation error for {function_name}: {result.error}")

                                # Track validation retries
                                self.validation_retry_count += 1

                                # Check if we've exceeded retry limit
                                if self.validation_retry_count >= self.max_validation_retries:
                                    # Max retries exceeded - add suggestion to try different approach
                                    error_with_suggestion = (
                                        f"{result.error}\n\n"
                                        f"You've attempted this {self.validation_retry_count} times with validation errors. "
                                        f"Consider:\n"
                                        f"1. Using a different tool to accomplish the task\n"
                                        f"2. Breaking the task into smaller steps\n"
                                        f"3. Carefully reviewing the tool's parameter requirements"
                                    )
                                    messages.append({
                                        "role": "user",
                                        "content": f"Tool '{function_name}' validation failed: {error_with_suggestion}",
                                    })
                                    # Reset counter for next tool
                                    self.validation_retry_count = 0
                                else:
                                    # Add validation error to conversation for LLM to learn from
                                    messages.append({
                                        "role": "user",
                                        "content": f"Tool '{function_name}' validation failed (attempt {self.validation_retry_count}/{self.max_validation_retries}): {result.error}",
                                    })

                                # Continue to next iteration (don't save as agent_action)
                                continue

                            # Reset validation retry counter on successful validation
                            self.validation_retry_count = 0

                            # Track tool call for loop detection
                            self.tool_call_history.append(function_name)

                            # Check for tool call loops (same tool failing repeatedly)
                            recent_calls = self.tool_call_history[-self.max_same_tool_retries:]
                            if len(recent_calls) == self.max_same_tool_retries and len(set(recent_calls)) == 1:
                                # Same tool called max_same_tool_retries times in a row
                                print(f"[REACT AGENT] Loop detected: {function_name} called {self.max_same_tool_retries} times")
                                observation = (
                                    f"Error: Tool '{function_name}' has been called {self.max_same_tool_retries} times "
                                    f"consecutively without success. This suggests the current approach isn't working. "
                                    f"Please try a different tool or approach to accomplish the task."
                                )
                                messages.append({
                                    "role": "user",
                                    "content": observation,
                                })
                                # Clear history to allow trying again later if needed
                                self.tool_call_history = []
                                continue

                            # Execution successful or execution error (not validation) - show in frontend
                            yield {
                                "type": "action",
                                "content": f"Using tool: {function_name}",
                                "tool": function_name,
                                "args": args,
                                "step": iteration + 1,
                            }

                            # Create observation
                            # For failures, include BOTH error message AND output so LLM can see what went wrong
                            if result.success:
                                observation = result.output
                            else:
                                # Combine error message with output (stdout/stderr) for better context
                                observation_parts = []
                                if result.error:
                                    observation_parts.append(f"Error: {result.error}")
                                if result.output:
                                    observation_parts.append(result.output)
                                observation = "\n".join(observation_parts) if observation_parts else "Error: Unknown failure"

                            yield {
                                "type": "observation",
                                "content": observation,
                                "success": result.success,
                                "step": iteration + 1,
                            }

                            # Add tool result to conversation as user message
                            messages.append({
                                "role": "user",
                                "content": f"Tool '{function_name}' returned: {observation}",
                            })

                            # Record step
                            steps.append(AgentStep(
                                thought=full_response if full_response else None,
                                action=function_name,
                                action_input=args,
                                observation=observation,
                                step_number=iteration + 1,
                            ))

                            # Continue loop
                            continue

                # No function call - agent is providing final answer
                if full_response:
                    print(f"[REACT AGENT] No function call - providing final answer")
                    print(f"[REACT AGENT] Final answer: {full_response[:100]}...")

                    # Chunks were already emitted during streaming above
                    return

                # If we get here with no response, something went wrong
                print(f"[REACT AGENT] ERROR: No response from LLM")
                yield {
                    "type": "error",
                    "content": "Agent did not provide a response",
                    "step": iteration + 1,
                }
                return

            except Exception as e:
                print(f"[REACT AGENT] EXCEPTION: {str(e)}")
                import traceback
                traceback.print_exc()
                yield {
                    "type": "error",
                    "content": f"Agent error: {str(e)}",
                    "step": iteration + 1,
                }
                return

        # Max iterations reached
        yield {
            "type": "final_answer",
            "content": "Task incomplete: reached maximum iterations. Please try breaking down the task into smaller steps.",
            "step": self.max_iterations,
        }
