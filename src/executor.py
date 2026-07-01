"""Parallel tool execution via ThreadPoolExecutor."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from src.retry import retry_tool_call
from src import logger
import time


class ToolExecutor:
    def __init__(self, registry, max_workers=4):
        self.registry = registry
        self.pool = ThreadPoolExecutor(max_workers=max_workers)

    def execute_single(self, name: str, arg: str) -> str:
        tool = self.registry.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'. Available: {', '.join(self.registry.names())}"
        t0 = time.perf_counter()
        try:
            result = retry_tool_call(tool["function"], arg)
        except Exception as exc:
            logger.log_error(f"tool:{name}", exc)
            return f"Error running {name}: {exc}"
        logger.log_tool_call(name, arg, result, (time.perf_counter() - t0) * 1000)
        return result

    def execute_batch(self, tasks: list[tuple[str, str]]) -> list[str]:
        """Run multiple (tool_name, arg) pairs in parallel. Returns results in order."""
        if len(tasks) == 1:
            return [self.execute_single(*tasks[0])]
        futures = {}
        for i, (name, arg) in enumerate(tasks):
            futures[self.pool.submit(self.execute_single, name, arg)] = i
        results = [""] * len(tasks)
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
        return results
