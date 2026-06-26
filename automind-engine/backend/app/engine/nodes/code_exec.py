"""
Code Execution Node - runs Python code in a restricted subprocess.
"""
import asyncio
import json
import logging
import os
import tempfile

from app.engine.nodes.base import BaseNodeExecutor
from app.engine.variables import interpolate

logger = logging.getLogger(__name__)

FORBIDDEN = [
    "import os",
    "import sys",
    "import subprocess",
    "import shutil",
    "__import__",
    "eval(",
    "exec(",
    "open(",
    "import socket",
    "import requests",
    "import urllib",
]


class CodeExecNodeExecutor(BaseNodeExecutor):
    async def execute(self, config: dict, variables: dict, **kwargs) -> dict:
        code_template = config.get("code", "")
        code = (
            interpolate(code_template, variables)
            if isinstance(code_template, str)
            else str(code_template)
        )
        timeout = min(config.get("timeout", 10), 30)  # Max 30 seconds
        output_variable = config.get("output_variable", "code_result")

        # Basic safety check
        for forbidden in FORBIDDEN:
            if forbidden in code:
                return {
                    "output_variables": {
                        output_variable: {"error": f"Forbidden: {forbidden}"}
                    },
                    "error": f"Code contains forbidden pattern: {forbidden}",
                }

        try:
            result = await self._run_code(code, timeout)
            return {"output_variables": {output_variable: result}}
        except Exception as e:
            return {
                "output_variables": {output_variable: {"error": str(e)}},
                "error": str(e),
            }

    async def _run_code(self, code: str, timeout: int) -> dict:
        """Execute Python code in a subprocess with timeout."""
        # Write code to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            # Indent each line of user code for the try block
            indented_lines = []
            for line in code.split("\n"):
                indented_lines.append("    " + line)
            indented_code = "\n".join(indented_lines)

            wrapped = f"""import json, sys
_output = {{}}
try:
{indented_code}
    # Try to capture local variables as output
    _output = {{k: v for k, v in locals().items() if not k.startswith("_") and k not in ("json", "sys") and isinstance(v, (str, int, float, bool, list, dict))}}
except Exception as e:
    _output = {{"error": str(e)}}
print(json.dumps(_output))
"""
            f.write(wrapped)
            f.flush()
            tmp_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                "python3",
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            output = stdout.decode().strip()
            if proc.returncode != 0:
                return {
                    "error": stderr.decode().strip()[:500],
                    "exit_code": proc.returncode,
                }

            try:
                return json.loads(output) if output else {"output": "No output"}
            except json.JSONDecodeError:
                return {"output": output}
        finally:
            os.unlink(tmp_path)
