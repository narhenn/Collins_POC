from app.engine.nodes.base import BaseNodeExecutor
from app.engine.variables import interpolate


class DecisionNodeExecutor(BaseNodeExecutor):
    async def execute(self, config: dict, variables: dict, **kwargs) -> dict:
        left_raw = config.get("left_operand", "")
        operator = config.get("operator", "==")
        right_raw = config.get("right_operand", "")

        left = str(interpolate(left_raw, variables))
        right = str(interpolate(right_raw, variables))

        result = self._evaluate(left, operator, right)
        return {
            "branch": "true" if result else "false",
            "condition_result": result,
        }

    @staticmethod
    def _evaluate(left: str, operator: str, right: str) -> bool:
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == "contains":
            return right in left

        # Numeric comparisons, fall back to string comparison
        try:
            l_num = float(left)
            r_num = float(right)
        except (ValueError, TypeError):
            l_num, r_num = None, None  # type: ignore[assignment]

        if l_num is not None and r_num is not None:
            if operator == ">":
                return l_num > r_num
            if operator == "<":
                return l_num < r_num
            if operator == ">=":
                return l_num >= r_num
            if operator == "<=":
                return l_num <= r_num
        else:
            if operator == ">":
                return left > right
            if operator == "<":
                return left < right
            if operator == ">=":
                return left >= right
            if operator == "<=":
                return left <= right

        return False
